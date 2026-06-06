"""Teste de integração isolado da consolidação de memória (Camada A).

Exercita ADD/UPDATE/DELETE/NOOP contra um SQLite temporário, usando o Ollama real
(embeddinggemma + qwen3-vl para as decisões). É lento por design: valida o
comportamento real, não mocks.

Invariante CRÍTICA verificada após cada passo: o nº de factos ativos
(semantic_facts.is_deleted=0) é igual ao nº de linhas em fact_vectors. Se divergir,
as tabelas base e vetorial saíram de sincronia (o bug mais comum).

Correr:  uv run pytest test_consolidation.py -v -s
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import db as dbmod
from config import settings
from memory import MemoryService
from schemas import ExtractedFact, FactType, Operation

pytestmark = pytest.mark.asyncio


def _counts(conn) -> tuple[int, int]:
    facts = conn.execute("SELECT COUNT(*) FROM semantic_facts WHERE is_deleted = 0").fetchone()[0]
    vecs = conn.execute("SELECT COUNT(*) FROM fact_vectors").fetchone()[0]
    return facts, vecs


def _active_texts(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT text FROM semantic_facts WHERE is_deleted = 0"
    ).fetchall()]


@pytest.fixture
def mem():
    tmp = tempfile.mktemp(suffix=".db")
    conn = dbmod.connect(tmp)
    dbmod.init_schema(conn)
    yield MemoryService(conn, settings)
    conn.close()
    Path(tmp).unlink(missing_ok=True)


async def _consolidate_one(mem: MemoryService, text: str, ftype: FactType = FactType.financial):
    return await mem.consolidate([ExtractedFact(text=text, fact_type=ftype)], source_turn=None)


async def test_lockstep_invariant_holds_through_scenario(mem: MemoryService):
    conn = mem.conn

    # Passo 1: facto novo -> ADD
    d1 = await _consolidate_one(mem, "O salário do utilizador é pago no dia 25")
    print("passo 1:", d1[0].operation)
    f, v = _counts(conn)
    assert (f, v) == (1, 1), f"esperado 1 facto/1 vetor, obtido {f}/{v}"
    assert d1[0].operation == Operation.ADD

    # Passo 2: mesmo atributo, valor novo -> UPDATE (ou NOOP+ADD não permitido: nunca 2 factos do mesmo)
    d2 = await _consolidate_one(mem, "O salário do utilizador é pago no dia 28")
    print("passo 2:", d2[0].operation, "| factos:", _active_texts(conn))
    f, v = _counts(conn)
    assert f == v, f"lockstep quebrado: {f} factos vs {v} vetores"
    assert f == 1, f"não deve haver factos de salário em conflito, obtido {f}: {_active_texts(conn)}"
    assert "28" in " ".join(_active_texts(conn)), "o facto deve refletir o dia 28"

    # Passo 3: duplicado semântico -> NOOP
    d3 = await _consolidate_one(mem, "O utilizador recebe no dia 28")
    print("passo 3:", d3[0].operation, "| factos:", _active_texts(conn))
    f, v = _counts(conn)
    assert f == v, f"lockstep quebrado: {f} vs {v}"
    assert f == 1, f"duplicado não devia criar facto novo, obtido {f}: {_active_texts(conn)}"

    # Passo 4: contradição que invalida -> DELETE (->0) ou UPDATE (->1); nunca acumular
    d4 = await _consolidate_one(mem, "O utilizador já não recebe salário, é freelancer")
    print("passo 4:", d4[0].operation, "| factos:", _active_texts(conn))
    f, v = _counts(conn)
    assert f == v, f"lockstep quebrado: {f} vs {v}"
    assert f <= 1, f"contradição não devia acumular factos, obtido {f}: {_active_texts(conn)}"


async def test_add_then_unrelated_add(mem: MemoryService):
    conn = mem.conn
    await _consolidate_one(mem, "O utilizador fala português em casa", FactType.language)
    await _consolidate_one(mem, "O utilizador prefere despesas categorizadas por comerciante", FactType.preference)
    f, v = _counts(conn)
    assert (f, v) == (2, 2), f"dois factos não relacionados deviam coexistir, obtido {f}/{v}"
