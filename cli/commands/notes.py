"""penelope note — manage notes."""
from __future__ import annotations

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_success, print_table


@click.group()
def note() -> None:
    """Gerir notas."""


@note.command("list")
@click.option("--pinned", is_flag=True, help="Mostrar apenas notas fixadas.")
def list_notes(pinned: bool) -> None:
    """Lista notas."""
    client = PenelopeClient()
    try:
        notes = client.list_notes()
    except Exception as e:
        print_error(str(e))
        return

    if pinned:
        notes = [n for n in notes if n.get("pinned")]

    if not notes:
        click.echo("Sem notas.")
        return

    rows = [
        [
            str(n.get("id", "")),
            "pin" if n.get("pinned") else "   ",
            (n.get("title") or "sem título")[:30],
            (n.get("content") or "")[:40].replace("\n", " "),
        ]
        for n in notes
    ]
    print_table("Notas", ["ID", "Pin", "Título", "Conteúdo"], rows)


@note.command("add")
@click.argument("title")
@click.option("--content", "-c", default="", help="Conteúdo da nota.")
def add_note(title: str, content: str) -> None:
    """Cria uma nova nota."""
    client = PenelopeClient()
    try:
        result = client.create_note(title, content=content)
        note_id = result.get("id", "?")
        print_success(f"Nota criada: #{note_id} — {title}")
    except Exception as e:
        print_error(str(e))


@note.command("delete")
@click.argument("note_id")
def delete_note(note_id: str) -> None:
    """Apaga uma nota pelo ID."""
    client = PenelopeClient()
    try:
        result = client.delete_note(note_id)
        if result.get("ok") or result.get("message") or result.get("deleted"):
            print_success(f"Nota #{note_id} apagada.")
        else:
            print_error(f"Não foi possível apagar a nota #{note_id}.")
    except Exception as e:
        print_error(str(e))
