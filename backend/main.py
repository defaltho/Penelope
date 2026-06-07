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
    PipelineExtractRequest,
    SkillExtraction,
    TransactionExtraction,
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

    system_content = settings.base_system_prompt
    system_extra = (cfg.get("system_extra") or "").strip()
    if system_extra:
        system_content += "\n\n" + system_extra

    # Recuperar + injetar memória (se ativa E não em modo anónimo)
    if cfg["memory_enabled"] == "1" and not req.incognito:
        injection = await memory.retrieve(user_text)
        if injection:
            system_content += "\n\n" + injection

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
    messages = [{"role": "system", "content": system_content}, *history]

    # Anexar a imagem ao último turno do utilizador (só neste pedido).
    if img_b64:
        messages[-1] = {**messages[-1], "images": [img_b64]}

    holder = {"text": ""}

    async def event_gen():
        try:
            async for token in oc.chat_stream(
                messages,
                model=chat_model,
                num_ctx=num_ctx,
                temperature=temperature,
                num_predict=(max_tokens or None),
            ):
                holder["text"] += token
                yield {"event": "token", "data": json.dumps({"token": token})}
        except oc.OllamaError as e:
            log.error("erro de chat: %s", e)
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
            return

        # MODO ANÓNIMO: não grava nada; termina o stream sem persistir.
        if req.incognito:
            yield {"event": "done", "data": json.dumps({"conversation_id": None, "incognito": True})}
            return

        # Persistir resposta do assistente
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, 'assistant', ?)",
            (conversation_id, holder["text"]),
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
        yield {"event": "done", "data": json.dumps({"conversation_id": conversation_id})}

    async def _post_exchange():
        # Corre depois da resposta ser enviada; nunca bloqueia o stream visível.
        # MODO ANÓNIMO: nada de memória nem auto-skills.
        if req.incognito:
            return
        await memory.remember(conversation_id, user_text, holder["text"])
        if _get_settings(conn)["skills_auto"] == "1":
            await _auto_skills(conn, user_text, holder["text"])

    return EventSourceResponse(event_gen(), background=BackgroundTask(_post_exchange))


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
        "SELECT role, content, image_path, created_at FROM messages "
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


@app.delete("/memory/facts/{fact_id}")
async def delete_fact(fact_id: int):
    conn = app.state.conn
    conn.execute("UPDATE semantic_facts SET is_deleted = 1 WHERE id = ?", (fact_id,))
    conn.execute("DELETE FROM fact_vectors WHERE fact_id = ?", (fact_id,))
    conn.commit()
    return {"deleted": fact_id}


# ---------- Agents (loop simples com ferramentas locais seguras) ----------

_AGENT_SYSTEM = (
    "És um agente que cumpre a tarefa do utilizador usando ferramentas LOCAIS. "
    "Ferramentas:\n"
    "- data_hora(): data e hora atuais.\n"
    "- pesquisar_memoria(query): procura factos guardados sobre o utilizador.\n"
    "- criar_nota(titulo, conteudo): cria uma nota.\n"
    "- criar_tarefa(texto): adiciona uma tarefa.\n"
    "- listar_tarefas(): lista as tarefas.\n"
    "- abrir_pagina(url): lê o texto de uma página web (SÓ funciona se a internet "
    "estiver ativada nas Definições; por defeito está desligada).\n\n"
    "A cada passo devolve JSON. Para usar uma ferramenta: {thought, tool, args}. "
    "Quando a tarefa estiver concluída: {thought, final: <resposta ao utilizador>}. "
    "Usa o mínimo de passos possível e não inventes resultados de ferramentas."
)


