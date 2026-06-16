"""Lightweight i18n for the Penelope CLI.

Two languages: English ("en", default) and Portuguese ("pt"). The choice is
persisted in ~/.penelope/lang and switched at runtime with the /language command.

Usage:
    from cli.i18n import t, set_language
    t("new.started")
    t("model.changed", m="qwen3-vl:8b")
"""
from __future__ import annotations

from pathlib import Path

LANGUAGES = ("en", "pt")
_DEFAULT = "en"
_lang = _DEFAULT


def _lang_file() -> Path:
    d = Path.home() / ".penelope"
    d.mkdir(exist_ok=True)
    return d / "lang"


def load_language() -> str:
    global _lang
    try:
        val = _lang_file().read_text(encoding="utf-8").strip().lower()
        if val in LANGUAGES:
            _lang = val
    except Exception:
        pass
    return _lang


def set_language(lang: str) -> bool:
    global _lang
    lang = (lang or "").strip().lower()
    if lang not in LANGUAGES:
        return False
    _lang = lang
    try:
        _lang_file().write_text(lang, encoding="utf-8")
    except Exception:
        pass
    return True


def get_language() -> str:
    return _lang


def language_name(lang: str | None = None) -> str:
    return t(f"lang.{lang or _lang}")


def t(key: str, **kw) -> str:
    entry = _MESSAGES.get(key)
    if entry is None:
        return key
    s = entry.get(_lang) or entry.get(_DEFAULT) or key
    return s.format(**kw) if kw else s


def capabilities() -> list[tuple[str, str]]:
    """The banner capability list (name, description) in the current language."""
    return [(t(f"cap.{k}.name"), t(f"cap.{k}.desc"))
            for k in ("memory", "vision", "pipeline", "skills", "gallery", "web")]


def status_text(kind: str) -> str:
    return t(f"status_text.{kind}") if f"status_text.{kind}" in _MESSAGES else t("status_text.thinking")


