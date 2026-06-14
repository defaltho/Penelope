#!/usr/bin/env pwsh
#
# setup.ps1 — one-time bootstrap for Penelope on a fresh Windows machine.
#
# Installs the missing prerequisites (Ollama, uv, Node) via winget, pulls the
# models, and writes backend\.env with the 8GB-friendly model. It asks before
# installing anything and is safe to re-run.

$ErrorActionPreference = 'Stop'

$Bin = $PSScriptRoot
$Root = Split-Path -Parent $Bin
$ChatModel = 'qwen3-vl:4b'   # 8GB-VRAM-friendly default on Windows
$EmbedModel = 'embeddinggemma'
$OllamaUrl = 'http://127.0.0.1:11434'

function Ask($msg) {
	$r = Read-Host "penelope setup: $msg [Y/n]"
	return ([string]::IsNullOrWhiteSpace($r) -or $r -match '^[Yy]')
}
function Have($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Test-Url($url) {
	try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $url | Out-Null; return $true }
	catch { return $false }
}
function Install-Winget($id) {
	winget install --id $id -e --accept-source-agreements --accept-package-agreements
}

Write-Host "penelope setup: project root = $Root"

if (-not (Have 'winget')) {
	Write-Warning "winget not found. Install 'App Installer' from the Microsoft Store (or install Ollama/uv/Node manually), then re-run."
}

# --- 1) Ollama ---
if (Have 'ollama') { Write-Host 'penelope setup: Ollama is installed.' }
elseif ((Have 'winget') -and (Ask 'Ollama is not installed. Install it now?')) { Install-Winget 'Ollama.Ollama' }

# --- 2) uv ---
if (Have 'uv') { Write-Host 'penelope setup: uv is installed.' }
elseif (Ask 'uv (Python package manager) is not installed. Install it now?') {
	if (Have 'winget') { Install-Winget 'astral-sh.uv' }
	else { powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex" }
}

# --- 3) Node.js ---
if ((Have 'node') -and (Have 'npm')) { Write-Host 'penelope setup: Node.js is installed.' }
elseif ((Have 'winget') -and (Ask 'Node.js is not installed. Install it now?')) { Install-Winget 'OpenJS.NodeJS.LTS' }

# Refresh PATH for this session so freshly installed tools resolve.
$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
            [System.Environment]::GetEnvironmentVariable('Path', 'User')

# --- 4) Pull the models (start Ollama briefly if needed) ---
if (Have 'ollama') {
	$proc = $null
	if (-not (Test-Url "$OllamaUrl/api/tags")) {
		Write-Host 'penelope setup: starting Ollama to pull models…'
		$proc = Start-Process ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden
		for ($i = 0; $i -lt 60; $i++) { if (Test-Url "$OllamaUrl/api/tags") { break }; Start-Sleep -Milliseconds 500 }
	}
	$list = (& ollama list 2>$null | Out-String)
	foreach ($m in @($ChatModel, $EmbedModel)) {
		if ($list -match [regex]::Escape($m)) { Write-Host "penelope setup: model $m already present." }
		else { Write-Host "penelope setup: pulling $m … (this can take a while)"; & ollama pull $m }
	}
	if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}

# --- 5) Write backend\.env with the 8GB-friendly model ---
$envFile = Join-Path $Root 'backend\.env'
if (Test-Path $envFile) {
	Write-Host "penelope setup: $envFile already exists, leaving it untouched."
}
elseif (Ask "Set ASSISTANT_CHAT_MODEL=$ChatModel in backend\.env (recommended for 8GB GPUs)?") {
	"ASSISTANT_CHAT_MODEL=$ChatModel" | Out-File -Encoding ascii $envFile
	Write-Host "penelope setup: wrote $envFile"
}

Write-Host ''
Write-Host 'penelope setup: done. To run `penelope` from anywhere, add this folder to your user PATH:'
Write-Host "    $Bin"
Write-Host "Then run 'penelope'  (or run '$Bin\penelope.cmd' directly)."
