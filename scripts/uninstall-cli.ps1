# scripts/uninstall-cli.ps1 — remove o comando 'penelope' do perfil PowerShell

$ProfilePath = $PROFILE.CurrentUserAllHosts

if (-not (Test-Path $ProfilePath)) {
    Write-Host "  [skip] Perfil não existe: $ProfilePath"
    exit 0
}

$Content = Get-Content $ProfilePath -Raw
if (-not $Content.Contains(">>> Penelope CLI")) {
    Write-Host "  [skip] Penelope CLI não estava instalado"
    exit 0
}

$Content = $Content -replace "(?s)\r?\n# >>> Penelope CLI.*?# <<< Penelope CLI <<<", ""
Set-Content $ProfilePath $Content -Encoding utf8

Write-Host "  [ok] Comando 'penelope' removido do perfil PowerShell"
