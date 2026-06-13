"""Cliente assíncrono do Ollama: chat em streaming, embeddings e structured output.

EmbeddingGemma exige prefixos de tarefa (verificámos que o template do Ollama é só
`{{ .Prompt }}`, não os injeta). Aplicamos manualmente:
  - query    -> "task: search result | query: <texto>"
  - document -> "title: none | text: <texto>"
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Literal

from ollama import AsyncClient

from config import settings


class OllamaError(RuntimeError):
    """Erro tipado para que o caminho de chat/memória nunca rebente em silêncio."""


# O AsyncClient (httpx) fica ligado ao event loop em que é criado. Em produção há
# um único loop (uvicorn); nos testes o pytest-asyncio cria um loop por teste. Por
# isso cacheamos um cliente por loop em vez de um singleton global.
_clients: dict[int, AsyncClient] = {}


def _client() -> AsyncClient:
    loop = asyncio.get_running_loop()
    c = _clients.get(id(loop))
    if c is None:
        c = AsyncClient(host=settings.ollama_url)
        _clients[id(loop)] = c
    return c

_EMBED_PREFIX = {
    "query": "task: search result | query: ",
    "document": "title: none | text: ",
}


async def chat_stream(
    messages: list[dict],
    *,
    model: str | None = None,
    num_ctx: int | None = None,
    temperature: float | None = None,
    num_predict: int | None = None,
    repeat_penalty: float | None = None,
    min_p: float | None = None,
) -> AsyncIterator[str]:
    """Faz stream da resposta do assistente, token a token, via /api/chat.

    `repeat_penalty`/`min_p` só são enviados quando definidos. O formato do prompt
    é tratado pelo template embebido no modelo, não aqui.
    """
    options = {
        "num_ctx": num_ctx or settings.num_ctx,
        "temperature": settings.chat_temperature if temperature is None else temperature,
    }
    if num_predict:  # 0/None = sem limite (default do modelo)
        options["num_predict"] = num_predict
    if repeat_penalty is not None:
        options["repeat_penalty"] = repeat_penalty
    if min_p is not None:
        options["min_p"] = min_p
    try:
        stream = await _client().chat(
            model=model or settings.chat_model,
            messages=messages,
            stream=True,
            options=options,
        )
        async for chunk in stream:
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                yield piece
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"chat_stream falhou: {e}") from e


async def embed(text: str, *, kind: Literal["query", "document"]) -> list[float]:
    """Devolve um embedding de 768 floats, aplicando o prefixo de tarefa correto."""
    prefixed = _EMBED_PREFIX[kind] + text
    try:
        resp = await _client().embeddings(model=settings.embed_model, prompt=prefixed)
        vec = list(resp["embedding"])
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"embed falhou: {e}") from e
    if len(vec) != settings.embed_dim:
        raise OllamaError(
            f"dimensão de embedding inesperada: {len(vec)} != {settings.embed_dim}"
        )
    return vec


async def extract_json(
    messages: list[dict],
    *,
    schema: dict,
    model: str | None = None,
    num_ctx: int | None = None,
) -> dict:
    """Chamada estruturada (format=schema, temperature 0).

    Devolve o JSON já parseado (dict). Levanta OllamaError em falha de rede ou
    JSON inválido; o chamador decide o fallback (tipicamente NOOP / lista vazia).

    Faz duas tentativas: primeiro com think=False (mais rápido); se o qwen3-vl
    devolver conteúdo vazio, repete deixando o thinking ativo e remove o bloco
    <think>...</think> da resposta antes de parsear.
    """
    mdl = model or settings.extract_model
    nctx = num_ctx or settings.num_ctx

    async def _call(think: bool | None) -> str:
        kwargs = dict(
            model=mdl, messages=messages, format=schema,
            options={"num_ctx": nctx, "temperature": 0},
        )
        if think is not None:
            kwargs["think"] = think
        resp = await _client().chat(**kwargs)
        return resp.get("message", {}).get("content", "").strip()

    try:
        content = await _call(think=False)
        if not content:
            content = _strip_think(await _call(think=None))
    except TypeError:
        # Cliente sem o parâmetro think=
        content = _strip_think(await _call(think=None))
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"extract_json falhou: {e}") from e

    if not content:
        raise OllamaError("modelo devolveu conteúdo vazio")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise OllamaError(f"JSON inválido do modelo: {content[:200]!r}") from e


async def chat_once(
    messages: list[dict],
    *,
    model: str,
    num_ctx: int | None = None,
    temperature: float | None = None,
) -> str:
    """Resposta completa (não-streaming) de um modelo. Usado pelo Compare."""
    try:
        resp = await _client().chat(
            model=model,
            messages=messages,
            options={
                "num_ctx": num_ctx or settings.num_ctx,
                "temperature": settings.chat_temperature if temperature is None else temperature,
            },
        )
        return _strip_think(resp.get("message", {}).get("content", "").strip())
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"chat_once ({model}) falhou: {e}") from e


async def vision_describe(
    image_b64: str,
    *,
    prompt: str,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """OCR/transcrição livre de uma imagem (texto, não JSON). temperature 0.

    Usada pelo pipeline (Stage 3): transcrever a imagem primeiro, depois fazer
    a extração estruturada texto->JSON (o structured output direto sobre imagem
    é pouco fiável; texto->JSON é robusto).
    """
    messages = [{"role": "user", "content": prompt, "images": [image_b64]}]
    try:
        resp = await _client().chat(
            model=model or settings.vision_model,
            messages=messages,
            options={"num_ctx": num_ctx or settings.num_ctx, "temperature": 0},
        )
        return _strip_think(resp.get("message", {}).get("content", "").strip())
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"vision_describe falhou: {e}") from e


def _strip_think(text: str) -> str:
    """Remove um bloco <think>...</think> (ou prefixo até </think>) do output."""
    import re
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "</think>" in text:  # caso o <think> de abertura não venha
        text = text.split("</think>", 1)[1]
    return text.strip()


async def list_models() -> list[str]:
    """Nomes dos modelos disponíveis no Ollama (para o health check)."""
    try:
        resp = await _client().list()
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"list falhou: {e}") from e
    out = []
    for m in resp.get("models", []):
        name = m.get("model") or m.get("name")
        if name:
            out.append(name)
    return out
