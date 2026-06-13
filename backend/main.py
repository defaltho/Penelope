"""Penelope - backend FastAPI (Stage 1: chat + memória).

Endpoints:
  POST   /chat                 -> resposta em streaming SSE, com memória injetada
  GET    /conversations        -> lista conversas
  POST   /conversations        -> cria conversa vazia
  GET    /memory/facts         -> lista factos semânticos (visibilidade/validação)
  DELETE /memory/facts/{id}    -> apaga facto (soft delete + remove vetor)
  GET    /health               -> estado do sistema
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

import ollama_client as oc
from config import settings
from db import connect, fts5_available, init_schema
from memory import MemoryService
from schemas import (
    AgentRunRequest,
    AgentStep,
    ChatRequest,
    CompactRequest,
    SkillExtraction,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("penelope")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Abrir DB (falha aqui se loadable extensions estiverem desativadas)
    conn = connect()
    init_schema(conn)

    if not fts5_available(conn):
        raise RuntimeError("FTS5 não está disponível neste SQLite.")

    # Health check: dimensão do embedding bate certo
    try:
        probe = await oc.embed("ok", kind="query")
    except oc.OllamaError as e:
        raise RuntimeError(f"Ollama/embeddings indisponível: {e}") from e
    if len(probe) != settings.embed_dim:
        raise RuntimeError(
            f"Dimensão de embedding {len(probe)} != esperado {settings.embed_dim}"
        )

    # Health check: modelos presentes (apenas aviso)
    try:
        models = await oc.list_models()
        for needed in (settings.chat_model, settings.embed_model):
            if needed not in models and f"{needed}:latest" not in models:
                log.warning("Modelo '%s' não encontrado em 'ollama list'.", needed)
    except oc.OllamaError as e:
        log.warning("Não foi possível listar modelos: %s", e)

    app.state.conn = conn
    app.state.memory = MemoryService(conn, settings)
    log.info("Penelope pronto. DB=%s chat=%s embed=%s",
             settings.db_path, settings.chat_model, settings.embed_model)
    yield
    conn.close()


app = FastAPI(title="Penelope", lifespan=lifespan)

# Permitir o dev server do SvelteKit (alternativa ao proxy do Vite)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir imagens anexadas persistidas (acessível via proxy em /api/images/<ficheiro>)
os.makedirs(settings.images_dir, exist_ok=True)
app.mount("/images", StaticFiles(directory=settings.images_dir), name="images")


# ---------- Helpers ----------

def _ensure_conversation(conn, conversation_id: int | None) -> int:
    if conversation_id is not None:
        row = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"conversa {conversation_id} não existe")
        return conversation_id
    cur = conn.execute("INSERT INTO conversations DEFAULT VALUES")
    conn.commit()
    return cur.lastrowid


def _recent_history(conn, conversation_id: int, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ---------- Chat ----------

@app.post("/chat")
async def chat(req: ChatRequest):
    conn = app.state.conn
    memory: MemoryService = app.state.memory

    has_image = bool(req.image_base64 and req.image_base64.strip())
    if not req.message.strip() and not has_image:
        raise HTTPException(400, "mensagem vazia")

    # Texto guardado no histórico; se for só imagem, usar um marcador legível.
    user_text = req.message.strip() or "[imagem]"

    # Preparar imagem (decode + resize) e persistir em disco, se houver.
    img_b64: str | None = None
    image_path: str | None = None
    if has_image and not req.incognito:
        raw = _decode_image(req.image_base64)
        jpeg = _resize_to_jpeg_bytes(raw, settings.vision_max_dim)
        img_b64 = base64.b64encode(jpeg).decode("ascii")
        image_path = _save_image(jpeg)
    elif has_image:
        # Anónimo: a imagem é vista pelo modelo mas NÃO é gravada em disco.
        raw = _decode_image(req.image_base64)
        jpeg = _resize_to_jpeg_bytes(raw, settings.vision_max_dim)
        img_b64 = base64.b64encode(jpeg).decode("ascii")

    if req.incognito:
        # MODO ANÓNIMO: nada é persistido (sem conversa, sem mensagens).
        conversation_id = None
    else:
        conversation_id = _ensure_conversation(conn, req.conversation_id)
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, image_path) VALUES (?, 'user', ?, ?)",
            (conversation_id, user_text, image_path),
        )
        conn.commit()

    cfg = _get_settings(conn)
    chat_model = (req.model or "").strip() or cfg["chat_model"]

    # Parâmetros de geração das definições (com fallbacks seguros)
    def _num(key, default, cast):
        try:
            return cast(cfg.get(key) or default)
        except (TypeError, ValueError):
            return default

    temperature = _num("temperature", settings.chat_temperature, float)
    num_ctx = _num("num_ctx", settings.num_ctx, int)
    max_tokens = _num("max_tokens", 0, int)

    # System prompt base: por defeito o do Penelope; override substitui.
    override = (req.system_override or "").strip()
    system_content = override or settings.base_system_prompt
    system_extra = (cfg.get("system_extra") or "").strip()
    if system_extra:
        system_content += "\n\n" + system_extra

    # Injetar skills ativas (se ativas nas definições)
    if cfg["skills_enabled"] == "1":
        skill_rows = conn.execute(
            "SELECT name, instruction FROM skills WHERE enabled = 1 ORDER BY id"
        ).fetchall()
        if skill_rows:
            block = "\n\n".join(f"[{s['name']}]\n{s['instruction']}" for s in skill_rows)
            system_content += "\n\nInstruções ativas (segue-as):\n" + block

    # Histórico: anónimo não lê nada do disco (só a mensagem atual).
    if req.incognito:
        history = [{"role": "user", "content": user_text}]
    else:
        history = _recent_history(conn, conversation_id, settings.recent_history_turns)

    # A pesquisa web e a recuperação de memória correm DENTRO do event_gen para
    # emitirem eventos `status` em tempo real (B2: activity lane). Flags pré-calculadas:
    do_web = bool(req.web_search and _internet_allowed(conn))
    do_memory = bool(cfg["memory_enabled"] == "1" and not req.incognito)

    holder = {"text": "", "tokens": 0, "tps": None}

    async def event_gen():
        import time as _time

        nonlocal system_content

        def _status(kind: str, text: str) -> dict:
            return {"event": "status", "data": json.dumps({"kind": kind, "text": text})}

        # --- Contexto em tempo real (B2: activity lane) ---
        # Cada fase emite um `status` antes de correr, para a UI mostrar o que se passa.
        if do_web:
            yield _status("web", "a pesquisar na web")
            try:
                web = await _web_search(conn, user_text)
            except Exception as e:  # noqa: BLE001 - nunca rebentar o chat
                web = []
                log.warning("pesquisa web no chat falhou: %s", e)
            if web:
                block = "\n".join(
                    f"- {r['title']} ({r['url']}): {r['snippet']}" for r in web[:5]
                )
                system_content += (
                    "\n\nResultados de pesquisa web (usa-os para responder e cita as fontes "
                    "quando fizer sentido):\n" + block
                )
        if do_memory:
            yield _status("memory", "a recuperar memória")
            try:
                injection = await memory.retrieve(user_text)
            except Exception as e:  # noqa: BLE001
                injection = ""
                log.warning("retrieve no chat falhou: %s", e)
            if injection:
                system_content += "\n\n" + injection

        # Construir as mensagens já com o contexto recolhido.
        msgs = [{"role": "system", "content": system_content}, *history]
        if img_b64:
            msgs[-1] = {**msgs[-1], "images": [img_b64]}

        yield _status("thinking", "a pensar")

        started = None
        try:
            async for token in oc.chat_stream(
                msgs,
                model=chat_model,
                num_ctx=num_ctx,
                temperature=temperature,
                num_predict=(max_tokens or None),
            ):
                if started is None:
                    started = _time.monotonic()
                holder["tokens"] += 1
                holder["text"] += token
                yield {"event": "token", "data": json.dumps({"token": token})}
        except oc.OllamaError as e:
            log.error("erro de chat: %s", e)
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
            return

        # Velocidade (tokens por segundo), medida no servidor.
        if started is not None and holder["tokens"] > 1:
            elapsed = _time.monotonic() - started
            if elapsed > 0:
                holder["tps"] = holder["tokens"] / elapsed

        # MODO ANÓNIMO: não grava nada; termina o stream sem persistir.
        if req.incognito:
            yield {
                "event": "done",
                "data": json.dumps(
                    {"conversation_id": None, "incognito": True, "tok_per_sec": holder["tps"]}
                ),
            }
            return

        # Persistir resposta do assistente (com metadados persistentes)
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, model, tok_per_sec) "
            "VALUES (?, 'assistant', ?, ?, ?)",
            (conversation_id, holder["text"], chat_model, holder["tps"]),
        )
        # Auto-título: derivar da 1ª mensagem do utilizador se ainda não houver.
        row = conn.execute(
            "SELECT title FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is not None and not (row["title"] or "").strip():
            first = conn.execute(
                "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' "
                "ORDER BY id LIMIT 1",
                (conversation_id,),
            ).fetchone()
            if first:
                title = first["content"].strip().splitlines()[0][:40] or "Conversa"
                conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (title, conversation_id),
                )
        conn.commit()
        yield {
            "event": "done",
            "data": json.dumps(
                {"conversation_id": conversation_id, "model": chat_model, "tok_per_sec": holder["tps"]}
            ),
        }

    async def _post_exchange():
        # Corre depois da resposta ser enviada; nunca bloqueia o stream visível.
        # MODO ANÓNIMO: nada de memória nem auto-skills.
        if req.incognito:
            return
        await memory.remember(conversation_id, user_text, holder["text"])
        if _get_settings(conn)["skills_auto"] == "1":
            await _auto_skills(conn, user_text, holder["text"])

    return EventSourceResponse(event_gen(), background=BackgroundTask(_post_exchange))



@app.post("/chat/compact")
async def compact_chat(req: CompactRequest):
    conn = app.state.conn
    row = conn.execute(
        "SELECT id FROM conversations WHERE id = ?", (req.conversation_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "conversa não encontrada")

    msgs = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
        (req.conversation_id,),
    ).fetchall()
    if not msgs:
        raise HTTPException(400, "conversa sem mensagens")

    transcript = "\n".join(f"[{m['role']}] {m['content']}" for m in msgs)
    cfg = _get_settings(conn)
    chat_model = cfg["chat_model"]

    summary = await oc.chat_once(
        [
            {
                "role": "system",
                "content": (
                    "Tu és um assistente que resume conversas. Resume a transcrição abaixo "
                    "num resumo conciso de 2-3 parágrafos, mantendo todos os factos importantes, "
                    "decisões tomadas e contexto relevante. Escreve na mesma língua da conversa."
                ),
            },
            {"role": "user", "content": transcript},
        ],
        model=chat_model,
    )

    conn.execute(
        "DELETE FROM messages WHERE conversation_id = ?", (req.conversation_id,)
    )
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', ?)",
        (req.conversation_id, "[contexto compactado]"),
    )
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'assistant', ?)",
        (req.conversation_id, summary),
    )
    conn.commit()

    return {"summary": summary, "conversation_id": req.conversation_id}


# ---------- Imagem (visão geral, Stage 2) ----------

def _decode_image(image_base64: str) -> bytes:
    """Aceita data URL ou base64 cru; devolve os bytes da imagem."""
    data = image_base64.strip()
    if data.startswith("data:"):
        _, _, b64 = data.partition(",")
        data = b64
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, f"base64 inválido: {e}")


def _resize_to_jpeg_bytes(raw: bytes, max_dim: int) -> bytes:
    """Redimensiona o lado maior para <= max_dim e devolve bytes JPEG.

    Se o Pillow não estiver disponível, devolve a imagem original sem redimensionar.
    """
    try:
        from PIL import Image
    except ImportError:
        log.warning("Pillow ausente: a usar imagem sem redimensionar.")
        return raw

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"imagem ilegível: {e}")

    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _save_image(data: bytes) -> str:
    """Grava bytes de imagem em data/images/<uuid>.jpg e devolve o nome do ficheiro."""
    fname = f"{uuid.uuid4().hex}.jpg"
    with open(os.path.join(settings.images_dir, fname), "wb") as f:
        f.write(data)
    return fname


# ---------- Galeria de imagens ----------

@app.get("/gallery")
async def gallery():
    conn = app.state.conn
    rows = conn.execute(
        """
        SELECT m.image_path, m.conversation_id, m.created_at, c.title,
               (SELECT content FROM messages
                WHERE conversation_id = m.conversation_id AND role = 'user'
                ORDER BY id LIMIT 1) AS conv_snippet
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE m.image_path IS NOT NULL
        ORDER BY m.id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------- Conversas ----------

