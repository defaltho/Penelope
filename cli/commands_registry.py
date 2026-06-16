"""Slash commands for the interactive TUI + prompt_toolkit completer.

Command descriptions are not stored here — they are resolved per-language from
cli.i18n under the key ``cmd.<name>`` so the menu/help follow /language.
"""
from __future__ import annotations

from dataclasses import dataclass

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from cli.i18n import t


@dataclass(frozen=True, slots=True)
class SlashCmd:
    name: str
    group: str = "geral"
    takes_arg: bool = False

    @property
    def desc(self) -> str:
        return t(f"cmd.{self.name}")


TUI_COMMANDS: list[SlashCmd] = [
    SlashCmd("/new", "conversa"),
    SlashCmd("/reset", "conversa"),
    SlashCmd("/compact", "conversa"),
    SlashCmd("/clear", "conversa"),
    SlashCmd("/model", "modos", takes_arg=True),
    SlashCmd("/language", "modos", takes_arg=True),
    SlashCmd("/incognito", "modos"),
    SlashCmd("/websearch", "modos"),
    SlashCmd("/think", "modos"),
    SlashCmd("/memory", "dados"),
    SlashCmd("/tasks", "dados"),
    SlashCmd("/task", "dados", takes_arg=True),
    SlashCmd("/status", "sistema"),
    SlashCmd("/config", "sistema"),
    SlashCmd("/web", "sistema"),
    SlashCmd("/help", "sistema"),
    SlashCmd("/exit", "sistema"),
    SlashCmd("/quit", "sistema"),
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
