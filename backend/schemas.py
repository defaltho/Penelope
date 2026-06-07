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


# --- Pipeline de estruturação (Stage 3) ---

class TransactionExtraction(BaseModel):
    """Transação estruturada extraída de texto ou imagem.

    Contrato anti-alucinação: campos ausentes vêm a null. Confiar em
    números/datas/totais; comerciante/categoria são menos fiáveis e devem ir em
    `low_confidence_fields` para confirmação do utilizador.
    """
    date: str | None = Field(default=None, description="Data ISO YYYY-MM-DD, ou null.")
    amount: float | None = Field(default=None, description="Valor total, ou null.")
    currency: str | None = Field(default=None, description="Código ISO da moeda (EUR, USD...), ou null.")
    merchant: str | None = Field(default=None, description="Comerciante/origem, ou null.")
    category: str | None = Field(default=None, description="Categoria (ex.: alimentação), ou null.")
    account: str | None = Field(default=None, description="Conta/método, ou null.")
    notes: str | None = Field(default=None, description="Notas, ou null.")
    confidence: float = Field(default=0.0, description="Confiança global 0.0 a 1.0.")
    low_confidence_fields: list[str] = Field(
        default_factory=list, description="Campos a confirmar pelo utilizador."
    )


class PipelineExtractRequest(BaseModel):
    text: str = ""
    image_base64: str | None = None


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


class ConversationOut(BaseModel):
    id: int
    created_at: str


class FactOut(BaseModel):
    id: int
    text: str
    fact_type: str
    updated_at: str
