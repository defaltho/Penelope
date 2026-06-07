# Penelope

```
───────────────────────────────────────────────
 ⊹ ࣪ ˖   Penelope vers. 1.1
───────────────────────────────────────────────
```

Assistente de IA **local-first**: chat com memória persistente, visão de uso geral,
notas/tarefas, pipeline de estruturação de transações, modo de jogo **AI Dungeon**, e
pesquisa global. Inspirado no UX/UI do projeto Odysseus, mas minimalista. Corre offline,
com os teus dados na tua máquina.

## Get started

A Penelope é tua. Open source e gratuita: sem equipa de vendas, sem pedido de demo, sem
cavalo de Troia. Corre no teu hardware, com os teus dados, local-first e privado.

```bash
git clone https://github.com/defaltho/Penelope.git && cd Penelope
```

Depois segue o [Arranque](#arranque) (macOS/Linux ou Windows). Corre em qualquer sistema
com [Ollama](https://ollama.com), [uv](https://docs.astral.sh/uv/) e [Node](https://nodejs.org).

## Stack

- **Backend**: Python + FastAPI (gerido por `uv`, Python 3.12). SSE para o chat.
  Memória estilo Mem0 em SQLite + sqlite-vec + FTS5 (um único ficheiro).
- **Frontend**: SvelteKit (Svelte 5 + runes), tema One Dark + Fira Code.
- **Modelos** (via [Ollama](https://ollama.com) local):
  - `qwen3-vl:8b` — chat + visão
  - `embeddinggemma` — embeddings (CPU, zero VRAM)

## Arranque

Pré-requisitos: [Ollama](https://ollama.com), [uv](https://docs.astral.sh/uv/) e
[Node.js](https://nodejs.org). Puxa os modelos:

```bash
ollama pull qwen3-vl:8b        # no Windows/8GB VRAM: qwen3-vl:4b (ASSISTANT_CHAT_MODEL)
ollama pull embeddinggemma
# opcional, para o modo AI Dungeon (~14GB):
ollama pull hf.co/LatitudeGames/Harbinger-24B-GGUF:Q4_K_M
```

### macOS / Linux: um só comando

```bash
penelope
```

Sobe (se preciso) o Ollama, o backend, o frontend e abre o browser. Ctrl+C para
parar tudo. O launcher vive em [`bin/penelope`](bin/penelope); liga-o uma vez ao PATH:

```bash
ln -s "$PWD/bin/penelope" ~/.local/bin/penelope   # garante que ~/.local/bin está no PATH
```

### Windows: um só comando

Em PowerShell ou cmd, a partir da pasta do projeto:

```powershell
bin\penelope.cmd
```

Faz o mesmo que no macOS: arranca Ollama + backend + uvicorn + frontend e abre o
browser. Para escreveres só `penelope` em qualquer pasta, acrescenta a pasta `bin`
ao PATH do utilizador (Definições → Variáveis de ambiente). Requer
[uv](https://docs.astral.sh/uv/) e [Node.js](https://nodejs.org) no PATH; o
PowerShell 5.1 (de fábrica) ou 7+ servem. Internamente usa
[`bin/penelope.ps1`](bin/penelope.ps1).

### Manual (dois processos, qualquer SO)

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
- **Comandos de chat** (escreve `/` no compositor), estilo Claude Code: `/help`,
  `/aidungeon`, `/new`, `/model`, `/search`, `/incognito`, `/think`, `/image`, `/retry`.
  O menu adapta-se ao contexto (chat normal vs aventura).
- **AI Dungeon** (`/aidungeon`): jogo de texto estilo [aidungeon.com](https://aidungeon.com),
  com o modelo **Harbinger-24B** (Latitude Games) e o sampler oficial (temp 0.8,
  repetition penalty 1.05, min-p 0.025) em ChatML. Setup híbrido (nova/continuar),
  modos **Fazer / Dizer / História** + **Continuar**, e **Repetir / Retroceder / Editar**;
  contexto persistente com `/lembrar` (memória), `/nota` (nota de autor) e `/cartao`
  (Story Cards). As histórias ficam guardadas na aba **Aventuras** (um ficheiro por
  história em `data/adventures/`); os metadados ficam nas Definições. Sem o Harbinger
  instalado, usa o modelo de reserva (qwen3-vl).
- **Agent Tools** (vista Agents + Definições → Agent Tools) — ferramentas locais
  estilo Odysseus, com toggle on/off por ferramenta. As perigosas (`bash`, `python`,
  `escrever_ficheiro`) estão **desligadas por defeito**; ligar é decisão explícita.
- **Definições** — modelo, dispatch, toggles; **Tema** comutável.

> **Segurança:** o acesso à internet e as ferramentas `bash`/`python` estão
> desligados por código até os ligares nas Definições. O modelo corre sempre offline.

## Documentação

- [`CLAUDE.md`](CLAUDE.md) — contexto técnico completo e decisões de arquitetura.
- [`docs/project_penelope.md`](docs/project_penelope.md) — memória do projeto
  (estado, comandos, armadilhas conhecidas).
