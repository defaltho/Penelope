# CLAUDE.md — Assistente Local-First (chat + memória + OCR/pipeline)

> Este ficheiro dá ao Claude Code o contexto COMPLETO do projeto, incluindo a
> investigação que fundamenta cada decisão técnica. Lê-o por inteiro antes de
> construir. Datas e versões válidas a junho de 2026.

---

## 1. Visão geral e objetivo

Assistente de IA **local-first**, a correr **offline**, com **memória persistente
de longo prazo** que aprende continuamente com as interações, **OCR/visão** via
modelo multimodal local, e um **pipeline de automação** que estrutura texto e
imagens em JSON e os envia para um software de destino próprio (ainda por
construir, do tipo gestão de finanças pessoais privada — referência:
whisper-money).

Multilingue, com **qualidade excecional em Inglês e Português**.

**Filosofia:** inspirado no estilo visual / UX / local-first do projeto Odysseus
(do PewDiePie), mas MUITO mais minimalista e leve. ELIMINAR explicitamente as
ferramentas pesadas do Odysseus — agentes autónomos, deep research, email,
calendário, geração de imagens — que sobrecarregariam o hardware modesto.
Focar APENAS em: **chat, memória persistente, pipeline de estruturação texto+imagem.**

---

## 2. Hardware-alvo

| Máquina | Specs | Papel |
|---|---|---|
| **Mac (prototipar AQUI primeiro)** | M5 Pro, 24GB memória unificada, MLX, 307 GB/s bandwidth | Desenvolvimento e protótipo |
| **Windows (portar depois)** | RTX 3060 8GB VRAM, i7-10700, 32GB RAM, CUDA | Deployment secundário |

A arquitetura é **idêntica** nas duas máquinas. A única diferença é o modelo
principal no config (8b no Mac, 4b no Windows). Todo o resto — SQLite, embeddings
em CPU, FastAPI, SvelteKit — é cross-platform sem alterações.

### Princípio-chave de hardware (CRÍTICO)
Embeddings (EmbeddingGemma) e busca vetorial (sqlite-vec) correm **em CPU/SQLite**
e consomem **ZERO VRAM**. Toda a VRAM (8GB no 3060) / memória unificada (24GB no
Mac) fica dedicada ao modelo Qwen3-VL. Esta decisão é o que torna o projeto viável
nos 8GB do RTX 3060.

---

## 3. Modelos (estado real a junho de 2026)

### Escolhas finais
| Função | Mac (M5 Pro 24GB) | Windows (RTX 3060 8GB) | Notas |
|---|---|---|---|
| Chat + Visão + OCR | **qwen3-vl:8b** (~6.1GB) | **qwen3-vl:4b** (Q4_K_M, ~3.3GB) | Modelo único: chat e OCR no mesmo modelo, sem custo de troca |
| Chat alternativo (EN/PT) | gemma4:12b-mlx | gemma4:e4b | Gemma tem afinação mais forte em línguas europeias |
| Embeddings | embeddinggemma (CPU) | embeddinggemma (CPU) | 300M params, 100+ línguas, corre em <200MB RAM |

**Requisito Ollama:** ≥ 0.12.7 (necessário para Qwen3-VL).

### Porquê um único modelo multimodal (decisão central)
Usar o Qwen3-VL como chat E como OCR/visão é a decisão mais importante para os 8GB.
Como já está carregado para chat, os pedidos de imagem não pagam penalização de
troca de modelo. Em 8GB isto é decisivo.

### Benchmarks que sustentam a escolha (OCR/visão)
- **Qwen3-VL-8B**: DocVQA 96.1%, OCRBench 89.6% (duas fontes independentes).
- **Qwen3-VL-4B**: OCRBench ~87.3%, DocVQA ~94.9%.
- **Extração de campos de recibos**: forte em números/datas/totais
  (Total ~0.81–0.84, Tax ~0.77–0.80, Time ~0.91), MAS fraco em texto livre
  (Nome da loja ~0.14–0.16, ID do recibo ~0.11–0.13).
  → **Confiar em valores numéricos/datas/totais; tratar nomes e IDs como baixa
  confiança e pedir confirmação ao utilizador.**
