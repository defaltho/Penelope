# scripts/install-cli.ps1
# Instala o comando 'penelope' no perfil PowerShell do utilizador.
# Seguro de re-correr — substitui a instalação anterior se já existir.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install-cli.ps1
#
# Para desinstalar:
#   powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-cli.ps1

$LauncherPath = Join-Path $PSScriptRoot "penelope-cli.ps1"
$ProfilePath  = $PROFILE.CurrentUserAllHosts

# Criar o ficheiro de perfil se não existir
if (-not (Test-Path $ProfilePath)) {
    New-Item -ItemType File -Path $ProfilePath -Force | Out-Null
    Write-Host "  [criado] $ProfilePath"
}

# Bloco a injectar (delimitado para facilitar remoção)
$Block = @"

# >>> Penelope CLI (instalado por install-cli.ps1) <<<
function penelope {
    & "$LauncherPath" @args
}
# <<< Penelope CLI <<<
"@

$Content = Get-Content $ProfilePath -Raw -ErrorAction SilentlyContinue

# Remover instalação anterior se existir
if ($Content -and $Content.Contains(">>> Penelope CLI")) {
    $Content = $Content -replace "(?s)\r?\n# >>> Penelope CLI.*?# <<< Penelope CLI <<<", ""
    Set-Content $ProfilePath $Content -Encoding utf8
}

# Adicionar bloco actualizado
Add-Content $ProfilePath $Block -Encoding utf8

Write-Host ""
Write-Host "  [ok] Comando 'penelope' instalado no perfil PowerShell"
Write-Host "       $ProfilePath"
Write-Host ""
Write-Host "  Abre um novo terminal e escreve:"
Write-Host "    penelope status"
Write-Host "    penelope tui"
Write-Host "    penelope chat `"olá`""
Write-Host ""
