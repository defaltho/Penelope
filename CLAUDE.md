# CLAUDE.md — Local-First Assistant (chat + memory + OCR/pipeline)

> This file gives Claude Code the COMPLETE context of the project, including the
> research that backs each technical decision. Read it in full before building.
> Dates and versions valid as of June 2026.

---

## 1. Overview and goal

A **local-first** AI assistant, running **offline**, with **persistent long-term
memory** that continuously learns from interactions, **OCR/vision** via a local
multimodal model, and an **automation pipeline** that structures text and images
into JSON and sends them to a target application of its own (still to be built, of
the private personal-finance management kind).

Multilingual, with **excellent quality in English and Portuguese**.

**Philosophy:** inspired by the visual style / UX / local-first nature of projects
like Odysseus (by PewDiePie) and Hermes Agent (Nous Research), but more minimalist
and lightweight, tuned to the target hardware. The historical core is: **chat,
persistent memory, text+image structuring pipeline.** The project is **open to
changing direction** (new features, patterns adopted from other projects), but each
addition is evaluated case by case against the local-first invariant and the hardware
budget: anything that would overload the modest machine (e.g. heavy autonomous agents,
deep research, image generation) stays out of scope until there is a lightweight,
offline way to do it.

> **Non-negotiable invariant: local-first, always.** Penelope runs offline, with the
> data on the user's machine, with no dependency on cloud services on the main path.
> Any change of direction is evaluated first against this invariant.

---

## 2. Target hardware

| Machine | Specs | Role |
|---|---|---|
| **Mac (prototype HERE first)** | M5 Pro, 24GB unified memory, MLX, 307 GB/s bandwidth | Development and prototype |
| **Windows (port later)** | RTX 3060 8GB VRAM, i7-10700, 32GB RAM, CUDA | Secondary deployment |

The architecture is **identical** on both machines. The only difference is the main
model in the config (8b on the Mac, 4b on Windows). Everything else — SQLite, CPU
embeddings, FastAPI, SvelteKit — is cross-platform with no changes.

### Key hardware principle (CRITICAL)
Embeddings (EmbeddingGemma) and vector search (sqlite-vec) run **on CPU/SQLite** and
consume **ZERO VRAM**. All the VRAM (8GB on the 3060) / unified memory (24GB on the
Mac) stays dedicated to the Qwen3-VL model. This decision is what makes the project
viable on the RTX 3060's 8GB.

---

## 3. Models (real state as of June 2026)

### Final choices
| Function | Mac (M5 Pro 24GB) | Windows (RTX 3060 8GB) | Notes |
|---|---|---|---|
| Chat + Vision + OCR | **qwen3-vl:8b** (~6.1GB) | **qwen3-vl:4b** (Q4_K_M, ~3.3GB) | Single model: chat and OCR on the same model, no switching cost |
| Alternative chat (EN/PT) | gemma4:12b-mlx | gemma4:e4b | Gemma has stronger tuning for European languages |
| Embeddings | embeddinggemma (CPU) | embeddinggemma (CPU) | 300M params, 100+ languages, runs in <200MB RAM |

**Ollama requirement:** ≥ 0.12.7 (needed for Qwen3-VL).

### Why a single multimodal model (central decision)
Using Qwen3-VL as both chat AND OCR/vision is the most important decision for the 8GB.
Since it is already loaded for chat, image requests pay no model-switch penalty. On
8GB this is decisive.

### Benchmarks that support the choice (OCR/vision)
- **Qwen3-VL-8B**: DocVQA 96.1%, OCRBench 89.6% (two independent sources).
- **Qwen3-VL-4B**: OCRBench ~87.3%, DocVQA ~94.9%.
- **Receipt field extraction**: strong on numbers/dates/totals
  (Total ~0.81–0.84, Tax ~0.77–0.80, Time ~0.91), BUT weak on free text
  (Store name ~0.14–0.16, Receipt ID ~0.11–0.13).
  → **Trust numeric values/dates/totals; treat names and IDs as low confidence and
  ask the user to confirm.**
- Qwen3-VL clearly beats Gemma 3 on receipts.

### Multilingual EN/PT
- Gemma 4 has stronger tuning for European languages (incl. PT); the community
  considered it superior to Qwen 3.5 on non-English tasks.
- Qwen3 is also strongly multilingual (119–201 languages).
- **Decision:** Qwen3-VL as default (unifies chat+OCR); Gemma 4 as a switchable chat
  model if PT quality in pure conversation is not satisfactory.