@app.get("/conversations")
async def list_conversations():
    conn = app.state.conn
    rows = conn.execute(
        """
        SELECT c.id, c.title, c.created_at,
               COALESCE(MAX(m.created_at), c.created_at) AS updated_at,
               COUNT(m.id) AS message_count,
               (SELECT content FROM messages
                WHERE conversation_id = c.id AND role = 'user'
                ORDER BY id LIMIT 1) AS snippet
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY updated_at DESC
        """
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        snip = (d.get("snippet") or "").strip().splitlines()
        d["snippet"] = (snip[0][:80] if snip else "")
        out.append(d)
    return out


@app.post("/conversations")
async def create_conversation():
    conn = app.state.conn
    cur = conn.execute("INSERT INTO conversations DEFAULT VALUES")
    conn.commit()
    return {"id": cur.lastrowid}


@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: int):
    conn = app.state.conn
    row = conn.execute(
        "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"conversa {conversation_id} não existe")
    rows = conn.execute(
        "SELECT role, content, image_path, model, tok_per_sec, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.patch("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: int, body: dict):
    conn = app.state.conn
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "título vazio")
    cur = conn.execute(
        "UPDATE conversations SET title = ? WHERE id = ?", (title[:80], conversation_id)
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"conversa {conversation_id} não existe")
    return {"id": conversation_id, "title": title[:80]}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    conn = app.state.conn
    # Sem ON DELETE CASCADE no schema: limpar em ordem segura.
    # 1) vetores dos turnos desta conversa, 2) turnos, 3) mensagens (triggers
    # limpam o FTS), 4) a conversa. Factos semânticos são globais: manter.
    conn.execute(
        "DELETE FROM turn_vectors WHERE turn_id IN "
        "(SELECT turn_id FROM turns WHERE conversation_id = ?)",
        (conversation_id,),
    )
    conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"conversa {conversation_id} não existe")
    return {"deleted": conversation_id}


# ---------- Memória (visibilidade/validação) ----------