- Qwen3-VL bate claramente o Gemma 3 em recibos.

### Multilingue EN/PT
- Gemma 4 tem afinação mais forte em línguas europeias (incl. PT); comunidade
  considerou-o superior ao Qwen 3.5 em tarefas não-inglesas.
- Qwen3 também é fortemente multilingue (119–201 línguas).
- **Decisão:** Qwen3-VL como default (unifica chat+OCR); Gemma 4 como modelo de
  chat comutável se a qualidade de PT em conversa pura não satisfizer.

### Esclarecimento de nomes de modelos (os nomes testados eram imprecisos)
- "gemma4" → Gemma 4 (abril 2026): E2B/E4B/12B/26B-A4B/31B, multimodal.
- "qwen3.6" → Qwen3.6-35B-A3B (MoE, ~21GB) ou 27B denso (~16.8GB) — DEMASIADO
  grandes para o 3060; reservar só para o Mac, se acaso.
- "qwen3.5 9b" → Qwen3.5-9B (real). CAVEAT: GGUFs de visão do Qwen3.5 ainda não
  correm bem em Ollama (ficheiros mmproj separados) — usar Qwen3-VL para visão.
- "qwen2.5-coder" (3/7/14B) → real, mas não central para este projeto.

---

## 4. Stack técnico

```
┌──────────────────────────────────────────────┐
│  Frontend: SvelteKit (Svelte 5 + Runes)        │
│  Stage 1: SÓ a vista de Chat                   │
│  Minimalista, dark, tipografia contida (Jony   │
│  Ive-style), PWA                               │
└──────────────┬─────────────────────────────────┘
               │ HTTP/SSE (localhost)
┌──────────────▼─────────────────────────────────┐
│  Backend: Python / FastAPI (processo único)     │
│  • Orquestração de chat + montagem de prompt    │
│  • Serviço de memória (extract/retrieve/consol.)│
│  • Visão/OCR + estruturação (JSON-schema)       │
│  • Dispatcher de webhook (Stage 3)              │
└───┬───────────────┬──────────────┬──────────────┘
    │               │              │
┌───▼────┐   ┌───────▼──────┐  ┌────▼─────────────┐
│ Ollama │   │ SQLite +     │  │ EmbeddingGemma   │
│qwen3-vl│   │ sqlite-vec + │  │ (via Ollama, CPU,│
│(+gemma)│   │ FTS5 (1 fich)│  │  ZERO VRAM)      │
└────────┘   └──────────────┘  └──────────────────┘
```

### Porquê estas escolhas
- **FastAPI (não Node):** ecossistema local-AI/RAG mais maduro em Python
  (cliente Ollama, structured outputs Pydantic, memória estilo Mem0, bindings
  sqlite-vec). Async + validação de schema com mínimo código.
- **SvelteKit:** compilador, bundles mínimos, sem virtual-DOM. Ideal para app
  local-first minimalista de utilizador único. (A nova App Store web da Apple
  é feita em Svelte — validação para UI de gama alta.)
- **sqlite-vec (não Chroma/Qdrant/pgvector):** um único ficheiro, in-process,
  zero servidor, idêntico em macOS/Windows. Co-localiza memória semântica +
  histórico de conversa + estado da app no mesmo ficheiro SQLite. Backup = copiar
  um ficheiro. Alternativa de futuro: LanceDB se os dados crescerem muito (>1M vetores).
- **EmbeddingGemma-300M:** melhor modelo de embedding multilingue <500M no MTEB
  à data; corre em <200MB RAM em CPU. Disponível em Ollama. Alternativas:
  nomic-embed-text-v2, BGE-M3.

---

## 5. Arquitetura de memória (dois níveis, um único ficheiro SQLite)

