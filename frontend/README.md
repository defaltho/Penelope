# Penelope: frontend

SvelteKit (Svelte 5 + runes) UI for Penelope, the local-first AI assistant.
One Dark theme + Fira Code. Talks to the FastAPI backend over HTTP/SSE.

For the full project overview and the one-command launcher, see the
[root README](../README.md).

## Develop

```bash
npm install
npm run dev          # Vite dev server on :5173, proxies /api -> backend :8000
```

The backend must be running on `127.0.0.1:8000` (see [`../backend`](../backend)).
Open http://localhost:5173.

## Useful scripts

```bash
npm run check        # svelte-check (types + Svelte diagnostics)
npm run build        # production build
npm run preview      # preview the production build
```

## Layout

```
src/
├── routes/+page.svelte      # app shell (icon rail + active view)
├── lib/
│   ├── api.ts               # backend helpers (conversations, memory, images…)
│   ├── chat.ts              # SSE streaming (normalizes sse-starlette CRLF)
│   ├── stream-buffer.ts     # smooth token rendering
│   ├── components/          # Spinner, ActivityLane, ThinkingPanel, Markdown…
│   └── views/               # Chat, Compare, Notes, Tasks, Settings, Agents…
└── app.html                 # document shell
```
