"""penelope language — show or switch the CLI language."""
from __future__ import annotations

import click

from cli.i18n import get_language, language_name, load_language, set_language
from cli.render import print_error, print_info, print_success


@click.command()
@click.argument("lang", required=False)
def language(lang: str | None) -> None:
    """Mostra ou altera o idioma do CLI.

    Idiomas disponíveis: en (English), pt (Português).

    Sem argumento: mostra o idioma actual.
    Com argumento (en ou pt): altera o idioma.
    """
    load_language()

    if not lang:
        print_info("Idioma actual", language_name())
        print_info("Disponíveis", "en (English), pt (Português)")
        return

    if set_language(lang):
        print_success(f"Idioma alterado para: {language_name()}")
    else:
        print_error(f"Idioma '{lang}' inválido. Usa: en ou pt")
