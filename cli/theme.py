"""Penelope TUI — One Dark theme constants and animated indicators."""
from __future__ import annotations

VERSION = "1.5"
BRAND = "penelope"
PROMPT_SYMBOL = "› "

# One Dark palette
ACCENT = "#61afef"
SUCCESS = "#98c379"
WARNING = "#e5c07b"
ERROR = "#e06c75"
MUTED = "#5c6370"
FG = "#abb2bf"
THINKING = "#c678dd"
ORANGE = "#d19a66"

# Chrome (rules, borders, status bar)
RULE = "#3b4048"          # thin separators / rules
BAR_BG = "#1b1f27"        # completion-menu background

# Brand
SPARK = "⊹"               # Penelope identity motif
# Human-language strings (tagline, status text, capability list) live in cli.i18n.

# Spinner animation (braille dots — clean, on-brand)
SPINNER_FRAMES: list[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Tool/activity icons for the feed (monochrome glyphs, cohesive with chrome)
TOOL_ICONS: dict[str, str] = {
    "thinking": "◇",
    "web": "⌕",
    "memory": "◈",
    "tool": "▪",
}

# Context bar thresholds (percentage → color)
CONTEXT_COLORS: list[tuple[int, str]] = [
    (50, SUCCESS),
    (80, WARNING),
    (95, ORANGE),
    (100, ERROR),
]

# Status bar (Hermes-style): ⚕ health │ ctx │ [bar] │ wall │ ⏲ turn
HEALTH_GLYPH = "⚕"
TIMER_GLYPH = "⏲"
BAR_CELLS = 10
BAR_FILLED = "█"
BAR_EMPTY = "░"
SEP = " │ "
# Estimated context window (tokens) used to fill the ctx bar when the backend
# does not report a real figure. Overridable from settings (num_ctx).
DEFAULT_CTX_WINDOW = 8192

# Small woven-loom motif (Penelope weaves) shown beside the banner lists.
LOOM_ART: list[str] = [
    "╭─┬─┬─┬─┬─╮",
    "├─┼─┼─┼─┼─┤",
    "├─┼─◈─┼─┼─┤",
    "├─┼─┼─┼─┼─┤",
    "╰─┴─┴─┴─┴─╯",
]
