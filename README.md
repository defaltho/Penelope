# Penelope

```
───────────────────────────────────────────────
 ⊹ ࣪ ˖   Penelope vers. 1.2
───────────────────────────────────────────────
```

A **local-first** AI assistant: chat with persistent memory, general-purpose
vision, notes and tasks, a transaction-structuring pipeline, an **AI Dungeon**
game mode, and global search. Inspired by the UX/UI of the Odysseus project, but
minimalist. It runs offline, with your data on your machine.

Penelope is yours. Open source and free: no sales team, no demo request, no
hidden cloud calls. It runs on your hardware, with your data, local-first and
private.

---

## Table of contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Manual setup](#manual-setup)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Stack](#stack)
- [Security](#security)
- [Credits and attributions](#credits-and-attributions)
- [Documentation](#documentation)

---

## Features

- **Multimodal chat**: text, **images** (vision) and **text/code files**
  (`.md`, `.csv`, `.json`, `.py`, `.ts`, and more, read and appended to the
  context). With a model selector, tok/s, copy, regenerate and context window.
- **Fluid response experience**: smooth streaming with a cursor, **real-time
  progress indicators** (web search, memory retrieval, thinking), a verb-based
  spinner per theme, a collapsible **reasoning panel**, and **rich markdown**
  (code blocks with copy, lists, tables, links).
- **Composer** with multiline input (Shift+Enter), a message **queue** while a
  response is in flight, and send history (up/down arrows). Status bar with
  Ollama health.
- **Persistent memory** that learns facts about you (view, search, edit, archive,
  restore). Retrieved context is **isolated against prompt injection**, and sync
  is ordered per conversation.
- **Skills**: reusable instructions injected into the system prompt.
- **Gallery** of attached images; **Notes** and **Tasks**.
- **Pipeline**: extracts structured transactions from text or image and dispatches
  them.
- **Compare**: two models side by side.
- **Global search** (Ctrl/Cmd+K) across all conversations.
- **Chat commands** (type `/` in the composer): `/help`, `/aidungeon`, `/new`,
  `/model`, `/search`, `/incognito`, `/think`, `/image`, `/retry`. The menu adapts
  to context (normal chat vs adventure).
- **AI Dungeon** (`/aidungeon`): a text game with the **Harbinger-24B** model and
  its official sampler (temp 0.8, repetition penalty 1.05, min-p 0.025) in ChatML.
  Do / Say / Story plus Continue modes, Retry / Undo / Edit, and persistent context
  with `/remember`, `/note` and `/card`. Stories are saved in the **Adventures**
  tab. Without Harbinger installed, it falls back to the reserve model (qwen3-vl).
- **Agent Tools** (Agents view and Settings → Agent Tools): local tools with a
  per-tool on/off toggle. The dangerous ones (`bash`, `python`, `write_file`) are
  **off by default**; even when enabled, each call requests **inline approval**
  (allow once / this session / always / deny).
- **Settings**: model, dispatch, toggles, and a switchable **theme**.

---

## Prerequisites

Penelope needs three tools on your `PATH`. The bootstrap in
[Quick start](#quick-start) can install them for you; this table is the reference.

| Tool | Minimum | Why | Install |
|---|---|---|---|
| [Ollama](https://ollama.com) | **0.12.7** | Runs the local models (chat, vision, embeddings). 0.12.7 is required for Qwen3-VL. | [ollama.com/download](https://ollama.com/download) |
| [uv](https://docs.astral.sh/uv/) | latest | Python 3.12 toolchain and backend dependencies, with no manual virtualenv. | [astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| [Node.js](https://nodejs.org) | **18+** | Builds and serves the SvelteKit frontend. | [nodejs.org](https://nodejs.org) |

**Hardware.** Penelope targets modest machines. The only setting that changes
between them is the chat model:

| Machine | Chat / vision model | Note |
|---|---|---|
| macOS (Apple Silicon, 16 GB+) | `qwen3-vl:8b` (~6 GB) | Default. |
| Windows / Linux (8 GB VRAM, e.g. RTX 3060) | `qwen3-vl:4b` (~3.3 GB) | Set `ASSISTANT_CHAT_MODEL=qwen3-vl:4b` (see [Configuration](#configuration)). |

Embeddings and vector search run on the **CPU** and use **zero VRAM**, so all the
GPU memory stays with the chat/vision model.

---

## Quick start

```bash
git clone https://github.com/defaltho/Penelope.git
cd Penelope
```

If you have **none** of the prerequisites yet, run the one-time bootstrap. It
detects what is missing, asks before installing each tool (Ollama, uv, Node),
pulls the models, and links the `penelope` command:

```bash
# macOS / Linux
bin/setup
```

```powershell
# Windows (PowerShell or cmd, from the project folder)
bin\setup.cmd
```

When it finishes, start everything with a single command:

```bash
penelope          # macOS / Linux
```

```powershell
bin\penelope.cmd  # Windows
```

This brings up Ollama (if needed), the backend, and the frontend, then opens the
browser at <http://localhost:5173>. Press `Ctrl+C` to stop everything.

> Already have the prerequisites installed? Skip the bootstrap and follow
> [Manual setup](#manual-setup).

---

## Manual setup

### 1. Pull the models

```bash
ollama pull qwen3-vl:8b        # 8 GB VRAM: use qwen3-vl:4b instead
ollama pull embeddinggemma     # embeddings (CPU, zero VRAM)

# optional, for AI Dungeon mode (~14 GB):
ollama pull hf.co/LatitudeGames/Harbinger-24B-GGUF:Q4_K_M
```

The `penelope` launcher also pulls any missing model automatically on first run.

### 2. Run

**One command (recommended).** The launcher starts Ollama, the backend (uvicorn,
port 8000) and the frontend (port 5173), and opens the browser:

```bash
# macOS / Linux
penelope
```

```powershell
# Windows (PowerShell or cmd, from the project folder)
bin\penelope.cmd
```

To call `penelope` from any folder, put the launcher on your `PATH`:

```bash
# macOS / Linux (ensure ~/.local/bin is on your PATH)
ln -s "$PWD/bin/penelope" ~/.local/bin/penelope
```

On **Windows**, add the project's `bin` folder to your user `PATH`
(Settings → Environment Variables). PowerShell 5.1 (built in) or 7+ both work;
internally the launcher uses [`bin/penelope.ps1`](bin/penelope.ps1).

**Two processes (any OS).** If you prefer to run the parts yourself:

```bash
# Backend — port 8000
cd backend
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

```bash
# Frontend — port 5173 (proxies /api -> backend)
cd frontend
npm install
npm run dev
```

### 3. Verify

1. Open <http://localhost:5173>.
2. The status bar should report **Ollama: healthy** and a model name.
3. Send a message; the response should stream token by token.

If anything fails, see [Troubleshooting](#troubleshooting).

---

## Configuration

The backend reads `backend/.env` at startup. All settings are optional; defaults
target the macOS profile.

```ini
# backend/.env

# Chat / vision model (use the 4B model on 8 GB VRAM machines)
ASSISTANT_CHAT_MODEL=qwen3-vl:4b

# Embeddings model (CPU)
ASSISTANT_EMBED_MODEL=embeddinggemma

# Ollama endpoint (default shown)
ASSISTANT_OLLAMA_URL=http://127.0.0.1:11434
```

> All settings use the `ASSISTANT_` prefix (see `backend/config.py`). Other useful
> keys: `ASSISTANT_NUM_CTX` (context window), `ASSISTANT_VISION_MAX_DIM` (image
> downscaling), `ASSISTANT_DISPATCH_URL` (pipeline webhook).

> **Windows / RTX 3060 (8 GB VRAM):** the only required change from the macOS
> defaults is `ASSISTANT_CHAT_MODEL=qwen3-vl:4b`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ollama: command not found` / status bar shows Ollama unhealthy | Install Ollama from [ollama.com](https://ollama.com) and make sure it is on your `PATH`. The launcher starts the server, but the binary must exist. |
| Out of VRAM, or the model is very slow on 8 GB | Switch to the 4B model: `ollama pull qwen3-vl:4b` and set `ASSISTANT_CHAT_MODEL=qwen3-vl:4b` in `backend/.env`. |
| Windows: `running scripts is disabled on this system` | Use `bin\penelope.cmd` (it passes `-ExecutionPolicy Bypass`). To run the script by hand: `pwsh -ExecutionPolicy Bypass -File bin\penelope.ps1`. |
| Port 8000 or 5173 already in use | Stop the process using it, or start the backend on another port and update the frontend proxy. |
| Qwen3-VL fails to load | Check your Ollama version: `ollama --version` must be **≥ 0.12.7**. |
| First reply is slow | The first request loads the model into memory; later ones are fast. |

---

## Stack

- **Backend**: Python + FastAPI (managed by `uv`, Python 3.12), SSE for chat.
  Mem0-style memory in SQLite + sqlite-vec + FTS5 (a single file).
- **Frontend**: SvelteKit (Svelte 5 + runes), One Dark theme + Fira Code.
- **Models** (via local [Ollama](https://ollama.com)):
  - `qwen3-vl:8b` (or `:4b`): chat + vision
  - `embeddinggemma`: embeddings (CPU, zero VRAM)

---

## Security

Internet access and the `bash` / `python` tools are off in code until you enable
them in Settings, and running a dangerous tool requires explicit approval. The
model always runs offline.

---

## Credits and attributions

Penelope is an **independent, local-first** implementation, written from scratch.
It is not a git fork of any of the projects below: it rebuilds the concepts to fit
modest hardware and the offline invariant. Even so, it **draws inspiration and
adapts** ideas, patterns and (where noted) configuration from these projects, with
thanks:

- **[Odysseus](https://github.com/pewdiepie-archdaemon/odysseus)** (PewDiePie):
  design/UX inspiration, the `[ icon rail | view ]` layout, the theme and the Lucide
  icons.
- **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** (Nous Research, MIT):
  terminal UX patterns adapted to web chat (a real-time progress activity lane, the
  verb-based spinner, the reasoning panel, inline tool approvals) and memory patterns
  (anti-injection fencing, per-conversation ordered sync, recoverable archive,
  "umbrella" consolidation).
- **[Harbinger-24B](https://huggingface.co/LatitudeGames/Harbinger-24B)** (Latitude Games):
  the model behind AI Dungeon mode, with the official sampler (temp 0.8 / rep 1.05 /
  min-p 0.025) and system message used **verbatim**.
- **[AI Dungeon](https://aidungeon.com)** (Latitude): the game-mode mechanics
  (Do/Say/Story, Continue, Memory / Author's Note / Story Cards).

Each project belongs to its respective authors and keeps its own license. Penelope
does not redistribute code from those repositories; it only reuses ideas and the
public model configuration, in the spirit of giving due credit.

---

## Documentation

- [`CLAUDE.md`](CLAUDE.md): full technical context and architecture decisions.
