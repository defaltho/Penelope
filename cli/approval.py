"""Inline agent approval prompt for the Penelope CLI."""
from __future__ import annotations

from cli.i18n import t
from cli.render import get_console
from cli.theme import ACCENT, ERROR, MUTED, SUCCESS


_CHOICES = {
    "1": "allow_once",
    "2": "allow_session",
    "3": "allow_always",
    "4": "deny",
}


def prompt_approval(tool: str, command: str) -> str:
    """Show an inline approval prompt and return the user's decision string.

    Called from a background thread (TUI) or main thread (one-shot chat).
    Returns one of: allow_once, allow_session, allow_always, deny.
    """
    console = get_console()
    console.print()
    console.print(f"  [{ERROR} bold]⚠  {t('approval.header')}:[/{ERROR} bold] [{ACCENT}]{tool}[/{ACCENT}]")
    if command:
        preview = command[:120] + ("…" if len(command) > 120 else "")
        console.print(f"    [{MUTED}]→ {preview}[/{MUTED}]")
    console.print()
    console.print(
        f"  [{MUTED}]{t('approval.prompt')}:[/{MUTED}] "
        f"[[{SUCCESS}]1[/{SUCCESS}]] {t('approval.allow_once')}  "
        f"[[{SUCCESS}]2[/{SUCCESS}]] {t('approval.allow_session')}  "
        f"[[{SUCCESS}]3[/{SUCCESS}]] {t('approval.allow_always')}  "
        f"[[{ERROR}]4[/{ERROR}]] {t('approval.deny')}  "
        f"[{MUTED}]{t('approval.hint')}[/{MUTED}]: ",
        end="",
    )
    try:
        raw = input().strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""
    decision = _CHOICES.get(raw, "deny")
    label = t(f"approval.{decision}")
    color = SUCCESS if decision != "deny" else ERROR
    console.print(f"  [{color}]→ {label}[/{color}]")
    console.print()
    return decision