### Model-name clarification (the tested names were imprecise)
- "gemma4" → Gemma 4 (April 2026): E2B/E4B/12B/26B-A4B/31B, multimodal.
- "qwen3.6" → Qwen3.6-35B-A3B (MoE, ~21GB) or 27B dense (~16.8GB) — TOO large for the
  3060; reserve only for the Mac, if ever.
- "qwen3.5 9b" → Qwen3.5-9B (real). CAVEAT: Qwen3.5 vision GGUFs still don't run well
  in Ollama (separate mmproj files) — use Qwen3-VL for vision.
- "qwen2.5-coder" (3/7/14B) → real, but not central to this project.

---

## 4. Technical stack

```
┌──────────────────────────────────────────────┐
│  Frontend: SvelteKit (Svelte 5 + Runes)        │
│  Stage 1: ONLY the Chat view                   │
│  Minimalist, dark, restrained typography (Jony │
│  Ive-style), PWA                               │
└──────────────┬─────────────────────────────────┘
               │ HTTP/SSE (localhost)
┌──────────────▼─────────────────────────────────┐
│  Backend: Python / FastAPI (single process)     │
│  • Chat orchestration + prompt assembly         │
│  • Memory service (extract/retrieve/consol.)    │
│  • Vision/OCR + structuring (JSON-schema)       │
│  • Webhook dispatcher (Stage 3)                 │
└───┬───────────────┬──────────────┬──────────────┘
    │               │              │
┌───▼────┐   ┌───────▼──────┐  ┌────▼─────────────┐
│ Ollama │   │ SQLite +     │  │ EmbeddingGemma   │
│qwen3-vl│   │ sqlite-vec + │  │ (via Ollama, CPU,│
│(+gemma)│   │ FTS5 (1 file)│  │  ZERO VRAM)      │
└────────┘   └──────────────┘  └──────────────────┘
```

### Why these choices
- **FastAPI (not Node):** a more mature local-AI/RAG ecosystem in Python
  (Ollama client, Pydantic structured outputs, Mem0-style memory, sqlite-vec
  bindings). Async + schema validation with minimal code.
- **SvelteKit:** a compiler, minimal bundles, no virtual DOM. Ideal for a
  minimalist single-user local-first app. (Apple's new web App Store is built in
  Svelte — validation for high-end UI.)
- **sqlite-vec (not Chroma/Qdrant/pgvector):** a single file, in-process, zero
  server, identical on macOS/Windows. Co-locates semantic memory + conversation
  history + app state in the same SQLite file. Backup = copy one file. Future
  alternative: LanceDB if the data grows a lot (>1M vectors).
- **EmbeddingGemma-300M:** the best multilingual embedding model <500M on MTEB at the
  time; runs in <200MB RAM on CPU. Available in Ollama. Alternatives:
  nomic-embed-text-v2, BGE-M3.

---

## 5. Memory architecture (two levels, a single SQLite file)

**Mem0-style pattern (extract → consolidate).** (Mem0 paper, arXiv:2504.19413:
+26% on LLM-as-Judge vs OpenAI, -91% p95 latency, -90% tokens vs putting the full
history in context — i.e. more accurate AND cheaper.)

