#!/usr/bin/env pwsh
#
# penelope.ps1 — unified launcher for Penelope on Windows.
#
# Usage:
#   penelope              → interactive TUI (terminal chat)
#   penelope web          → start the full web stack (backend + frontend + browser)
#   penelope <command>    → pass-through to the CLI (status, chat, task, etc.)
#
# First time? Run `bin\setup.cmd` once.

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root 'backend\.venv\Scripts\python.exe'

if (-not (Test-Path $Venv)) {
    Write-Warning "penelope: venv not found at $Venv. Run 'bin\setup.cmd' first."
    exit 1
}

# --- Route by first argument ---

$sub = if ($args.Count -gt 0) { $args[0] } else { $null }

if ($sub -eq 'web') {
    # Launch the full web stack (Ollama + backend + frontend + browser).
    & $PSScriptRoot\penelope-web.ps1 @($args | Select-Object -Skip 1)
    exit $LASTEXITCODE
}

# Everything else goes to `python -m cli` from the project root.
Push-Location $Root
try {
    & $Venv -m cli @args
}
finally {
    Pop-Location
}
exit $LASTEXITCODE
