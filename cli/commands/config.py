"""penelope config — read/write settings."""
from __future__ import annotations

import json

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_info, print_success


@click.group()
def config() -> None:
    """Ler e alterar definições."""


@config.command()
@click.argument("key")
def get(key: str) -> None:
    """Lê o valor de uma definição."""
    client = PenelopeClient()
    try:
        settings = client.get_settings()
    except Exception as e:
        print_error(str(e))
        return

    if key in settings:
        print_info(key, str(settings[key]))
    else:
        available = ", ".join(sorted(settings.keys()))
        print_error(f"Chave '{key}' não encontrada. Disponíveis: {available}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_val(key: str, value: str) -> None:
    """Altera o valor de uma definição."""
    client = PenelopeClient()
    try:
        parsed: str | int | float | bool = value
        if value.lower() in ("true", "false"):
            parsed = value.lower() == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                try:
                    parsed = float(value)
                except ValueError:
                    pass
        client.put_settings({key: parsed})
        print_success(f"{key} = {parsed}")
    except Exception as e:
        print_error(str(e))


@config.command("list")
def list_settings() -> None:
    """Lista todas as definições."""
    client = PenelopeClient()
    try:
        settings = client.get_settings()
    except Exception as e:
        print_error(str(e))
        return

    for k, v in sorted(settings.items()):
        print_info(k, str(v))
