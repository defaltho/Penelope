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
from prompt_toolkit.layout import Float, FloatContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import TextArea

from cli.client import PenelopeClient
from cli.commands_registry import SlashCompleter, TUI_COMMANDS
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
    ERROR,
    FG,
    MUTED,
    RULE,
    SPARK,
    SPINNER_FRAMES,
    STATUS_TEXT,
    SUCCESS,
)


def _esc(text: str) -> str:
    """Escape rich markup so literal [brackets] in user text aren't parsed."""
    from rich.markup import escape
    return escape(text)


def _ensure_data_dir() -> Path:
    d = Path.home() / ".penelope"
    d.mkdir(exist_ok=True)
    return d


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
    "completion-menu.completion": f"bg:{BAR_BG} {FG}",
    "completion-menu.completion.current": f"bg:{ACCENT} #0d0e11 bold",
    "completion-menu.meta.completion": f"bg:{BAR_BG} {MUTED}",
    "completion-menu.meta.completion.current": f"bg:{ACCENT} #0d0e11",
})


class PenelopeTUI:
    def __init__(self, *, model_override: str | None = None):
        self.client = PenelopeClient()
        self.console = get_console()
        self.conversation_id: int | None = None
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

    @staticmethod
    def _term_width() -> int:
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 80

    def _conversation_label(self) -> str:
        return f"conversa #{self.conversation_id}" if self.conversation_id else "nova conversa"

    # --- Layout fragment providers (called every render) ---

    def _brand_rule_fragments(self):
        width = self._term_width()
        label = f" {SPARK} penelope "
        line_len = max(width - get_cwidth(label) - 3, 0)
        return [
            ("class:rule", "──"),
            ("class:brand", label),
            ("class:rule", "─" * line_len),
        ]

    def _spinner_fragments(self):
        if not self._spinner_text:
            return []
        frame = SPINNER_FRAMES[int(time.monotonic() * 10) % len(SPINNER_FRAMES)]
        start = self._spinner_start or time.monotonic()
        elapsed = time.monotonic() - start
        return [("class:spin", f"  {SPARK} {frame} {self._spinner_text}  ({elapsed:.1f}s)")]

    def _statusbar_fragments(self):
        frags = [
            ("class:sb-brand", f"  {SPARK} "),
            ("class:sb-model", self.model or "—"),
            ("class:sb-sep", "   "),
        ]
        if self.conversation_id:
            frags.append(("class:sb-conv", self._conversation_label()))
        else:
            frags.append(("class:sb-conv-dim", "nova conversa"))
        if self.incognito:
            frags += [("class:sb-sep", "   "), ("class:sb-flag-warn", "incógnito")]
        if self.web_search:
            frags += [("class:sb-sep", "   "), ("class:sb-flag-web", "web")]
        frags += [("class:sb-sep", "   "), ("class:sb-hint", "enter envia · alt+enter linha · /help")]
        return frags

    def _spinner_height(self) -> int:
        return 1 if self._spinner_text else 0

    # --- App assembly ---

    def _build_app(self, *, app_input=None, app_output=None) -> Application:
        data_dir = _ensure_data_dir()

        self._input = TextArea(
            height=Dimension(min=1, max=8),
            prompt=[("class:prompt", "› ")],
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
        brand_rule = Window(
            content=FormattedTextControl(self._brand_rule_fragments),
            height=1,
        )
        status_bar = Window(
            content=FormattedTextControl(self._statusbar_fragments),
            height=1,
            wrap_lines=False,
        )

        body = HSplit([
            Window(height=0),
            spinner,
            brand_rule,
            self._input,
            status_bar,
        ])
        root = FloatContainer(
            content=body,
            floats=[Float(
                xcursor=True,
                ycursor=True,
                content=CompletionsMenu(max_height=10, scroll_offset=1),
            )],
        )

        app = Application(
            layout=Layout(root, focused_element=self._input),
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

    def _submit(self) -> None:
        if self._busy:
            return
        text = self._input.text.strip()
        self._input.buffer.reset()
        if not text:
            return
        self._echo_user(text)
        if text.startswith("/"):
            cmd = text.split(None, 1)[0].lower()
            if cmd == "/compact":
                # Network-heavy and slow; run off the UI thread.
                self._start_command_thread(text, "a compactar…")
                return
            should_exit = self._handle_command(text)
            if should_exit and self._app is not None:
                self._app.exit()
            self._invalidate()
        else:
            self._start_chat(text)

    def _start_command_thread(self, text: str, spinner_text: str) -> None:
        self._busy = True
        self._set_spinner(spinner_text)

        def work() -> None:
            try:
                self._handle_command(text)
            finally:
                self._busy = False
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

        def work() -> None:
            try:
                self._chat(text)
            finally:
                self._busy = False
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

    def run(self) -> None:
        self._load_settings()
        _install_input_extras()
        print_banner(self.model or "—", cwd=os.getcwd(), conversation=self._conversation_label())

        app = self._build_app()
        try:
            with patch_stdout():
                app.run()
        except (EOFError, KeyboardInterrupt):
            pass

        print_goodbye()
        if self._pending_action == "web":
            self._cmd_web_server()

    # --- Settings ---

    def _load_settings(self) -> None:
        try:
            settings = self.client.get_settings()
            if not self.model:
                self.model = settings.get("chat_model", "")
        except Exception:
            print_error(
                f"backend não encontrado em {self.client.base_url}\n"
                "  para iniciar:  cd backend && uvicorn main:app --reload"
            )

    # --- Chat streaming ---

    def _chat(self, message: str) -> None:
        self._set_spinner(STATUS_TEXT.get("thinking", "a pensar…"))

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
                conversation_id=self.conversation_id,
                model=self.model or None,
                incognito=self.incognito,
            ):
                if self._interrupt:
                    break

                if event == "status":
                    kind = payload.get("kind", "thinking")
                    status_text = STATUS_TEXT.get(kind, payload.get("text", ""))
                    now = time.monotonic()
                    elapsed = now - last_status_time
                    if activities:
                        pk, pt, _ = activities[-1]
                        activities[-1] = (pk, pt, elapsed)
                    activities.append((kind, status_text, 0.0))
                    last_status_time = now
                    self._set_spinner(status_text)

                elif event == "token":
                    tok = payload.get("token", "")
                    if not tok:
                        continue
                    _flush_feed()
                    renderer.feed(tok)

                elif event == "error":
                    _flush_feed()
                    renderer.flush()
                    print_error(payload.get("error", "Erro desconhecido"))
                    return

                elif event == "done":
                    self.conversation_id = payload.get("conversation_id", self.conversation_id)
                    model_used = payload.get("model", model_used)
                    tok_per_sec = payload.get("tok_per_sec")

        except Exception as e:
            _flush_feed()
            renderer.flush()
            print_error(str(e))
            return

        _flush_feed()
        renderer.flush()

        if self._interrupt:
            self.console.print(f"  [{MUTED}]interrompido[/{MUTED}]")
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
            case "/new":
                self._cmd_new()
            case "/clear":
                self._cmd_clear()
            case "/compact":
                self._cmd_compact()
            case "/model":
                self._cmd_model(arg)
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
                print_error(f"Comando desconhecido: {cmd}")
        return False

    def _cmd_help(self) -> None:
        self.console.print()
        print_help_table(TUI_COMMANDS)
        self.console.print()

    def _cmd_new(self) -> None:
        self.conversation_id = None
        print_success("Nova conversa iniciada.")

    def _cmd_clear(self) -> None:
        self.console.clear()
        print_banner(self.model or "—", cwd=os.getcwd(), conversation=self._conversation_label())

    def _cmd_compact(self) -> None:
        if self.conversation_id is None:
            print_error("Nenhuma conversa activa para compactar.")
            return
        try:
            resp = self.client.client.post(
                "/chat/compact",
                json={"conversation_id": self.conversation_id},
                timeout=120.0,
            )
            data = resp.json()
            print_success("Conversa compactada.")
            summary = data.get("summary", "")
            if summary:
                print_markdown(summary)
        except Exception as e:
            print_error(f"Falha ao compactar: {e}")

    def _cmd_model(self, arg: str) -> None:
        if not arg:
            print_info("Modelo actual", self.model or "?")
            try:
                models = self.client.list_models()
                if models:
                    print_info("Disponíveis", ", ".join(models))
            except Exception:
                pass
            return
        self.model = arg
        print_success(f"Modelo alterado para {arg}")

    def _cmd_incognito(self) -> None:
        self.incognito = not self.incognito
        state = "activado" if self.incognito else "desactivado"
        print_info("Modo anónimo", state)

    def _cmd_websearch(self) -> None:
        self.web_search = not self.web_search
        state = "activada" if self.web_search else "desactivada"
        print_info("Pesquisa web", state)

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
            print_error("'uv' não encontrado no PATH. Corre 'bin\\setup.cmd' primeiro.")
            return
        if not npm_exe:
            print_error("'npm' não encontrado no PATH. Instala o Node.js primeiro.")
            return

        procs: list[subprocess.Popen] = []
        ollama_started = False
        backend_already_running = False
        frontend_already_running = False

        try:
            # --- Ollama ---
            if self._url_reachable(f"{ollama_url}/api/tags"):
                print_info("Ollama", "já está a correr")
            elif shutil.which("ollama"):
                print_info("Ollama", "a iniciar…")
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
                print_error("'ollama' não encontrado. Instala a partir de https://ollama.com")
                return

            # --- Backend ---
            if self._port_in_use(backend_port):
                print_info("Backend", f"já está a correr na porta {backend_port}")
                backend_already_running = True
            else:
                print_info("Backend", f"a iniciar na porta {backend_port}…")
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
                print_info("Frontend", f"já está a correr na porta {frontend_port}")
                frontend_already_running = True
            else:
                node_modules = frontend_dir / "node_modules"
                if not node_modules.exists():
                    print_info("Frontend", "a instalar dependências (primeira vez)…")
                    subprocess.run(
                        [npm_exe, "install"],
                        cwd=str(frontend_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True,
                    )

                print_info("Frontend", f"a iniciar na porta {frontend_port}…")
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
                print_success(f"Interface web pronta → {app_url}")
                webbrowser.open(app_url)
            else:
                print_info("URL", f"abre manualmente: {app_url}")

            self.console.print()
            if not procs:
                print_info("Web", "todos os serviços já estavam a correr — browser aberto")
                return
            print_info("Web", "a correr. Ctrl+C para parar e voltar ao terminal.")
            self.console.print()

            # Block until Ctrl+C or a managed process dies
            while True:
                for p in procs:
                    if p.poll() is not None:
                        print_error("Um dos serviços parou inesperadamente.")
                        raise KeyboardInterrupt
                time.sleep(1)

        except KeyboardInterrupt:
            self.console.print()
            print_info("Web", "a desligar…")
        finally:
            for p in reversed(procs):
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill()
            if procs:
                print_success("Servidores web parados.")
            if ollama_started:
                print_info("Ollama", "iniciado por /web — ainda a correr em background")

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
                print_info("Memória", "vazia")
                return
            rows = []
            for f in facts[:20]:
                fid = str(f.get("id", ""))
                text = f.get("text", "")[:80]
                rows.append([fid, text])
            print_table("Memória", ["ID", "Facto"], rows)
        except Exception as e:
            print_error(f"Falha ao listar memória: {e}")

    def _cmd_tasks(self) -> None:
        try:
            tasks = self.client.list_tasks()
            if not tasks:
                print_info("Tarefas", "nenhuma")
                return
            rows = []
            for t in tasks:
                tid = str(t.get("id", ""))
                done = "✓" if t.get("done") else " "
                text = t.get("text", "")[:60]
                rows.append([tid, done, text])
            print_table("Tarefas", ["ID", "✓", "Texto"], rows)
        except Exception as e:
            print_error(f"Falha ao listar tarefas: {e}")

    def _cmd_task_add(self, arg: str) -> None:
        if not arg:
            print_error("Uso: /task <texto da tarefa>")
            return
        try:
            self.client.create_task(arg)
            print_success(f"Tarefa criada: {arg}")
        except Exception as e:
            print_error(f"Falha ao criar tarefa: {e}")

    def _cmd_status(self) -> None:
        try:
            h = self.client.health()
            print_success("Backend online")
            print_info("Chat model", h.get("chat_model", "?"))
            print_info("Embed model", h.get("embed_model", "?"))
            models = self.client.list_models()
            print_info("Modelos instalados", ", ".join(models) if models else "nenhum")
        except Exception as e:
            print_error(f"Backend não acessível: {e}")

    def _cmd_config(self) -> None:
        try:
            settings = self.client.get_settings()
            for k, v in settings.items():
                print_info(k, str(v))
        except Exception as e:
            print_error(f"Falha ao ler definições: {e}")

    def _cmd_think(self) -> None:
        self._show_thinking = not self._show_thinking
        state = "visível" if self._show_thinking else "escondido"
        print_info("Raciocínio", state)
