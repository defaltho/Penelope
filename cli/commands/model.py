"""penelope model — show or set the default model."""
from __future__ import annotations

from pathlib import Path

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_info, print_success


def _last_model_file() -> Path:
    d = Path.home() / ".penelope"
    d.mkdir(exist_ok=True)
    return d / "last_model"


def _load_last_model() -> str:
    try:
        return _last_model_file().read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _save_last_model(name: str) -> None:
    try:
        _last_model_file().write_text(name, encoding="utf-8")
    except Exception:
        pass


@click.command()
@click.argument("name", required=False)
def model(name: str | None) -> None:
    """Mostra ou define o modelo padrão.

    Sem argumento: lista modelos disponíveis e mostra o actual.
    Com argumento: define NAME como modelo padrão.
    """
    client = PenelopeClient()

    if not name:
        current = _load_last_model()
        try:
            settings = client.get_settings()
            if not current:
                current = settings.get("chat_model", "")
        except Exception:
            pass

        print_info("Modelo actual", current or "(não definido)")

        try:
            models = client.list_models()
            if models:
                print_info("Modelos disponíveis", ", ".join(models))
        except Exception as e:
            print_error(f"Não foi possível listar modelos: {e}")
        return

    _save_last_model(name)
    try:
        client.put_settings({"chat_model": name})
        print_success(f"Modelo definido: {name}")
    except Exception as e:
        print_error(f"Falha ao actualizar definição: {e}")
