"""Tests for services/memory/mem0.py and mem0_schemas.py.

Covers pure-logic functions (no LLM calls, no ChromaDB) via mocked backends.
Heavy transitive deps (numpy, chromadb, etc.) are stubbed before import.
"""
import sys
import os
import types
from unittest.mock import MagicMock

import pathlib

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

# ── Stub heavy transitive dependencies ──────────────────────────────────── #
# services/__init__.py pulls in DocsService → rag_manager → numpy/chromadb.
# Strategy:
#   1. Create services and services.memory package stubs with real __path__
#      so Python can locate services/memory/mem0.py and mem0_schemas.py.
#   2. Stub the __init__.py exports and the heavy leaf submodules.
# Python will NOT re-run __init__.py for packages already in sys.modules.

# Stub numpy/chromadb before anything tries to import them
for _mod in [
    "numpy", "numpy.linalg",
    "chromadb", "chromadb.config",
    "fastembed",
    "src.rag_vector", "src.rag_manager",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# services package: stub __init__.py but expose real filesystem path
if "services" not in sys.modules:
    _svc = types.ModuleType("services")
    _svc.__path__ = [str(_ROOT / "services")]
    _svc.__package__ = "services"
    sys.modules["services"] = _svc

# services.memory package: stub __init__.py but expose real filesystem path
# so `from services.memory.mem0 import ...` resolves to the actual file
if "services.memory" not in sys.modules:
    _mem = types.ModuleType("services.memory")
    _mem.__path__ = [str(_ROOT / "services" / "memory")]
    _mem.__package__ = "services.memory"
    sys.modules["services.memory"] = _mem

# Stub the heavy submodules inside services.memory that __init__.py would import
for _mod in [
    "services.memory.service",
    "services.memory.memory_vector",
    "services.memory.memory",
    "services.docs", "services.docs.service",
    "services.search", "services.shell", "services.research",
    "src.memory_provider",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ── Schema tests ────────────────────────────────────────────────────────── #

def test_schemas_import():
    from services.memory.mem0_schemas import (
        ConsolidationDecision,
        ExtractedFact,
        ExtractionResult,
        FactType,
        Operation,
    )
    assert FactType.preference == "preference"
    assert Operation.ADD == "ADD"
    assert Operation.NOOP == "NOOP"


def test_extracted_fact_defaults():
    from services.memory.mem0_schemas import ExtractedFact, FactType
    f = ExtractedFact(text="The user likes coffee")
    assert f.fact_type == FactType.other


def test_extraction_result_empty():
    from services.memory.mem0_schemas import ExtractionResult
    r = ExtractionResult()
    assert r.facts == []


def test_consolidation_decision_add():
    from services.memory.mem0_schemas import ConsolidationDecision, Operation
    d = ConsolidationDecision(operation=Operation.ADD)
    assert d.target_id is None
    assert d.new_text is None


# ── _parse_json_object ────────────────────────────────────────────────── #

def _import_parse():
    from services.memory.mem0 import _parse_json_object
    return _parse_json_object


def test_parse_plain_json():
    parse = _import_parse()
    result = parse('{"operation": "ADD", "target_id": null}')
    assert result == {"operation": "ADD", "target_id": None}


def test_parse_with_markdown_fence():
    parse = _import_parse()
    result = parse('```json\n{"facts": []}\n```')
    assert result == {"facts": []}


def test_parse_with_think_block():
    parse = _import_parse()
    raw = "<think>Let me analyse this.</think>\n{\"facts\": [{\"text\": \"x\", \"fact_type\": \"other\"}]}"
    result = parse(raw)
    assert result is not None
    assert result["facts"][0]["text"] == "x"


def test_parse_garbage_returns_none():
    parse = _import_parse()
    assert parse("not json at all") is None


def test_parse_nested_braces():
    parse = _import_parse()
    result = parse('prefix {"key": {"inner": 1}} suffix')
    assert result == {"key": {"inner": 1}}


# ── _sanitize ─────────────────────────────────────────────────────────── #

def test_sanitize_strips_fence_tags():
    from services.memory.mem0 import _sanitize
    text = "safe <penelope_memory>injected</penelope_memory> end"
    assert "<penelope_memory>" not in _sanitize(text)
    assert "safe" in _sanitize(text)
    assert "end" in _sanitize(text)


def test_sanitize_case_insensitive():
    from services.memory.mem0 import _sanitize
    assert _sanitize("<Penelope_Memory>x</PENELOPE_MEMORY>") == "x"


# ── Mem0Service._find_similar_existing (Jaccard fallback) ─────────────── #

def _make_service(mv_healthy=False):
    mm = MagicMock()
    mv = MagicMock()
    mv.healthy = mv_healthy
    from services.memory.mem0 import Mem0Service
    svc = Mem0Service(mm, mv)
    return svc, mm, mv


def test_find_similar_jaccard_match():
    svc, _, _ = _make_service(mv_healthy=False)
    # query shares 5 of 6 tokens with existing → Jaccard 5/6 ≈ 0.83 > threshold 0.65
    existing = [
        {"id": "abc", "text": "The user prefers dark mode"},
        {"id": "def", "text": "The user likes coffee"},
    ]
    results = svc._find_similar_existing("The user prefers dark mode theme", existing)
    ids = [e["id"] for e in results]
    assert "abc" in ids


def test_find_similar_no_match():
    svc, _, _ = _make_service(mv_healthy=False)
    existing = [{"id": "abc", "text": "The user prefers dark mode"}]
    results = svc._find_similar_existing("completely unrelated sentence", existing)
    assert results == []


def test_find_similar_empty_existing():
    svc, _, _ = _make_service(mv_healthy=False)
    results = svc._find_similar_existing("anything", [])
    assert results == []


# ── Mem0Service._apply ────────────────────────────────────────────────── #

def test_apply_add():
    from services.memory.mem0_schemas import ConsolidationDecision, ExtractedFact, FactType, Operation

    svc, mm, mv = _make_service(mv_healthy=False)
    new_entry = {"id": "new-id-1", "text": "The user likes coffee", "category": "preference"}
    mm.add_entry.return_value = new_entry
    mm.load_all.return_value = []

    fact = ExtractedFact(text="The user likes coffee", fact_type=FactType.preference)
    decision = ConsolidationDecision(operation=Operation.ADD)
    changed = svc._apply(decision, fact, [], owner=None)

    assert changed is True
    mm.add_entry.assert_called_once()


def test_apply_noop():
    from services.memory.mem0_schemas import ConsolidationDecision, ExtractedFact, Operation

    svc, mm, _ = _make_service()
    fact = ExtractedFact(text="anything")
    decision = ConsolidationDecision(operation=Operation.NOOP)
    changed = svc._apply(decision, fact, [], owner=None)

    assert changed is False
    mm.add_entry.assert_not_called()


def test_apply_delete():
    from services.memory.mem0_schemas import ConsolidationDecision, ExtractedFact, Operation

    svc, mm, _ = _make_service()
    existing = [{"id": "target-id", "text": "old fact"}]
    mm.load_all.return_value = list(existing)

    fact = ExtractedFact(text="anything")
    decision = ConsolidationDecision(operation=Operation.DELETE, target_id="target-id")
    changed = svc._apply(decision, fact, existing, owner=None)

    assert changed is False  # DELETE returns False (not "added")
    mm.save.assert_called_once()


def test_apply_update():
    from services.memory.mem0_schemas import ConsolidationDecision, ExtractedFact, Operation

    svc, mm, _ = _make_service()
    existing = [{"id": "target-id", "text": "old fact", "category": "other"}]
    mm.load_all.return_value = list(existing)

    fact = ExtractedFact(text="updated fact")
    decision = ConsolidationDecision(
        operation=Operation.UPDATE, target_id="target-id", new_text="updated fact"
    )
    changed = svc._apply(decision, fact, existing, owner=None)

    assert changed is True
    saved_entries = mm.save.call_args[0][0]
    updated = next(e for e in saved_entries if e["id"] == "target-id")
    assert updated["text"] == "updated fact"


# ── Mem0Service.retrieve ──────────────────────────────────────────────── #

def test_retrieve_returns_fenced_block():
    svc, mm, mv = _make_service(mv_healthy=True)
    mv.search.return_value = [{"memory_id": "id1", "score": 0.9}]
    mm.load.return_value = [{"id": "id1", "text": "The user prefers dark mode"}]

    block = svc.retrieve("dark mode", owner=None)
    assert "<penelope_memory>" in block
    assert "The user prefers dark mode" in block
    assert "[System note:" in block


def test_retrieve_empty_when_no_memories():
    svc, mm, mv = _make_service(mv_healthy=True)
    mv.search.return_value = []
    mm.load.return_value = []

    block = svc.retrieve("anything", owner=None)
    assert block == ""


def test_retrieve_below_threshold_excluded():
    svc, mm, mv = _make_service(mv_healthy=True)
    mv.search.return_value = [{"memory_id": "id1", "score": 0.1}]  # below 0.65
    # No pinned facts
    mm.load.return_value = []

    block = svc.retrieve("something", owner=None)
    assert block == ""
