"""HTTP client for the Penelope (Odysseus) backend API."""
from __future__ import annotations

import json
import os
from typing import Generator

import httpx

DEFAULT_URL = os.environ.get("PENELOPE_URL", "http://localhost:7000")
_SESSION_COOKIE = "odysseus_session"


class PenelopeClient:
    """REST + SSE client for the Penelope backend.

    Auth (in priority order):
      1. PENELOPE_API_KEY env var → X-API-Key header (recommended for CLI)
      2. PENELOPE_USER + PENELOPE_PASSWORD env vars → cookie login on first request
      3. Unauthenticated (works when AUTH_ENABLED=false)
    """

    def __init__(self, base_url: str = DEFAULT_URL):
        self.base_url = base_url.rstrip("/")
        self._api_key = os.environ.get("PENELOPE_API_KEY", "")
        self._cookie: str = ""
        headers: dict = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    def _ensure_auth(self) -> None:
        """Login with PENELOPE_USER/PASSWORD if no other auth is configured."""
        if self._api_key or self._cookie:
            return
        user = os.environ.get("PENELOPE_USER", "")
        pw = os.environ.get("PENELOPE_PASSWORD", "")
        if not user or not pw:
            return
        try:
            resp = self.client.post(
                "/api/auth/login",
                json={"username": user, "password": pw, "remember": True},
            )
            resp.raise_for_status()
            cookie = resp.cookies.get(_SESSION_COOKIE, "")
            if cookie:
                self._cookie = cookie
                self.client.cookies.set(_SESSION_COOKIE, cookie)
        except Exception:
            pass

    def _get(self, path: str, **kwargs) -> httpx.Response:
        self._ensure_auth()
        return self.client.get(path, **kwargs)

    def _post(self, path: str, **kwargs) -> httpx.Response:
        self._ensure_auth()
        return self.client.post(path, **kwargs)

    # -- Health --

    def health(self) -> dict:
        return self._get("/api/health").json()

    # -- Models --

    def list_models(self) -> list[str]:
        try:
            data = self._get("/api/models").json()
            if isinstance(data, list):
                return [str(m) for m in data]
            if isinstance(data, dict):
                return [str(m) for m in data.get("models", [])]
        except Exception:
            pass
        return []

    # -- Settings --

    def get_settings(self) -> dict:
        try:
            return self._get("/api/settings").json()
        except Exception:
            return {}

    def put_settings(self, patch: dict) -> dict:
        try:
            return self._post("/api/settings", json=patch).json()
        except Exception:
            return {}

    # -- Sessions (replaces conversations) --

    def list_sessions(self) -> list[dict]:
        try:
            data = self._get("/api/sessions").json()
            if isinstance(data, list):
                return data
            return data.get("sessions", [])
        except Exception:
            return []

    def create_session(self, name: str = "Penelope CLI") -> dict:
        """Create a new chat session; returns the session dict with 'id'."""
        try:
            resp = self._post(
                "/api/sessions",
                data={"name": name},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    # -- Memory --

    def list_facts(self, q: str | None = None) -> list[dict]:
        """Return memory entries; optional keyword filter applied client-side."""
        try:
            data = self._get("/api/memory").json()
            entries = data.get("memory", data) if isinstance(data, dict) else data
            if q:
                q_lower = q.lower()
                entries = [e for e in entries if q_lower in e.get("text", "").lower()]
            return entries
        except Exception:
            return []

    def add_fact(self, text: str, category: str = "preference", source: str = "user") -> dict:
        try:
            resp = self._post("/api/memory/add", json={"text": text, "category": category, "source": source})
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    def delete_fact(self, memory_id: str) -> dict:
        try:
            resp = self.client.delete(f"/api/memory/{memory_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    def pin_fact(self, memory_id: str, pinned: bool = True) -> dict:
        try:
            resp = self.client.post(f"/api/memory/{memory_id}/pin", data={"pinned": str(pinned).lower()})
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    def approve_decision(self, approval_id: str, decision: str, session_id: str, tool: str) -> dict:
        try:
            resp = self._post("/api/agent/approve", json={
                "approval_id": approval_id,
                "decision": decision,
                "session_id": session_id,
                "tool": tool,
            })
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    # -- Notes --

    def create_note(self, title: str, content: str = "") -> dict:
        try:
            resp = self._post("/api/notes", json={"title": title, "content": content})
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    def delete_note(self, note_id: str) -> dict:
        try:
            resp = self.client.delete(f"/api/notes/{note_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    # -- Skills --

    def list_skills(self) -> list[dict]:
        try:
            data = self._get("/api/skills").json()
            return data if isinstance(data, list) else data.get("skills", [])
        except Exception:
            return []

    # -- Notes --

    def list_notes(self) -> list[dict]:
        try:
            data = self._get("/api/notes").json()
            return data if isinstance(data, list) else data.get("notes", [])
        except Exception:
            return []

    # -- Tasks --

    def list_tasks(self) -> list[dict]:
        try:
            data = self._get("/api/tasks").json()
            return data if isinstance(data, list) else data.get("tasks", [])
        except Exception:
            return []

    def create_task(self, text: str) -> dict:
        try:
            return self._post("/api/tasks", json={"text": text}).json()
        except Exception:
            return {}

    def update_task(self, task_id: int, *, done: bool | None = None, text: str | None = None) -> dict:
        patch: dict = {}
        if done is not None:
            patch["done"] = done
        if text is not None:
            patch["text"] = text
        try:
            return self.client.patch(f"/api/tasks/{task_id}", json=patch).json()
        except Exception:
            return {}

    def delete_task(self, task_id: int) -> dict:
        try:
            return self.client.delete(f"/api/tasks/{task_id}").json()
        except Exception:
            return {}

    # -- Chat (SSE streaming) --

    def chat_stream(
        self,
        message: str,
        *,
        session_id: str | None = None,
        model: str | None = None,
        incognito: bool = False,
        use_web: bool = False,
        conversation_id: str | None = None,
    ) -> Generator[tuple[str, dict], None, None]:
        """Stream a chat message; yields (event, payload) pairs.

        Event normalization (Odysseus → Penelope-old CLI convention):
          {"delta": "..."} → event="token", payload={"token": "..."}
          {"type": "tool_start", ...} → event="status", payload={...}
          [DONE] → event="done", payload={}
        """
        self._ensure_auth()

        sid = session_id or conversation_id

        body: dict = {
            "message": message,
            "incognito": incognito,
        }
        if sid:
            body["session"] = sid
        if model:
            body["model"] = model
        if use_web:
            body["use_web"] = True

        with self.client.stream(
            "POST", "/api/chat_stream",
            json=body,
            timeout=300.0,
        ) as resp:
            resp.raise_for_status()
            buffer = ""
            for chunk in resp.iter_text():
                buffer += chunk
                buffer = buffer.replace("\r\n", "\n")
                while "\n\n" in buffer:
                    idx = buffer.index("\n\n")
                    block = buffer[:idx]
                    buffer = buffer[idx + 2:]
                    ev, payload = _parse_sse_block(block)
                    if payload is None:
                        continue
                    yield from _normalize_event(ev, payload)


def _parse_sse_block(block: str) -> tuple[str, dict | None]:
    event = "message"
    data_lines: list[str] = []
    for line in block.split("\n"):
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return event, None
    joined = "\n".join(data_lines)
    if joined == "[DONE]":
        return "done_sentinel", {}
    try:
        return event, json.loads(joined)
    except json.JSONDecodeError:
        return event, None


def _normalize_event(event: str, payload: dict) -> list[tuple[str, dict]]:
    """Translate Odysseus SSE events → (event, payload) pairs the TUI understands."""
    if event == "done_sentinel":
        return [("done", payload)]

    if isinstance(payload, dict):
        if "delta" in payload:
            return [("token", {"token": payload["delta"]})]

        t = payload.get("type", "")
        if t in ("tool_start", "tool_end", "agent_step"):
            text = payload.get("tool") or payload.get("text") or ""
            return [("status", {"kind": "thinking", "text": text})]
        if t == "compacted":
            return [("status", {"kind": "compacting", "text": "Compactando contexto…"})]
        if t == "model_info":
            return [("model_info", payload)]
        if t == "message_saved":
            return [("done", payload)]
        if t == "error":
            return [("error", {"error": payload.get("message", "Erro desconhecido")})]
        if t == "approval_required":
            return [("approval", payload)]
        if t == "memories_used":
            return [("memories_used", payload)]

    return []
