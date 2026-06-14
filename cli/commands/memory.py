"""penelope memory — manage semantic facts."""
from __future__ import annotations

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_table


@click.group()
def memory() -> None:
    """Gerir a memória semântica (factos)."""


@memory.command("list")
@click.option("--query", "-q", default=None, help="Pesquisa semântica.")
def list_facts(query: str | None) -> None:
    """Lista factos semânticos."""
    client = PenelopeClient()
    try:
        facts = client.list_facts(q=query)
    except Exception as e:
        print_error(str(e))
        return

    if not facts:
        click.echo("Sem factos." if not query else "Nenhum resultado.")
        return

    rows = [[str(f["id"]), f.get("fact_type", ""), f["text"][:80]] for f in facts]
    print_table("Memória", ["ID", "Tipo", "Texto"], rows)


@memory.command()
@click.argument("query")
def search(query: str) -> None:
    """Pesquisa semântica na memória."""
    client = PenelopeClient()
    try:
        facts = client.list_facts(q=query)
    except Exception as e:
        print_error(str(e))
        return

    if not facts:
        click.echo("Nenhum resultado.")
        return

    rows = [[str(f["id"]), f.get("fact_type", ""), f["text"][:80]] for f in facts]
    print_table(f"Resultados: \"{query}\"", ["ID", "Tipo", "Texto"], rows)
