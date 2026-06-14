> Generated: 2026-06-11

# Project Documentation

## Table of Contents
- [Overview](#overview)
- [Setup](#setup)
- [Architecture](#architecture)
- [Frontend](#frontend)
- [CLI](#cli)
- [Reference](#reference)

---

## Overview

### README.md
_Source: `README.md`_

Penelope is a **local-first** AI assistant with persistent memory, general-purpose vision, notes/tasks, a transaction-structuring pipeline, an AI Dungeon game mode, and global search. Runs offline with all data on the user's machine. Open source.

**Stack:**
- **Backend:** Python + FastAPI, SSE streaming. Mem0-style memory in SQLite + sqlite-vec + FTS5 (single file).
- **Frontend:** SvelteKit (Svelte 5 + runes), One Dark theme + Fira Code.
- **Models** (via Ollama): `qwen3-vl:8b` (chat + vision), `embeddinggemma` (embeddings, CPU, zero VRAM).

**Features:**
- Multimodal chat (text, images, code/text files via drag-and-drop or attach)
- Fluid streaming with real-time progress indicators, reasoning panel, rich markdown
- Composer with multiline input, message queue, send history, slash commands (`/help`, `/clear`, `/compact`, `/model`, `/search`, etc.)
- Persistent semantic memory (extract/consolidate/retrieve, anti-injection fencing)
- Skills (reusable instructions), Gallery, Notes + Tasks (unified "Bloco" tab), Documents
- Pipeline (structured transaction extraction from text/image)
- Compare (two models side by side), Global search (Ctrl+K)
- AI Dungeon mode (`/aidungeon`) with Harbinger-24B, Do/Say/Story modes, persistent context
- Agent Tools with per-tool on/off toggle and inline approval for dangerous operations
- Native browser notifications when responses arrive in background tabs
- CLI interface (`python -m cli`) for terminal-based interaction

---

## Setup

### Quick Start (Bootstrap)

From the project root:

```bash
# macOS / Linux
bin/setup

# Windows (PowerShell or cmd)
bin\setup.cmd
```

This detects missing prerequisites (Ollama, uv, Node), installs them, pulls models, and links the `penelope` command.

### One-Command Launch

```bash
# macOS / Linux
penelope

# Windows
bin\penelope.cmd
```

Starts Ollama + backend + frontend and opens the browser. Ctrl+C to stop.

### Manual (Two Processes)

```bash
# Backend (port 8000)
cd backend
uv run uvicorn main:app --host 127.0.0.1 --port 8000

# Frontend (port 5173, proxies /api -> backend)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Windows Notes

- **RTX 3060 / 8GB VRAM:** use `qwen3-vl:4b`. Pull with `ollama pull qwen3-vl:4b` and set `ASSISTANT_CHAT_MODEL=qwen3-vl:4b` in `backend/.env`.
- **ExecutionPolicy:** `bin\penelope.cmd` handles this automatically via `-ExecutionPolicy Bypass`.

### Model Installation

```bash
ollama pull qwen3-vl:8b           # Mac (24GB) — or qwen3-vl:4b for Windows 8GB
ollama pull embeddinggemma         # CPU embeddings, zero VRAM
ollama pull hf.co/LatitudeGames/Harbinger-24B-GGUF:Q4_K_M   # optional, AI Dungeon
```

---

## Architecture

### CLAUDE.md
_Source: `CLAUDE.md`_

Complete technical architecture document. Key decisions and invariants:

#### Non-Negotiable Invariant
**Local-first, always.** No dependency on cloud services on the main path. All data on the user's machine.

#### Target Hardware

| Machine | Specs | Role |
|---|---|---|
| Mac | M5 Pro, 24GB unified, MLX | Development/prototype |
| Windows | RTX 3060 8GB, i7-10700, 32GB RAM, CUDA | Secondary deployment |

Embeddings (EmbeddingGemma) and vector search (sqlite-vec) run on **CPU/SQLite, zero VRAM**. All VRAM reserved for the chat model.

#### Models

| Function | Mac | Windows | Notes |
|---|---|---|---|
| Chat + Vision + OCR | qwen3-vl:8b (~6.1GB) | qwen3-vl:4b (~3.3GB) | Single model for chat and OCR |
| Alternative chat | gemma4:12b-mlx | gemma4:e4b | Stronger European language tuning |
| Embeddings | embeddinggemma (CPU) | embeddinggemma (CPU) | 300M params, 100+ languages |

Single multimodal model (Qwen3-VL) for both chat and OCR/vision eliminates model-switch penalty on 8GB.

#### Stack Diagram

```
Frontend: SvelteKit (Svelte 5 + Runes)
    │ HTTP/SSE (localhost)
Backend: Python / FastAPI (single process)
    ├── Ollama (qwen3-vl)
    ├── SQLite + sqlite-vec + FTS5 (1 file)
    └── EmbeddingGemma (CPU, zero VRAM)
```

#### Memory Architecture (Two Layers, Single SQLite)

**Layer A — Semantic Facts:** After each exchange, extract durable facts via JSON-schema. Embed with EmbeddingGemma, store in sqlite-vec. On write: compare top-k similar existing facts, decide ADD/UPDATE/DELETE/NOOP. Anti-injection: recovered memory wrapped in `<memoria>` tags.

**Layer B — Conversation History:** Literal messages in SQLite (FTS5 for keyword search) + embeddings in sqlite-vec for semantic retrieval.

**Injection at retrieval:** embed query → top-k facts + top-k past turns → inject into system prompt.

#### File Structure

```
project/
├── CLAUDE.md              # architecture docs
├── backend/
│   ├── main.py            # FastAPI endpoints
│   ├── ollama_client.py   # Ollama client (chat stream, embeddings)
│   ├── memory.py          # extract → consolidate → retrieve
│   ├── db.py              # SQLite + sqlite-vec + FTS5
│   ├── config.py          # Settings (models, paths)
│   ├── schemas.py         # Pydantic models
│   └── adventure.py       # AI Dungeon file store
├── frontend/              # SvelteKit
├── cli/                   # Terminal CLI (click + httpx + rich)
├── bin/                   # Launcher scripts
└── data/
    ├── memory.db          # single database file
    ├── images/            # attached images
    └── adventures/        # adventure JSON files
```

#### Phased Build Plan

- **Stage 1** (DONE): Chat + memory
- **Stage 2** (DONE): General-purpose vision (OCR via Qwen3-VL)
- **Stage 3** (DONE): Transaction structuring pipeline + dispatch
- **Management layer** (DONE): Chats, Memory, Skills, Gallery, Notes, Tasks, Documents, Adventures, Agents, Compare

---

## Frontend

### frontend/README.md
_Source: `frontend/README.md`_

SvelteKit (Svelte 5 + runes) UI. One Dark theme + Fira Code. Communicates with backend over HTTP/SSE.

#### Development

```bash
cd frontend
npm install
npm run dev          # Vite dev server on :5173, proxies /api -> backend :8000
```

#### Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server with HMR |
| `npm run check` | svelte-check (types + diagnostics) |
| `npm run build` | Production build |
| `npm run preview` | Preview production build |

#### Layout

```
src/
├── routes/+page.svelte      # app shell (sidebar + active view)
├── lib/
│   ├── api.ts               # backend helpers
│   ├── chat.ts              # SSE streaming
│   ├── stream-buffer.ts     # smooth token rendering
│   ├── commands.ts          # slash command definitions
│   ├── markdown.ts          # markdown renderer
│   ├── notifications.ts     # browser notification utility
│   ├── components/          # Icon, Spinner, ActivityLane, Markdown, NavSidebar...
│   └── views/               # ChatView, WorkspaceView, CompareView, SettingsView...
└── app.html                 # document shell
```

#### Key Components

- **ChatView** — main chat with streaming, file drag-and-drop, slash commands, adventure mode
- **WorkspaceView** — unified Notes + Tasks tab with sub-tab switcher
- **AdventureSetup** — creation modal for AI Dungeon (scenario/hero/instructions form)
- **NavSidebar** — navigation with conversation list, view switching

---

## CLI

### cli/
_Source: `cli/` directory_

Terminal interface for Penelope. Communicates with the running backend via HTTP (localhost:8000).

#### Dependencies

- `click` (CLI framework, already in backend venv)
- `httpx` (HTTP client, already in backend venv)
- `rich` (terminal rendering — markdown, tables, colours)

#### Usage

```bash
cd Penelope
backend\.venv\Scripts\python.exe -m cli <command>
```

#### Commands

| Command | Description |
|---|---|
| `cli chat "message"` | Send message, stream response to terminal |
| `cli chat "msg" --model X` | Use specific model |
| `cli chat "msg" --incognito` | Anonymous mode (nothing saved) |
| `cli chat "msg" --markdown` | Render response as rich markdown |
| `cli status` | Check backend health, list installed models |
| `cli memory list` | List semantic facts |
| `cli memory search "query"` | Semantic search in memory |
| `cli task list` | List tasks (pending + done) |
| `cli task add "text"` | Create a task |
| `cli task done <id>` | Mark task as completed |
| `cli task rm <id>` | Delete a task |
| `cli note list` | List notes |
| `cli config list` | List all settings |
| `cli config get <key>` | Read a setting value |
| `cli config set <key> <value>` | Change a setting |

#### Architecture

```
cli/
├── __init__.py
├── __main__.py          # entry point (click group)
├── client.py            # PenelopeClient (httpx, SSE parser)
├── render.py            # rich rendering (markdown, tables, fallback to plain text)
└── commands/
    ├── chat.py          # streaming chat
    ├── status.py        # health check
    ├── memory.py        # fact management
    ├── tasks.py         # task CRUD
    ├── notes.py         # note listing
    └── config.py        # settings read/write
```

---

## Reference

### API Endpoints (Backend)

**Chat:**
- `POST /chat` — streaming SSE response with memory injection
- `POST /chat/compact` — summarize and compact conversation context

**Conversations:**
- `GET /conversations` | `POST /conversations` | `GET /conversations/{id}/messages`
- `PATCH /conversations/{id}` | `DELETE /conversations/{id}`

**Adventures (AI Dungeon):**
- `GET /adventures` | `POST /adventures` | `GET /adventures/{id}`
- `PATCH /adventures/{id}` | `DELETE /adventures/{id}` | `POST /adventures/{id}/turn`

**Memory:**
- `GET /memory/facts` | `PATCH /memory/facts/{id}` | `DELETE /memory/facts/{id}`
- `POST /memory/facts/{id}/restore` | `DELETE /memory/facts/{id}/purge`
- `GET /memory/pending` | `POST /memory/pending/{id}/approve` | `DELETE /memory/pending/{id}`
- `GET /memory/export` | `POST /memory/import` | `GET /memory/facts/archived`

**Skills:**
- `GET /skills` | `POST /skills` | `PATCH /skills/{id}` | `DELETE /skills/{id}`
- `GET /skills/export` | `POST /skills/import`
- `GET /skills/pending` | `POST /skills/pending/{id}/approve` | `DELETE /skills/pending/{id}`

**Notes & Tasks:**
- `GET /notes` | `POST /notes` | `PATCH /notes/{id}` | `DELETE /notes/{id}`
- `GET /tasks` | `POST /tasks` | `PATCH /tasks/{id}` | `DELETE /tasks/{id}`

**Documents:**
- `GET /documents` | `POST /documents` | `PATCH /documents/{id}` | `DELETE /documents/{id}`
- `POST /documents/assist`

**Other:**
- `GET /gallery` | `GET /models` | `POST /compare`
- `GET /settings` | `PUT /settings`
- `GET /search` | `POST /search/web`
- `GET /agent/tools` | `POST /agent/run`
- `GET /data/export` | `POST /data/import` | `POST /data/wipe/{target}`
- `GET /health`

### Slash Commands (Frontend)

**Global:** `/help`, `/new`, `/clear`, `/compact`, `/search`, `/image`, `/retry`
**Both modes:** `/model`, `/incognito`, `/think`
**Adventure — Actions:** `/fazer`, `/dizer`, `/historia`, `/continuar`
**Adventure — Editing:** `/repetir`, `/retroceder`, `/refazer`, `/editar`
**Adventure — Context:** `/lembrar`, `/nota`, `/cartao`, `/personagem`, `/cenario`
**Adventure — Management:** `/guardar`, `/aventuras`, `/sair`, `/ajuda`

### Credits

- **Odysseus** (PewDiePie): design/UX inspiration, layout, theme, Lucide icons
- **Hermes Agent** (Nous Research): terminal UX patterns, memory patterns
- **Harbinger-24B** (Latitude Games): AI Dungeon model + official sampler
- **AI Dungeon** (Latitude): game-mode mechanics (Do/Say/Story, Memory, Story Cards)
