"""Tests for src/agent_approval.py.

All tests are synchronous-safe or use pytest-asyncio for the async gate.
No external deps required.
"""
import asyncio
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Helpers ────────────────────────────────────────────────────────────── #

def _fresh_state():
    """Clear module-level state between tests to avoid leakage."""
    import src.agent_approval as mod
    mod._pending.clear()
    mod._decisions.clear()
    mod._session_allowed.clear()


# ── Unit tests ─────────────────────────────────────────────────────────── #

def test_new_approval_id_returns_hex_string():
    from src.agent_approval import new_approval_id
    aid = new_approval_id()
    assert isinstance(aid, str)
    assert len(aid) == 16  # secrets.token_hex(8) → 16 hex chars
    int(aid, 16)  # must be valid hex


def test_new_approval_id_unique():
    from src.agent_approval import new_approval_id
    ids = {new_approval_id() for _ in range(20)}
    assert len(ids) == 20


def test_is_allowed_for_session_false_by_default():
    from src.agent_approval import is_allowed_for_session
    _fresh_state()
    assert is_allowed_for_session("session-1", "bash") is False


def test_record_decision_not_found():
    from src.agent_approval import record_decision
    _fresh_state()
    found = record_decision("nonexistent-id", "allow_once")
    assert found is False


def test_clear_session_removes_allowances():
    from src.agent_approval import clear_session, is_allowed_for_session
    import src.agent_approval as mod
    _fresh_state()
    mod._session_allowed["sess-abc"] = {"bash", "python"}
    clear_session("sess-abc")
    assert is_allowed_for_session("sess-abc", "bash") is False


def test_clear_session_nonexistent_does_not_raise():
    from src.agent_approval import clear_session
    _fresh_state()
    clear_session("does-not-exist")  # must not raise


# ── Async gate tests ────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_wait_for_approval_allow_once():
    from src.agent_approval import new_approval_id, record_decision, wait_for_approval, is_allowed_for_session
    _fresh_state()

    aid = new_approval_id()

    async def _decide_later():
        await asyncio.sleep(0.05)
        record_decision(aid, "allow_once", session_id="sess-1", tool_name="bash")

    asyncio.create_task(_decide_later())
    decision = await wait_for_approval(aid)

    assert decision == "allow_once"
    # allow_once must NOT grant session-level permission
    assert is_allowed_for_session("sess-1", "bash") is False


@pytest.mark.asyncio
async def test_wait_for_approval_allow_session():
    from src.agent_approval import new_approval_id, record_decision, wait_for_approval, is_allowed_for_session
    _fresh_state()

    aid = new_approval_id()

    async def _decide_later():
        await asyncio.sleep(0.05)
        record_decision(aid, "allow_session", session_id="sess-2", tool_name="python")

    asyncio.create_task(_decide_later())
    decision = await wait_for_approval(aid)

    assert decision == "allow_session"
    assert is_allowed_for_session("sess-2", "python") is True
    assert is_allowed_for_session("sess-2", "bash") is False


@pytest.mark.asyncio
async def test_wait_for_approval_deny():
    from src.agent_approval import new_approval_id, record_decision, wait_for_approval
    _fresh_state()

    aid = new_approval_id()

    async def _decide_later():
        await asyncio.sleep(0.05)
        record_decision(aid, "deny")

    asyncio.create_task(_decide_later())
    decision = await wait_for_approval(aid)
    assert decision == "deny"


@pytest.mark.asyncio
async def test_wait_for_approval_timeout_auto_deny(monkeypatch):
    """Short timeout → auto-deny without user response."""
    import src.agent_approval as mod
    _fresh_state()

    monkeypatch.setattr(mod, "APPROVAL_TIMEOUT", 0.05)

    aid = mod.new_approval_id()
    decision = await mod.wait_for_approval(aid)
    assert decision == "deny"


@pytest.mark.asyncio
async def test_pending_cleared_after_decision():
    import src.agent_approval as mod
    _fresh_state()

    aid = mod.new_approval_id()

    async def _decide():
        await asyncio.sleep(0.02)
        mod.record_decision(aid, "allow_once")

    asyncio.create_task(_decide())
    await mod.wait_for_approval(aid)

    # After wait resolves, pending and decisions should be cleaned up
    assert aid not in mod._pending
    assert aid not in mod._decisions


@pytest.mark.asyncio
async def test_allow_always_grants_session_permission():
    import src.agent_approval as mod
    _fresh_state()

    aid = mod.new_approval_id()

    async def _decide():
        await asyncio.sleep(0.02)
        mod.record_decision(aid, "allow_always", session_id="sess-3", tool_name="write_file")

    asyncio.create_task(_decide())
    await mod.wait_for_approval(aid)

    assert mod.is_allowed_for_session("sess-3", "write_file") is True