@app.get("/memory/facts")
async def list_facts(q: str | None = None):
    conn = app.state.conn
    memory: MemoryService = app.state.memory
    if q and q.strip():
        rows = await memory.search_facts(q.strip(), 30)
        return [
            {"id": r["id"], "text": r["text"], "fact_type": r["fact_type"], "updated_at": None}
            for r in rows
        ]
    rows = conn.execute(
        "SELECT id, text, fact_type, updated_at FROM semantic_facts "
        "WHERE is_deleted = 0 ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.patch("/memory/facts/{fact_id}")
async def edit_fact(fact_id: int, body: dict):
    memory: MemoryService = app.state.memory
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "texto vazio")
    ok = await memory.edit_fact(fact_id, text)
    if not ok:
        raise HTTPException(404, f"facto {fact_id} não existe")
    return {"id": fact_id, "text": text}


@app.get("/memory/pending")
async def list_pending():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT id, text, fact_type, created_at FROM pending_facts ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/memory/pending/{pending_id}/approve")
async def approve_pending(pending_id: int):
    memory: MemoryService = app.state.memory
    ok = await memory.approve_pending(pending_id)
    if not ok:
        raise HTTPException(404, f"pendente {pending_id} não existe")
    return {"approved": pending_id}


@app.delete("/memory/pending/{pending_id}")
async def reject_pending(pending_id: int):
    memory: MemoryService = app.state.memory
    if not memory.reject_pending(pending_id):
        raise HTTPException(404, f"pendente {pending_id} não existe")
    return {"rejected": pending_id}


@app.get("/memory/export")
async def export_facts():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT text, fact_type FROM semantic_facts WHERE is_deleted = 0 ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/memory/import")
async def import_facts(body: dict):
    memory: MemoryService = app.state.memory
    facts = body.get("facts")
    if not isinstance(facts, list):
        raise HTTPException(400, "esperado {facts: [...]}")
    added = await memory.import_facts(facts)
    return {"added": added}


@app.get("/memory/facts/archived")
async def list_archived_facts():
    """Factos arquivados (recuperáveis). Para o separador 'Arquivados' (A3)."""
    memory: MemoryService = app.state.memory
    return [dict(r) for r in memory.list_archived()]


@app.delete("/memory/facts/{fact_id}")
async def archive_fact(fact_id: int):
    """Arquiva (soft-delete recuperável). É a ação por defeito do botão de apagar."""
    memory: MemoryService = app.state.memory
    memory.archive_fact(fact_id)  # idempotente: já-arquivado/inexistente não rebenta
    return {"archived": fact_id}


@app.post("/memory/facts/{fact_id}/restore")
async def restore_fact(fact_id: int):
    """Restaura um facto arquivado (re-embebe e volta ao KNN)."""
    memory: MemoryService = app.state.memory
    ok = await memory.restore_fact(fact_id)
    if not ok:
        raise HTTPException(404, f"facto {fact_id} não está arquivado")
    return {"restored": fact_id}


@app.delete("/memory/facts/{fact_id}/purge")
async def purge_fact(fact_id: int):
    """Apaga DEFINITIVAMENTE um facto (ação explícita, não recuperável)."""
    conn = app.state.conn
    conn.execute("DELETE FROM fact_vectors WHERE fact_id = ?", (fact_id,))
    conn.execute("DELETE FROM semantic_facts WHERE id = ?", (fact_id,))
    conn.commit()
    return {"purged": fact_id}


# ---------- Pesquisa web (estilo Odysseus: DuckDuckGo / SearXNG) ----------

async def _web_search(conn, query: str) -> list[dict]:
    """Pesquisa na web e devolve [{title, url, snippet}]. Réplica do padrão do
    Odysseus (DuckDuckGo por scrape de html.duckduckgo.com, ou SearXNG via JSON).
    GATED: o chamador tem de garantir _internet_allowed."""
    import re as _r
    import urllib.parse as _up

    cfg = _get_settings(conn)
    try:
        count = max(1, min(10, int(cfg.get("search_results") or 5)))
    except (TypeError, ValueError):
        count = 5
    provider = (cfg.get("search_provider") or "duckduckgo").lower()
    searxng_url = (cfg.get("search_url") or "").strip().rstrip("/")
    headers = {"User-Agent": "Mozilla/5.0"}

    import httpx

    # SearXNG (instância self-hosted), JSON API.
    if provider == "searxng" and searxng_url:
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                r = await c.get(
                    f"{searxng_url}/search",
                    params={"q": query, "format": "json"},
                    headers=headers,
                )
                data = r.json()
            return [
                {"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")}
                for x in (data.get("results") or [])[:count]
                if x.get("url")
            ]
        except Exception as e:  # noqa: BLE001 - cai para DuckDuckGo
            log.warning("searxng falhou (%s); fallback DuckDuckGo", e)

    # DuckDuckGo (sem chave): scrape de html.duckduckgo.com.
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
            r = await c.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers)
            html = r.text
    except Exception as e:  # noqa: BLE001
        log.warning("duckduckgo falhou: %s", e)
        return []

    results: list[dict] = []
    for m in _r.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, _r.S):
        href, raw_title = m.group(1), m.group(2)
        mu = _r.search(r"uddg=([^&]+)", href)
        url = _up.unquote(mu.group(1)) if mu else href
        if url.startswith("//"):
            url = "https:" + url
        title = _r.sub(r"<[^>]+>", "", raw_title).strip()
        results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= count:
            break
    snippets = _r.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, _r.S)
    for i, s in enumerate(snippets[: len(results)]):
        results[i]["snippet"] = _r.sub(r"<[^>]+>", "", s).strip()
    return results


@app.post("/search/web")
async def search_web(body: dict):
    conn = app.state.conn
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "falta a query")
    # GATE DE INTERNET (fail-closed).
    if not _internet_allowed(conn):
        raise HTTPException(403, "acesso à internet desligado — ativa-o nas Definições")
    return {"results": await _web_search(conn, query)}


# ---------- Agents (loop com ferramentas locais — estilo Odysseus) ----------

# Registo de ferramentas (à imagem dos "Built-in Tools" do Odysseus, mas local).
#   dangerous=True       -> DESLIGADA por defeito; só liga nas Definições (com aviso).
#   requires_internet=True -> atrás do gate de internet (fail-closed).
# A ordem é a que aparece ao modelo no system prompt.
_TOOL_REGISTRY: list[dict] = [
    {"name": "data_hora", "desc": "data e hora atuais.", "dangerous": False, "requires_internet": False},
    {"name": "pesquisar_memoria", "desc": "procura factos guardados sobre o utilizador. args: query", "dangerous": False, "requires_internet": False},
    {"name": "pesquisar_conversas", "desc": "procura em conversas antigas. args: query", "dangerous": False, "requires_internet": False},
    {"name": "criar_nota", "desc": "cria uma nota. args: titulo, conteudo", "dangerous": False, "requires_internet": False},
    {"name": "listar_notas", "desc": "lista as notas.", "dangerous": False, "requires_internet": False},
    {"name": "criar_tarefa", "desc": "adiciona uma tarefa. args: texto", "dangerous": False, "requires_internet": False},
    {"name": "listar_tarefas", "desc": "lista as tarefas.", "dangerous": False, "requires_internet": False},
    {"name": "concluir_tarefa", "desc": "marca como concluída a tarefa que contém o texto. args: texto", "dangerous": False, "requires_internet": False},
    {"name": "criar_documento", "desc": "cria um documento. args: titulo, conteudo", "dangerous": False, "requires_internet": False},
    {"name": "listar_modelos", "desc": "lista os modelos Ollama instalados.", "dangerous": False, "requires_internet": False},
    {"name": "gerir_skills", "desc": "gere instruções reutilizáveis. args: accao(listar|criar), nome, instrucao", "dangerous": False, "requires_internet": False},
    {"name": "ler_ficheiro", "desc": "lê um ficheiro de texto DENTRO da pasta do projeto. args: caminho", "dangerous": False, "requires_internet": False},
    {"name": "pesquisar_web", "desc": "pesquisa na web. args: query", "dangerous": False, "requires_internet": True},
    {"name": "abrir_pagina", "desc": "lê o texto de uma página web. args: url", "dangerous": False, "requires_internet": True},
    # PERIGOSAS — desligadas por defeito (acesso à máquina). Ligar é decisão explícita.
    {"name": "escrever_ficheiro", "desc": "escreve/cria um ficheiro DENTRO da pasta do projeto. args: caminho, conteudo", "dangerous": True, "requires_internet": False},
    {"name": "bash", "desc": "executa um comando de shell com ACESSO TOTAL à máquina. args: comando", "dangerous": True, "requires_internet": False},
    {"name": "python", "desc": "executa código Python num subprocesso com ACESSO TOTAL. args: codigo", "dangerous": True, "requires_internet": False},
]

