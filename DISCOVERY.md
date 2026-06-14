# DISCOVERY.md — Descobertas difíceis (Penelope)

Registo de problemas que custaram várias tentativas ou cuja solução não era óbvia.
Preserva conhecimento entre sessões e evita regredir para o comportamento errado.

---

## CLI: arquitectura do input persistente (Application + patch_stdout)

**Problema:** a primeira versão usava `PromptSession.prompt()` com `bottom_toolbar`,
que cola uma faixa de fundo colorida ao **fundo da janela do terminal**. O resultado
parecia pobre e não acompanhava o conteúdo.

**Como o Hermes Agent faz (estudado no `cli.py`, deps: `prompt_toolkit==3.0.52` +
`rich`):** NÃO usa `prompt()` nem `bottom_toolbar`. Constrói **uma** `Application`
full-screen=False com um `Layout` (`HSplit`) onde o input é um `TextArea` emoldurado
por janelas: spinner, régua de marca, input, barra de estado. Corre **uma vez** dentro
de `with patch_stdout(): app.run()`. O `patch_stdout` redirecciona o `sys.stdout` para
um proxy que imprime o output do chat **acima** do bloco de input persistente, que fica
fixo. `refresh_interval=0.1` anima o spinner sem chamadas manuais.

**O que a Penelope replica (`cli/tui.py`):**
- Layout (cima→baixo): spinner widget · régua `── ⊹ penelope ──` · `TextArea` · barra
  de estado. A barra fica **por baixo da linha do chat** (parte do bloco), não numa
  faixa no fundo da janela, e **sem fundo colorido** (estilos sem `bg`).
- O chat corre numa **thread daemon** (`_start_chat`) e imprime via console
  (proxy do patch_stdout); a UI não bloqueia e o spinner anima. `Ctrl+C` durante o
  chat liga `self._interrupt` (não mata a app).
- `/web` e `/compact` não podem bloquear o event loop: `/web` sai da app e lança o
  stack depois (`_pending_action`); `/compact` corre em thread.
- Enter submete; `Alt+Enter`/`Ctrl+J` inserem nova linha; `Ctrl+D` (input vazio) sai.

**rich + patch_stdout (crítico, Windows):** o console NÃO pode capturar
`io.TextIOWrapper(sys.stdout.buffer)` no import — isso ignora o proxy do patch_stdout e
corrompe o ecrã. Em vez disso: `sys.stdout.reconfigure(encoding="utf-8")` (resolve o
cp1252 do Windows) + `Console(force_terminal=True)` com `file=None`, que resolve o
`sys.stdout` actual a cada escrita → respeita o patch_stdout. Ver `cli/render.py`.

**Testar sem TTY real:** o ambiente não tem consola Windows (a app rebenta com
`NoConsoleScreenBufferError` em subprocessos). Testa-se a app com `create_pipe_input()`
+ `DummyOutput()` (o mesmo mecanismo dos testes do prompt_toolkit): alimenta teclas,
corre `app.run()` numa thread com watchdog, verifica estado. Ver `cli/test_app.py`.
O **render visual** só se valida correndo `penelope` num terminal verdadeiro.

---

## CLI: streaming de respostas e detecção de tags de raciocínio

**Contexto:** o CLI da Penelope faz streaming token-a-token do backend (SSE) e
renderiza num "response box". O modelo (qwen3-vl) emite tags de raciocínio
(`<think>…</think>`) que têm de ser suprimidas ou mostradas numa caixa separada.

**Bugs descobertos ao estudar o código do Hermes Agent (`cli.py:_stream_delta`):**

1. **Tags divididas entre tokens.** A abordagem ingénua `if "<think>" in token`
   falha porque o streaming token-a-token parte a tag (`<thi` + `nk>`). A tag nunca
   é detectada e o raciocínio vaza para o ecrã.
   → **Solução:** acumular num *pre-filter buffer* (`_prefilt`) antes de filtrar, e
   segurar no buffer qualquer sufixo que possa ser uma tag parcial até chegar mais
   texto.