# en, pt for every user-facing string in the CLI.
_MESSAGES: dict[str, dict[str, str]] = {
    # — branding / banner —
    "tagline": {"en": "local assistant", "pt": "assistente local"},
    "banner.capabilities": {"en": "Capabilities", "pt": "Capacidades"},
    "banner.skills": {"en": "Active skills", "pt": "Skills activas"},
    "banner.skills_none": {"en": "none active", "pt": "nenhuma activa"},
    "banner.count_caps": {"en": "{n} capabilities", "pt": "{n} capacidades"},
    "banner.count_skills": {"en": "{n} skills", "pt": "{n} skills"},
    "banner.help_suffix": {"en": "for commands", "pt": "para comandos"},
    "banner.model": {"en": "model:", "pt": "modelo:"},
    "banner.session": {"en": "session:", "pt": "sessão:"},
    "hint.send": {"en": "send", "pt": "enviar"},
    "hint.newline": {"en": "new line", "pt": "nova linha"},
    "hint.commands": {"en": "commands", "pt": "comandos"},

    # — capabilities (banner) —
    "cap.memory.name": {"en": "memory", "pt": "memória"},
    "cap.memory.desc": {"en": "semantic facts + FTS5 history", "pt": "factos semânticos + histórico FTS5"},
    "cap.vision.name": {"en": "vision", "pt": "visão"},
    "cap.vision.desc": {"en": "OCR and image description (qwen3-vl)", "pt": "OCR e descrição de imagens (qwen3-vl)"},
    "cap.pipeline.name": {"en": "pipeline", "pt": "pipeline"},
    "cap.pipeline.desc": {"en": "text and image → JSON", "pt": "texto e imagem → JSON"},
    "cap.skills.name": {"en": "skills", "pt": "skills"},
    "cap.skills.desc": {"en": "lightweight instructions in the prompt", "pt": "instruções leves injetadas no prompt"},
    "cap.gallery.name": {"en": "gallery", "pt": "galeria"},
    "cap.gallery.desc": {"en": "images saved per conversation", "pt": "imagens guardadas por conversa"},
    "cap.web.name": {"en": "web", "pt": "web"},
    "cap.web.desc": {"en": "full interface in the browser", "pt": "interface completa no browser"},

    # — spinner / activity —
    "status_text.thinking": {"en": "thinking…", "pt": "a pensar…"},
    "status_text.web": {"en": "searching the web…", "pt": "a pesquisar na web…"},
    "status_text.memory": {"en": "retrieving memory…", "pt": "a recuperar memória…"},
    "status_text.compacting": {"en": "compacting…", "pt": "a compactar…"},

    # — status bar health —
    "health.thinking": {"en": "thinking", "pt": "a pensar"},
    "health.online": {"en": "online", "pt": "online"},
    "health.offline": {"en": "offline", "pt": "offline"},
    "health.unknown": {"en": "unknown", "pt": "unknown"},
    "flag.incognito": {"en": "incognito", "pt": "incógnito"},
    "flag.web": {"en": "web", "pt": "web"},

    # — conversation labels —
    "conv.new": {"en": "new conversation", "pt": "nova conversa"},
    "conv.n": {"en": "conversation #{id}", "pt": "conversa #{id}"},

    # — misc —
    "goodbye": {"en": "see you", "pt": "até já"},
    "interrupted": {"en": "interrupted", "pt": "interrompido"},
    "reasoning": {"en": "reasoning", "pt": "raciocínio"},

    # — help —
    "help.title": {"en": "commands", "pt": "comandos"},
    "group.conversa": {"en": "conversation", "pt": "conversa"},
    "group.modos": {"en": "modes", "pt": "modos"},
    "group.dados": {"en": "data & memory", "pt": "dados & memória"},
    "group.sistema": {"en": "system", "pt": "sistema"},

    # — backend hint —
    "hint.backend.notup": {"en": "the backend is not responding yet at",
                            "pt": "o backend ainda não responde em"},
    "hint.backend.web": {"en": "type {cmd} to start Ollama, the backend and the interface",
                          "pt": "escreve {cmd} para arrancar o Ollama, o backend e a interface"},
    "hint.backend.alt": {"en": "or separately: {cmd}", "pt": "ou, à parte: {cmd}"},

    # — command descriptions —
    "cmd./new": {"en": "Start a new conversation (fresh session + history).",
                 "pt": "Começa uma conversa nova (sessão e histórico limpos)."},
    "cmd./reset": {"en": "Start a new conversation (alias of /new).",
                   "pt": "Começa uma conversa nova (alias de /new)."},
    "cmd./compact": {"en": "Summarize and compact the conversation context.",
                     "pt": "Resume e compacta o contexto da conversa."},
    "cmd./clear": {"en": "Clear the screen and redraw the banner.",
                   "pt": "Limpa o ecrã e redesenha o banner."},
    "cmd./model": {"en": "Show or change the model (usage: /model [name]).",
                   "pt": "Mostra ou troca o modelo (uso: /model [nome])."},
    "cmd./language": {"en": "Switch language: English or Portuguese (usage: /language [en|pt]).",
                      "pt": "Troca o idioma: inglês ou português (uso: /language [en|pt])."},
    "cmd./incognito": {"en": "Toggle incognito mode (no memory writes).",
                       "pt": "Alterna o modo anónimo (sem escrever na memória)."},
    "cmd./websearch": {"en": "Toggle web search.", "pt": "Alterna a pesquisa na web."},
    "cmd./think": {"en": "Show or hide the model's reasoning.",
                   "pt": "Mostra ou esconde o raciocínio do modelo."},
    "cmd./memory": {"en": "List the facts stored in memory.",
                    "pt": "Lista os factos guardados na memória."},
    "cmd./tasks": {"en": "List the tasks.", "pt": "Lista as tarefas."},
    "cmd./task": {"en": "Add a task (usage: /task <text>).",
                  "pt": "Adiciona uma tarefa (uso: /task <texto>)."},
    "cmd./status": {"en": "Show backend and model status.",
                    "pt": "Mostra o estado do backend e dos modelos."},
    "cmd./config": {"en": "Show current settings.", "pt": "Mostra as definições actuais."},
    "cmd./web": {"en": "Open the full web interface in the browser.",
                 "pt": "Abre a interface web completa no browser."},
    "cmd./help": {"en": "Show help with all commands.", "pt": "Mostra a ajuda com todos os comandos."},
    "cmd./exit": {"en": "Exit Penelope.", "pt": "Sai da Penelope."},
    "cmd./quit": {"en": "Exit Penelope (alias of /exit).", "pt": "Sai da Penelope (alias de /exit)."},

    # — command outputs —
    "new.started": {"en": "New conversation started.", "pt": "Nova conversa iniciada."},
    "compact.noconv": {"en": "No active conversation to compact.",
                       "pt": "Nenhuma conversa activa para compactar."},
    "compact.done": {"en": "Conversation compacted.", "pt": "Conversa compactada."},
    "compact.fail": {"en": "Failed to compact: {e}", "pt": "Falha ao compactar: {e}"},
    "model.current": {"en": "Current model", "pt": "Modelo actual"},
    "model.available": {"en": "Available", "pt": "Disponíveis"},
    "model.changed": {"en": "Model changed to {m}", "pt": "Modelo alterado para {m}"},
    "incognito.label": {"en": "Incognito mode", "pt": "Modo anónimo"},
    "incognito.on": {"en": "enabled", "pt": "activado"},
    "incognito.off": {"en": "disabled", "pt": "desactivado"},
    "websearch.label": {"en": "Web search", "pt": "Pesquisa web"},
    "websearch.on": {"en": "enabled", "pt": "activada"},
    "websearch.off": {"en": "disabled", "pt": "desactivada"},
    "think.label": {"en": "Reasoning", "pt": "Raciocínio"},
    "think.on": {"en": "visible", "pt": "visível"},
    "think.off": {"en": "hidden", "pt": "escondido"},
    "task.usage": {"en": "Usage: /task <task text>", "pt": "Uso: /task <texto da tarefa>"},
    "task.created": {"en": "Task created: {t}", "pt": "Tarefa criada: {t}"},
    "task.fail": {"en": "Failed to create task: {e}", "pt": "Falha ao criar tarefa: {e}"},
    "memory.label": {"en": "Memory", "pt": "Memória"},
    "memory.empty": {"en": "empty", "pt": "vazia"},
    "memory.fail": {"en": "Failed to list memory: {e}", "pt": "Falha ao listar memória: {e}"},
    "memory.col.fact": {"en": "Fact", "pt": "Facto"},
    "tasks.label": {"en": "Tasks", "pt": "Tarefas"},
    "tasks.none": {"en": "none", "pt": "nenhuma"},
    "tasks.col.text": {"en": "Text", "pt": "Texto"},
    "tasks.fail": {"en": "Failed to list tasks: {e}", "pt": "Falha ao listar tarefas: {e}"},
    "status.online": {"en": "Backend online", "pt": "Backend online"},
    "status.chat_model": {"en": "Chat model", "pt": "Chat model"},
    "status.embed_model": {"en": "Embed model", "pt": "Embed model"},
    "status.models_installed": {"en": "Installed models", "pt": "Modelos instalados"},
    "status.none": {"en": "none", "pt": "nenhum"},
    "status.fail": {"en": "Backend not reachable: {e}", "pt": "Backend não acessível: {e}"},
    "config.fail": {"en": "Failed to read settings: {e}", "pt": "Falha ao ler definições: {e}"},
    "unknown.cmd": {"en": "Unknown command: {cmd}", "pt": "Comando desconhecido: {cmd}"},

    # — language command —
    "language.current": {"en": "Current language: {lang}", "pt": "Idioma actual: {lang}"},
    "language.changed": {"en": "Language changed to {lang}", "pt": "Idioma alterado para {lang}"},
    "language.invalid": {"en": "Use: /language en  or  /language pt",
                         "pt": "Usa: /language en  ou  /language pt"},
    "language.hint": {"en": "(reopen with /clear to redraw the banner)",
                      "pt": "(reabre com /clear para redesenhar o banner)"},
    "lang.en": {"en": "English", "pt": "Inglês"},
    "lang.pt": {"en": "Portuguese", "pt": "Português"},

    # — agent approval —
    "approval.header": {"en": "Agent wants to execute", "pt": "Agent quer executar"},
    "approval.prompt": {"en": "Decision", "pt": "Decisão"},
    "approval.hint": {"en": "(enter=deny)", "pt": "(enter=negar)"},
    "approval.allow_once": {"en": "Once", "pt": "Uma vez"},
    "approval.allow_session": {"en": "Session", "pt": "Sessão"},
    "approval.allow_always": {"en": "Always", "pt": "Sempre"},
    "approval.deny": {"en": "Deny", "pt": "Negar"},

    # — /web server flow —
    "web.uv_missing": {"en": "'uv' not found in PATH. Run 'bin\\setup.cmd' first.",
                       "pt": "'uv' não encontrado no PATH. Corre 'bin\\setup.cmd' primeiro."},
    "web.npm_missing": {"en": "'npm' not found in PATH. Install Node.js first.",
                        "pt": "'npm' não encontrado no PATH. Instala o Node.js primeiro."},
    "web.ollama.label": {"en": "Ollama", "pt": "Ollama"},
    "web.running": {"en": "already running", "pt": "já está a correr"},
    "web.starting": {"en": "starting…", "pt": "a iniciar…"},
    "web.ollama.missing": {"en": "'ollama' not found. Install from https://ollama.com",
                           "pt": "'ollama' não encontrado. Instala a partir de https://ollama.com"},
    "web.backend.label": {"en": "Backend", "pt": "Backend"},
    "web.backend.running": {"en": "already running on port {p}", "pt": "já está a correr na porta {p}"},
    "web.backend.starting": {"en": "starting on port {p}…", "pt": "a iniciar na porta {p}…"},
    "web.frontend.label": {"en": "Frontend", "pt": "Frontend"},
    "web.frontend.installing": {"en": "installing dependencies (first time)…",
                                "pt": "a instalar dependências (primeira vez)…"},
    "web.frontend.starting": {"en": "starting on port {p}…", "pt": "a iniciar na porta {p}…"},
    "web.ready": {"en": "Web interface ready → {url}", "pt": "Interface web pronta → {url}"},
    "web.url.label": {"en": "URL", "pt": "URL"},
    "web.url.manual": {"en": "open manually: {url}", "pt": "abre manualmente: {url}"},
    "web.label": {"en": "Web", "pt": "Web"},
    "web.all_running": {"en": "all services were already running — browser opened",
                        "pt": "todos os serviços já estavam a correr — browser aberto"},
    "web.running_hint": {"en": "running. Ctrl+C to stop and return to the terminal.",
                         "pt": "a correr. Ctrl+C para parar e voltar ao terminal."},
    "web.service_died": {"en": "A service stopped unexpectedly.",
                         "pt": "Um dos serviços parou inesperadamente."},
    "web.shutting": {"en": "shutting down…", "pt": "a desligar…"},
    "web.stopped": {"en": "Web servers stopped.", "pt": "Servidores web parados."},
    "web.ollama.bg": {"en": "started by /web — still running in the background",
                      "pt": "iniciado por /web — ainda a correr em background"},
}
