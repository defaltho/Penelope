"""Penelope interactive TUI — prompt_toolkit + rich."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.widgets import TextArea

from cli.client import PenelopeClient
from cli.commands_registry import SlashCompleter, TUI_COMMANDS
from cli.i18n import (
    get_language,
    language_name,
    load_language,
    set_language,
    status_text,
    t,
)
from cli.render import (
    get_console,
    print_activity,
    print_banner,
    print_error,
    print_goodbye,
    print_help_table,
    print_info,
    print_markdown,
    print_response_stats,
    print_success,
    print_table,
)
from cli.stream import StreamRenderer
from cli.theme import (
    ACCENT,
    BAR_BG,
    BAR_CELLS,
    BAR_EMPTY,
    BAR_FILLED,
    CONTEXT_COLORS,
    DEFAULT_CTX_WINDOW,
    ERROR,
    FG,
    HEALTH_GLYPH,
    MUTED,
    RULE,
    SEP,
    SPARK,
    SPINNER_FRAMES,
    SUCCESS,
    TIMER_GLYPH,
)


def _esc(text: str) -> str:
    """Escape rich markup so literal [brackets] in user text aren't parsed."""
    from rich.markup import escape
    return escape(text)


# The ⚕ health indicator reflects the LLM engine (Ollama), probed directly at
# its local URL. Penelope is local-first, so this address is fixed/known.
OLLAMA_URL = os.environ.get("ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434")


def _ensure_data_dir() -> Path:
    d = Path.home() / ".penelope"
    d.mkdir(exist_ok=True)
    return d


def _probe_ollama() -> bool:
    import httpx
    try:
        httpx.get(OLLAMA_URL.rstrip("/") + "/api/version", timeout=1.5)
        return True
    except Exception:
        return False


def _install_input_extras() -> None:
    """Augment prompt_toolkit's key tables (Hermes pt_input_extras port).

    - Map Shift+Enter / Ctrl+Enter byte sequences (Kitty/xterm modifyOtherKeys)
      to the Alt+Enter tuple, so the newline binding fires for terminals that
      emit a distinct sequence for those chords.
    - Swallow terminal focus-report sequences (``\\x1b[I`` / ``\\x1b[O``) so they
      don't leak ``[I`` / ``[O`` into the input buffer.
    """
    try:
        from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
        from prompt_toolkit.keys import Keys
    except Exception:
        return

    alt_enter = (Keys.Escape, Keys.ControlM)
    # Shift+Enter and Ctrl+Enter variants → newline (Alt+Enter behaviour).
    for seq in ("\x1b[13;2u", "\x1b[27;2;13~", "\x1b[27;2;13u",
                "\x1b[13;5u", "\x1b[27;5;13~", "\x1b[27;5;13u"):
        ANSI_SEQUENCES[seq] = alt_enter
    # Focus in/out reports → ignore at the parser level.
    for seq in ("\x1b[I", "\x1b[O"):
        ANSI_SEQUENCES.setdefault(seq, Keys.Ignore)


# The input block lives in the layout (not a fixed bottom_toolbar), so the
# status bar sits directly under the chat line and flows with the content —
# no full-width coloured strip pinned to the terminal floor.
_PT_STYLE = PTStyle.from_dict({
    "input": "",                       # inherit terminal fg (readable on any bg)
    "prompt": f"{ACCENT} bold",
    "rule": RULE,
    "brand": f"{ACCENT} bold",
    "spin": ACCENT,
    "sb-brand": f"{ACCENT} bold",
    "sb-model": f"{FG} bold",
    "sb-sep": MUTED,
    "sb-conv": SUCCESS,
    "sb-conv-dim": MUTED,
    "sb-flag-warn": f"{ERROR} bold",
    "sb-flag-web": f"{ACCENT} bold",
    "sb-hint": MUTED,
    # Hermes-style command sub-menu rendered below the chat bar.
    "cmenu.name": f"bg:{BAR_BG} {ACCENT} bold",
    "cmenu.meta": f"bg:{BAR_BG} {MUTED}",
    "cmenu.sel.name": f"bg:{ACCENT} #0d0e11 bold",
    "cmenu.sel.meta": f"bg:{ACCENT} #0d0e11",
})


