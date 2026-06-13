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

**Estado:** A verificar — referência para streaming / tool-use patterns.

*Notas a adicionar após verificação.*
