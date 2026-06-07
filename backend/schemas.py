"""Modelos Pydantic do Penelope.

Os schemas de extração e consolidação são passados ao Ollama via `format=` (structured
outputs). Validar a resposta = construir o modelo a partir do JSON; erros são apanhados
e tratados como NOOP no memory.py.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# --- Extração de factos (Camada A, passo 1) ---

class FactType(str, Enum):
    preference = "preference"
    profile = "profile"
    financial = "financial"
    language = "language"
    other = "other"


class ExtractedFact(BaseModel):
    text: str = Field(description="Facto durável sobre o utilizador, frase curta e autónoma.")
    fact_type: FactType = FactType.other


class ExtractionResult(BaseModel):
    """Resultado da extração. .model_json_schema() -> format= do Ollama."""
    facts: list[ExtractedFact] = Field(default_factory=list)


# --- Auto-aprendizagem de skills ---

class SkillSuggestion(BaseModel):
    name: str = Field(description="Nome curto da skill (ex.: 'Tom formal').")
    instruction: str = Field(description="Instrução reutilizável a seguir sempre.")


class SkillExtraction(BaseModel):
    skills: list[SkillSuggestion] = Field(default_factory=list)


# --- Agents (loop simples com ferramentas locais) ---

class AgentStep(BaseModel):
    thought: str = Field(default="", description="Raciocínio curto sobre o próximo passo.")
    tool: str | None = Field(default=None, description="Ferramenta a usar, ou null se terminou.")
    args: dict = Field(default_factory=dict, description="Argumentos da ferramenta.")
    final: str | None = Field(default=None, description="Resposta final ao utilizador (quando terminado).")


class AgentRunRequest(BaseModel):
    task: str


# --- Aventura (/aidungeon, estilo AI Dungeon) ---

class AdventureCreate(BaseModel):
    title: str = Field(default="", description="Título da aventura.")
    scenario: str = Field(default="", description="Premissa/mundo (Quick Start).")
    instructions: str = Field(default="", description="AI Instructions extra (opcional).")


class AdventureMode(str, Enum):
    do = "do"               # ação da personagem
    say = "say"             # fala da personagem
    story = "story"         # narração escrita pelo jogador
    continue_ = "continue"  # o MJ avança sem novo input


class AdventureTurn(BaseModel):
    input: str = Field(default="", description="Texto do jogador (vazio em modo continue).")
    mode: AdventureMode = AdventureMode.do


class AdventurePatch(BaseModel):
    """Edições de contexto/turnos (undo, edit, memory, author's note, story cards)."""
    title: str | None = None
    scenario: str | None = None
    instructions: str | None = None
    memory: str | None = None
    authors_note: str | None = None
    story_cards: list[dict] | None = None
    turns: list[dict] | None = None


# --- Consolidação (Camada A, passo 2) ---

class Operation(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class ConsolidationDecision(BaseModel):
    """Decisão para um facto candidato face aos factos existentes semelhantes."""
    operation: Operation
    target_id: int | None = Field(
        default=None, description="ID do facto existente a alterar/apagar (UPDATE/DELETE)."
    )
    new_text: str | None = Field(
        default=None, description="Novo texto do facto (apenas UPDATE)."
    )


# --- API HTTP ---

class ChatRequest(BaseModel):
    conversation_id: int | None = None
    message: str = ""
    image_base64: str | None = Field(
        default=None,
        description="Imagem opcional (data URL ou base64 cru) para chat multimodal/visão.",
    )
    model: str | None = Field(default=None, description="Modelo a usar; default = definições.")
    incognito: bool = Field(default=False, description="Modo anónimo: nada é guardado nem memorizado.")
    web_search: bool = Field(default=False, description="Pesquisa na web antes de responder (requer internet).")
    system_override: str | None = Field(
        default=None,
        description="System prompt base alternativo (ex.: modo /aidungeon). Memória/skills continuam a poder ser injetadas.",
    )


class ConversationOut(BaseModel):
    id: int
    created_at: str


class FactOut(BaseModel):
    id: int
    text: str
    fact_type: str
    updated_at: str
