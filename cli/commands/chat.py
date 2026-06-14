"""penelope chat — send a message and stream the response."""
from __future__ import annotations

import sys

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_markdown, print_token


@click.command()
@click.argument("message")
@click.option("--model", "-m", default=None, help="Modelo Ollama a usar.")
@click.option("--conversation", "-c", default=None, type=int, help="ID da conversa existente.")
@click.option("--incognito", "-i", is_flag=True, help="Modo anónimo (nada é guardado).")
@click.option("--markdown", "use_md", is_flag=True, help="Renderizar resposta como Markdown.")
def chat(message: str, model: str | None, conversation: int | None, incognito: bool, use_md: bool) -> None:
    """Envia uma mensagem e mostra a resposta em streaming."""
    client = PenelopeClient()
    full_response = ""
    try:
        for event, data in client.chat_stream(
            message,
            conversation_id=conversation,
            model=model,
            incognito=incognito,
        ):
            if event == "token":
                token = data.get("token", "")
                if use_md:
                    full_response += token
                else:
                    print_token(token)
            elif event == "error":
                print_error(data.get("error", "erro desconhecido"))
                sys.exit(1)
            elif event == "done":
                if not use_md:
                    print()
                cid = data.get("conversation_id")
                if cid:
                    click.echo(f"\n[conversa #{cid}]", err=True)
    except Exception as e:
        print_error(str(e))
        sys.exit(1)

    if use_md and full_response:
        print_markdown(full_response)
