"""Persistent last-session store for the Penelope CLI."""
from __future__ import annotations

from pathlib import Path


def _data_dir() -> Path:
    d = Path.home() / ".penelope"
    d.mkdir(exist_ok=True)
    return d


def save_last_session(session_id: str) -> None:
    try:
        (_data_dir() / "last_session").write_text(session_id, encoding="utf-8")
    except Exception:
        pass


def load_last_session() -> str | None:
    try:
        sid = (_data_dir() / "last_session").read_text(encoding="utf-8").strip()
        return sid or None
    except Exception:
        return None
