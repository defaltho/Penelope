"""penelope chat — send a message and stream the response."""
from __future__ import annotations

import sys

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_markdown, print_token
from cli.session_store import load_last_session, save_last_session


@click.command()
@click.argument("message")
@click.option("--model", "-m", default=None, help="Modelo a usar.")
@click.option("--session", "-s", default=None, help="ID de sessão existente.")
@click.option("--incognito", "-i", is_flag=True, help="Modo anónimo (nada é guardado).")
@click.option("--markdown", "use_md", is_flag=True, help="Renderizar resposta como Markdown.")
@click.option("--web", "use_web", is_flag=True, help="Activar pesquisa web.")
@click.option("--no-think", "hide_think", is_flag=True, help="Suprimir bloco de raciocínio.")
def chat(
    message: str,
    model: str | None,
    session: str | None,
    incognito: bool,
    use_md: bool,
    use_web: bool,
    hide_think: bool,
) -> None:
    """Envia uma mensagem e mostra a resposta em streaming."""
    client = PenelopeClient()

    # Reutilizar última sessão se não fornecida explicitamente
    if not session:
        session = load_last_session()

    if not session:
        sess_data = client.create_session("Penelope CLI")
        session = sess_data.get("id") or sess_data.get("session_id")
        if not session:
            print_error("Não foi possível criar sessão. Backend disponível?")
            sys.exit(1)

    full_response = ""
    in_think = False
    try:
        for event, data in client.chat_stream(
            message,
            session_id=session,
            model=model,
            incognito=incognito,
            use_web=use_web,
        ):
            if event == "token":
                token = data.get("token", "")
                if not token:
                    continue
                if hide_think:
                    if "<think>" in token or "<THINK>" in token:
                        in_think = True
                    if "</think>" in token or "</THINK>" in token:
                        in_think = False
                        continue
                    if in_think:
                        continue
                if use_md:
                    full_response += token
                else:
                    print_token(token)
            elif event == "approval":
                from cli.approval import prompt_approval
                decision = prompt_approval(data.get("tool", "?"), data.get("command", ""))
                client.approve_decision(
                    approval_id=data.get("approval_id", ""),
                    decision=decision,
                    session_id=session or "",
                    tool=data.get("tool", ""),
                )
            elif event == "error":
                print_error(data.get("error", "erro desconhecido"))
                sys.exit(1)
            elif event == "done":
                sid = data.get("session_id") or session
                if sid:
                    save_last_session(str(sid))
                    if not use_md:
                        click.echo(f"\n[sessão {str(sid)[:8]}]", err=True)
    except Exception as e:
        print_error(str(e))
        sys.exit(1)

    if use_md and full_response:
        print_markdown(full_response)