class PenelopeTUI:
    def __init__(self, *, model_override: str | None = None):
        self.client = PenelopeClient()
        self.console = get_console()
        self.conversation_id: str | None = None  # Odysseus session ID (string UUID)
        self.model: str = model_override or ""
        self.incognito: bool = False
        self.web_search: bool = False
        self._show_thinking: bool = True

        # Live-app state
        self._app: Application | None = None
        self._input: TextArea | None = None
        self._busy: bool = False
        self._interrupt: bool = False
        self._spinner_text: str = ""
        self._spinner_start: float = 0.0
        self._pending_action: str | None = None

        # Status-bar state (Hermes-style ⚕ │ ctx │ [bar] │ wall │ ⏲)
        self._session_start: float = time.monotonic()
        self._session_id: str = ""
        self._turn_start: float | None = None
        self._online: bool | None = None   # Ollama reachable (drives ⚕)
        self._backend_up: bool = False      # Penelope backend API reachable
        self._ctx_chars: int = 0
        self._ctx_window: int = DEFAULT_CTX_WINDOW
        self._closing: bool = False

    @staticmethod
    def _term_width() -> int:
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 80

    def _conversation_label(self) -> str:
        if not self.conversation_id:
            return t("conv.new")
        short = self.conversation_id[:8] if len(self.conversation_id) > 8 else self.conversation_id
        return t("conv.n", id=short)

    # --- Layout fragment providers (called every render) ---

    def _rule_fragments(self):
        return [("class:rule", "─" * self._term_width())]

    # --- Command sub-menu (Hermes-style, below the chat bar) ---

    _MENU_MAX = 10

    def _menu_completions(self):
        cs = self._input.buffer.complete_state if self._input else None
        if not cs or not cs.completions:
            return None
        return cs

    def _menu_visible(self) -> bool:
        return self._menu_completions() is not None

    def _menu_height(self) -> int:
        cs = self._menu_completions()
        if not cs:
            return 0
        return min(len(cs.completions), self._MENU_MAX)

    def _menu_fragments(self):
        cs = self._menu_completions()
        if not cs:
            return []
        comps = cs.completions
        cur = cs.complete_index if cs.complete_index is not None else 0
        n = len(comps)
        # Window the list so the highlighted row stays visible.
        start = 0
        if n > self._MENU_MAX:
            start = min(max(cur - self._MENU_MAX // 2, 0), n - self._MENU_MAX)
        width = self._term_width()
        name_col = 18
        frags = []
        for i in range(start, min(start + self._MENU_MAX, n)):
            c = comps[i]
            name = c.text
            meta = (c.display_meta_text or "").strip()
            namecell = f" {name:<{name_col}} "
            pad = max(width - len(namecell) - len(meta), 0)
            metacell = meta + " " * pad
            if i == cur:
                frags.append(("class:cmenu.sel.name", namecell))
                frags.append(("class:cmenu.sel.meta", metacell))
            else:
                frags.append(("class:cmenu.name", namecell))
                frags.append(("class:cmenu.meta", metacell))
            frags.append(("", "\n"))
        if frags:
            frags.pop()  # drop trailing newline
        return frags

    def _spinner_fragments(self):
        if not self._spinner_text:
            return []
        frame = SPINNER_FRAMES[int(time.monotonic() * 10) % len(SPINNER_FRAMES)]
        start = self._spinner_start or time.monotonic()
        elapsed = time.monotonic() - start
        return [("class:spin", f"  {SPARK} {frame} {self._spinner_text}  ({elapsed:.1f}s)")]

    @staticmethod
    def _fmt_dur(secs: float) -> str:
        secs = int(secs)
        if secs < 60:
            return f"{secs}s"
        m = secs // 60
        if m < 60:
            return f"{m}m"
        return f"{m // 60}h{m % 60:02d}m"

    def _ctx_state(self) -> tuple[str, str, str]:
        """Return (bar, percent_label, color) for the context indicator."""
        if self._ctx_chars <= 0 or self._ctx_window <= 0:
            return "[" + BAR_EMPTY * BAR_CELLS + "]", "--", MUTED
        tokens = self._ctx_chars / 4  # rough chars→tokens estimate
        pct = min(tokens / self._ctx_window, 1.0)
        filled = round(pct * BAR_CELLS)
        bar = "[" + BAR_FILLED * filled + BAR_EMPTY * (BAR_CELLS - filled) + "]"
        color = ERROR
        for thr, c in CONTEXT_COLORS:
            if pct * 100 <= thr:
                color = c
                break
        return bar, f"{int(pct * 100)}%", color

    def _statusbar_fragments(self):
        now = time.monotonic()
        if self._busy:
            health, hcolor = t("health.thinking"), ACCENT
        elif self._online is True:
            health, hcolor = t("health.online"), SUCCESS
        elif self._online is False:
            health, hcolor = t("health.offline"), ERROR
        else:
            health, hcolor = t("health.unknown"), MUTED

        bar, ctxval, barcolor = self._ctx_state()
        wall = self._fmt_dur(now - self._session_start)
        turn = self._fmt_dur(now - self._turn_start) if (self._busy and self._turn_start) else "0s"
        sep = (MUTED, SEP)

        frags = [
            (f"{hcolor} bold", f" {HEALTH_GLYPH} {health}"),
            sep,
            (MUTED, f"ctx {ctxval}"),
            sep,
            (barcolor, bar),
            (MUTED, f" {ctxval}"),
            sep,
            (FG, wall),
            sep,
            (MUTED, f"{TIMER_GLYPH} {turn}"),
        ]
        if self.incognito:
            frags += [sep, (f"{ERROR} bold", t("flag.incognito"))]
        if self.web_search:
            frags += [sep, (f"{ACCENT} bold", t("flag.web"))]
        return frags

    def _spinner_height(self) -> int:
        return 1 if self._spinner_text else 0

    def _input_height(self) -> int:
        """Exact height = wrapped line count (clamped 1..8).

        Returning an exact (min==max) height stops the input from being a
        *flexible* child of the HSplit. A flexible TextArea would otherwise
        absorb the rows freed when the command menu collapses, leaving a tall
        empty gap above the bottom rule.
        """
        if not self._input:
            return 1
        width = max(self._term_width() - 2, 1)
        rows = 0
        for line in (self._input.buffer.text.split("\n") or [""]):
            rows += max(1, -(-len(line) // width))  # ceil division
        return max(1, min(rows, 8))

    # --- App assembly ---

    def _build_app(self, *, app_input=None, app_output=None) -> Application:
        data_dir = _ensure_data_dir()

        self._input = TextArea(
            height=self._input_height,
            prompt=[("class:prompt", "❯ ")],
            style="class:input",
            multiline=True,
            wrap_lines=True,
            completer=SlashCompleter(),
            complete_while_typing=True,
            history=FileHistory(str(data_dir / "history")),
            read_only=Condition(lambda: self._busy),
        )

        spinner = Window(
            content=FormattedTextControl(self._spinner_fragments),
            height=self._spinner_height,
            wrap_lines=False,
        )
        status_bar = Window(
            content=FormattedTextControl(self._statusbar_fragments),
            height=1,
            wrap_lines=False,
        )
        top_rule = Window(content=FormattedTextControl(self._rule_fragments), height=1)
        bottom_rule = Window(content=FormattedTextControl(self._rule_fragments), height=1)

        # Command sub-menu: a full-width list under the chat bar (Hermes-style),
        # shown only while slash-command completions are active.
        command_menu = ConditionalContainer(
            content=Window(
                content=FormattedTextControl(self._menu_fragments),
                height=self._menu_height,
                wrap_lines=False,
                style=f"bg:{BAR_BG}",
            ),
            filter=Condition(self._menu_visible),
        )

        body = HSplit([
            Window(height=0),
            spinner,
            status_bar,
            top_rule,
            self._input,
            bottom_rule,
            command_menu,
        ])

        app = Application(
            layout=Layout(body, focused_element=self._input),
            key_bindings=self._build_app_keybindings(),
            style=_PT_STYLE,
            full_screen=False,
            mouse_support=False,
            erase_when_done=True,
            refresh_interval=0.1,
            **({"input": app_input} if app_input is not None else {}),
            **({"output": app_output} if app_output is not None else {}),
        )
        self._app = app
        return app

    def _build_app_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            buf = self._input.buffer
            cs = buf.complete_state
            if cs and cs.current_completion:
                buf.apply_completion(cs.current_completion)
                return
            self._submit()

        @kb.add("escape", "enter")
        @kb.add("c-j")
        def _(event):
            self._input.buffer.insert_text("\n")

        @kb.add("tab")
        def _(event):
            buf = self._input.buffer
            if buf.complete_state:
                buf.complete_next()
            else:
                buf.start_completion(select_first=False)

        @kb.add("s-tab")
        def _(event):
            buf = self._input.buffer
            if buf.complete_state:
                buf.complete_previous()

        @kb.add("down")
        def _(event):
            buf = self._input.buffer
            if buf.complete_state:
                buf.complete_next()
            else:
                buf.auto_down()

        @kb.add("up")
        def _(event):
            buf = self._input.buffer
            if buf.complete_state:
                buf.complete_previous()
            else:
                buf.auto_up()

        @kb.add("c-c")
        def _(event):
            if self._busy:
                self._interrupt = True
            else:
                self._input.buffer.reset()

        @kb.add("c-d")
        def _(event):
            if not self._input.text and not self._busy:
                event.app.exit()

        return kb

    def _invalidate(self) -> None:
        if self._app is not None:
            try:
                self._app.invalidate()
            except Exception:
                pass

    # Commands that tear the app down; echoing them through rich right before
    # app.exit() flushes the captured ANSI during teardown, which leaks raw
    # escape codes on some Windows consoles. Their own output is clear enough.
    _EXIT_COMMANDS = {"/web", "/exit", "/quit"}

    def _submit(self) -> None:
        if self._busy:
            return
        text = self._input.text.strip()
        self._input.buffer.reset()
        if not text:
            return
        if text.startswith("/"):
            cmd = text.split(None, 1)[0].lower()
            if cmd not in self._EXIT_COMMANDS:
                self._echo_user(text)
            if cmd == "/compact":
                # Network-heavy and slow; run off the UI thread.
                self._start_command_thread(text, status_text("compacting"))
                return
            should_exit = self._handle_command(text)
            if should_exit and self._app is not None:
                self._app.exit()
            self._invalidate()
        else:
            self._echo_user(text)
            self._start_chat(text)

    def _start_command_thread(self, text: str, spinner_text: str) -> None:
        self._busy = True
        self._turn_start = time.monotonic()
        self._set_spinner(spinner_text)

        def work() -> None:
            try:
                self._handle_command(text)
            finally:
                self._busy = False
                self._turn_start = None
                self._set_spinner("")
                self._invalidate()

        threading.Thread(target=work, daemon=True).start()
        self._invalidate()

    def _echo_user(self, text: str) -> None:
        self.console.print()
        first, *rest = text.split("\n")
        self.console.print(f"  [{ACCENT}]›[/{ACCENT}] [{FG}]{_esc(first)}[/{FG}]")
        for line in rest:
            self.console.print(f"    [{FG}]{_esc(line)}[/{FG}]")

    def _start_chat(self, text: str) -> None:
        self._busy = True
        self._interrupt = False
        self._turn_start = time.monotonic()
        self._ctx_chars += len(text)

        def work() -> None:
            try:
                self._chat(text)
            finally:
                self._busy = False
                self._turn_start = None
                self._spinner_text = ""
                self._spinner_start = 0.0
                self._invalidate()

        threading.Thread(target=work, daemon=True).start()
        self._invalidate()

    def _set_spinner(self, text: str) -> None:
        self._spinner_text = text
        if text:
            if not self._spinner_start:
                self._spinner_start = time.monotonic()
        else:
            self._spinner_start = 0.0
        self._invalidate()

    def _session_label(self) -> str:
        import datetime
        if not self._session_id:
            self._session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._session_id

    def _active_skill_names(self) -> list[str]:
        try:
            skills = self.client.list_skills()
        except Exception:
            return []
        names = []
        for s in skills:
            if isinstance(s, dict) and s.get("enabled", True):
                names.append(s.get("name", "") or s.get("title", ""))
        return [n for n in names if n]

    def _show_banner(self) -> None:
        print_banner(
            self.model or "—",
            cwd=os.getcwd(),
            conversation=self._conversation_label(),
            skills=self._active_skill_names(),
            session_id=self._session_label(),
        )

    def _start_health_poller(self) -> None:
        """Re-probe Ollama every few seconds so the ⚕ status flips to online by
        itself once the engine comes up (no CLI restart needed)."""
        def poll() -> None:
            while not self._closing:
                online = _probe_ollama()
                if online != self._online:
                    self._online = online
                    self._invalidate()
                time.sleep(2.0)

        threading.Thread(target=poll, daemon=True).start()

    def run(self) -> None:
        self._session_start = time.monotonic()
        load_language()
        self._load_settings()
        self._online = _probe_ollama()
        _install_input_extras()
        self._show_banner()
        if not self._backend_up:
            self._print_backend_hint()

        app = self._build_app()
        self._start_health_poller()
        try:
            with patch_stdout():
                app.run()
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            self._closing = True

        print_goodbye()
        if self._pending_action == "web":
            self._cmd_web_server()

    # --- Settings ---

    # --- Last-used model (shown in the banner as "modelo:") ---

    def _last_model_file(self) -> Path:
        return _ensure_data_dir() / "last_model"

    def _load_last_model(self) -> str:
        try:
            return self._last_model_file().read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _save_last_model(self, model: str) -> None:
        if not model or model == "—":
            return
        try:
            self._last_model_file().write_text(model, encoding="utf-8")
        except Exception:
            pass

    def _load_settings(self) -> None:
        # "modelo:" in the banner is the LAST model actually used; fall back to
        # the backend default, then to nothing.
        if not self.model:
            self.model = self._load_last_model()
        try:
            settings = self.client.get_settings()
            self._backend_up = True
            if not self.model:
                self.model = settings.get("chat_model", "")
            for key in ("num_ctx", "context_window", "ctx_window"):
                if settings.get(key):
                    self._ctx_window = int(settings[key])
                    break
        except Exception:
            self._backend_up = False

    def _print_backend_hint(self) -> None:
        """Soft, actionable note when the Penelope backend API is not up yet.
        (The ⚕ indicator tracks Ollama; this is about the local API server.)"""
        c = self.console
        c.print(f"  [{MUTED}]{SPARK} {t('hint.backend.notup')}[/{MUTED}] [{FG}]{self.client.base_url}[/{FG}]")
        web_msg = t("hint.backend.web", cmd="/web")
        web_msg = web_msg.replace("/web", f"[/{MUTED}][{ACCENT}]/web[/{ACCENT}][{MUTED}]")
        c.print(f"    [{MUTED}]{web_msg}[/{MUTED}]")
        c.print(f"    [{MUTED}]{t('hint.backend.alt', cmd='')}[/{MUTED}] [{FG}]powershell bin\\penelope-web.ps1[/{FG}]")
        c.print()

    # --- Chat streaming ---

    def _ensure_session(self) -> bool:
        """Create a backend session if none exists yet. Returns True on success."""
        if self.conversation_id:
            return True
        try:
            sess = self.client.create_session("Penelope CLI")
            sid = sess.get("id") or sess.get("session_id")
            if sid:
                self.conversation_id = str(sid)
                return True
        except Exception as e:
            print_error(f"Erro ao criar sessão: {e}")
        return False

    def _chat(self, message: str) -> None:
        if not self._ensure_session():
            return
        self._set_spinner(status_text("thinking"))

        renderer = StreamRenderer(show_reasoning=self._show_thinking)
        model_used = self.model
        tok_per_sec: float | None = None
        activities: list[tuple[str, str, float]] = []
        last_status_time = time.monotonic()
        start = time.monotonic()
        feed_flushed = False

        def _flush_feed() -> None:
            # Clear the live spinner widget and stamp the activity feed into
            # scrollback before the renderer draws its first box.
            nonlocal feed_flushed
            if feed_flushed:
                return
            feed_flushed = True
            self._set_spinner("")
            if activities:
                now = time.monotonic()
                pk, pt, _ = activities[-1]
                activities[-1] = (pk, pt, now - last_status_time)
                for kind, text, el in activities:
                    print_activity(kind, text, el if el > 0 else None)

        try:
            for event, payload in self.client.chat_stream(
                message,
                session_id=self.conversation_id,
                model=self.model or None,
                incognito=self.incognito,
                use_web=self.web_search,
            ):
                if self._interrupt:
                    break

                if event == "status":
                    kind = payload.get("kind", "thinking")
                    if kind in ("thinking", "web", "memory", "compacting"):
                        st_text = status_text(kind)
                    else:
                        st_text = payload.get("text") or status_text("thinking")
                    now = time.monotonic()
                    elapsed = now - last_status_time
                    if activities:
                        pk, pt, _ = activities[-1]
                        activities[-1] = (pk, pt, elapsed)
                    activities.append((kind, st_text, 0.0))
                    last_status_time = now
                    self._set_spinner(st_text)

                elif event == "token":
                    tok = payload.get("token", "")
                    if not tok:
                        continue
                    self._ctx_chars += len(tok)
                    _flush_feed()
                    renderer.feed(tok)

                elif event == "approval":
                    _flush_feed()
                    renderer.flush()
                    from cli.approval import prompt_approval
                    decision = prompt_approval(
                        payload.get("tool", "?"),
                        payload.get("command", ""),
                    )
                    self.client.approve_decision(
                        approval_id=payload.get("approval_id", ""),
                        decision=decision,
                        session_id=self.conversation_id or "",
                        tool=payload.get("tool", ""),
                    )
                    self._set_spinner(status_text("thinking"))

                elif event == "memories_used":
                    facts = payload.get("data", [])
                    if facts:
                        mem0_count = sum(1 for f in facts if f.get("type") == "mem0")
                        label = f"Mem0: {mem0_count} factos" if mem0_count else f"Memória: {len(facts)} factos"
                        activities.append(("memory", label, 0.0))
                        self._set_spinner(status_text("memory"))

                elif event == "model_info":
                    m = payload.get("model")
                    if m:
                        model_used = m

                elif event == "error":
                    _flush_feed()
                    renderer.flush()
                    print_error(payload.get("error", "Erro desconhecido"))
                    return

                elif event == "done":
                    self.conversation_id = payload.get("session_id") or payload.get("conversation_id") or self.conversation_id
                    model_used = payload.get("model", model_used)
                    tok_per_sec = payload.get("tok_per_sec")
                    if model_used:
                        # Remember the model actually used (banner "modelo:").
                        self.model = model_used
                        self._save_last_model(model_used)

        except Exception as e:
            _flush_feed()
            renderer.flush()
            print_error(str(e))
            return

        _flush_feed()
        renderer.flush()

        if self._interrupt:
            self.console.print(f"  [{MUTED}]{t('interrupted')}[/{MUTED}]")
            self.console.print()
            return

        self.console.print()
        print_response_stats(model_used, tok_per_sec, time.monotonic() - start)
        self.console.print()

    # --- Slash commands ---

    def _handle_command(self, text: str) -> bool:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        match cmd:
            case "/exit" | "/quit":
                return True
            case "/help":
                self._cmd_help()
            case "/new" | "/reset":
                self._cmd_new()
            case "/clear":
                self._cmd_clear()
            case "/compact":
                self._cmd_compact()
            case "/model":
                self._cmd_model(arg)
            case "/language":
                self._cmd_language(arg)
            case "/incognito":
                self._cmd_incognito()
            case "/web":
                # Web stack blocks; leave the TUI and launch it after run().
                self._pending_action = "web"
                return True
            case "/websearch":
                self._cmd_websearch()
            case "/memory":
                self._cmd_memory()
            case "/tasks":
                self._cmd_tasks()
            case "/task":
                self._cmd_task_add(arg)
            case "/status":
                self._cmd_status()
            case "/config":
                self._cmd_config()
            case "/think":
                self._cmd_think()
            case _:
                print_error(t("unknown.cmd", cmd=cmd))
        return False

    def _cmd_help(self) -> None:
        self.console.print()
        print_help_table(TUI_COMMANDS)
        self.console.print()

    def _cmd_language(self, arg: str) -> None:
        if not arg:
            print_info(t("language.current", lang=language_name()), get_language())
            print_info("", t("language.invalid"))
            return
        if set_language(arg):
            print_success(t("language.changed", lang=language_name()))
            self.console.print(f"  [{MUTED}]{t('language.hint')}[/{MUTED}]")
        else:
            print_error(t("language.invalid"))

    def _cmd_new(self) -> None:
        self.conversation_id = None
        self._ctx_chars = 0
        print_success(t("new.started"))

    def _cmd_clear(self) -> None:
        self.console.clear()
        self._show_banner()

    def _cmd_compact(self) -> None:
        if self.conversation_id is None:
            print_error(t("compact.noconv"))
            return
        try:
            resp = self.client.client.post(
                f"/api/sessions/{self.conversation_id}/compact",
                timeout=120.0,
            )
            data = resp.json()
            print_success(t("compact.done"))
            summary = data.get("summary", "")
            if summary:
                print_markdown(summary)
        except Exception as e:
            print_error(t("compact.fail", e=e))

    def _cmd_model(self, arg: str) -> None:
        if not arg:
            print_info(t("model.current"), self.model or "?")
            try:
                models = self.client.list_models()
                if models:
                    print_info(t("model.available"), ", ".join(models))
            except Exception:
                pass
            return
        self.model = arg
        self._save_last_model(arg)
        print_success(t("model.changed", m=arg))

    def _cmd_incognito(self) -> None:
        self.incognito = not self.incognito
        print_info(t("incognito.label"), t("incognito.on") if self.incognito else t("incognito.off"))

    def _cmd_websearch(self) -> None:
        self.web_search = not self.web_search
        print_info(t("websearch.label"), t("websearch.on") if self.web_search else t("websearch.off"))

    def _cmd_web_server(self) -> None:
        import socket

        project_root = Path(__file__).resolve().parent.parent
        backend_dir = project_root / "backend"
        frontend_dir = project_root / "frontend"

        ollama_url = "http://127.0.0.1:11434"
        backend_port = 8000
        frontend_port = 5173
        backend_url = f"http://127.0.0.1:{backend_port}"
        app_url = f"http://localhost:{frontend_port}"

        uv_exe = shutil.which("uv")
        npm_exe = shutil.which("npm")

        if not uv_exe:
            print_error(t("web.uv_missing"))
            return
        if not npm_exe:
            print_error(t("web.npm_missing"))
            return

        procs: list[subprocess.Popen] = []
        ollama_started = False
        backend_already_running = False
        frontend_already_running = False

        try:
            # --- Ollama ---
            if self._url_reachable(f"{ollama_url}/api/tags"):
                print_info(t("web.ollama.label"), t("web.running"))
            elif shutil.which("ollama"):
                print_info(t("web.ollama.label"), t("web.starting"))
                p = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                procs.append(p)
                ollama_started = True
                self._wait_for_url(f"{ollama_url}/api/tags", timeout=30)
            else:
                print_error(t("web.ollama.missing"))
                return

            # --- Backend ---
            if self._port_in_use(backend_port):
                print_info(t("web.backend.label"), t("web.backend.running", p=backend_port))
                backend_already_running = True
            else:
                print_info(t("web.backend.label"), t("web.backend.starting", p=backend_port))
                backend_proc = subprocess.Popen(
                    [uv_exe, "run", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(backend_port)],
                    cwd=str(backend_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                procs.append(backend_proc)

            # --- Frontend ---
            if self._port_in_use(frontend_port):
                print_info(t("web.frontend.label"), t("web.backend.running", p=frontend_port))
                frontend_already_running = True
            else:
                node_modules = frontend_dir / "node_modules"
                if not node_modules.exists():
                    print_info(t("web.frontend.label"), t("web.frontend.installing"))
                    subprocess.run(
                        [npm_exe, "install"],
                        cwd=str(frontend_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True,
                    )

                print_info(t("web.frontend.label"), t("web.frontend.starting", p=frontend_port))
                frontend_proc = subprocess.Popen(
                    [npm_exe, "run", "dev", "--", "--port", str(frontend_port), "--strictPort"],
                    cwd=str(frontend_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                procs.append(frontend_proc)

            # --- Wait and open browser ---
            if self._wait_for_url(app_url, timeout=40):
                print_success(t("web.ready", url=app_url))
                webbrowser.open(app_url)
            else:
                print_info(t("web.url.label"), t("web.url.manual", url=app_url))

            self.console.print()
            if not procs:
                print_info(t("web.label"), t("web.all_running"))
                return
            print_info(t("web.label"), t("web.running_hint"))
            self.console.print()

            # Block until Ctrl+C or a managed process dies
            while True:
                for p in procs:
                    if p.poll() is not None:
                        print_error(t("web.service_died"))
                        raise KeyboardInterrupt
                time.sleep(1)

        except KeyboardInterrupt:
            self.console.print()
            print_info(t("web.label"), t("web.shutting"))
        finally:
            for p in reversed(procs):
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill()
            if procs:
                print_success(t("web.stopped"))
            if ollama_started:
                print_info(t("web.ollama.label"), t("web.ollama.bg"))

    @staticmethod
    def _port_in_use(port: int) -> bool:
        import socket
        for family, addr in [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")]:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                try:
                    s.bind((addr, port))
                except OSError:
                    return True
        return False

    @staticmethod
    def _url_reachable(url: str) -> bool:
        import httpx
        try:
            httpx.get(url, timeout=2)
            return True
        except Exception:
            return False

    @staticmethod
    def _wait_for_url(url: str, timeout: int = 30) -> bool:
        import httpx
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                httpx.get(url, timeout=2)
                return True
            except Exception:
                time.sleep(0.5)
        return False

    def _cmd_memory(self) -> None:
        try:
            facts = self.client.list_facts()
            if not facts:
                print_info(t("memory.label"), t("memory.empty"))
                return
            rows = []
            for f in facts[:20]:
                fid = str(f.get("id", ""))
                text = f.get("text", "")[:80]
                rows.append([fid, text])
            print_table(t("memory.label"), ["ID", t("memory.col.fact")], rows)
        except Exception as e:
            print_error(t("memory.fail", e=e))

    def _cmd_tasks(self) -> None:
        try:
            tasks = self.client.list_tasks()
            if not tasks:
                print_info(t("tasks.label"), t("tasks.none"))
                return
            rows = []
            for tk in tasks:
                tid = str(tk.get("id", ""))
                done = "✓" if tk.get("done") else " "
                text = tk.get("text", "")[:60]
                rows.append([tid, done, text])
            print_table(t("tasks.label"), ["ID", "✓", t("tasks.col.text")], rows)
        except Exception as e:
            print_error(t("tasks.fail", e=e))

    def _cmd_task_add(self, arg: str) -> None:
        if not arg:
            print_error(t("task.usage"))
            return
        try:
            self.client.create_task(arg)
            print_success(t("task.created", t=arg))
        except Exception as e:
            print_error(t("task.fail", e=e))

    def _cmd_status(self) -> None:
        try:
            h = self.client.health()
            print_success(t("status.online"))
            print_info(t("status.chat_model"), h.get("chat_model", "?"))
            print_info(t("status.embed_model"), h.get("embed_model", "?"))
            models = self.client.list_models()
            print_info(t("status.models_installed"), ", ".join(models) if models else t("status.none"))
        except Exception as e:
            print_error(t("status.fail", e=e))

    def _cmd_config(self) -> None:
        try:
            settings = self.client.get_settings()
            for k, v in settings.items():
                print_info(k, str(v))
        except Exception as e:
            print_error(t("config.fail", e=e))

    def _cmd_think(self) -> None:
        self._show_thinking = not self._show_thinking
        print_info(t("think.label"), t("think.on") if self._show_thinking else t("think.off"))
