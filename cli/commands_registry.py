"""Slash commands for the interactive TUI + prompt_toolkit completer."""
from __future__ import annotations

from dataclasses import dataclass

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


@dataclass(frozen=True, slots=True)
class SlashCmd:
    name: str
    desc: str
    group: str = "geral"
    takes_arg: bool = False


TUI_COMMANDS: list[SlashCmd] = [
    SlashCmd("/new", "Começa uma conversa nova.", "conversa"),
    SlashCmd("/compact", "Resume e compacta o contexto.", "conversa"),
    SlashCmd("/clear", "Limpa o ecrã.", "conversa"),
    SlashCmd("/model", "Mostra ou troca o modelo.", "modos", takes_arg=True),
    SlashCmd("/incognito", "Alterna o modo anónimo (sem memória).", "modos"),
    SlashCmd("/websearch", "Alterna a pesquisa na web.", "modos"),
    SlashCmd("/think", "Mostra ou esconde o raciocínio.", "modos"),
    SlashCmd("/memory", "Lista factos da memória.", "dados"),
    SlashCmd("/tasks", "Lista tarefas.", "dados"),
    SlashCmd("/task", "Adiciona uma tarefa.", "dados", takes_arg=True),
    SlashCmd("/status", "Estado do backend e modelos.", "sistema"),
    SlashCmd("/config", "Mostra as definições.", "sistema"),
    SlashCmd("/web", "Abre a interface web no browser.", "sistema"),
    SlashCmd("/help", "Mostra esta ajuda.", "sistema"),
    SlashCmd("/exit", "Sai da Penelope.", "sistema"),
]

# Display order for grouped help.
COMMAND_GROUPS: list[str] = ["conversa", "modos", "dados", "sistema"]


class SlashCompleter(Completer):
    def get_completions(
        self, document: Document, complete_event: object
    ):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        prefix = text[1:]
        for cmd in TUI_COMMANDS:
            if cmd.name[1:].startswith(prefix):
                yield Completion(
                    cmd.name,
                    start_position=-len(text),
                    display_meta=cmd.desc,
                )