2. **Falsos positivos em prosa.** Se o modelo *menciona* `<think>` numa frase
   ("usa o `<think>` para pensar"), a detecção ingénua entra em modo raciocínio a
   meio da resposta.
   → **Solução:** só tratar a tag como raciocínio se estiver num *limite de bloco*
   (início do stream, ou após `\n` com só whitespace antes da tag).

3. **Bloco de raciocínio não fechado.** Se a tag de abertura era afinal prosa e
   nunca há fecho, o conteúdo fica preso no buffer.
   → **Solução:** no `flush()` final, recuperar `_prefilt` como texto normal.

**Outros detalhes do Hermes adoptados:**
- O conteúdo da resposta indenta-se com 4 espaços (`_STREAM_PAD`), **não** com o
  prefixo `┊`. O `┊` (`tool_prefix`) é reservado para o *activity feed* (linhas de
  estado/ferramentas), não para o texto da resposta.
- O reasoning, quando visível, renderiza numa caixa dim `┌─ raciocínio ─┐` **acima**
  da resposta; texto de resposta que chegue enquanto essa caixa está aberta fica
  diferido até ela fechar.
- `console.print(..., markup=False)` ao imprimir texto do modelo, senão `[colchetes]`
  no output são interpretados como markup do rich e desaparecem.

Implementação: `cli/stream.py` (`StreamRenderer`), testes em `cli/test_stream.py`.

---

## CLI: correcções de input do prompt_toolkit (porta do Hermes `pt_input_extras.py`)

- **Shift+Enter / Ctrl+Enter** não fazem nova linha por defeito em terminais
  Kitty/xterm com `modifyOtherKeys` — as sequências CSI-u (`\x1b[13;2u`, etc.) não
  estão mapeadas no prompt_toolkit. Mapeá-las para o tuplo `(Escape, ControlM)` faz
  o handler de Alt+Enter disparar.
- **Focus reports** (`\x1b[I` / `\x1b[O`, emitidos por iTerm2/Ghostty ao trocar de
  separador) vazam `[I`/`[O` para o input buffer. Mapeá-las para `Keys.Ignore`
  consome-as ao nível do parser.

Implementação: `_install_input_extras()` em `cli/tui.py`, chamado no `__init__`.

---

## Windows: encoding do output rich/Unicode

`rich.Console` tenta usar o cp1252 do Windows e rebenta com `UnicodeEncodeError` em
caracteres como `⊹ ˖`. Solução: embrulhar o stdout em UTF-8 —
`io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")` — e criar
o Console com `force_terminal=True`. Ver `cli/render.py`.

---

## Web: detecção de porta ocupada (IPv4 + IPv6)

O Node (Vite) escuta em `::1` (IPv6); `connect_ex("127.0.0.1", porta)` devolvia
"connection refused" e não detectava o conflito. Solução: tentar `socket.bind()` em
**ambas** as famílias (`AF_INET`/`127.0.0.1` e `AF_INET6`/`::1`) — se qualquer bind
falhar, a porta está em uso. Ver `_port_in_use()` em `cli/tui.py`.

---

## Fontes web (Google Fonts)

- O endpoint `fonts.google.com/download?family=…` devolve HTML, não ZIP. Usar os
  TTF crus do repo `github.com/google/fonts/…` em alternativa.
- O CSS da API Google Fonts só devolve URLs `.woff2` com um User-Agent moderno
  (Chrome); caso contrário devolve `.ttf`. Em alternativa, converter TTF→woff2
  localmente com `fonttools` + `brotli`.
- PowerShell trata `Lora[wght].ttf` como wildcard — usar nomes sem `[]`
  (`Lora-Variable.ttf`).

Fontes finais: Lora (corpo/serifa), Cuprum (UI), Fira Code (mono). Ver
`frontend/src/app.css`.
