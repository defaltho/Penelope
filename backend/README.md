# Penelope: backend

Python + FastAPI backend for Penelope, the local-first AI assistant. Single
process; managed by [`uv`](https://docs.astral.sh/uv/) (Python 3.12). Streams chat
over SSE and stores Mem0-style memory in a single SQLite file
(sqlite-vec + FTS5).

For the full project overview and the one-command launcher, see the
[root README](../README.md).

## Run

```bash
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Requires a local [Ollama](https://ollama.com) with the models pulled
(`qwen3-vl:8b` for chat + vision, `embeddinggemma` for embeddings). All embeddings
and vector search run on CPU/SQLite, so they use zero VRAM.

## Configuration

Settings are read from the environment (and `backend/.env` at startup). Common keys:

- `ASSISTANT_CHAT_MODEL` — chat/vision model (default `qwen3-vl:8b`; use
  `qwen3-vl:4b` on 8GB GPUs).
- `vision_max_dim` — longer-side limit for attached images before they are sent to
  the model.

## Layout

```
backend/
├── main.py            # FastAPI app: /chat (SSE, multimodal), /conversations,
│                      #   /memory/facts, /images (StaticFiles), /pipeline…
├── ollama_client.py   # Ollama calls (chat stream + embeddings)
├── memory.py          # extract -> consolidate -> retrieve; search/edit
├── adventure.py       # AI Dungeon mode (Harbinger-24B sampler in ChatML)
├── db.py              # SQLite + sqlite-vec + FTS5 (one file) + migrations
├── config.py          # Settings (models, paths, images_dir, vision_max_dim)
└── schemas.py         # Pydantic models (ChatRequest with image_base64…)
```

Local data (`data/`: `memory.db`, attached images, adventures) is gitignored and
never leaves your machine.
