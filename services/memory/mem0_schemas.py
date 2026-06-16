# services/memory/mem0_schemas.py
"""Pydantic schemas para o sistema Mem0 (extracção + consolidação de factos)."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class FactType(str, Enum):
    preference = "preference"
    profile = "profile"
    financial = "financial"
    language = "language"
    other = "other"


class ExtractedFact(BaseModel):
    text: str
    fact_type: FactType = FactType.other


class ExtractionResult(BaseModel):
    facts: List[ExtractedFact] = []


class Operation(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class ConsolidationDecision(BaseModel):
    operation: Operation
    target_id: Optional[str] = None  # ID da memória existente (string, como no MemoryManager)
    new_text: Optional[str] = None   # Novo texto para UPDATE
