"""Serviço de memória estilo Mem0 (extract -> consolidate -> retrieve).

Duas camadas, um único ficheiro SQLite:
  - Camada A (semantic_facts + fact_vectors): factos duráveis sobre o utilizador,
    consolidados com ADD/UPDATE/DELETE/NOOP para evitar duplicados e contradições.
  - Camada B (turns + turn_vectors): cada turno embebido para recuperação semântica.

Esta é a parte mais subtil do projeto. As tabelas base e as tabelas vec0 são
mantidas em lockstep manualmente (os embeddings vêm de chamadas async ao Ollama,
logo não podem ser triggers SQL).
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3

import sqlite_vec
from pydantic import ValidationError

import ollama_client as oc
from config import Settings
from schemas import (
    ConsolidationDecision,
    ExtractedFact,
    ExtractionResult,
    Operation,
)

log = logging.getLogger("penelope.memory")


_EXTRACT_SYSTEM = (
    "És um extrator de memória. A partir da troca entre o utilizador e o assistente, "
    "extrai APENAS factos ou preferências DURÁVEIS sobre o utilizador que sejam úteis "
    "em conversas futuras (ex.: preferências, dados de perfil, hábitos financeiros, "
    "idioma). Ignora conteúdo efémero, perguntas, ou factos sobre o mundo. "
    "Reformula cada facto como uma frase curta e autónoma, na 3ª pessoa "
    "(ex.: 'O salário do utilizador é pago no dia 25'). "
    "Se não houver nada durável, devolve uma lista vazia."
)

_CONSOLIDATE_SYSTEM = (
    "És um gestor de memória. Recebes um FACTO CANDIDATO novo e uma lista de FACTOS "
    "EXISTENTES semelhantes (com id). Decide UMA operação:\n"
    "- ADD: o candidato é genuinamente novo, sem sobreposição com os existentes.\n"
    "- UPDATE: o candidato refere o MESMO atributo do MESMO sujeito que um existente, "
    "mas com informação nova/mais específica que o substitui. Devolve target_id e new_text.\n"
    "- DELETE: o candidato contradiz e invalida um existente, sem substituto. Devolve target_id.\n"
    "- NOOP: o candidato já é conhecido (duplicado ou quase-duplicado) ou não é durável.\n"
    "Prefere UPDATE a ADD quando é o mesmo atributo do mesmo sujeito. "
    "Prefere NOOP a ADD para quase-duplicados."
)


def _serialize(vec: list[float]) -> bytes:
    return sqlite_vec.serialize_float32(vec)


class MemoryService:
    def __init__(self, conn: sqlite3.Connection, cfg: Settings):
        self.conn = conn
        self.cfg = cfg
        self._write_lock = asyncio.Lock()

    # ---------- KNN helpers ----------

    def _knn_facts(self, query_vec: list[float], k: int) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT f.id, f.text, f.fact_type, v.distance
            FROM (
                SELECT fact_id, distance FROM fact_vectors
                WHERE embedding MATCH ? AND k = ?
                ORDER BY distance
            ) v
            JOIN semantic_facts f ON f.id = v.fact_id
            WHERE f.is_deleted = 0
            ORDER BY v.distance
            """,
            (_serialize(query_vec), k),
        ).fetchall()
        return rows

    def _knn_turns(self, query_vec: list[float], k: int) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT t.turn_id, t.text, v.distance
            FROM (
                SELECT turn_id, distance FROM turn_vectors
                WHERE embedding MATCH ? AND k = ?
                ORDER BY distance
            ) v
            JOIN turns t ON t.turn_id = v.turn_id
            ORDER BY v.distance
            """,
            (_serialize(query_vec), k),
        ).fetchall()
        return rows

    # ---------- Camada B: armazenar turno ----------

    async def store_turn(self, conversation_id: int, user_text: str, assistant_text: str) -> int:
        text = f"User: {user_text}\nAssistant: {assistant_text}"
        vec = await oc.embed(text, kind="document")
        async with self._write_lock:
            cur = self.conn.execute(
                "INSERT INTO turns (conversation_id, text) VALUES (?, ?)",
                (conversation_id, text),
            )
            turn_id = cur.lastrowid
            self.conn.execute(
                "INSERT INTO turn_vectors (turn_id, embedding) VALUES (?, ?)",
                (turn_id, _serialize(vec)),
            )
            self.conn.commit()
        return turn_id

    # ---------- Camada A, passo 1: extração ----------

    async def extract(self, user_text: str, assistant_text: str) -> list[ExtractedFact]:
        messages = [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Utilizador: {user_text}\nAssistente: {assistant_text}\n\n"
                    "Extrai os factos duráveis."
                ),
            },
        ]
        try:
            raw = await oc.extract_json(
                messages, schema=ExtractionResult.model_json_schema()
            )
            result = ExtractionResult.model_validate(raw)
        except (oc.OllamaError, ValidationError) as e:
            log.warning("extração falhou, a ignorar: %s", e)
            return []
        # Filtrar factos vazios
        return [f for f in result.facts if f.text.strip()]

    # ---------- Camada A, passo 2: consolidação ----------

    async def consolidate(self, facts: list[ExtractedFact], source_turn: int | None) -> list[ConsolidationDecision]:
        decisions: list[ConsolidationDecision] = []
        for fact in facts:
            try:
                vec = await oc.embed(fact.text, kind="query")
            except oc.OllamaError as e:
                log.warning("embed do candidato falhou, a ignorar: %s", e)
                continue

            existing = self._knn_facts(vec, self.cfg.consolidate_k)
            decision = await self._decide(fact, existing)

            # Vetor a persistir: para UPDATE com texto diferente, re-embeber o new_text
            store_vec = vec
            if decision.operation == Operation.UPDATE and decision.new_text and decision.new_text.strip() != fact.text.strip():
                try:
                    store_vec = await oc.embed(decision.new_text, kind="query")
                except oc.OllamaError as e:
                    log.warning("re-embed do new_text falhou, a usar vetor do candidato: %s", e)

            self._apply(decision, fact, store_vec, source_turn, existing)
            decisions.append(decision)
            log.info("consolidação: %s | candidato=%r | decisão=%s target=%s",
                     fact.fact_type, fact.text, decision.operation, decision.target_id)
        return decisions

    async def _decide(self, fact: ExtractedFact, existing: list[sqlite3.Row]) -> ConsolidationDecision:
        if not existing:
            return ConsolidationDecision(operation=Operation.ADD)
        listing = "\n".join(f"- id={r['id']}: {r['text']}" for r in existing)
        messages = [
            {"role": "system", "content": _CONSOLIDATE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"FACTO CANDIDATO:\n{fact.text}\n\n"
                    f"FACTOS EXISTENTES SEMELHANTES:\n{listing}\n\n"
                    "Decide a operação."
                ),
            },
        ]
        try:
            raw = await oc.extract_json(
                messages, schema=ConsolidationDecision.model_json_schema()
            )
            decision = ConsolidationDecision.model_validate(raw)
        except (oc.OllamaError, ValidationError) as e:
            log.warning("decisão de consolidação falhou -> NOOP: %s", e)
            return ConsolidationDecision(operation=Operation.NOOP)

        # Validar coerência: UPDATE/DELETE precisam de target_id válido entre os existentes
        valid_ids = {r["id"] for r in existing}
        if decision.operation in (Operation.UPDATE, Operation.DELETE):
            if decision.target_id not in valid_ids:
                log.warning("target_id %s inválido -> NOOP", decision.target_id)
                return ConsolidationDecision(operation=Operation.NOOP)
        if decision.operation == Operation.UPDATE and not (decision.new_text and decision.new_text.strip()):
            log.warning("UPDATE sem new_text -> NOOP")
            return ConsolidationDecision(operation=Operation.NOOP)
        return decision

    def _apply(
        self,
        decision: ConsolidationDecision,
        fact: ExtractedFact,
        candidate_vec: list[float],
        source_turn: int | None,
        existing: list[sqlite3.Row],
    ) -> None:
        op = decision.operation
        if op == Operation.NOOP:
            return
        try:
            if op == Operation.ADD:
                cur = self.conn.execute(
                    "INSERT INTO semantic_facts (text, fact_type, source_turn) VALUES (?, ?, ?)",
                    (fact.text, fact.fact_type.value, source_turn),
                )
                fid = cur.lastrowid
                self.conn.execute(
                    "INSERT INTO fact_vectors (fact_id, embedding) VALUES (?, ?)",
                    (fid, _serialize(candidate_vec)),
                )
            elif op == Operation.UPDATE:
                self.conn.execute(
                    "UPDATE semantic_facts SET text = ?, updated_at = datetime('now') WHERE id = ?",
                    (decision.new_text, decision.target_id),
                )
                # re-embeber o novo texto (sync: usamos o vetor do candidato apenas se
                # new_text == candidato; por segurança re-embebemos de forma lazy abaixo)
                # delete+insert da linha vec mantendo o mesmo id
                self.conn.execute(
                    "DELETE FROM fact_vectors WHERE fact_id = ?", (decision.target_id,)
                )
                self.conn.execute(
                    "INSERT INTO fact_vectors (fact_id, embedding) VALUES (?, ?)",
                    (decision.target_id, _serialize(candidate_vec)),
                )
            elif op == Operation.DELETE:
                self.conn.execute(
                    "UPDATE semantic_facts SET is_deleted = 1, updated_at = datetime('now') WHERE id = ?",
                    (decision.target_id,),
                )
                self.conn.execute(
                    "DELETE FROM fact_vectors WHERE fact_id = ?", (decision.target_id,)
                )
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            log.error("falha ao aplicar %s: %s", op, e)

    # ---------- Gestão (painel de memória) ----------

    async def search_facts(self, query: str, k: int) -> list[sqlite3.Row]:
        """Factos ativos ordenados por relevância semântica à query."""
        vec = await oc.embed(query, kind="query")
        return self._knn_facts(vec, k)

    async def edit_fact(self, fact_id: int, new_text: str) -> bool:
        """Edita o texto de um facto e re-embebe (delete+insert do vetor).

        Segue o mesmo padrão de UPDATE de `_apply` para manter o lockstep entre
        `semantic_facts` e `fact_vectors`. Devolve False se o facto não existir.
        """
        new_text = new_text.strip()
        if not new_text:
            return False
        vec = await oc.embed(new_text, kind="query")
        async with self._write_lock:
            cur = self.conn.execute(
                "UPDATE semantic_facts SET text = ?, updated_at = datetime('now') "
                "WHERE id = ? AND is_deleted = 0",
                (new_text, fact_id),
            )
            if cur.rowcount == 0:
                self.conn.rollback()
                return False
            self.conn.execute("DELETE FROM fact_vectors WHERE fact_id = ?", (fact_id,))
            self.conn.execute(
                "INSERT INTO fact_vectors (fact_id, embedding) VALUES (?, ?)",
                (fact_id, _serialize(vec)),
            )
            self.conn.commit()
        return True

    # ---------- Recuperação + injeção ----------

    async def retrieve(self, query_text: str) -> str:
        try:
            vec = await oc.embed(query_text, kind="query")
        except oc.OllamaError as e:
            log.warning("retrieve: embed falhou, sem injeção: %s", e)
            return ""

        facts = self._knn_facts(vec, self.cfg.top_k_facts)
        turns = self._knn_turns(vec, self.cfg.top_k_turns)

        parts: list[str] = []
        if facts:
            parts.append("O que sei sobre ti:")
            parts.extend(f"- {r['text']}" for r in facts)
        if turns:
            if parts:
                parts.append("")
            parts.append("Contexto relevante de conversas passadas:")
            parts.extend(f"- {r['text']}" for r in turns)
        return "\n".join(parts)

    # ---------- Orquestrador pós-troca (background) ----------

    async def remember(self, conversation_id: int, user_text: str, assistant_text: str) -> None:
        try:
            turn_id = await self.store_turn(conversation_id, user_text, assistant_text)
            facts = await self.extract(user_text, assistant_text)
            if facts:
                await self.consolidate(facts, turn_id)
        except Exception as e:  # noqa: BLE001 - nunca rebentar o caminho de chat
            log.error("remember falhou: %s", e)
