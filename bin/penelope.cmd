@echo off
REM penelope.cmd — atalho Windows: corre o launcher PowerShell.
REM Coloca esta pasta (bin) no PATH para escreveres só `penelope` em qualquer lado.
where pwsh >nul 2>nul
if %ERRORLEVEL%==0 (
	pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0penelope.ps1" %*
) else (
	powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0penelope.ps1" %*
)
