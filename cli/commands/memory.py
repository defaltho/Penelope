"""penelope memory — manage semantic facts."""
from __future__ import annotations

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_success, print_table


@click.group()
def memory() -> None:
    """Gerir a memória semântica (factos)."""


@memory.command("list")
@click.option("--query", "-q", default=None, help="Filtro por texto.")
@click.option("--mem0", "only_mem0", is_flag=True, help="Mostrar apenas factos consolidados pelo Mem0.")
def list_facts(query: str | None, only_mem0: bool) -> None:
    """Lista factos semânticos."""
    client = PenelopeClient()
    try:
        facts = client.list_facts(q=query)
    except Exception as e:
        print_error(str(e))
        return

    if only_mem0:
        facts = [f for f in facts if f.get("source") == "mem0" or f.get("type") == "mem0"]

    if not facts:
        click.echo("Sem factos." if not query else "Nenhum resultado.")
        return

    rows = [
        [str(f.get("id", "")), f.get("fact_type") or f.get("category", ""), f.get("text", "")[:80]]
        for f in facts
    ]
    title = "Mem0 Memory" if only_mem0 else "Memória"
    print_table(title, ["ID", "Tipo", "Texto"], rows)


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

    rows = [
        [str(f.get("id", "")), f.get("fact_type") or f.get("category", ""), f.get("text", "")[:80]]
        for f in facts
    ]
    print_table(f'Resultados: "{query}"', ["ID", "Tipo", "Texto"], rows)


@memory.command("add")
@click.argument("text")
@click.option("--category", "-c", default="preference", show_default=True,
              help="Categoria: preference, profile, financial, language, other.")
def add_fact(text: str, category: str) -> None:
    """Adiciona um facto à memória."""
    client = PenelopeClient()
    try:
        result = client.add_fact(text, category=category)
        if result.get("ok"):
            print_success(f"Facto adicionado. Total: {result.get('count', '?')}")
        else:
            print_error("Não foi possível adicionar o facto.")
    except Exception as e:
        print_error(str(e))


@memory.command("delete")
@click.argument("memory_id")
def delete_fact(memory_id: str) -> None:
    """Apaga um facto da memória pelo ID."""
    client = PenelopeClient()
    try:
        result = client.delete_fact(memory_id)
        if result.get("ok") or result.get("message"):
            print_success(f"Facto {memory_id} apagado.")
        else:
            print_error(f"Não foi possível apagar {memory_id}.")
    except Exception as e:
        print_error(str(e))


@memory.command("pin")
@click.argument("memory_id")
@click.option("--unpin", is_flag=True, help="Desafixar em vez de fixar.")
def pin_fact(memory_id: str, unpin: bool) -> None:
    """Fixa (ou desfixa) um facto para ser sempre incluído no contexto."""
    client = PenelopeClient()
    pinned = not unpin
    try:
        result = client.pin_fact(memory_id, pinned=pinned)
        if result.get("ok") or result.get("message"):
            action = "Desafixado" if unpin else "Fixado"
            print_success(f"{action}: facto {memory_id}")
        else:
            print_error(f"Não foi possível alterar pin de {memory_id}.")
    except Exception as e:
        print_error(str(e))
