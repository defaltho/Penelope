"""Penelope CLI — entry point.

Usage:
    python -m cli              # interactive TUI (default)
    python -m cli chat "msg"   # one-shot command
    python -m cli status       # check backend health
    python -m cli model        # show/set model
    python -m cli session list # manage sessions
    python -m cli language pt  # switch language
    python -m cli web          # start web interface
"""
from __future__ import annotations

import click

from cli.commands.chat import chat
from cli.commands.config import config
from cli.commands.language import language
from cli.commands.memory import memory
from cli.commands.model import model
from cli.commands.notes import note
from cli.commands.session import session
from cli.commands.status import status
from cli.commands.tasks import task
from cli.commands.web import web


@click.group(invoke_without_command=True)
@click.version_option(version="1.5", prog_name="penelope")
@click.option("--model", "-m", "model_override", default=None, help="Modelo a usar no modo interactivo.")
@click.pass_context
def cli(ctx: click.Context, model_override: str | None) -> None:
    """Penelope — assistente local de IA."""
    if ctx.invoked_subcommand is None:
        from cli.tui import PenelopeTUI

        tui = PenelopeTUI(model_override=model_override)
        tui.run()


cli.add_command(chat)
cli.add_command(status)
cli.add_command(memory)
cli.add_command(task)
cli.add_command(note)
cli.add_command(config)
cli.add_command(model)
cli.add_command(session)
cli.add_command(language)
cli.add_command(web)


if __name__ == "__main__":
    cli()
