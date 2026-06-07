#!/usr/bin/env pwsh
#
# penelope.ps1 — arranca a Penelope com um só comando no Windows (PowerShell 5.1+ ou 7+).
#
# Sobe (se preciso) o Ollama, o backend (FastAPI/uvicorn :8000) e o frontend
# (SvelteKit/Vite :5173), espera o frontend e abre o browser. Ctrl+C / fechar a
# janela encerra os processos-filho.
#
# Uso: a partir de qualquer pasta, `penelope` (via bin\penelope.cmd no PATH) ou
#      `pwsh -File bin\penelope.ps1`.

$ErrorActionPreference = 'Stop'

# Raiz do projeto = pasta acima de bin\.
$Root = Split-Path -Parent $PSScriptRoot
$BackendPort = 8000
$FrontendPort = 5173
$OllamaUrl = 'http://127.0.0.1:11434'
$AppUrl = "http://localhost:$FrontendPort"

function Test-Url($url) {
	try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $url | Out-Null; return $true }
	catch { return $false }
}
function Wait-Url($url, $tries = 80) {
	for ($i = 0; $i -lt $tries; $i++) {
		if (Test-Url $url) { return $true }
		Start-Sleep -Milliseconds 500
	}
	return $false
}

Write-Host "penelope: raiz do projeto = $Root"

$ollama = $null
$backend = $null
$frontend = $null

try {
	# --- 1) Ollama ---
	if (Test-Url "$OllamaUrl/api/tags") {
		Write-Host 'penelope: Ollama já está a correr.'
	}
	elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
		Write-Host 'penelope: a arrancar o Ollama…'
		$ollama = Start-Process ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden
		Wait-Url "$OllamaUrl/api/tags" 60 | Out-Null
	}
	else {
		Write-Warning "penelope: 'ollama' não encontrado. Instala/abre o Ollama e tenta de novo."
	}

	# --- 2) Backend (FastAPI) ---
	Write-Host "penelope: a arrancar o backend (:$BackendPort)…"
	$backend = Start-Process uv -PassThru -WorkingDirectory "$Root\backend" `
		-ArgumentList @('run', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$BackendPort")

	# --- 3) Frontend (Vite) ---
	if (-not (Test-Path "$Root\frontend\node_modules")) {
		Write-Host 'penelope: a instalar dependências do frontend (1ª vez)…'
		Push-Location "$Root\frontend"
		npm install
		Pop-Location
	}
	Write-Host "penelope: a arrancar o frontend (:$FrontendPort)…"
	$frontend = Start-Process npm -PassThru -WorkingDirectory "$Root\frontend" `
		-ArgumentList @('run', 'dev', '--', '--port', "$FrontendPort", '--strictPort')

	# --- 4) Esperar e abrir o browser ---
	if (Wait-Url $AppUrl 80) {
		Write-Host "penelope: pronto -> $AppUrl"
		Start-Process $AppUrl
	}
	else {
		Write-Warning "penelope: abre manualmente $AppUrl"
	}

	Write-Host 'penelope: a correr. Carrega Ctrl+C (ou fecha a janela) para parar tudo.'
	# Bloqueia enquanto o backend viver.
	Wait-Process -Id $backend.Id
}
finally {
	Write-Host ''
	Write-Host 'penelope: a encerrar…'
	foreach ($p in @($frontend, $backend)) {
		if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
	}
	# Só matamos o Ollama se fomos NÓS a arrancá-lo.
	if ($ollama -and -not $ollama.HasExited) { Stop-Process -Id $ollama.Id -Force -ErrorAction SilentlyContinue }
}