### Layer A — Semantic memory (facts/preferences about the user)
After each exchange, an extraction call (local LLM with JSON-schema) extracts durable
facts ("prefers expenses categorized by merchant", "salary paid on the 25th", "speaks
Portuguese at home"). Each fact is embedded with EmbeddingGemma and stored in
sqlite-vec with metadata (type, timestamp, source). On write, compare against the
top-k similar existing facts and decide **ADD / UPDATE / DELETE / NOOP** to avoid
duplicates and resolve contradictions.

### Layer B — Searchable conversation history
Store each literal message in a normal SQLite table (searchable via FTS5), AND also
embed each turn in sqlite-vec for semantic retrieval. This gives keyword search AND
semantic search ("what did we talk about regarding my rent?").

### Injection at retrieval
On each new turn: (1) embed the query, (2) retrieve top-k semantic facts + top-k
relevant past turns from sqlite-vec, (3) optionally rerank, (4) inject into a compact
block in the system prompt ("What I know about you" + "Relevant past context"),
(5) call Qwen3-VL. All retrieval is CPU/SQLite — **ZERO VRAM.**

> The **consolidation** logic (Layer A) is the subtlest part of the project. It is
> what decides whether the assistant seems smart or accumulates duplicated junk. It
> is worth stabilizing and testing in isolation.

---

## 6. Vision (Stage 2 — IMPLEMENTED as GENERAL-purpose vision)

> UPDATE (real state): Stage 2 was built as **general-purpose multimodal chat**, not
> structured receipt extraction. It turned out that `qwen3-vl` reads images
> excellently in free form (OCR/description), but rigid *structured output* (a receipt
> schema via `format=`) collapsed the fields to `null`. Decision: the image enters
> `/chat` (the `image_base64` field), is decoded, resized (longer side <=
> `vision_max_dim`, JPEG q88 via Pillow) and attached to the user's turn for
> `qwen3-vl` to see; the response streams normally. The image is persisted in
> `data/images/<uuid>.jpg` and the path saved in `messages.image_path` (visible when
> reloading the conversation). The **JSON structuring of transactions** (receipts ->
> `{date, amount, ...}`) returns as an EXPLICIT action in Stage 3, not as a silent
> chat mode.

### Technical notes on the vision pipeline (kept, still valid)

1. **One model, no switching.** Qwen3-VL does chat and OCR/vision. Already loaded → no
   switching penalty.
2. **Images via the Ollama API** (`images: [base64]`). `temperature: 0` +
   **structured outputs** (`format` = JSON schema) → validated JSON, not prose.
3. **Anti-hallucination contract (prompt):** transcribe exactly; return `null` for
   missing fields; attach per-field confidence. Trust numbers/dates/totals; flag
   names/IDs for confirmation.
4. **Modest context:** the vision encoder adds 1–3GB over the text model; large
   images consume tokens. On the 3060, shrink very large images. Set `num_ctx`
   explicitly (Ollama's silent default is small).
5. **Optional hybrid fallback** (only if accuracy fails on dense documents): route
   low-confidence pages to Tesseract. For receipts/statements in a personal-finance
   context, Qwen3-VL alone is the recommended default.

**Validate in PT:** there is no public OCR-accuracy figure specific to Portuguese for
these small models. It must be **validated empirically** with your real receipts/
statements (PT and EN) in Stage 2.

---

## 7. Structuring/automation pipeline (Stage 3)

1. **Input:** chat text, pasted text, or an image.
2. **Structure:** Qwen3-VL with **JSON-schema structured output** (via Ollama's
   `format`, or Pydantic `model_json_schema()`) describing the shape of the target
   transaction: `{date, amount, currency, merchant, category, account, notes,
   confidence}`. For images, this does OCR + extraction in a single call.
3. **Validate:** parse with Pydantic; business rules (currency, sign, date
   normalization); route low-confidence fields to a quick confirmation UI.
4. **Dispatch:** POST the validated JSON to the target software's API/webhook
   (configurable endpoint + auth). Since the target does not exist yet, define a
   stable internal schema now and add a thin adapter later.
5. **Log + learn:** write the structured record and the user's corrections back into
   memory to improve categorization over time.

---

## 8. File structure

```
project/
├── CLAUDE.md              # this file
├── backend/
│   ├── main.py            # FastAPI: /chat (SSE, multimodal), /conversations,
│   │                      #   /memory/facts, /images (StaticFiles)
│   ├── ollama_client.py   # Ollama calls (chat stream + embeddings)
│   ├── memory.py          # extract -> consolidate -> retrieve; search/edit (panel)
│   ├── db.py              # SQLite + sqlite-vec + FTS5 (1 file) + migrations
│   ├── config.py          # Settings (models, paths, images_dir, vision_max_dim)
│   └── schemas.py         # Pydantic (ChatRequest with image_base64)
├── frontend/              # SvelteKit (Svelte 5), One Dark theme + Fira Code
│   └── src/
│       ├── routes/+page.svelte      # shell: Sidebar + chat + panels
│       ├── lib/chat.ts              # SSE streaming (normalizes sse-starlette CRLF)
│       ├── lib/api.ts               # conversation + memory + image helpers
│       └── lib/components/
│           ├── Sidebar.svelte       # conversation list (rename/delete)
│           └── MemoryPanel.svelte   # view/search/edit/delete facts
└── data/
    ├── memory.db          # single memory file
    └── images/            # persisted attached images (<uuid>.jpg)
```

### Management layer (Odysseus-style, but minimalist) — IMPLEMENTED
- **Chats**: sidebar with a conversation list (auto-generated title from the 1st
  message), load history, rename (`PATCH /conversations/{id}`), delete (`DELETE`,
  ordered cleanup without `ON DELETE CASCADE`).
- **Memory**: panel (sidebar icon) to view/search (`GET /memory/facts?q=`, semantic
  ordering), edit (`PATCH`, re-embeds keeping lockstep) and delete facts.
- **Images**: persisted per conversation (see section 6) + **gallery** (`GET
  /gallery`, panel with grid + lightbox, opens the source conversation).
- **Skills** (lightweight instructions): `skills` table, CRUD at `/skills`, with an
  enabled toggle. Active skills are injected into each chat's system prompt
  (`SkillsPanel.svelte`). They are NOT auto-learned (decision: lightweight version).
- **Pipeline (Stage 3)**: dedicated view (`PipelinePanel.svelte`). Paste text or
  attach an image -> `POST /pipeline/extract`: if an image, transcribe first
  (`vision_describe`) and then do text->JSON extraction (more reliable than direct
  JSON over an image) into `TransactionExtraction` {date, amount, currency, merchant,
  category, account, notes, confidence, low_confidence_fields}. The confirmation UI
  highlights low-confidence fields. `POST /pipeline/dispatch` logs to `transactions`
  and, if `dispatch_url` is configured, POSTs to the webhook.
- **UI**: One Dark palette and self-hosted Fira Code font, mirroring Odysseus
  (`pewdiepie-archdaemon/odysseus`), but reduced to the essentials. Sidebar icons:
  ◈ Memory, ✦ Skills, ▦ Gallery, ⇄ Pipeline.

---

## 9. Phased build plan

> CURRENT STATE: Stage 1 (chat + memory), Stage 2 (general vision) and Stage 3
> (structuring pipeline + dispatch) DONE. Management layer complete: Chats, Memory,
> Images+Gallery, Skills (lightweight), Pipeline (see section 8). Open/future:
> dispatch to a real target (a personal-finance app), auto-learned skills, and
> empirical OCR validation in PT with real documents.

### STAGE 1 — Chat + memory (DONE)
1. Minimal FastAPI backend: `/chat` endpoint → Ollama with SSE streaming (no memory,
   just confirm the pipe).
2. Raw persistence: store each message in SQLite + FTS5.
3. Semantic layer: extraction with JSON-schema → EmbeddingGemma embedding →
   sqlite-vec; ADD/UPDATE/DELETE/NOOP consolidation; top-k retrieval + injection into
   the prompt.
4. SvelteKit frontend: minimalist, dark chat view.
5. **Validation test:** state facts in one conversation, close it, open a new one
   → the assistant should "remember". This is the criterion for moving to Stage 2.

### STAGE 2 — OCR/vision (do not build until Stage 1 is validated)
Image upload → Qwen3-VL with `temperature:0` + JSON-schema + anti-hallucination
contract. Test with real PT and EN receipts.
**Criterion:** numbers/dates/totals reliable; low-confidence fields flagged.

### STAGE 3 — Dispatch + polish
Stable internal transaction schema; webhook dispatcher (configurable endpoint/auth);
Memory (browse/edit/delete facts) and Pipeline views.

---

## 10. Caveats and known pitfalls

- **OCR in Portuguese is NOT validated:** no public figures for small models.
  Validate with your own documents in Stage 2.
- **Quantization vs accuracy:** Q4_K_M (Ollama default) costs ~3–5% on OCR tasks. On
  the Mac (24GB) prefer higher precision for document work.
- **Hallucination is the VLM failure mode:** they invent values for empty fields.
  Mitigate with a strict prompt + temperature 0 + structured outputs.
- **Qwen3.5 vision in Ollama:** still has friction (separate mmproj). Use Qwen3-VL
  for vision.
- **Tool-calling in Gemma 4** is weaker than Qwen/Llama; if adding tool use later,
  prefer Qwen3-VL and keep Ollama up to date.
- **Odysseus is "vibecoded"** with possible security flaws in the agents — use it only
  as design/concept inspiration, do NOT fork the code. The minimalist rebuild avoids
  the entire risk surface (agents/shell/email).
- **Versions change fast:** reconfirm tags on ollama.com/library before pinning
  versions.

---

## 11. Current scope and what stays out (for now)

The rule is not "never", it's "not while it costs more than this hardware can handle
or breaks local-first". **Out of current scope**, re-evaluable case by case: heavy
autonomous agents, deep research, email/calendar, image generation, external database
servers. Each extra surface is VRAM, complexity and risk; it only comes in if there is
a **lightweight, offline** way to do it that passes the local-first invariant filter
(section 1). Design inspiration from larger projects (Odysseus, Hermes Agent) is
welcome; the **weight** of those projects is not.
