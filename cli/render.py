"""Terminal rendering utilities — rich-powered TUI components."""
from __future__ import annotations

import sys

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    # Force the underlying stdout to UTF-8 so box-drawing/emoji glyphs don't
    # raise UnicodeEncodeError on the Windows cp1252 console. Reconfiguring the
    # real stream (rather than wrapping sys.stdout.buffer) keeps the console
    # writing through whatever sys.stdout currently is — crucially, that lets
    # rich output flow through prompt_toolkit's patch_stdout proxy so it scrolls
    # above the persistent input block instead of corrupting it.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    # file=None → rich resolves sys.stdout at write time (respects patch_stdout).
    _console = Console(force_terminal=True)
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    _console = None  # type: ignore[assignment]


def get_console() -> Console:
    return _console


# ─── Basic output ───────────────────────────────────────────


def print_markdown(text: str) -> None:
    if HAS_RICH:
        _console.print(Markdown(text))
    else:
        print(text)


def print_token(token: str) -> None:
    print(token, end="", flush=True)


def print_error(msg: str) -> None:
    if HAS_RICH:
        from cli.theme import ERROR
        _console.print(f"  [{ERROR}]✗[/{ERROR}] {msg}")
    else:
        print(f"x {msg}")


def print_success(msg: str) -> None:
    if HAS_RICH:
        from cli.theme import SUCCESS
        _console.print(f"  [{SUCCESS}]✓[/{SUCCESS}] {msg}")
    else:
        print(f"+ {msg}")


def print_warning(msg: str) -> None:
    if HAS_RICH:
        from cli.theme import WARNING
        _console.print(f"  [{WARNING}]▲[/{WARNING}] {msg}")
    else:
        print(f"! {msg}")


def print_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    if HAS_RICH:
        from rich import box as _box
        from cli.theme import ACCENT, FG, MUTED, RULE, SPARK

        _console.print()
        head = Text("  ")
        head.append(f"{SPARK} ", style=f"bold {ACCENT}")
        head.append(title, style=f"bold {FG}")
        _console.print(head)

        table = Table(
            box=_box.SIMPLE_HEAD,
            show_edge=False,
            pad_edge=False,
            padding=(0, 2),
            header_style=f"{MUTED} italic",
            border_style=RULE,
        )
        for col in columns:
            table.add_column(col, style=FG)
        for row in rows:
            table.add_row(*row)
        from rich.padding import Padding
        _console.print(Padding(table, (0, 0, 0, 2)))
    else:
        print(f"\n{title}")
        print("-" * 60)
        header = " | ".join(f"{c:>10}" for c in columns)
        print(header)
        print("-" * 60)
        for row in rows:
            print(" | ".join(f"{v:>10}" for v in row))


def print_info(key: str, value: str) -> None:
    if HAS_RICH:
        from cli.theme import FG, MUTED
        _console.print(f"  [{MUTED}]{key:<16}[/{MUTED}] [{FG}]{value}[/{FG}]")
    else:
        print(f"{key}: {value}")


# ─── Banner ─────────────────────────────────────────────────


# ASCII wordmark shown at the top of the banner.
BANNER_ART = [
    "██████╗ ███████╗███╗   ██╗███████╗██╗      ██████╗ ██████╗ ███████╗",
    "██╔══██╗██╔════╝████╗  ██║██╔════╝██║     ██╔═══██╗██╔══██╗██╔════╝",
    "██████╔╝█████╗  ██╔██╗ ██║█████╗  ██║     ██║   ██║██████╔╝█████╗  ",
    "██╔═══╝ ██╔══╝  ██║╚██╗██║██╔══╝  ██║     ██║   ██║██╔═══╝ ██╔══╝  ",
    "██║     ███████╗██║ ╚████║███████╗███████╗╚██████╔╝██║     ███████╗",
    "╚═╝     ╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚══════╝",
]


def print_banner(model: str, *, cwd: str = "", conversation: str = "nova conversa") -> None:
    from cli.theme import ACCENT, FG, MUTED, RULE, SPARK, TAGLINE, VERSION

    if not HAS_RICH:
        print(f"penelope · cli v{VERSION}")
        print(f"modelo: {model} · /help para comandos")
        return

    w = min(_console.width or 80, 76)

    _console.print()
    # ASCII wordmark (no_wrap+crop so a narrow terminal trims instead of wrapping).
    for line in BANNER_ART:
        _console.print(Text("  " + line, style=f"bold {ACCENT}"), no_wrap=True, crop=True)
    _console.print()

    # Sub-line: ⊹ assistente local                              v0.2.0
    head = Text()
    head.append(f"  {SPARK} ", style=f"bold {ACCENT}")
    head.append(TAGLINE, style=MUTED)
    pad = max(w - 2 - len(f"{SPARK} {TAGLINE}") - len(f"v{VERSION}"), 1)
    head.append(" " * pad + f"v{VERSION}", style=RULE)
    _console.print(head)

    _console.print(Text("  " + "─" * (w - 2), style=RULE))

    def _row(label: str, value: str, vstyle: str) -> None:
        t = Text()
        t.append(f"  {label:<8}", style=MUTED)
        t.append(value, style=vstyle)
        _console.print(t)

    _row("modelo", model, f"bold {ACCENT}")
    if cwd:
        _row("pasta", cwd, FG)
    _row("sessão", conversation, MUTED)

    _console.print()
    hint = Text("  ")
    hint.append("/help", style=f"bold {ACCENT}")
    hint.append(" comandos    ", style=MUTED)
    hint.append("enter", style=FG)
    hint.append(" enviar    ", style=MUTED)
    hint.append("alt+enter", style=FG)
    hint.append(" nova linha", style=MUTED)
    _console.print(hint)
    _console.print()


