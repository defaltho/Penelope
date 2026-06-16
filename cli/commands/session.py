"""penelope session — manage chat sessions."""
from __future__ import annotations

import sys

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_info, print_markdown, print_success, print_table
from cli.session_store import load_last_session, save_last_session


@click.group()
def session() -> None:
    """Gerir sessões de chat."""


@session.command("list")
def list_sessions() -> None:
    """Lista sessões existentes."""
    client = PenelopeClient()
    try:
        sessions = client.list_sessions()
    except Exception as e:
        print_error(str(e))
        return

    if not sessions:
        click.echo("Sem sessões.")
        return

    last = load_last_session()
    rows = []
    for s in sessions:
        sid = str(s.get("id", ""))
        name = (s.get("name") or "")[:40]
        mark = "*" if sid == last else " "
        rows.append([mark, sid[:8], name])
    print_table("Sessões", ["", "ID", "Nome"], rows)


@session.command("new")
@click.option("--name", "-n", default="Penelope CLI", show_default=True, help="Nome da sessão.")
def new_session(name: str) -> None:
    """Cria uma nova sessão."""
    client = PenelopeClient()
    try:
        sess = client.create_session(name)
        sid = sess.get("id") or sess.get("session_id")
        if not sid:
            print_error("Resposta inesperada do backend.")
            sys.exit(1)
        save_last_session(str(sid))
        print_success(f"Sessão criada: {sid}")
        print_info("Nome", name)
    except Exception as e:
        print_error(str(e))
        sys.exit(1)


@session.command("compact")
@click.option("--session", "-s", "session_id", default=None,
              help="ID da sessão (padrão: última sessão usada).")
def compact(session_id: str | None) -> None:
    """Compacta o contexto de uma sessão (resume e trunca o histórico)."""
    client = PenelopeClient()

    sid = session_id or load_last_session()
    if not sid:
        print_error("Nenhuma sessão activa. Fornece --session <id> ou usa 'penelope chat' primeiro.")
        sys.exit(1)

    try:
        resp = client.client.post(f"/api/sessions/{sid}/compact", timeout=120.0)
        resp.raise_for_status()
        data = resp.json()
        print_success("Sessão compactada.")
        summary = data.get("summary", "")
        if summary:
            print_markdown(summary)
    except Exception as e:
        print_error(f"Falha ao compactar: {e}")
        sys.exit(1)