# Ferramentas perigosas DESLIGADAS por defeito (até o utilizador as ligar).
_DEFAULT_DISABLED_TOOLS = [t["name"] for t in _TOOL_REGISTRY if t["dangerous"]]

_AGENT_RULES = (
    "\n\nREGRAS:\n"
    "1. A cada passo devolve SÓ um JSON. Para agir: {\"thought\": \"...\", \"tool\": "
    "\"nome\", \"args\": {...}}.\n"
    "2. Quando tiveres a resposta, devolve {\"thought\": \"...\", \"final\": \"<a "
    "resposta DIRETA ao utilizador, sem explicar o teu raciocínio>\"}.\n"
    "3. O campo `final` é a mensagem que o utilizador vê: escreve-a de forma natural "
    "e completa, NÃO descrevas o que fizeste nem menciones ferramentas.\n"
    "4. Usa o mínimo de passos. Não inventes resultados; usa as observações reais.\n"
    "5. Para tarefas simples (ex.: uma saudação ou uma pergunta de conhecimento "
    "geral) responde logo com `final`, sem ferramentas.\n"
    "6. Só podes usar as ferramentas listadas acima. As que não aparecem estão "
    "desativadas e devolverão um erro se as tentares."
)


def _disabled_tools(conn) -> set[str]:
    """Conjunto de ferramentas desativadas nas Definições (perigosas off por defeito)."""
    raw = _get_settings(conn).get("tools_disabled")
    if raw is None:
        return set(_DEFAULT_DISABLED_TOOLS)
    try:
        return set(json.loads(raw))
    except (ValueError, TypeError):
        return set(_DEFAULT_DISABLED_TOOLS)


def _auto_approved(conn) -> set[str]:
    """Ferramentas perigosas que o utilizador marcou como 'permitir sempre' (B8).
    Persistido em app_settings; vazio por defeito (cada chamada pede aprovação)."""
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'tools_auto_approved'"
    ).fetchone()
    if not row:
        return set()
    try:
        return set(json.loads(row[0]))
    except (ValueError, TypeError):
        return set()


def _add_auto_approved(conn, name: str) -> None:
    s = _auto_approved(conn)
    s.add(name)
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('tools_auto_approved', ?)",
        (json.dumps(sorted(s)),),
    )
    conn.commit()


def _needs_approval(conn, name: str, granted: set[str]) -> bool:
    """Uma ferramenta perigosa ATIVADA precisa de aprovação inline, exceto se já
    concedida nesta sessão (granted) ou marcada como 'sempre' (auto_approved)."""
    spec = next((t for t in _TOOL_REGISTRY if t["name"] == name), None)
    if not spec or not spec["dangerous"]:
        return False
    if name in _disabled_tools(conn):
        return False  # desativada: fica escondida/bloqueada, não há o que aprovar
    return name not in granted and name not in _auto_approved(conn)


def _tool_allowed(conn, name: str) -> tuple[bool, str]:
    """Gate central: existe? está ligada? a internet (se preciso) está ligada?"""
    spec = next((t for t in _TOOL_REGISTRY if t["name"] == name), None)
    if spec is None:
        return False, f"ferramenta desconhecida '{name}'"
    if name in _disabled_tools(conn):
        return False, f"ferramenta '{name}' está DESATIVADA nas Definições"
    if spec["requires_internet"] and not _internet_allowed(conn):
        return False, "acesso à internet desligado — ativa-o nas Definições"
    return True, ""


def _agent_system(conn) -> str:
    """System prompt do agente, listando apenas as ferramentas atualmente ativas."""
    disabled = _disabled_tools(conn)
    inet = _internet_allowed(conn)
    lines = []
    for t in _TOOL_REGISTRY:
        if t["name"] in disabled:
            continue
        if t["requires_internet"] and not inet:
            continue
        lines.append(f"- {t['name']}: {t['desc']}")
    header = (
        "És um agente que cumpre a tarefa do utilizador usando ferramentas LOCAIS. "
        "Ferramentas disponíveis:\n" + "\n".join(lines)
    )
    return header + _AGENT_RULES


def _safe_project_path(rel: str) -> str | None:
    """Resolve um caminho relativo e garante que fica DENTRO da raiz do projeto."""
    base = os.path.realpath(settings.project_root)
    full = os.path.realpath(os.path.join(base, rel))
    if full == base or full.startswith(base + os.sep):
        return full
    return None


async def _run_subprocess(argv: list[str] | None = None, *, shell: str | None = None, timeout: int = 30) -> str:
    """Executa um subprocesso (lista de args OU comando de shell) com timeout."""
    import asyncio

    try:
        if shell is not None:
            proc = await asyncio.create_subprocess_shell(
                shell,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=settings.project_root,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *(argv or []),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=settings.project_root,
            )
    except Exception as e:  # noqa: BLE001
        return f"erro ao arrancar: {e}"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return f"erro: tempo esgotado ({timeout}s)"
    text = (out or b"").decode("utf-8", "replace")
    return f"(saída exit={proc.returncode})\n{text[:2000]}"


