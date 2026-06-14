@echo off
REM setup.cmd — Windows one-time bootstrap: runs the PowerShell setup script.
REM Installs missing prerequisites (Ollama, uv, Node), pulls the models, and
REM configures backend\.env. Run it once from the project folder.
where pwsh >nul 2>nul
if %ERRORLEVEL%==0 (
	pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
) else (
	powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
)
