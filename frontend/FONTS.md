# Typography plan — Penelope

Penelope uses **three type roles** and nothing more. Two of them carry meaning
(sans = "you operating the app"; serif = "the assistant speaking"); the third is
for code. All fonts are **self-hosted** — no CDN, no network request — so the UI
renders identically offline, in line with the local-first invariant.

## The three roles

| Role | Variable | Font | Where it is used |
|---|---|---|---|
| **UI / sans** | `--font-ui` | **Rubik** (self-hosted) | Everything you operate: navigation, panels, buttons, inputs, labels, status bar, **your own chat messages**. |
| **Reading / serif** | `--font-body` | **Lora** (self-hosted) | **The LLM output only** — the assistant's prose in chat. Reserved for long-form reading. |
| **Code / mono** | `--font-mono` | **Fira Code** (self-hosted) | Code blocks and inline code, anywhere. |

Defined in [`src/app.css`](src/app.css) as CSS variables, themeable in one place.

## Why this split (the "better use" verdict)

The task was to decide the better use of two type families. The verdict:

- **Serif for the assistant's output, sans for everything else.** Long model
  replies read like prose, and a humanist serif (Lora) is more comfortable for
  sustained reading than a UI sans. Restricting serif to the LLM output also gives
  a clear visual signal: serif = "Penelope is talking", sans = "this is the app /
  this is me". Your own messages stay in sans, so the contrast stays meaningful.
- **Sans for the whole shell.** Controls, labels and dense data read better in a
  neutral sans. Rubik is clean and unobtrusive, which fits the minimalist intent.
- **Mono only for code.** Code never inherits the serif; `Markdown.svelte` forces
  `--font-mono` on code blocks and inline code.

Using serif for *everything* (the previous state) made your own messages and code
context feel like a document and blurred the "who is speaking" signal. Using sans
for *everything* loses the comfort of reading long replies. The split keeps both
strengths.

## Rules

1. **Never reference a web font CDN.** All `@font-face` `src` URLs point to
   `/fonts/*.woff2`. A `@import` from `fonts.googleapis.com` breaks offline use and
   the local-first invariant. (This was fixed: Rubik is now self-hosted.)
2. **Serif is for LLM output only.** Apply `--font-body` via `.msg-ai .body`, not
   the shared `.body`. User messages use `--font-ui`.
3. **Code is always `--font-mono`**, even inside an assistant (serif) message.
4. **Keep it to three roles.** New surfaces pick one of the existing variables; do
   not introduce a fourth family without a reason that survives the minimalist filter.

## Open item: Cuprum

`static/fonts/Cuprum-*.woff2` are present but **not wired** into any rule. Cuprum is
a *condensed display* sans — good for a wordmark or large headings, not for dense UI
text. Two clean options, your call:

- **Drop it** (remove the two woff2) to keep the font set minimal. *(Recommended,
  matches the minimalist philosophy.)*
- **Keep it as a display face** for the app wordmark / large titles only, via a new
  `--font-display: 'Cuprum', ...` used sparingly. Do **not** make it the UI body
  font.

## Files

- [`src/app.css`](src/app.css) — `@font-face` declarations and the `--font-*` tokens.
- [`src/lib/views/ChatView.svelte`](src/lib/views/ChatView.svelte) — `.msg-ai .body`
  serif scoping.
- `static/fonts/` — Rubik (UI), Lora (serif), Fira Code (mono) woff2.