async def _agent_tool(conn, memory, name: str, args: dict) -> str:
    name = (name or "").strip()
    args = args or {}
    # GATE CENTRAL (fail-closed): existência + ativação + internet.
    ok, why = _tool_allowed(conn, name)
    if not ok:
        return f"BLOQUEADO: {why}"
    if name == "data_hora":
        import datetime
        return datetime.datetime.now().strftime("Agora: %Y-%m-%d %H:%M")
    if name == "pesquisar_memoria":
        q = str(args.get("query") or args.get("consulta") or "").strip()
        if not q:
            return "erro: falta 'query'"
        rows = await memory.search_facts(q, 5)
        return ("Factos: " + " | ".join(r["text"] for r in rows)) if rows else "sem factos relevantes"
    if name == "criar_nota":
        title = str(args.get("titulo") or args.get("title") or "").strip()
        content = str(args.get("conteudo") or args.get("content") or "").strip()
        if not title and not content:
            return "erro: nota vazia"
        conn.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title[:120], content))
        conn.commit()
        return f"nota criada: {title or '(sem título)'}"
    if name == "pesquisar_conversas":
        q = str(args.get("query") or args.get("consulta") or "").strip()
        if not q:
            return "erro: falta 'query'"
        import re as _re3

        toks = [t for t in _re3.findall(r"\w+", q.lower())]
        if not toks:
            return "sem resultados"
        match = " ".join(f"{t}*" for t in toks)
        try:
            rows = conn.execute(
                "SELECT m.content FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid "
                "WHERE messages_fts MATCH ? ORDER BY m.id DESC LIMIT 5",
                (match,),
            ).fetchall()
        except Exception:
            return "sem resultados"
        return ("Encontrado: " + " | ".join((r["content"] or "")[:80] for r in rows)) if rows else "sem resultados"
    if name == "listar_notas":
        rows = conn.execute("SELECT title FROM notes ORDER BY updated_at DESC LIMIT 20").fetchall()
        return ("Notas: " + " | ".join(r["title"] or "(sem título)" for r in rows)) if rows else "sem notas"
    if name == "criar_documento":
        title = str(args.get("titulo") or args.get("title") or "Novo documento").strip()
        content = str(args.get("conteudo") or args.get("content") or "")
        conn.execute("INSERT INTO documents (title, content) VALUES (?, ?)", (title[:160], content))
        conn.commit()
        return f"documento criado: {title}"
    if name == "criar_tarefa":
        text = str(args.get("texto") or args.get("text") or "").strip()
        if not text:
            return "erro: tarefa vazia"
        conn.execute("INSERT INTO tasks (text) VALUES (?)", (text,))
        conn.commit()
        return f"tarefa criada: {text}"
    if name == "concluir_tarefa":
        text = str(args.get("texto") or args.get("text") or "").strip()
        if not text:
            return "erro: falta o texto da tarefa"
        cur = conn.execute(
            "UPDATE tasks SET done = 1 WHERE done = 0 AND text LIKE ?", (f"%{text}%",)
        )
        conn.commit()
        return f"{cur.rowcount} tarefa(s) marcada(s) como concluída(s)"
    if name == "listar_tarefas":
        rows = conn.execute(
            "SELECT text, done FROM tasks ORDER BY done, id DESC LIMIT 20"
        ).fetchall()
        if not rows:
            return "sem tarefas"
        return "Tarefas: " + " | ".join(
            ("[x] " if r["done"] else "[ ] ") + r["text"] for r in rows
        )
    if name == "pesquisar_web":
        # GATED: só com internet explicitamente ativada (fail-closed).
        if not _internet_allowed(conn):
            return "BLOQUEADO: acesso à internet desligado. Ativa-o nas Definições para pesquisar."
        q = str(args.get("query") or args.get("consulta") or "").strip()
        if not q:
            return "erro: falta 'query'"
        res = await _web_search(conn, q)
        if not res:
            return "sem resultados"
        return "Resultados:\n" + "\n".join(
            f"- {r['title']} ({r['url']}): {r['snippet'][:140]}" for r in res[:5]
        )
    if name == "abrir_pagina":
        # GATED: só com internet explicitamente ativada (fail-closed).
        if not _internet_allowed(conn):
            return "BLOQUEADO: acesso à internet desligado. Ativa-o nas Definições para usar a web."
        url = str(args.get("url") or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            return "erro: url tem de começar por http:// ou https://"
        low = url.lower()
        if any(h in low for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "192.168.", "169.254.", "/10.")):
            return "BLOQUEADO: endereços locais/privados não são permitidos."
        try:
            import httpx
            import re as _re2

            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                r = await c.get(url, headers={"User-Agent": "Penelope/1.0"})
            txt = _re2.sub(r"<[^>]+>", " ", r.text)
            txt = _re2.sub(r"\s+", " ", txt).strip()
            return f"Conteúdo de {url} (truncado): {txt[:1500]}"
        except Exception as e:  # noqa: BLE001
            return f"erro ao abrir página: {e}"
    if name == "listar_modelos":
        try:
            models = await oc.list_models()
        except oc.OllamaError as e:
            return f"erro ao listar modelos: {e}"
        return ("Modelos: " + ", ".join(models)) if models else "sem modelos instalados"
    if name == "gerir_skills":
        accao = str(args.get("accao") or args.get("action") or "listar").strip().lower()
        if accao in ("criar", "create", "add"):
            nome = str(args.get("nome") or args.get("name") or "").strip()
            instr = str(args.get("instrucao") or args.get("instruction") or "").strip()
            if not nome or not instr:
                return "erro: 'nome' e 'instrucao' são obrigatórios"
            conn.execute(
                "INSERT INTO skills (name, instruction, enabled) VALUES (?, ?, 1)",
                (nome[:60], instr),
            )
            conn.commit()
            return f"skill criada: {nome[:60]}"
        rows = conn.execute(
            "SELECT name, enabled FROM skills ORDER BY id DESC LIMIT 30"
        ).fetchall()
        if not rows:
            return "sem skills"
        return "Skills: " + " | ".join(
            (r["name"] or "(sem nome)") + ("" if r["enabled"] else " (off)") for r in rows
        )
    if name == "ler_ficheiro":
        rel = str(args.get("caminho") or args.get("path") or "").strip()
        if not rel:
            return "erro: falta 'caminho'"
        full = _safe_project_path(rel)
        if full is None:
            return "BLOQUEADO: caminho fora da pasta do projeto."
        if not os.path.isfile(full):
            return f"erro: ficheiro não encontrado: {rel}"
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                data = f.read(4000)
        except Exception as e:  # noqa: BLE001
            return f"erro ao ler: {e}"
        return f"Conteúdo de {rel} (truncado):\n{data}"
    if name == "escrever_ficheiro":
        rel = str(args.get("caminho") or args.get("path") or "").strip()
        content = str(args.get("conteudo") or args.get("content") or "")
        if not rel:
            return "erro: falta 'caminho'"
        full = _safe_project_path(rel)
        if full is None:
            return "BLOQUEADO: caminho fora da pasta do projeto."
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:  # noqa: BLE001
            return f"erro ao escrever: {e}"
        log.warning("AGENT escrever_ficheiro: %s (%d bytes)", rel, len(content))
        return f"ficheiro escrito: {rel} ({len(content)} bytes)"
    if name == "bash":
        cmd = str(args.get("comando") or args.get("command") or "").strip()
        if not cmd:
            return "erro: falta 'comando'"
        log.warning("AGENT bash: %s", cmd)
        return await _run_subprocess(shell=cmd)
    if name == "python":
        import sys as _sys

        code = str(args.get("codigo") or args.get("code") or "")
        if not code.strip():
            return "erro: falta 'codigo'"
        log.warning("AGENT python: %d chars", len(code))
        return await _run_subprocess([_sys.executable, "-c", code])
    return f"erro: ferramenta desconhecida '{name}'"


@app.get("/agent/tools")
async def agent_tools():
    """Registo de ferramentas + estado (ligada/desligada) para o painel de Definições."""
    conn = app.state.conn
    disabled = _disabled_tools(conn)
    return [
        {
            "name": t["name"],
            "desc": t["desc"],
            "dangerous": t["dangerous"],
            "requires_internet": t["requires_internet"],
            "enabled": t["name"] not in disabled,
        }
        for t in _TOOL_REGISTRY
    ]


_AGENT_MAX_STEPS = 5


