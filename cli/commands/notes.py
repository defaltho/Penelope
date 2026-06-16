"""penelope note — list notes."""
from __future__ import annotations

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_table


@click.group()
def note() -> None:
    """Gerir notas."""


@note.command("list")
def list_notes() -> None:
    """Lista notas."""
    client = PenelopeClient()
    try:
        notes = client.list_notes()
    except Exception as e:
        print_error(str(e))
        return

    if not notes:
        click.echo("Sem notas.")
        return

    rows = [
        [
            str(n["id"]),
            "pin" if n.get("pinned") else "   ",
            (n.get("title") or "sem título")[:30],
            (n.get("content") or "")[:40].replace("\n", " "),
        ]
        for n in notes
    ]
    print_table("Notas", ["ID", "Pin", "Título", "Conteúdo"], rows)
