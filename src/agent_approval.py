"""Agent tool approval system for Penelope.

Before executing dangerous tools (bash, python, write_file, edit_file),
the agent loop yields an approval_required event. The frontend shows a panel
with four decisions; the user's choice is posted to /api/agent/approve and
wakes the suspended agent via an asyncio.Event.

Decision values:
  allow_once    — execute this single invocation; ask again next time
  allow_session — allow this tool for the rest of this session
  allow_always  — remember the allowance (future sessions, implemented as
                  allow_session for now — can be persisted later)
  deny          — block this invocation; the agent sees an error result
"""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Dict, Optional

# Tools that require explicit user approval
DANGEROUS_TOOLS = {"bash", "python", "write_file", "edit_file"}

# approval_id → asyncio.Event (waiting for user input)
_pending: Dict[str, asyncio.Event] = {}
# approval_id → decision string
_decisions: Dict[str, str] = {}
# session_id → set of tool names allowed for this session
_session_allowed: Dict[str, set] = {}

# Approval panel timeout in seconds (auto-deny if user doesn't respond)
APPROVAL_TIMEOUT = 300


def new_approval_id() -> str:
    return secrets.token_hex(8)


def is_allowed_for_session(session_id: str, tool_name: str) -> bool:
    return tool_name in _session_allowed.get(session_id, set())


async def wait_for_approval(approval_id: str) -> str:
    """Block until the user decides (or APPROVAL_TIMEOUT elapses).

    Returns the decision string, or "deny" on timeout.
    """
    evt = asyncio.Event()
    _pending[approval_id] = evt
    try:
        await asyncio.wait_for(evt.wait(), timeout=APPROVAL_TIMEOUT)
        return _decisions.get(approval_id, "deny")
    except asyncio.TimeoutError:
        return "deny"
    finally:
        _pending.pop(approval_id, None)
        _decisions.pop(approval_id, None)


def record_decision(approval_id: str, decision: str, session_id: str = "", tool_name: str = "") -> bool:
    """Called by the approval API route to register a user decision.

    Returns True if approval_id was found and the event was triggered.
    """
    evt = _pending.get(approval_id)
    if evt is None:
        return False

    _decisions[approval_id] = decision

    if decision in ("allow_session", "allow_always") and session_id and tool_name:
        _session_allowed.setdefault(session_id, set()).add(tool_name)

    evt.set()
    return True


def clear_session(session_id: str) -> None:
    """Remove session-level allowances (called when conversation resets)."""
    _session_allowed.pop(session_id, None)
