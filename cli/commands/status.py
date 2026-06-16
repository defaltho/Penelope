"""penelope status — check backend health."""
from __future__ import annotations

import sys

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_info, print_success


@click.command()
def status() -> None:
    """Verifica o estado do backend Penelope."""
    client = PenelopeClient()
    try:
        h = client.health()
    except Exception as e:
        print_error(f"Backend não acessível: {e}")
        sys.exit(1)

    print_success("Backend online")
    print_info("URL", client.base_url)
    print_info("Estado", h.get("status", "healthy"))

    try:
        models = client.list_models()
        print_info("Modelos disponíveis", ", ".join(models) if models else "nenhum")
    except Exception:
        pass
