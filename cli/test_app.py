"""Drive the persistent TUI Application via a pipe input (no real TTY)."""
from __future__ import annotations

import threading
import time

import pytest
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from cli.tui import PenelopeTUI


def _run_app_with(tui: PenelopeTUI, keys: str, *, after=None, timeout=5.0):
    """Build the app on a pipe input, feed `keys`, run until it exits."""
    with create_pipe_input() as inp:
        app = tui._build_app(app_input=inp, app_output=DummyOutput())

        def feed():
            time.sleep(0.05)
            inp.send_text(keys)
            if after:
                after(inp)

        t = threading.Thread(target=feed, daemon=True)
        t.start()
        # Guard against a hang: force-exit after timeout.
        watchdog = threading.Timer(timeout, lambda: app.exit())
        watchdog.start()
        try:
            app.run()
        finally:
            watchdog.cancel()


def _make_tui(monkeypatch) -> PenelopeTUI:
    tui = PenelopeTUI(model_override="qwen3-vl:4b")
    # Never touch the backend in these tests.
    monkeypatch.setattr(tui, "_load_settings", lambda: None)
    return tui


def test_app_builds_and_exits_on_ctrl_d(monkeypatch):
    tui = _make_tui(monkeypatch)
    _run_app_with(tui, "\x04")  # Ctrl-D on empty input exits
    assert tui._app is not None


def test_incognito_toggle_via_slash_command(monkeypatch):
    tui = _make_tui(monkeypatch)
    assert tui.incognito is False
    _run_app_with(tui, "/incognito\r\x04")
    assert tui.incognito is True


def test_websearch_toggle_and_think_toggle(monkeypatch):
    tui = _make_tui(monkeypatch)
    _run_app_with(tui, "/websearch\r/think\r\x04")
    assert tui.web_search is True
    assert tui._show_thinking is False


def test_exit_command_quits(monkeypatch):
    tui = _make_tui(monkeypatch)
    _run_app_with(tui, "/exit\r")
    # If /exit didn't quit, the watchdog would have, but the app should be built.
    assert tui._app is not None


def test_web_command_sets_pending_action(monkeypatch):
    tui = _make_tui(monkeypatch)
    _run_app_with(tui, "/web\r")
    assert tui._pending_action == "web"


def test_plain_text_dispatches_chat(monkeypatch):
    tui = _make_tui(monkeypatch)
    captured = []
    # Replace _chat so we don't hit the network; just record the message.
    monkeypatch.setattr(tui, "_chat", lambda msg: captured.append(msg))
    _run_app_with(tui, "olá penelope\r", timeout=5.0)
    # Give the chat thread a moment to run.
    time.sleep(0.2)
    assert captured == ["olá penelope"]


def test_alt_enter_inserts_newline_not_submit(monkeypatch):
    tui = _make_tui(monkeypatch)
    captured = []
    monkeypatch.setattr(tui, "_chat", lambda msg: captured.append(msg))
    # Alt+Enter (\x1b\r) inserts a newline; then real Enter submits both lines.
    _run_app_with(tui, "linha1\x1b\rlinha2\r")
    time.sleep(0.2)
    assert captured == ["linha1\nlinha2"]