@app.post("/agent/run")
async def agent_run(req: AgentRunRequest):
    """Loop do agente, RETOMÁVEL para aprovação inline de tools perigosas (B8).

    Fluxo: corre passos até concluir OU até propor uma ferramenta perigosa ativada
    que ainda não foi aprovada. Nesse caso devolve `pending` (a UI mostra o prompt
    permitir/negar) + `state` (progresso). A UI volta a chamar este endpoint com
    `decision` + `state` para retomar.
    """
    conn = app.state.conn
    memory: MemoryService = app.state.memory

    # Estado: novo arranque vs retoma de uma aprovação.
    if req.state:
        convo: list[str] = list(req.state.get("convo", []))
        steps: list[dict] = list(req.state.get("steps", []))
        granted: set[str] = set(req.state.get("granted", []))
    else:
        task = (req.task or "").strip()
        if not task:
            raise HTTPException(400, "tarefa vazia")
        convo, steps, granted = [f"Tarefa: {task}"], [], set()

    # Resolver uma ferramenta pendente segundo a decisão do utilizador.
    if req.decision and req.pending_tool:
        tool, args = req.pending_tool, (req.pending_args or {})
        if req.decision == "deny":
            obs = "(execução negada pelo utilizador)"
        else:
            if req.decision in ("allow_session", "allow_always"):
                granted.add(tool)
            if req.decision == "allow_always":
                _add_auto_approved(conn, tool)
            obs = await _agent_tool(conn, memory, tool, args)
        steps.append({"thought": req.pending_thought, "tool": tool, "args": args, "observation": obs})
        convo.append(f"Ação: {tool}({args}) -> {obs}")

    agent_system = _agent_system(conn)
    final: str | None = None

    while len(steps) < _AGENT_MAX_STEPS:
        messages = [
            {"role": "system", "content": agent_system},
            {"role": "user", "content": "\n".join(convo) + "\n\nDecide o próximo passo (JSON)."},
        ]
        try:
            raw = await oc.extract_json(messages, schema=AgentStep.model_json_schema())
            step = AgentStep.model_validate(raw)
        except Exception as e:  # noqa: BLE001
            final = f"(o agente falhou a decidir: {e})"
            break

        if step.final:
            steps.append({"thought": step.thought, "tool": None, "args": {}, "observation": None})
            final = step.final
            break
        if not step.tool:
            final = step.thought or "(sem ação)"
            break

        # Ferramenta perigosa ativada sem aprovação: PAUSA e pede confirmação (B8).
        if _needs_approval(conn, step.tool, granted):
            return {
                "steps": steps,
                "final": None,
                "pending": {
                    "tool": step.tool,
                    "args": step.args or {},
                    "thought": step.thought,
                },
                "state": {"convo": convo, "steps": steps, "granted": sorted(granted)},
            }

        obs = await _agent_tool(conn, memory, step.tool, step.args or {})
        steps.append(
            {"thought": step.thought, "tool": step.tool, "args": step.args or {}, "observation": obs}
        )
        convo.append(f"Ação: {step.tool}({step.args or {}}) -> {obs}")

    if final is None:
        final = "(atingi o limite de passos sem concluir a tarefa)"
    return {"steps": steps, "final": final, "pending": None}


# ---------- Skills (instruções reutilizáveis) ----------

@app.get("/skills")
async def list_skills():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT id, name, instruction, enabled, created_at FROM skills ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/skills")
async def create_skill(body: dict):
    conn = app.state.conn
    name = (body.get("name") or "").strip()
    instruction = (body.get("instruction") or "").strip()
    if not name or not instruction:
        raise HTTPException(400, "nome e instrução são obrigatórios")
    cur = conn.execute(
        "INSERT INTO skills (name, instruction, enabled) VALUES (?, ?, 1)",
        (name[:60], instruction),
    )
    conn.commit()
    return {"id": cur.lastrowid, "name": name[:60], "instruction": instruction, "enabled": 1}


@app.patch("/skills/{skill_id}")
async def update_skill(skill_id: int, body: dict):
    conn = app.state.conn
    fields, params = [], []
    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "nome vazio")
        fields.append("name = ?")
        params.append(name[:60])
    if "instruction" in body:
        instruction = (body.get("instruction") or "").strip()
        if not instruction:
            raise HTTPException(400, "instrução vazia")
        fields.append("instruction = ?")
        params.append(instruction)
    if "enabled" in body:
        fields.append("enabled = ?")
        params.append(1 if body.get("enabled") else 0)
    if not fields:
        raise HTTPException(400, "nada para atualizar")
    params.append(skill_id)
    cur = conn.execute(f"UPDATE skills SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"skill {skill_id} não existe")
    return {"id": skill_id}


_SKILL_EXTRACT_SYSTEM = (
    "Detetas INSTRUÇÕES REUTILIZÁVEIS que o utilizador queira que o assistente siga "
    "SEMPRE dali em diante (persona, tom, formato, regras de comportamento) — por ex.: "
    "'responde sempre em português', 'usa sempre tom formal', 'mostra o código em blocos'. "
    "NÃO incluas pedidos pontuais nem factos sobre o utilizador. Para cada uma, dá um nome "
    "curto e a instrução. Se não houver nenhuma instrução durável, devolve lista vazia."
)


async def _auto_skills(conn, user_text: str, assistant_text: str) -> None:
    """Propõe skills (instruções duráveis) a partir da troca, para a fila de aprovação."""
    messages = [
        {"role": "system", "content": _SKILL_EXTRACT_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Utilizador: {user_text}\nAssistente: {assistant_text}\n\n"
                "Deteta skills reutilizáveis."
            ),
        },
    ]
    try:
        raw = await oc.extract_json(messages, schema=SkillExtraction.model_json_schema())
        result = SkillExtraction.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        log.warning("auto-skills: extração falhou: %s", e)
        return
    if not result.skills:
        return
    existing = {
        (r[0] or "").strip().lower()
        for r in conn.execute("SELECT name FROM skills").fetchall()
    }
    pend = {
        (r[0] or "").strip().lower()
        for r in conn.execute("SELECT name FROM pending_skills").fetchall()
    }
    for s in result.skills:
        name = s.name.strip()
        instr = s.instruction.strip()
        if not name or not instr or name.lower() in existing or name.lower() in pend:
            continue
        conn.execute(
            "INSERT INTO pending_skills (name, instruction) VALUES (?, ?)",
            (name[:60], instr),
        )
        pend.add(name.lower())
    conn.commit()


@app.get("/skills/pending")
async def list_pending_skills():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT id, name, instruction, created_at FROM pending_skills ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/skills/pending/{pending_id}/approve")
async def approve_pending_skill(pending_id: int):
    conn = app.state.conn
    row = conn.execute(
        "SELECT name, instruction FROM pending_skills WHERE id = ?", (pending_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"skill pendente {pending_id} não existe")
    conn.execute(
        "INSERT INTO skills (name, instruction, enabled) VALUES (?, ?, 1)",
        (row["name"], row["instruction"]),
    )
    conn.execute("DELETE FROM pending_skills WHERE id = ?", (pending_id,))
    conn.commit()
    return {"approved": pending_id}


@app.delete("/skills/pending/{pending_id}")
async def reject_pending_skill(pending_id: int):
    conn = app.state.conn
    cur = conn.execute("DELETE FROM pending_skills WHERE id = ?", (pending_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"skill pendente {pending_id} não existe")
    return {"rejected": pending_id}


@app.get("/skills/export")
async def export_skills():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT name, instruction, enabled FROM skills ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/skills/import")
async def import_skills(body: dict):
    conn = app.state.conn
    skills = body.get("skills")
    if not isinstance(skills, list):
        raise HTTPException(400, "esperado {skills: [...]}")
    existing = {
        (r[0] or "").strip()
        for r in conn.execute("SELECT name FROM skills").fetchall()
    }
    added = 0
    for s in skills:
        name = (s.get("name") or "").strip()
        instruction = (s.get("instruction") or "").strip()
        if not name or not instruction or name in existing:
            continue
        enabled = 1 if s.get("enabled", True) else 0
        conn.execute(
            "INSERT INTO skills (name, instruction, enabled) VALUES (?, ?, ?)",
            (name[:60], instruction, enabled),
        )
        existing.add(name)
        added += 1
    conn.commit()
    return {"added": added}


@app.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int):
    conn = app.state.conn
    cur = conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"skill {skill_id} não existe")
    return {"deleted": skill_id}


# ---------- Pesquisa global (FTS5) ----------

import re as _re


