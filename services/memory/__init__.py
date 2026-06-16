# services/memory/__init__.py
"""Memory service — persistent memory storage and retrieval."""

from .service import MemoryService, Memory, MemorySearchResult
from .memory import MemoryManager
from .memory_vector import MemoryVectorStore
from .mem0 import Mem0Service
from .mem0_schemas import FactType, ExtractedFact, ConsolidationDecision, Operation

__all__ = [
    "MemoryService",
    "Memory",
    "MemorySearchResult",
    "MemoryManager",
    "MemoryVectorStore",
    "Mem0Service",
    "FactType",
    "ExtractedFact",
    "ConsolidationDecision",
    "Operation",
]
