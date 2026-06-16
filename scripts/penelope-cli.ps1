# scripts/penelope-cli.ps1 — Penelope CLI launcher (Windows PowerShell)
#
# Usage:
#   .\scripts\penelope-cli.ps1                  # interactive TUI
#   .\scripts\penelope-cli.ps1 chat "olá"       # one-shot
#   .\scripts\penelope-cli.ps1 status           # health check
#   .\scripts\penelope-cli.ps1 memory list      # list facts
#
# Environment variables (optional):
#   PENELOPE_URL      — backend URL (default: http://localhost:7000)
#   PENELOPE_API_KEY  — API key from Settings → Security → API Tokens
#   PENELOPE_USER     — username (fallback if no API key)
#   PENELOPE_PASSWORD — password (fallback if no API key)

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# python -m cli must run from the project root so Python finds the cli package
Push-Location $ProjectRoot
try {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

    if (Test-Path $VenvPython) {
        & $VenvPython -m cli @Args
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        uv run python -m cli @Args
    } else {
        python -m cli @Args
    }
} finally {
    Pop-Location
}