@app.get("/search")
async def search_messages(q: str | None = None):
    conn = app.state.conn
    raw = (q or "").strip()
    if not raw:
        return []
    # Construir uma query FTS5 segura: tokens alfanuméricos com prefixo *.
    tokens = [t for t in _re.findall(r"\w+", raw.lower()) if t]
    if not tokens:
        return []
    match = " ".join(f"{t}*" for t in tokens)
    try:
        rows = conn.execute(
            """
            SELECT m.id, m.conversation_id, m.role, m.content, m.created_at,
                   c.title AS conv_title
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN conversations c ON c.id = m.conversation_id
            WHERE messages_fts MATCH ?
            ORDER BY m.id DESC
            LIMIT 60
            """,
            (match,),
        ).fetchall()
    except Exception as e:  # noqa: BLE001 - query inválida nunca deve rebentar
        log.warning("pesquisa falhou: %s", e)
        return []
    return [dict(r) for r in rows]


# ---------- Definições (editáveis em runtime) ----------

def _get_settings(conn) -> dict:
    out = {
        "chat_model": settings.chat_model,
        "dispatch_url": settings.dispatch_url,
        "memory_enabled": "1",
        "skills_enabled": "1",
        "memory_review": "0",
        "skills_auto": "0",
        "temperature": str(settings.chat_temperature),
        "num_ctx": str(settings.num_ctx),
        "max_tokens": "0",  # 0 = sem limite (default do modelo)
        "system_extra": "",
        # SEGURANÇA: acesso à internet DESLIGADO por defeito. Só "1" quando o
        # utilizador o ativa explicitamente nas Definições.
        "internet_enabled": "0",
        # Perfil / onboarding (single-user local)
        "user_name": "",
        "onboarded": "0",
        # Aparência
        "ui_anim": "1",
        "ui_welcome": "1",
        "ui_thinking": "0",
        "ui_text_emojis": "0",
        # Pesquisa web (estilo Odysseus). Requer internet ligada (fail-closed).
        "search_provider": "duckduckgo",
        "search_results": "5",
        "search_url": "",  # instância SearXNG (vazio = usar DuckDuckGo)
        # Agent tools: lista JSON das ferramentas DESATIVADAS (perigosas off por defeito).
        "tools_disabled": json.dumps(_DEFAULT_DISABLED_TOOLS),
    }
    for r in conn.execute("SELECT key, value FROM app_settings").fetchall():
        out[r["key"]] = r["value"]
    return out


_BOOL_KEYS = {
    "memory_enabled",
    "skills_enabled",
    "memory_review",
    "skills_auto",
    "internet_enabled",
    "onboarded",
    "ui_anim",
    "ui_welcome",
    "ui_thinking",
    "ui_text_emojis",
}


def _internet_allowed(conn) -> bool:
    """Gate único e fail-closed de acesso à internet. Desligado por defeito."""
    return _get_settings(conn)["internet_enabled"] == "1"


@app.get("/settings")
async def get_settings():
    s = _get_settings(app.state.conn)

    def _f(key, default):
        try:
            return float(s.get(key) or default)
        except (TypeError, ValueError):
            return default

    def _i(key, default):
        try:
            return int(float(s.get(key) or default))
        except (TypeError, ValueError):
            return default

    return {
        "chat_model": s["chat_model"],
        "dispatch_url": s["dispatch_url"],
        "memory_enabled": s["memory_enabled"] == "1",
        "skills_enabled": s["skills_enabled"] == "1",
        "memory_review": s["memory_review"] == "1",
        "skills_auto": s["skills_auto"] == "1",
        "temperature": _f("temperature", 0.7),
        "num_ctx": _i("num_ctx", 8192),
        "max_tokens": _i("max_tokens", 0),
        "system_extra": s["system_extra"],
        "internet_enabled": s["internet_enabled"] == "1",
        "user_name": s["user_name"],
        "onboarded": s["onboarded"] == "1",
        "ui_anim": s["ui_anim"] == "1",
        "ui_welcome": s["ui_welcome"] == "1",
        "ui_thinking": s["ui_thinking"] == "1",
        "ui_text_emojis": s["ui_text_emojis"] == "1",
        "search_provider": s["search_provider"],
        "search_results": _i("search_results", 5),
        "search_url": s["search_url"],
        "tools_disabled": s["tools_disabled"],
    }


@app.put("/settings")
async def put_settings(body: dict):
    conn = app.state.conn
    allowed = {
        "chat_model",
        "dispatch_url",
        "system_extra",
        "temperature",
        "num_ctx",
        "max_tokens",
        "user_name",
        "search_provider",
        "search_results",
        "search_url",
        "tools_disabled",
    } | _BOOL_KEYS
    for key in allowed & body.keys():
        val = body[key]
        if key in _BOOL_KEYS:
            val = "1" if val else "0"
        elif key == "temperature":
            try:
                val = min(2.0, max(0.0, float(val)))
            except (TypeError, ValueError):
                continue
        elif key == "num_ctx":
            try:
                val = min(32768, max(512, int(float(val))))
            except (TypeError, ValueError):
                continue
        elif key == "max_tokens":
            try:
                val = min(8192, max(0, int(float(val))))
            except (TypeError, ValueError):
                continue
        elif key == "tools_disabled":
            # Aceita lista (do frontend) ou string JSON; guarda sempre JSON válido,
            # filtrando para nomes de ferramentas reais.
            try:
                items = val if isinstance(val, list) else json.loads(val)
                names = {t["name"] for t in _TOOL_REGISTRY}
                val = json.dumps([n for n in items if n in names])
            except (TypeError, ValueError):
                continue
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(val)),
        )
    conn.commit()
    return await get_settings()


# ---------- Modelos / Compare ----------

@app.get("/models")
async def available_models():
    try:
        return {"models": await oc.list_models()}
    except oc.OllamaError as e:
        raise HTTPException(502, str(e))


@app.post("/compare")
async def compare(body: dict):
    prompt = (body.get("prompt") or "").strip()
    model_a = (body.get("model_a") or "").strip()
    model_b = (body.get("model_b") or "").strip()
    if not prompt or not model_a or not model_b:
        raise HTTPException(400, "prompt e dois modelos são obrigatórios")

    messages = [
        {"role": "system", "content": settings.base_system_prompt},
        {"role": "user", "content": prompt},
    ]

    async def run(model: str) -> dict:
        try:
            text = await oc.chat_once(messages, model=model)
            return {"model": model, "text": text, "error": None}
        except oc.OllamaError as e:
            return {"model": model, "text": "", "error": str(e)}

    left, right = await asyncio.gather(run(model_a), run(model_b))
    return {"left": left, "right": right}


# ---------- Notas ----------

@app.get("/notes")
async def list_notes():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT id, title, content, pinned, created_at, updated_at FROM notes "
        "ORDER BY pinned DESC, updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/notes")
async def create_note(body: dict):
    conn = app.state.conn
    title = (body.get("title") or "").strip()
    content = (body.get("content") or "").strip()
    if not title and not content:
        raise HTTPException(400, "nota vazia")
    cur = conn.execute(
        "INSERT INTO notes (title, content) VALUES (?, ?)", (title[:120], content)
    )
    conn.commit()
    return {"id": cur.lastrowid}