Padrão **estilo Mem0 (extract → consolidate)**. (Paper Mem0, arXiv:2504.19413:
+26% em LLM-as-Judge vs OpenAI, -91% latência p95, -90% tokens vs meter histórico
completo no contexto — i.e. mais preciso E mais barato.)

### Camada A — Memória semântica (factos/preferências sobre o utilizador)
Após cada troca, uma chamada de extração (LLM local com JSON-schema) extrai factos
duráveis ("prefere despesas categorizadas por comerciante", "salário pago no dia
25", "fala português em casa"). Cada facto é embebido com EmbeddingGemma e guardado
em sqlite-vec com metadados (tipo, timestamp, fonte). Na escrita, comparar com os
top-k factos semelhantes existentes e decidir **ADD / UPDATE / DELETE / NOOP** para
evitar duplicados e resolver contradições.

### Camada B — Histórico de conversa pesquisável
Guardar cada mensagem literal numa tabela SQLite normal (pesquisável por FTS5), E
também embeber cada turno em sqlite-vec para recuperação semântica. Dá pesquisa por
palavra-chave E pesquisa semântica ("o que falámos sobre a minha renda?").

### Injeção na recuperação
A cada novo turno: (1) embeber a query, (2) recuperar top-k factos semânticos +
top-k turnos passados relevantes do sqlite-vec, (3) opcionalmente reordenar,
(4) injetar num bloco compacto no system prompt ("O que sei sobre ti" + "Contexto
relevante passado"), (5) chamar o Qwen3-VL. Toda a recuperação é CPU/SQLite —
**ZERO VRAM.**

> A lógica de **consolidação** (Camada A) é a parte com mais subtileza do projeto.
> É o que decide se o assistente parece inteligente ou se acumula lixo duplicado.
> Vale a pena estabilizá-la e testá-la isoladamente.

---

## 6. Visão (Stage 2 — IMPLEMENTADO como visão de uso GERAL)

> ATUALIZAÇÃO (estado real): o Stage 2 foi construído como **chat multimodal de
> uso geral**, não como extração estruturada de recibos. Descobriu-se que o
> `qwen3-vl` lê imagens com excelência em formato livre (OCR/descrição), mas o
> *structured output* rígido (schema de recibo via `format=`) colapsava os campos
> para `null`. Decisão: a imagem entra no `/chat` (campo `image_base64`), é
> descodificada, redimensionada (lado maior <= `vision_max_dim`, JPEG q88 via
> Pillow) e anexada ao turno do utilizador para o `qwen3-vl` ver; a resposta vem
> em streaming normal. A imagem é persistida em `data/images/<uuid>.jpg` e o
> caminho guardado em `messages.image_path` (visível ao recarregar a conversa).
> A **estruturação JSON de transações** (recibos -> `{date, amount, ...}`) regressa
> como ação EXPLÍCITA no Stage 3, não como modo silencioso do chat.

### Notas técnicas do pipeline de visão (mantidas, ainda válidas)

1. **Um modelo, sem troca.** Qwen3-VL faz chat e OCR/visão. Já carregado → sem
   penalização de troca.
2. **Imagens via API do Ollama** (`images: [base64]`). `temperature: 0` +
   **structured outputs** (`format` = JSON schema) → JSON validado, não prosa.
3. **Contrato anti-alucinação (prompt):** transcrever exatamente; devolver `null`
   para campos ausentes; anexar confiança por campo. Confiar em
   números/datas/totais; sinalizar nomes/IDs para confirmação.
4. **Contexto modesto:** encoder de visão soma 1–3GB sobre o modelo de texto;
   imagens grandes consomem tokens. No 3060, reduzir imagens muito grandes.
   Definir `num_ctx` explicitamente (default silencioso do Ollama é pequeno).
5. **Fallback híbrido opcional** (só se a precisão falhar em documentos densos):
   rotear páginas de baixa confiança para Tesseract. Para recibos/extratos num
   contexto de finanças pessoais, Qwen3-VL sozinho é o default recomendado.

**Validar em PT:** não existe número público de precisão de OCR específico para
português nestes modelos pequenos. É preciso **validar empiricamente** com
recibos/extratos reais teus (PT e EN) no Stage 2.

---

## 7. Pipeline de estruturação/automação (Stage 3)

1. **Input:** texto de chat, texto colado, ou imagem.
2. **Estruturar:** Qwen3-VL com **JSON-schema structured output** (via `format`
   do Ollama, ou Pydantic `model_json_schema()`) descrevendo a forma da transação
   de destino: `{date, amount, currency, merchant, category, account, notes,
   confidence}`. Para imagens, isto faz OCR + extração numa só chamada.
3. **Validar:** parse com Pydantic; regras de negócio (moeda, sinal, normalização
   de datas); rotear campos de baixa confiança para uma UI de confirmação rápida.
4. **Despachar:** POST do JSON validado para a API/webhook do software de destino
   (endpoint + auth configuráveis). Como o destino ainda não existe, definir já um
   schema interno estável e adicionar um adapter fino depois (estilo whisper-money).
5. **Registar + aprender:** escrever o registo estruturado e as correções do
   utilizador de volta na memória para melhorar a categorização ao longo do tempo.

---

## 8. Estrutura de ficheiros

```
projeto/
├── CLAUDE.md              # este ficheiro
├── backend/
│   ├── main.py            # FastAPI: /chat (SSE, multimodal), /conversations,
│   │                      #   /memory/facts, /images (StaticFiles)
│   ├── ollama_client.py   # chamadas ao Ollama (chat stream + embeddings)
│   ├── memory.py          # extract -> consolidate -> retrieve; search/edit (painel)
│   ├── db.py              # SQLite + sqlite-vec + FTS5 (1 ficheiro) + migrações
│   ├── config.py          # Settings (modelos, paths, images_dir, vision_max_dim)
│   └── schemas.py         # Pydantic (ChatRequest com image_base64)
├── frontend/              # SvelteKit (Svelte 5), tema One Dark + Fira Code
│   └── src/
│       ├── routes/+page.svelte      # shell: Sidebar + chat + painéis
│       ├── lib/chat.ts              # streaming SSE (normaliza CRLF do sse-starlette)
│       ├── lib/api.ts               # helpers de conversas + memória + imagens
│       └── lib/components/
│           ├── Sidebar.svelte       # lista de conversas (rename/apagar)
│           └── MemoryPanel.svelte   # ver/pesquisar/editar/apagar factos
└── data/
    ├── memory.db          # ficheiro único de memória
    └── images/            # imagens anexadas persistidas (<uuid>.jpg)
```

### Camada de gestão (estilo Odysseus, mas minimalista) — IMPLEMENTADA
- **Chats**: sidebar com lista de conversas (título auto-gerado da 1ª mensagem),
  carregar histórico, renomear (`PATCH /conversations/{id}`), apagar (`DELETE`,
  limpeza ordenada sem `ON DELETE CASCADE`).
- **Memória**: painel (ícone na sidebar) para ver/pesquisar (`GET
  /memory/facts?q=`, ordenação semântica), editar (`PATCH`, re-embebe mantendo o
  lockstep) e apagar factos.
- **Imagens**: persistidas por conversa (ver secção 6) + **galeria** (`GET
  /gallery`, painel com grelha + lightbox, abre a conversa de origem).
- **Skills** (instruções leves): tabela `skills`, CRUD em `/skills`, com toggle
  enabled. As skills ativas são injetadas no system prompt de cada chat
  (`SkillsPanel.svelte`). NÃO são auto-aprendidas (decisão: versão leve).
- **Pipeline (Stage 3)**: vista dedicada (`PipelinePanel.svelte`). Cola texto ou
  anexa imagem -> `POST /pipeline/extract`: se imagem, transcreve primeiro
  (`vision_describe`) e depois faz extração texto->JSON (mais fiável que JSON
  direto sobre imagem) para `TransactionExtraction` {date, amount, currency,
  merchant, category, account, notes, confidence, low_confidence_fields}. UI de
  confirmação realça campos de baixa confiança. `POST /pipeline/dispatch` regista
  em `transactions` e, se `dispatch_url` estiver configurado, faz POST ao webhook.
- **UI**: paleta One Dark e fonte Fira Code self-hosted, espelhando o Odysseus
  (`pewdiepie-archdaemon/odysseus`), mas reduzido só ao essencial. Ícones na
  sidebar: ◈ Memória, ✦ Skills, ▦ Galeria, ⇄ Pipeline.

---

## 9. Plano de construção faseado

> ESTADO ATUAL: Stage 1 (chat + memória), Stage 2 (visão geral) e Stage 3
> (pipeline de estruturação + dispatch) CONCLUÍDOS. Camada de gestão completa:
> Chats, Memória, Imagens+Galeria, Skills (leves), Pipeline (ver secção 8). Em
> aberto/futuro: dispatch para um destino real (whisper-money), skills
> auto-aprendidas, e validação empírica de OCR em PT com documentos reais.

### STAGE 1 — Chat + memória (CONCLUÍDO)
1. Backend FastAPI mínimo: endpoint `/chat` → Ollama em streaming SSE (sem memória,
   só confirmar o tubo).
2. Persistência crua: guardar cada mensagem em SQLite + FTS5.
3. Camada semântica: extração com JSON-schema → embedding EmbeddingGemma →
   sqlite-vec; consolidação ADD/UPDATE/DELETE/NOOP; recuperação top-k + injeção no
   prompt.
4. Frontend SvelteKit: vista de chat minimalista, dark.
5. **Teste de validação:** dizer factos numa conversa, fechar, abrir conversa nova
   → o assistente deve "lembrar-se". Este é o critério para avançar para o Stage 2.

### STAGE 2 — OCR/visão (NÃO construir até o Stage 1 estar validado)
Upload de imagem → Qwen3-VL com `temperature:0` + JSON-schema + contrato
anti-alucinação. Testar com recibos reais PT e EN.
**Critério:** números/datas/totais fiáveis; campos de baixa confiança sinalizados.

### STAGE 3 — Dispatch + polish
Schema interno estável de transação; dispatcher de webhook (endpoint/auth
configuráveis); vistas de Memória (browse/editar/apagar factos) e de Pipeline.

---

## 10. Caveats e armadilhas conhecidas

- **OCR em português NÃO está validado:** sem números públicos para modelos
  pequenos. Validar com documentos próprios no Stage 2.
- **Quantização vs precisão:** Q4_K_M (default Ollama) custa ~3–5% em tarefas de
  OCR. No Mac (24GB) preferir precisão mais alta para trabalho com documentos.
- **Alucinação é o modo de falha dos VLMs:** inventam valores para campos vazios.
  Mitigar com prompt estrito + temperature 0 + structured outputs.
- **Qwen3.5 visão em Ollama:** ainda com fricção (mmproj separado). Usar Qwen3-VL
  para visão.
- **Tool-calling no Gemma 4** é mais fraco que Qwen/Llama; se adicionar tool use
  mais tarde, preferir Qwen3-VL e manter Ollama atualizado.
- **Odysseus é "vibecoded"** com possíveis falhas de segurança nos agentes — usar
  só como inspiração de design/conceito, NÃO fazer fork do código. A reconstrução
  minimalista evita toda a superfície de risco (agentes/shell/email).
- **Versões mudam depressa:** reconfirmar tags em ollama.com/library antes de fixar
  versões.

---

## 11. O que NÃO incluir (manter leve)

Sem agentes autónomos. Sem deep research. Sem email/calendário. Sem geração de
imagens. Sem servidores de base de dados externos. Cada superfície a mais é VRAM,
complexidade e risco que este hardware não suporta.
