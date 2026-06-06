# Penelope

Assistente de IA **local-first**: chat com memória persistente, visão de uso geral,
notas/tarefas, pipeline de estruturação de transações, e pesquisa global. Inspirado
no UX/UI do projeto Odysseus, mas minimalista. Corre offline, com os teus dados na
tua máquina.

## Stack

- **Backend**: Python + FastAPI (gerido por `uv`, Python 3.12). SSE para o chat.
  Memória estilo Mem0 em SQLite + sqlite-vec + FTS5 (um único ficheiro).
- **Frontend**: SvelteKit (Svelte 5 + runes), tema One Dark + Fira Code.
- **Modelos** (via [Ollama](https://ollama.com) local):
  - `qwen3-vl:8b` — chat + visão
  - `embeddinggemma` — embeddings (CPU, zero VRAM)

## Arranque

Pré-requisito: Ollama a correr com os modelos acima
(`ollama pull qwen3-vl:8b` e `ollama pull embeddinggemma`).

```bash
# Backend (porta 8000)
cd backend
uv run uvicorn main:app --host 127.0.0.1 --port 8000

# Frontend (porta 5173; faz proxy de /api -> backend)
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173.

## Funcionalidades

- **Chat** multimodal (texto + imagem), com seletor de modelo, tok/s, copiar,
  regenerar e janela de contexto.
- **Memória** persistente que aprende factos sobre ti (ver/pesquisar/editar/apagar).
- **Skills** — instruções reutilizáveis injetadas no system prompt.
- **Galeria** de imagens anexadas; **Notas** e **Tarefas**.
- **Pipeline** — extrai transações estruturadas de texto/imagem e despacha.
- **Compare** — dois modelos lado a lado.
- **Pesquisa global** (Ctrl/Cmd+K) sobre todas as conversas.
- **Definições** — modelo, dispatch, toggles; **Tema** comutável.

## Documentação

- [`CLAUDE.md`](CLAUDE.md) — contexto técnico completo e decisões de arquitetura.
- [`docs/project_penelope.md`](docs/project_penelope.md) — memória do projeto
  (estado, comandos, armadilhas conhecidas).
