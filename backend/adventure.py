"""Store de aventuras do modo /aidungeon (estilo AI Dungeon).

Cada aventura é UM ficheiro JSON em `data/adventures/<id>.json` com toda a história
(turnos) + contexto persistente (memory/author's note/story cards). Este módulo é
puramente de ficheiros (sem dependência da base de dados); o índice de metadados é
arquivado nas settings pelo `main.py` (chave `adventures`), que chama `list_index()`.

Forma de um ficheiro de aventura:
{
  "id": "ab12cd34ef56",
  "title": "A Cripta de Vael",
  "scenario": "Premissa/mundo escrito no setup (Quick Start).",
  "instructions": "",          # AI Instructions extra (opcional)
  "memory": "",                # Story Summary / factos persistentes (/lembrar)
  "authors_note": "",          # Author's Note (/nota)
  "story_cards": [{"keys": ["rei"], "text": "..."}],   # world info por keyword (/cartao)
  "model": "hf.co/...:Q4_K_M",
  "sampler": {"temperature": 0.8, "repeat_penalty": 1.05, "min_p": 0.025},
  "turns": [{"role": "user"|"assistant", "mode": "do"|"say"|"story"|"continue"|null,
             "content": "...", "ts": "ISO8601"}],
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dir() -> Path:
    d = Path(settings.adventures_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(adv_id: str) -> Path:
    # IDs são hex de 12 chars; valida para impedir path traversal.
    if not re.fullmatch(r"[a-f0-9]{6,32}", adv_id or ""):
        raise ValueError("id de aventura inválido")
    return _dir() / f"{adv_id}.json"


def create(
    *,
    title: str,
    scenario: str,
    instructions: str = "",
    model: str = "",
    sampler: dict | None = None,
) -> dict:
    adv_id = uuid.uuid4().hex[:12]
    now = _now()
    adv = {
        "id": adv_id,
        "title": (title or "Aventura sem título").strip()[:120],
        "scenario": (scenario or "").strip(),
        "instructions": (instructions or "").strip(),
        "memory": "",
        "authors_note": "",
        "story_cards": [],
        "model": model or "",
        "sampler": sampler
        or {
            "temperature": settings.adventure_temperature,
            "repeat_penalty": settings.adventure_repeat_penalty,
            "min_p": settings.adventure_min_p,
        },
        "turns": [],
        "created_at": now,
        "updated_at": now,
    }
    save(adv)
    return adv


def load(adv_id: str) -> dict | None:
    p = _path(adv_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save(adv: dict) -> dict:
    adv["updated_at"] = _now()
    p = _path(adv["id"])
    p.write_text(json.dumps(adv, ensure_ascii=False, indent=2), encoding="utf-8")
    return adv


def append_turn(adv_id: str, *, role: str, content: str, mode: str | None = None) -> dict | None:
    adv = load(adv_id)
    if adv is None:
        return None
    adv["turns"].append(
        {"role": role, "mode": mode, "content": content, "ts": _now()}
    )
    return save(adv)


def replace_turns(adv_id: str, turns: list[dict]) -> dict | None:
    """Substitui os turnos (usado por undo/retroceder e edit)."""
    adv = load(adv_id)
    if adv is None:
        return None
    adv["turns"] = turns
    return save(adv)


def patch(adv_id: str, fields: dict) -> dict | None:
    """Atualiza campos editáveis (title/memory/authors_note/story_cards/instructions)."""
    adv = load(adv_id)
    if adv is None:
        return None
    for k in ("title", "memory", "authors_note", "instructions", "scenario"):
        if k in fields and isinstance(fields[k], str):
            adv[k] = fields[k]
    if "story_cards" in fields and isinstance(fields["story_cards"], list):
        adv["story_cards"] = fields["story_cards"]
    if "turns" in fields and isinstance(fields["turns"], list):
        adv["turns"] = fields["turns"]
    return save(adv)


def delete(adv_id: str) -> bool:
    p = _path(adv_id)
    if p.exists():
        p.unlink()
        return True
    return False


def meta(adv: dict) -> dict:
    """Metadados (sem os turnos) para o índice arquivado nas settings + lista da UI."""
    return {
        "id": adv["id"],
        "title": adv.get("title", ""),
        "scenario_summary": (adv.get("scenario", "") or "")[:160],
        "model": adv.get("model", ""),
        "turn_count": len(adv.get("turns", [])),
        "created_at": adv.get("created_at", ""),
        "updated_at": adv.get("updated_at", ""),
    }


def list_index() -> list[dict]:
    """Lista de metadados de todas as aventuras, mais recentes primeiro."""
    out: list[dict] = []
    for p in _dir().glob("*.json"):
        try:
            adv = json.loads(p.read_text(encoding="utf-8"))
            out.append(meta(adv))
        except (json.JSONDecodeError, OSError):
            continue
    out.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
    return out
