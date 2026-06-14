"""HTTP client for the Penelope backend API."""
from __future__ import annotations

import json
from typing import Generator

import httpx

DEFAULT_URL = "http://localhost:8000"


class PenelopeClient:
    def __init__(self, base_url: str = DEFAULT_URL):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=30.0)

    def health(self) -> dict:
        return self.client.get("/health").json()

    def list_models(self) -> list[str]:
        data = self.client.get("/models").json()
        return data.get("models", []) if isinstance(data, dict) else data

    def get_settings(self) -> dict:
        return self.client.get("/settings").json()

    def put_settings(self, patch: dict) -> dict:
        return self.client.put("/settings", json=patch).json()

    # -- Memory --

    def list_facts(self, q: str | None = None) -> list[dict]:
        params = {"q": q} if q else {}
        return self.client.get("/memory/facts", params=params).json()

    # -- Notes --

    def list_notes(self) -> list[dict]:
        return self.client.get("/notes").json()

    # -- Tasks --

    def list_tasks(self) -> list[dict]:
        return self.client.get("/tasks").json()

    def create_task(self, text: str) -> dict:
        return self.client.post("/tasks", json={"text": text}).json()

    def update_task(self, task_id: int, *, done: bool | None = None, text: str | None = None) -> dict:
        patch: dict = {}
        if done is not None:
            patch["done"] = done
        if text is not None:
            patch["text"] = text
        return self.client.patch(f"/tasks/{task_id}", json=patch).json()

    def delete_task(self, task_id: int) -> dict:
        return self.client.delete(f"/tasks/{task_id}").json()

    # -- Conversations --

    def list_conversations(self) -> list[dict]:
        return self.client.get("/conversations").json()

    # -- Chat (SSE streaming) --

    def chat_stream(
        self,
        message: str,
        *,
        conversation_id: int | None = None,
        model: str | None = None,
        incognito: bool = False,
    ) -> Generator[tuple[str, dict], None, None]:
        body = {
            "message": message,
            "conversation_id": conversation_id,
            "model": model,
            "incognito": incognito,
        }
        with self.client.stream("POST", "/chat", json=body, timeout=300.0) as resp:
            resp.raise_for_status()
            buffer = ""
            for chunk in resp.iter_text():
                buffer += chunk
                buffer = buffer.replace("\r\n", "\n")
                while "\n\n" in buffer:
                    idx = buffer.index("\n\n")
                    block = buffer[:idx]
                    buffer = buffer[idx + 2 :]
                    event, payload = _parse_sse_block(block)
                    if payload is not None:
                        yield event, payload


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
    try:
        return event, json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return event, None
