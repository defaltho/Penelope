"""Tests for the streaming renderer's tag detection and buffering."""
from __future__ import annotations

import io

import pytest

from cli import stream as stream_mod
from cli.stream import StreamRenderer, strip_markdown_syntax


@pytest.fixture
def capture(monkeypatch):
    """Capture everything the renderer prints, stripped of rich markup/style."""
    from rich.console import Console

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=80, markup=True)
    monkeypatch.setattr(stream_mod, "get_console", lambda: console)
    return buf


def _feed_tokens(renderer: StreamRenderer, tokens: list[str]) -> None:
    for tok in tokens:
        renderer.feed(tok)
    renderer.flush()


# ── Split-tag detection (the bug naive `tag in token` misses) ──


def test_open_tag_split_across_tokens(capture):
    r = StreamRenderer(show_reasoning=False, show_timestamp=False)
    # "<think>" arrives in three fragments, then reasoning, then close split too.
    _feed_tokens(r, ["<thi", "nk>", "segredo interno", "</think>", "Olá!"])
    out = capture.getvalue()
    assert "segredo interno" not in out  # reasoning dropped (show_reasoning=False)
    assert "Olá!" in out
    assert r.reasoning_text == "segredo interno"


def test_close_tag_split_across_tokens(capture):
    r = StreamRenderer(show_reasoning=False, show_timestamp=False)
    _feed_tokens(r, ["<think>", "raciocinio", "</thi", "nk>", "resposta"])
    out = capture.getvalue()
    assert "raciocinio" not in out
    assert "resposta" in out


# ── Block-boundary detection (avoid prose false positives) ──


def test_tag_mentioned_in_prose_is_not_reasoning(capture):
    r = StreamRenderer(show_reasoning=False, show_timestamp=False)
    # The model talks ABOUT the tag mid-sentence — must not enter reasoning.
    _feed_tokens(r, ["Usa o <think> para pensar."])
    out = capture.getvalue()
    assert "Usa o <think> para pensar." in out
    assert r.reasoning_text == ""


def test_tag_at_line_start_is_reasoning(capture):
    r = StreamRenderer(show_reasoning=False, show_timestamp=False)
    _feed_tokens(r, ["<think>oculto</think>visivel"])
    out = capture.getvalue()
    assert "oculto" not in out
    assert "visivel" in out


# ── Reasoning rendering ──


def test_reasoning_shown_in_box_above_response(capture):
    r = StreamRenderer(show_reasoning=True, show_timestamp=False)
    _feed_tokens(r, ["<think>\na minha analise\n</think>\nA resposta final"])
    out = capture.getvalue()
    assert "raciocínio" in out  # reasoning box header
    assert "a minha analise" in out
    assert "A resposta final" in out
    # Reasoning box must appear before the response box.
    assert out.index("raciocínio") < out.index("A resposta final")


# ── Response box framing ──


def test_response_box_drawn(capture):
    r = StreamRenderer(show_reasoning=False, show_timestamp=False)
    _feed_tokens(r, ["linha um\nlinha dois"])
    out = capture.getvalue()
    assert "╭─" in out and "╰" in out
    assert "penelope" in out
    assert "linha um" in out and "linha dois" in out


def test_no_box_when_only_reasoning(capture):
    r = StreamRenderer(show_reasoning=False, show_timestamp=False)
    _feed_tokens(r, ["<think>so penso</think>"])
    out = capture.getvalue()
    assert "╭─" not in out
    assert r.produced_response is False


def test_produced_response_true_after_flush(capture):
    r = StreamRenderer(show_reasoning=False, show_timestamp=False)
    _feed_tokens(r, ["uma resposta"])
    # produced_response must stay True even after the box has been closed.
    assert r.produced_response is True


# ── Markdown stripping ──


def test_markdown_stripped_in_response(capture):
    r = StreamRenderer(show_reasoning=False, strip_markdown=True, show_timestamp=False)
    _feed_tokens(r, ["**negrito** e `codigo`"])
    out = capture.getvalue()
    assert "negrito e codigo" in out
    assert "**" not in out
    assert "`" not in out


def test_strip_markdown_syntax_preserves_cron():
    # "* * * * *" must not be mangled into a horizontal rule.
    assert strip_markdown_syntax("* * * * *") == "* * * * *"


def test_bracketed_text_not_treated_as_rich_markup(capture):
    r = StreamRenderer(show_reasoning=False, strip_markdown=False, show_timestamp=False)
    _feed_tokens(r, ["valor [importante] aqui"])
    out = capture.getvalue()
    assert "[importante]" in out