# ─── Response stats ─────────────────────────────────────────


def print_response_stats(model: str, tok_per_sec: float | None, elapsed: float | None = None) -> None:
    from cli.theme import ACCENT, MUTED, SPARK

    parts = []
    if tok_per_sec is not None:
        parts.append(f"{tok_per_sec:.1f} tok/s")
    if elapsed is not None:
        parts.append(f"{elapsed:.1f}s")
    parts.append(model)

    if HAS_RICH:
        body = " · ".join(parts)
        _console.print(f"  [{ACCENT}]{SPARK}[/{ACCENT}] [{MUTED}]{body}[/{MUTED}]")
    else:
        print(" · ".join(parts))


# ─── Thinking / Reasoning ──────────────────────────────────


def print_thinking(text: str) -> None:
    from cli.theme import THINKING

    if HAS_RICH:
        _console.print(
            Panel(
                Text(text.strip(), style="dim italic"),
                title="raciocínio",
                title_align="left",
                border_style=THINKING,
                expand=False,
                padding=(0, 1),
            )
        )
    else:
        print(f"[raciocínio] {text}")


# ─── Activity feed line (Hermes-style) ─────────────────────


def print_activity(kind: str, text: str, elapsed: float | None = None) -> None:
    from cli.theme import MUTED, TOOL_ICONS

    icon = TOOL_ICONS.get(kind, "⚙")
    if HAS_RICH:
        line = Text()
        line.append("  ┊ ", style=MUTED)
        line.append(f"{icon} ", style="")
        line.append(text, style=MUTED)
        if elapsed is not None:
            line.append(f" ({elapsed:.1f}s)", style=MUTED)
        _console.print(line)
    else:
        suffix = f" ({elapsed:.1f}s)" if elapsed is not None else ""
        print(f"  | {icon} {text}{suffix}")


# ─── Goodbye / Help ────────────────────────────────────────


def print_goodbye() -> None:
    from cli.theme import ACCENT, MUTED, SPARK

    if HAS_RICH:
        _console.print(f"\n  [{ACCENT}]{SPARK}[/{ACCENT}] [{MUTED}]até já[/{MUTED}]\n")
    else:
        print("\naté já")


_GROUP_LABELS = {
    "conversa": "conversa",
    "modos": "modos",
    "dados": "dados & memória",
    "sistema": "sistema",
}


def print_help_table(commands: list) -> None:
    if not HAS_RICH:
        for cmd in commands:
            print(f"  {cmd.name:<15} {cmd.desc}")
        return

    from cli.commands_registry import COMMAND_GROUPS
    from cli.theme import ACCENT, FG, MUTED, RULE, SPARK

    w = min(_console.width or 80, 76)

    _console.print()
    title = Text("  ")
    title.append(f"{SPARK} ", style=f"bold {ACCENT}")
    title.append("comandos", style=f"bold {FG}")
    _console.print(title)
    _console.print(Text("  " + "─" * (w - 2), style=RULE))

    groups = list(COMMAND_GROUPS)
    seen = {c.group for c in commands}
    for g in sorted(seen):
        if g not in groups:
            groups.append(g)

    for gi, group in enumerate(groups):
        members = [c for c in commands if c.group == group]
        if not members:
            continue
        if gi > 0:
            _console.print()
        _console.print(Text(f"  {_GROUP_LABELS.get(group, group)}", style=f"{MUTED} italic"))
        for cmd in members:
            line = Text("    ")
            line.append(f"{cmd.name:<12}", style=f"bold {ACCENT}")
            line.append(cmd.desc, style=FG)
            _console.print(line)
    _console.print()


# ─── Notification panel (Hermes-style) ─────────────────────


def print_notification(title: str, body: str) -> None:
    from cli.theme import ACCENT, SPARK

    if HAS_RICH:
        _console.print(Panel(
            Text(body),
            title=f"{SPARK} {title}",
            title_align="left",
            border_style=ACCENT,
            expand=False,
            padding=(0, 1),
        ))
    else:
        print(f"[{title}] {body}")
