@echo off
REM penelope.cmd — Windows shortcut: runs the PowerShell launcher.
REM Put this folder (bin) on your PATH to type just `penelope` anywhere.
where pwsh >nul 2>nul
if %ERRORLEVEL%==0 (
	pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0penelope.ps1" %*
) else (
	powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0penelope.ps1" %*
)
