"""Inline agent approval prompt for the Penelope CLI."""
from __future__ import annotations

from cli.render import get_console
from cli.theme import ACCENT, ERROR, MUTED, SUCCESS, FG


_CHOICES = {
    "1": "allow_once",
    "2": "allow_session",
    "3": "allow_always",
    "4": "deny",
}

_LABELS = {
    "allow_once": "Uma vez",
    "allow_session": "Esta sessão",
    "allow_always": "Sempre",
    "deny": "Negar",
}


def prompt_approval(tool: str, command: str) -> str:
    """Show an inline approval prompt and return the user's decision string.

    Called from a background thread (TUI) or main thread (one-shot chat).
    Returns one of: allow_once, allow_session, allow_always, deny.
    """
    console = get_console()
    console.print()
    console.print(f"  [{ERROR} bold]⚠  Agent quer executar:[/{ERROR} bold] [{ACCENT}]{tool}[/{ACCENT}]")
    if command:
        preview = command[:120] + ("…" if len(command) > 120 else "")
        console.print(f"    [{MUTED}]→ {preview}[/{MUTED}]")
    console.print()
    console.print(
        f"  [{MUTED}]Decisão:[/{MUTED}] "
        f"[[{SUCCESS}]1[/{SUCCESS}]] Uma vez  "
        f"[[{SUCCESS}]2[/{SUCCESS}]] Sessão  "
        f"[[{SUCCESS}]3[/{SUCCESS}]] Sempre  "
        f"[[{ERROR}]4[/{ERROR}]] Negar  "
        f"[{MUTED}](enter=negar)[/{MUTED}]: ",
        end="",
    )
    try:
        raw = input().strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""
    decision = _CHOICES.get(raw, "deny")
    label = _LABELS[decision]
    color = SUCCESS if decision != "deny" else ERROR
    console.print(f"  [{color}]→ {label}[/{color}]")
    console.print()
    return decision