@app.patch("/notes/{note_id}")
async def update_note(note_id: int, body: dict):
    conn = app.state.conn
    fields, params = [], []
    if "title" in body:
        fields.append("title = ?")
        params.append((body.get("title") or "").strip()[:120])
    if "content" in body:
        fields.append("content = ?")
        params.append((body.get("content") or "").strip())
    if "pinned" in body:
        fields.append("pinned = ?")
        params.append(1 if body.get("pinned") else 0)
    if not fields:
        raise HTTPException(400, "nada para atualizar")
    fields.append("updated_at = datetime('now')")
    params.append(note_id)
    cur = conn.execute(f"UPDATE notes SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"nota {note_id} não existe")
    return {"id": note_id}


@app.delete("/notes/{note_id}")
async def delete_note(note_id: int):
    conn = app.state.conn
    cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"nota {note_id} não existe")
    return {"deleted": note_id}


# ---------- Tarefas ----------

@app.get("/tasks")
async def list_tasks():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT id, text, done, created_at FROM tasks ORDER BY done, id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/tasks")
async def create_task(body: dict):
    conn = app.state.conn
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "tarefa vazia")
    cur = conn.execute("INSERT INTO tasks (text) VALUES (?)", (text,))
    conn.commit()
    return {"id": cur.lastrowid}


@app.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: dict):
    conn = app.state.conn
    fields, params = [], []
    if "text" in body:
        t = (body.get("text") or "").strip()
        if not t:
            raise HTTPException(400, "texto vazio")
        fields.append("text = ?")
        params.append(t)
    if "done" in body:
        fields.append("done = ?")
        params.append(1 if body.get("done") else 0)
    if not fields:
        raise HTTPException(400, "nada para atualizar")
    params.append(task_id)
    cur = conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"tarefa {task_id} não existe")
    return {"id": task_id}


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    conn = app.state.conn
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"tarefa {task_id} não existe")
    return {"deleted": task_id}


# ---------- Documentos (editor com IA a assistir) ----------

@app.get("/documents")
async def list_documents():
    conn = app.state.conn
    rows = conn.execute(
        "SELECT id, title, content, updated_at FROM documents ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/documents")
async def create_document(body: dict):
    conn = app.state.conn
    title = (body.get("title") or "Novo documento").strip()
    content = body.get("content") or ""
    cur = conn.execute(
        "INSERT INTO documents (title, content) VALUES (?, ?)", (title[:160], content)
    )
    conn.commit()
    return {"id": cur.lastrowid}


@app.patch("/documents/{doc_id}")
async def update_document(doc_id: int, body: dict):
    conn = app.state.conn
    fields, params = [], []
    if "title" in body:
        fields.append("title = ?")
        params.append((body.get("title") or "").strip()[:160])
    if "content" in body:
        fields.append("content = ?")
        params.append(body.get("content") or "")
    if not fields:
        raise HTTPException(400, "nada para atualizar")
    fields.append("updated_at = datetime('now')")
    params.append(doc_id)
    cur = conn.execute(f"UPDATE documents SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"documento {doc_id} não existe")
    return {"id": doc_id}


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    conn = app.state.conn
    cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"documento {doc_id} não existe")
    return {"deleted": doc_id}


_DOC_ASSIST_SYSTEM = (
    "És um assistente de escrita. O utilizador escreve; tu ajudas. Recebes o TEXTO "
    "atual e uma INSTRUÇÃO. Aplica a instrução e devolve APENAS o texto resultante "
    "(sem comentários, sem aspas à volta). Mantém a língua do texto."
)


@app.post("/documents/assist")
async def document_assist(body: dict):
    content = (body.get("content") or "").strip()
    instruction = (body.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(400, "falta a instrução")
    cfg = _get_settings(app.state.conn)
    messages = [
        {"role": "system", "content": _DOC_ASSIST_SYSTEM},
        {
            "role": "user",
            "content": f"TEXTO:\n{content or '(vazio)'}\n\nINSTRUÇÃO: {instruction}",
        },
    ]
    try:
        out = await oc.chat_once(messages, model=cfg["chat_model"])
    except oc.OllamaError as e:
        raise HTTPException(502, f"assistência falhou: {e}")
    return {"text": out}


# ---------- Dados (backup + danger zone) ----------

@app.get("/data/export")
async def data_export():
    conn = app.state.conn
    facts = [
        dict(r)
        for r in conn.execute(
            "SELECT text, fact_type FROM semantic_facts WHERE is_deleted = 0"
        ).fetchall()
    ]
    skills = [
        dict(r)
        for r in conn.execute("SELECT name, instruction, enabled FROM skills").fetchall()
    ]
    notes = [
        dict(r)
        for r in conn.execute("SELECT title, content, pinned FROM notes").fetchall()
    ]
    tasks = [dict(r) for r in conn.execute("SELECT text, done FROM tasks").fetchall()]
    return {"facts": facts, "skills": skills, "notes": notes, "tasks": tasks}


@app.post("/data/import")
async def data_import(body: dict):
    conn = app.state.conn
    memory: MemoryService = app.state.memory
    added = {"facts": 0, "skills": 0, "notes": 0, "tasks": 0}
    if isinstance(body.get("facts"), list):
        added["facts"] = await memory.import_facts(body["facts"])
    if isinstance(body.get("skills"), list):
        existing = {(r[0] or "").strip() for r in conn.execute("SELECT name FROM skills").fetchall()}
        for s in body["skills"]:
            name = (s.get("name") or "").strip()
            instr = (s.get("instruction") or "").strip()
            if not name or not instr or name in existing:
                continue
            conn.execute(
                "INSERT INTO skills (name, instruction, enabled) VALUES (?, ?, ?)",
                (name[:60], instr, 1 if s.get("enabled", True) else 0),
            )
            existing.add(name)
            added["skills"] += 1
    if isinstance(body.get("notes"), list):
        for n in body["notes"]:
            title = (n.get("title") or "").strip()
            content = (n.get("content") or "").strip()
            if not title and not content:
                continue
            conn.execute(
                "INSERT INTO notes (title, content, pinned) VALUES (?, ?, ?)",
                (title[:120], content, 1 if n.get("pinned") else 0),
            )
            added["notes"] += 1
    if isinstance(body.get("tasks"), list):
        for t in body["tasks"]:
            text = (t.get("text") or "").strip()
            if not text:
                continue
            conn.execute(
                "INSERT INTO tasks (text, done) VALUES (?, ?)",
                (text, 1 if t.get("done") else 0),
            )
            added["tasks"] += 1
    conn.commit()
    return {"added": added}


@app.post("/data/wipe/{target}")
async def data_wipe(target: str):
    conn = app.state.conn
    if target == "chats":
        conn.execute("DELETE FROM turn_vectors")
        conn.execute("DELETE FROM turns")
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM conversations")
    elif target == "memory":
        conn.execute("UPDATE semantic_facts SET is_deleted = 1")
        conn.execute("DELETE FROM fact_vectors")
        conn.execute("DELETE FROM pending_facts")
    elif target == "skills":
        conn.execute("DELETE FROM skills")
        conn.execute("DELETE FROM pending_skills")
    elif target == "notes":
        conn.execute("DELETE FROM notes")
    elif target == "tasks":
        conn.execute("DELETE FROM tasks")
    elif target == "gallery":
        # apagar ficheiros em disco + limpar referências
        try:
            for fn in os.listdir(settings.images_dir):
                fp = os.path.join(settings.images_dir, fn)
                if os.path.isfile(fp):
                    os.remove(fp)
        except OSError as e:
            log.warning("wipe gallery: %s", e)
        conn.execute("UPDATE messages SET image_path = NULL WHERE image_path IS NOT NULL")
    else:
        raise HTTPException(400, f"alvo desconhecido: {target}")
    conn.commit()
    return {"wiped": target}


@app.get("/health")
async def health():
    return {"status": "ok", "chat_model": settings.chat_model, "embed_model": settings.embed_model}
