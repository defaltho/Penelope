"""Streaming response renderer — line-buffered, tag-aware, box-framed.

Faithful port of the Hermes Agent CLI streaming display
(``cli.py:_stream_delta`` / ``_emit_stream_text`` / ``_flush_stream``),
adapted to Penelope's rich console and One Dark theme.

Design notes carried over from Hermes:

- A **pre-filter buffer** accumulates raw deltas so reasoning tags
  (``<think>`` …) are detected even when split across token boundaries
  (``<thi`` + ``nk>``) — the naive ``if tag in token`` check misses these.
- Reasoning tags are only honoured at a **block boundary** (start of stream
  or after a newline with only whitespace before the tag), so a model that
  *mentions* ``<think>`` in prose does not flip the renderer into reasoning
  mode.
- The response body is indented with ``_STREAM_PAD`` (4 spaces) to match the
  box padding. ``┊`` stays reserved for the activity/tool feed, not response
  text.
- Reasoning, when shown, renders in a dim box ABOVE the response; response
  text that arrives while the reasoning box is open is deferred until it
  closes.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

from cli.render import get_console
from cli.theme import ACCENT, FG, MUTED

_STREAM_PAD = "    "  # 4-space indent for streamed response text

_OPEN_TAGS = ("<REASONING_SCRATCHPAD>", "<think>", "<reasoning>", "<THINKING>", "<thinking>", "<thought>")
_CLOSE_TAGS = ("</REASONING_SCRATCHPAD>", "</think>", "</reasoning>", "</THINKING>", "</thinking>", "</thought>")
_MAX_CLOSE_LEN = max(len(t) for t in _CLOSE_TAGS)


def strip_markdown_syntax(text: str) -> str:
    """Best-effort markdown marker removal for plain-text display."""
    plain = text or ""
    plain = re.sub(r"^\s{0,3}(?:[-_]\s*){3,}$", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"^\s{0,3}(?:\*\s*){3}\s*$", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"^\s{0,3}#{1,6}\s+", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"(```+|~~~+)", "", plain)
    plain = re.sub(r"`([^`]*)`", r"\1", plain)
    plain = re.sub(r"!\[([^\]]*)\]\([^\)]*\)", r"\1", plain)
    plain = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", plain)
    plain = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", plain)
    plain = re.sub(r"(?<!\w)___([^_]+)___(?!\w)", r"\1", plain)
    plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", plain)
    plain = re.sub(r"(?<!\w)__([^_]+)__(?!\w)", r"\1", plain)
    plain = re.sub(r"\*([^\s*][^*]*?[^\s*])\*", r"\1", plain)
    plain = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", plain)
    plain = re.sub(r"~~([^~]+)~~", r"\1", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip("\n")


class StreamRenderer:
    """Stateful renderer for one streamed assistant turn.

    Feed it text deltas via :meth:`feed`; call :meth:`flush` once the stream
    ends. ``show_reasoning`` toggles whether reasoning blocks render in a dim
    box (True) or are silently dropped (False). ``strip_markdown`` removes
    markdown markers from the response body for clean plain-text display.
    """

    def __init__(self, *, label: str = " ⊹ penelope ", show_reasoning: bool = True,
                 strip_markdown: bool = True, show_timestamp: bool = True) -> None:
        self.console = get_console()
        self._label = label
        self.show_reasoning = show_reasoning
        self.strip_markdown = strip_markdown
        self.show_timestamp = show_timestamp

        self.started = False
        self._box_opened = False
        self._produced = False
        self._reasoning_opened = False
        self._in_reasoning = False
        self._last_was_newline = True

        self._prefilt = ""
        self._buf = ""
        self._reasoning_buf = ""
        self._deferred = ""

        # Captured plain reasoning text (for callers that want it).
        self.reasoning_text = ""

    # ── Public API ──────────────────────────────────────────

    def feed(self, text: str | None) -> None:
        """Process one streamed delta. ``None`` flushes and resets boxes."""
        if text is None:
            self.flush()
            return
        if not text:
            return
        self.started = True
        self._prefilt += text
        self._pump()

    def flush(self) -> None:
        """Emit any buffered remainder and close open boxes."""
        # Unclosed reasoning block at end-of-stream = false positive; recover.
        if self._in_reasoning and self._prefilt:
            self._in_reasoning = False
            self._emit_text(self._prefilt)
            self._prefilt = ""

        self._close_reasoning_box()

        if self._buf:
            self._emit_line(self._buf)
            self._buf = ""

        if self._box_opened:
            w = self._width()
            self.console.print(f"[{ACCENT}]╰{'─' * (w - 2)}╯[/{ACCENT}]")
            self._box_opened = False

    @property
    def produced_response(self) -> bool:
        """True if any response text (not just reasoning) was rendered."""
        return self._produced

    # ── Tag-aware pump (mirrors Hermes _stream_delta) ───────

    def _pump(self) -> None:
        if not self._in_reasoning:
            if self._enter_reasoning_if_boundary():
                # Recurse to process remaining prefilt as reasoning.
                self._pump()
                return
            # Hold back a possible partial open tag at the buffer tail.
            safe = self._prefilt
            for tag in _OPEN_TAGS:
                for i in range(1, len(tag)):
                    if self._prefilt.endswith(tag[:i]):
                        safe = self._prefilt[:-i]
                        break
            if safe:
                self._emit_text(safe)
                self._last_was_newline = safe.endswith("\n")
                self._prefilt = self._prefilt[len(safe):]
            return

        # Inside a reasoning block — look for a close tag.
        for tag in _CLOSE_TAGS:
            idx = self._prefilt.find(tag)
            if idx != -1:
                self._in_reasoning = False
                inner = self._prefilt[:idx]
                if inner and self.show_reasoning:
                    self._reasoning_delta(inner)
                self.reasoning_text += inner
                after = self._prefilt[idx + len(tag):]
                self._prefilt = ""
                if after:
                    self._prefilt = after
                    self._pump()
                return
        # No close tag yet: stream the safe prefix, hold tail for a split tag.
        if len(self._prefilt) > _MAX_CLOSE_LEN:
            safe = self._prefilt[:-_MAX_CLOSE_LEN]
            if self.show_reasoning:
                self._reasoning_delta(safe)
            self.reasoning_text += safe
            self._prefilt = self._prefilt[-_MAX_CLOSE_LEN:]

    def _enter_reasoning_if_boundary(self) -> bool:
        """If an open tag sits at a block boundary, emit preceding text,
        enter reasoning mode, and consume up to the tag. Returns True if so."""
        for tag in _OPEN_TAGS:
            search = 0
            while True:
                idx = self._prefilt.find(tag, search)
                if idx == -1:
                    break
                preceding = self._prefilt[:idx]
                if idx == 0:
                    boundary = self._last_was_newline
                else:
                    last_nl = preceding.rfind("\n")
                    if last_nl == -1:
                        boundary = self._last_was_newline and preceding.strip() == ""
                    else:
                        boundary = preceding[last_nl + 1:].strip() == ""
                if boundary:
                    if preceding:
                        self._emit_text(preceding)
                        self._last_was_newline = preceding.endswith("\n")
                    self._in_reasoning = True
                    self._prefilt = self._prefilt[idx + len(tag):]
                    return True
                search = idx + 1
        return False

    # ── Response box emission ───────────────────────────────

    def _emit_text(self, text: str) -> None:
        if not text:
            return
        # Defer response content while the reasoning box is still open so
        # reasoning always renders above the response.
        if self.show_reasoning and self._reasoning_opened:
            self._deferred += text
            return

        self._close_reasoning_box()

        if not self._box_opened:
            text = text.lstrip("\n")
            if not text:
                return
            self._open_box()

        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._emit_line(line)

    def _open_box(self) -> None:
        self._box_opened = True
        self._produced = True
        label = self._label
        if self.show_timestamp:
            label = f"{label}{datetime.now().strftime('%H:%M')} "
        w = self._width()
        fill = w - 2 - len(label)
        self.console.print(f"[{ACCENT}]╭─{label}{'─' * max(fill - 1, 0)}╮[/{ACCENT}]")

    def _emit_line(self, line: str) -> None:
        if self.strip_markdown:
            line = strip_markdown_syntax(line)
        self.console.print(f"{_STREAM_PAD}{line}", style=FG, markup=False)

    # ── Reasoning box ───────────────────────────────────────

    def _reasoning_delta(self, text: str) -> None:
        if not text or self._box_opened:
            return
        if not self._reasoning_opened:
            text = text.lstrip("\n")
            if not text:
                return
            self._reasoning_opened = True
            w = self._width()
            label = " raciocínio "
            fill = w - 2 - len(label)
            self.console.print(f"[{MUTED}]┌─{label}{'─' * max(fill - 1, 0)}┐[/{MUTED}]")
        self._reasoning_buf += text
        while "\n" in self._reasoning_buf:
            line, self._reasoning_buf = self._reasoning_buf.split("\n", 1)
            self.console.print(f"{_STREAM_PAD}{line}", style=f"{MUTED} italic", markup=False)
        if len(self._reasoning_buf) > 80:
            self.console.print(f"{_STREAM_PAD}{self._reasoning_buf}", style=f"{MUTED} italic", markup=False)
            self._reasoning_buf = ""

    def _close_reasoning_box(self) -> None:
        if not self._reasoning_opened:
            return
        if self._reasoning_buf:
            self.console.print(f"{_STREAM_PAD}{self._reasoning_buf}", style=f"{MUTED} italic", markup=False)
            self._reasoning_buf = ""
        w = self._width()
        self.console.print(f"[{MUTED}]└{'─' * (w - 2)}┘[/{MUTED}]")
        self._reasoning_opened = False
        if self._deferred:
            deferred, self._deferred = self._deferred, ""
            self._emit_text(deferred)

    def _width(self) -> int:
        return max(32, self.console.width or 80)
