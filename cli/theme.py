"""Penelope TUI — One Dark theme constants and animated indicators."""
from __future__ import annotations

VERSION = "0.2.0"
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
TAGLINE = "assistente local"

STATUS_TEXT: dict[str, str] = {
    "thinking": "a pensar…",
    "web": "a pesquisar na web…",
    "memory": "a recuperar memória…",
}

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