async def _agent_tool(conn, memory, name: str, args: dict) -> str:
    name = (name or "").strip()
    args = args or {}
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
    if name == "criar_tarefa":
        text = str(args.get("texto") or args.get("text") or "").strip()
        if not text:
            return "erro: tarefa vazia"
        conn.execute("INSERT INTO tasks (text) VALUES (?)", (text,))
        conn.commit()
        return f"tarefa criada: {text}"
    if name == "listar_tarefas":
        rows = conn.execute(
            "SELECT text, done FROM tasks ORDER BY done, id DESC LIMIT 20"
        ).fetchall()
        if not rows:
            return "sem tarefas"
        return "Tarefas: " + " | ".join(
            ("[x] " if r["done"] else "[ ] ") + r["text"] for r in rows
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
    return f"erro: ferramenta desconhecida '{name}'"


@app.post("/agent/run")
async def agent_run(req: AgentRunRequest):
    conn = app.state.conn
    memory: MemoryService = app.state.memory
    task = req.task.strip()
    if not task:
        raise HTTPException(400, "tarefa vazia")

    convo = [f"Tarefa: {task}"]
    steps: list[dict] = []
    final: str | None = None
    MAX_STEPS = 5

    for _ in range(MAX_STEPS):
        messages = [
            {"role": "system", "content": _AGENT_SYSTEM},
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

        obs = await _agent_tool(conn, memory, step.tool, step.args or {})
        steps.append(
            {"thought": step.thought, "tool": step.tool, "args": step.args or {}, "observation": obs}
        )
        convo.append(f"Ação: {step.tool}({step.args or {}}) -> {obs}")

    if final is None:
        final = "(atingi o limite de passos sem concluir a tarefa)"
    return {"steps": steps, "final": final}


# ---------- Pipeline de estruturação (Stage 3) ----------

_PIPELINE_SYSTEM = (
    "És um extrator de transações financeiras. A partir do texto fornecido (que pode "
    "ser a transcrição de um recibo/extrato), devolve uma transação estruturada. "
    "REGRAS: para qualquer campo ausente devolve null (NUNCA inventes). Confia em "
    "números, datas e totais; comerciante e categoria são menos fiáveis: se tiveres "
    "dúvida, inclui o nome do campo em low_confidence_fields. Datas em ISO "
    "YYYY-MM-DD; amount e currency a partir do total. Responde só com o JSON do schema."
)


@app.post("/pipeline/extract", response_model=TransactionExtraction)
async def pipeline_extract(req: PipelineExtractRequest):
    source_text = req.text.strip()

    # Se vier imagem: transcrever primeiro (texto->JSON é mais fiável que JSON direto).
    if req.image_base64 and req.image_base64.strip():
        raw = _decode_image(req.image_base64)
        jpeg = _resize_to_jpeg_bytes(raw, settings.vision_max_dim)
        img_b64 = base64.b64encode(jpeg).decode("ascii")
        try:
            transcription = await oc.vision_describe(
                img_b64,
                prompt="Transcreve TODO o texto visível nesta imagem, exatamente como aparece.",
            )
        except oc.OllamaError as e:
            raise HTTPException(502, f"transcrição falhou: {e}")
        source_text = (source_text + "\n\n" + transcription).strip() if source_text else transcription

    if not source_text:
        raise HTTPException(400, "fornece texto ou imagem")

    messages = [
        {"role": "system", "content": _PIPELINE_SYSTEM},
        {"role": "user", "content": f"Texto:\n{source_text}\n\nExtrai a transação."},
    ]
    try:
        raw_json = await oc.extract_json(
            messages, schema=TransactionExtraction.model_json_schema()
        )
        return TransactionExtraction.model_validate(raw_json)
    except (oc.OllamaError, Exception) as e:  # noqa: BLE001
        log.error("extração de pipeline falhou: %s", e)
        raise HTTPException(502, f"extração falhou: {e}")


@app.post("/pipeline/dispatch")
async def pipeline_dispatch(tx: TransactionExtraction):
    conn = app.state.conn
    # Registar sempre localmente (Stage 3, passo "registar + aprender").
    cur = conn.execute(
        "INSERT INTO transactions (date, amount, currency, merchant, category, account, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (tx.date, tx.amount, tx.currency, tx.merchant, tx.category, tx.account, tx.notes),
    )
    tx_id = cur.lastrowid
    conn.commit()

    dispatch_url = _get_settings(conn)["dispatch_url"]
    dispatched = False
    detail = "guardado localmente (sem endpoint de destino configurado)"
    # GATE DE INTERNET (fail-closed): nenhuma saída sem o utilizador ligar a internet.
    if dispatch_url and not _internet_allowed(conn):
        detail = "guardado localmente (acesso à internet desligado — ativa-o nas Definições)"
    elif dispatch_url:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(dispatch_url, json=tx.model_dump())
                r.raise_for_status()
            dispatched = True
            detail = f"despachado para {dispatch_url}"
            conn.execute("UPDATE transactions SET dispatched = 1 WHERE id = ?", (tx_id,))
            conn.commit()
        except Exception as e:  # noqa: BLE001
            detail = f"falha ao despachar: {e} (guardado localmente)"

    return {"id": tx_id, "dispatched": dispatched, "detail": detail}


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
