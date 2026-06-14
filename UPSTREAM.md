# UPSTREAM.md — Referências upstream do Penelope

Penelope foi inspirado visualmente e conceitualmente pelo Odysseus
(`pewdiepie-archdaemon/odysseus`). Este ficheiro regista o estado do upstream
e o que é ou não relevante mergear. **Nunca mergear cegamente — sempre analisar
caso a caso contra o invariante local-first.**

---

## Odysseus — `pewdiepie-archdaemon/odysseus`

**Última verificação:** 2026-06-13

### O que o Odysseus se tornou

O Odysseus evoluiu para uma plataforma multi-utilizador, multi-cloud, com autenticação,
email, CI/CD própria e suporte a dezenas de providers de LLM (Anthropic, Mistral,
Deepseek, etc.). É um projeto open-source com muitos contribuidores activos.

Isto **diverge fundamentalmente** da filosofia do Penelope:

| Dimensão | Odysseus | Penelope |
|---|---|---|
| Utilizadores | Multi-user, auth obrigatória | Single-user, sem auth |
| LLM | Anthropic + OpenAI-compat + cloud | Ollama local apenas |
| Memória | ChromaDB (servidor externo) | sqlite-vec (in-process) |
| Agentes | Workspace confinado, cookbook | Loop simples, ferramentas locais |
| Email | Integração IMAP | Fora de escopo |
| CI | Gitleaks + CodeQL + Trivy | N/A |

### Commits recentes com possível relevância

#### ✓ Potencialmente útil

- **fix(search): batch FTS hit lookups into one query (N+1)**
  (`f941db2`, 2026-06-11)
  — O Penelope usa FTS5 para pesquisa de mensagens. Se a rota `/api/search`
  fizer lookups em loop por ID, o padrão de batch com `IN(...)` aplica-se.
  **Verificar `memory.py` e a rota de pesquisa antes de adaptar.**

- **fix(search): read plain-text, Markdown, and JSON URLs in fetch_webpage_content**
  (`bfac1d5`, 2026-06-11)
  — O web fetch do Penelope pode ter o mesmo problema (URLs de raw GitHub,
  .md, .json retornam `text/plain`). **Verificar `tools/web.py` ou equivalente.**

- **feat(agent): workspace confinement** (`620fdd0`, 2026-06-11)
  — Ideia interessante: confinar file/shell tools a uma pasta seleccionada.
  O Penelope já tem `project_root` como sandbox — o padrão de `vet_workspace`
  (rejeitar raízes sensíveis, filesystem roots) pode ser útil se os agentes
  ganharem mais acesso.

#### ✗ Não aplicável ao Penelope

- Fixes de auth/tokens/owner-isolation — Penelope não tem multi-user
- Fixes de provider cloud (Anthropic temperature, llama.cpp slot affinity) — Penelope usa só Ollama
- Email, cookbook, research CLI — fora de escopo
- Windows launcher (Find-GitBash) — o Penelope arranca com uvicorn direto
- CI/security scanning — infraestrutura do Odysseus, não relevante

### Conclusão

O Odysseus deixou de ser uma referência directa de código para o Penelope.
A inspiração mantém-se ao nível de UX/visual. Mergear código directamente
seria perigoso (assunções multi-user em toda a parte, ChromaDB em vez de
sqlite-vec, autenticação implícita).

**Recomendação:** continuar a observar commits de `fix(search)` e `fix(agent)`
pela lógica de dados — são as únicas áreas com overlap real.

---

## hermes-agent — `NousResearch/hermes-agent`

**Última verificação:** 2026-06-13

### O que o hermes-agent se tornou

O hermes-agent (por Teknium/NousResearch) é uma plataforma de agente AI massiva:

- **Escala:** ficheiros únicos de 200–600KB (`cli.py` 638KB, `run_agent.py` 239KB, `gateway.py` 268KB, `web_server.py` 464KB, `main.py` 495KB, `hermes_state.py` 205KB)
- **Multi-plataforma:** gateway para Telegram, WhatsApp, WeCom, Matrix, DingTalk, QQ, Slack…
- **Multi-provider:** Gemini, Codex, modelos custom, OpenAI-compat
- **Multi-user:** auth, pairing, perfis, grupos
- **Sistemas adicionais:** Kanban (`kanban_db.py` 316KB), skills, plugins, ACP adapter, MCP server, TUI, dashboard web

Isto diverge completamente da filosofia do Penelope:

| Dimensão | hermes-agent | Penelope |
|---|---|---|
| Escala | Monolito gigante | Single-purpose, ficheiros pequenos |
| Plataformas | 10+ gateways | CLI + web local |
| Utilizadores | Multi-user com auth/pairing | Single-user |
| LLM | Cloud multi-provider | Ollama local |
| Extras | Kanban, dashboard, voice, skills hub | Fora de escopo |

### O que foi portado (histórico)

O `StreamRenderer` do CLI da Penelope foi inspirado no padrão de streaming do hermes-agent — especificamente como o CLI consome chunks SSE e os renderiza incrementalmente. Este port já está feito.

**`hermes_cli/stdio.py`** (10KB) — o único ficheiro com sobreposição directa ainda relevante:
- Windows UTF-8 stdio fix: `SetConsoleCP(65001)` + `reconfigure(encoding='utf-8')`
- O Penelope no Windows pode ter o mesmo problema se o CLI imprimir box-drawing/emoji

### Commits recentes com possível relevância

#### ✓ Potencialmente útil

- **fix: keep CLI idle timer ticking** (`6724daa`, 2026-06-13)
  — Se o CLI da Penelope tiver um timer de idle para fechar sessões, este fix pode ser relevante.
  **Verificar se o Penelope CLI tem idle timeout implementado.**

#### ✗ Não aplicável

- Fixes de gateway (Telegram, WeCom, Matrix, WhatsApp) — fora de escopo
- Fixes de auth/allowlists/security gating — Penelope é single-user sem rede exposta
- Gemini/Codex provider fixes — Penelope usa só Ollama
- Dashboard, kanban, profiles, plugins — fora de escopo
- Windows bootstrap recovery (startup PS1 + venv) — Penelope arranca com `uvicorn` directamente

### Conclusão

O hermes-agent deixou de ser uma referência prática para o Penelope — é um projecto de escala e filosofia completamente diferentes. A inspiração manteve-se no `StreamRenderer` (já portado) e no `stdio.py` para suporte Windows.

**Recomendação:** não monitorizar activamente. Verificar `hermes_cli/stdio.py` apenas se o CLI da Penelope apresentar problemas de encoding no Windows.
