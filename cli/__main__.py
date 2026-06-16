"""Penelope CLI — entry point.

Usage:
    python -m cli              # interactive TUI (default)
    python -m cli chat "msg"   # one-shot command
    python -m cli status       # check backend health
"""
from __future__ import annotations

import click

from cli.commands.chat import chat
from cli.commands.config import config
from cli.commands.memory import memory
from cli.commands.notes import note
from cli.commands.status import status
from cli.commands.tasks import task


@click.group(invoke_without_command=True)
@click.version_option(version="0.2.0", prog_name="penelope")
@click.option("--model", "-m", default=None, help="Modelo a usar no modo interactivo.")
@click.pass_context
def cli(ctx: click.Context, model: str | None) -> None:
    """Penelope — assistente local de IA."""
    if ctx.invoked_subcommand is None:
        from cli.tui import PenelopeTUI

        tui = PenelopeTUI(model_override=model)
        tui.run()


cli.add_command(chat)
cli.add_command(status)
cli.add_command(memory)
cli.add_command(task)
cli.add_command(note)
cli.add_command(config)


if __name__ == "__main__":
    cli()
