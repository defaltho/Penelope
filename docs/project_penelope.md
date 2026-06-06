---
name: project_penelope
description: "Penelope, assistente de IA local-first (chat + memória + visão) em ~/Library/CloudStorage/SynologyDrive-defaltho-pack/Projects/penelope"
metadata: 
  node_type: memory
  type: project
  originSessionId: 86eaa2a7-01db-456b-8be5-cb41bf63d597
---

**Penelope** é um assistente de IA local-first do utilizador, em
`~/Library/CloudStorage/SynologyDrive-defaltho-pack/Projects/penelope` (não é git).
Inspirado no UX/UI do projeto Odysseus (`pewdiepie-archdaemon/odysseus`) mas muito
mais minimalista.

**Stack:** backend Python FastAPI (`backend/`, gerido por `uv`, Python 3.12) +
frontend SvelteKit/Svelte 5 (`frontend/`). Modelos via Ollama local:
`qwen3-vl:8b` (chat + visão) e `embeddinggemma` (embeddings em CPU). Memória estilo
Mem0 em SQLite + sqlite-vec + FTS5 (1 ficheiro `data/memory.db`).

**Arrancar (precisa do Ollama a correr com aqueles 2 modelos):**
- backend: `cd backend && uv run uvicorn main:app --host 127.0.0.1 --port 8000`
- frontend: `cd frontend && npm run dev` (porta 5173; proxy `/api/*` -> backend)

**Estado (a 2026-06-06):** Stage 1 (chat+memória), Stage 2 (visão de uso GERAL,
não recibos) e Stage 3 (pipeline de transações) concluídos. Funcionalidades:
Memória (`MemoryPanel.svelte`), Skills leves (instruções injetadas no system
prompt, `SkillsPanel.svelte`), Galeria (`GalleryPanel.svelte`), Pipeline
(`PipelinePanel.svelte`: texto/imagem -> JSON de transação -> confirmar ->
dispatch). Imagens persistidas em `data/images/`. UI One Dark + Fira Code +
ícones Lucide do Odysseus.

**Reorganização UI estilo Odysseus (EM CURSO, plano faseado).** Plano em
`~/.claude/plans/podes-planear-tal-como-gleaming-rain.md`. Objetivo: layout
`[ rail de ícones | vista ativa ]` igual ao Odysseus (repo local em
`~/Documents/odysseus`, usar como referência), motor de IA fraco por isso só
ferramentas leves.
- FASE 1 FEITA: `IconRail.svelte` (rail vertical) + `lib/views/ChatView.svelte`
  (chat extraído, fica sempre montado) + `+page.svelte` virou shell com
  `activeView`. Memória/Skills/Galeria/Pipeline passaram de modais a VISTAS
  (prop `inline` nos `*Panel.svelte`: sem `.overlay`, preenchem a área).
- FASES PENDENTES: 2) Notas+Tarefas, 3) Definições+Tema (escolher modelo Ollama,
  dispatch_url, toggles), 4) Pesquisa global Ctrl+K (sobre `messages_fts`),
  5) Documentos (editor com IA a assistir), 6) Compare leve (qwen3-vl vs gemma).
  Excluídas (motor fraco): Email, Calendário, Deep Research, Cookbook.
- Reutilizar: `chat_stream(model=...)` já aceita modelo (p/ Compare/Definições);
  `messages_fts` (FTS5) já existe (p/ Pesquisa); `Icon.svelte` (ícones Lucide);
  `db.py::_migrate` para migrações idempotentes de novas tabelas.

Em aberto também: dispatch para destino real (whisper-money), skills
auto-aprendidas.

**Armadilhas já resolvidas (não repetir):**
- O `sse-starlette` emite eventos SSE com `\r\n`; o parser do frontend
  (`lib/chat.ts`) tem de normalizar `\r\n` para `\n` ou nenhum token aparece.
- O endpoint MCP do GitHub Copilot (`api.githubcopilot.com/mcp`) NÃO suporta OAuth
  dynamic client registration: precisa de token no header `Authorization: Bearer`.
- Visão: `qwen3-vl` lê imagens bem em formato livre, mas `format=<schema>` rígido
  colapsava campos para `null`. Por isso a visão é chat livre, não extração.

Relacionado: [[project_odysseus_setup]] (a inspiração de design), [[feedback_no_em_dash]].
