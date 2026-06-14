#!/usr/bin/env pwsh
#
# penelope-web.ps1 — start the full Penelope web stack on Windows.
#
# Brings up (if needed) Ollama, the backend (FastAPI/uvicorn :8000) and the
# frontend (SvelteKit/Vite :5173), waits for the frontend and opens the browser.
# Ctrl+C / closing the window stops the child processes.
#
# Called via: penelope web

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$BackendPort = 8000
$FrontendPort = 5173
$OllamaUrl = 'http://127.0.0.1:11434'
$AppUrl = "http://localhost:$FrontendPort"

function Test-Url($url) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $url | Out-Null; return $true }
    catch { return $false }
}
function Resolve-Exe($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}
function Wait-Url($url, $tries = 80) {
    for ($i = 0; $i -lt $tries; $i++) {
        if (Test-Url $url) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Write-Host "penelope web: project root = $Root"

$ollama = $null
$backend = $null
$frontend = $null

try {
    # --- 1) Ollama ---
    if (Test-Url "$OllamaUrl/api/tags") {
        Write-Host 'penelope web: Ollama is already running.'
    }
    elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
        Write-Host 'penelope web: starting Ollama…'
        $ollama = Start-Process ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden
        Wait-Url "$OllamaUrl/api/tags" 60 | Out-Null
    }
    else {
        Write-Warning "penelope web: 'ollama' not found. Run 'bin\setup.cmd' or install it from https://ollama.com."
    }

    # --- 1b) Make sure the required models are present ---
    if ((Get-Command ollama -ErrorAction SilentlyContinue) -and (Test-Url "$OllamaUrl/api/tags")) {
        $list = (& ollama list 2>$null | Out-String)
        foreach ($pair in @(@('qwen3-vl:4b', 'qwen3-vl'), @('embeddinggemma', 'embeddinggemma'))) {
            if ($list -notmatch [regex]::Escape($pair[1])) {
                Write-Host "penelope web: model missing, pulling $($pair[0]) … (first run only)"
                & ollama pull $pair[0]
                $list = (& ollama list 2>$null | Out-String)
            }
        }
    }

    # Resolve the executables once.
    $uvExe = Resolve-Exe 'uv'
    $npmExe = Resolve-Exe 'npm'
    if (-not $uvExe) { throw "penelope web: 'uv' not found on PATH. Run 'bin\setup.cmd' or install uv." }
    if (-not $npmExe) { throw "penelope web: 'npm' not found on PATH. Run 'bin\setup.cmd' or install Node.js." }

    # --- 2) Backend (FastAPI) ---
    Write-Host "penelope web: starting the backend (:$BackendPort)…"
    $backend = Start-Process $uvExe -PassThru -WorkingDirectory "$Root\backend" `
        -ArgumentList @('run', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$BackendPort")

    # --- 3) Frontend (Vite) ---
    if (-not (Test-Path "$Root\frontend\node_modules")) {
        Write-Host 'penelope web: installing frontend dependencies (first run)…'
        Push-Location "$Root\frontend"
        & $npmExe install
        Pop-Location
    }
    Write-Host "penelope web: starting the frontend (:$FrontendPort)…"
    $frontend = Start-Process $npmExe -PassThru -WorkingDirectory "$Root\frontend" `
        -ArgumentList @('run', 'dev', '--', '--port', "$FrontendPort", '--strictPort')

    # --- 4) Wait and open the browser ---
    if (Wait-Url $AppUrl 80) {
        Write-Host "penelope web: ready -> $AppUrl"
        Start-Process $AppUrl
    }
    else {
        Write-Warning "penelope web: open $AppUrl manually"
    }

    Write-Host 'penelope web: running. Press Ctrl+C (or close the window) to stop everything.'
    Wait-Process -Id $backend.Id
}
finally {
    Write-Host ''
    Write-Host 'penelope web: shutting down…'
    foreach ($p in @($frontend, $backend)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    if ($ollama -and -not $ollama.HasExited) { Stop-Process -Id $ollama.Id -Force -ErrorAction SilentlyContinue }
}
