@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\logs" mkdir "runtime\logs"
echo Running Local Swarm tests (uses a fake model server, not the GPU)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m pytest -q 2>&1 | Out-File -Encoding utf8 'runtime\logs\tests.log'"
type runtime\logs\tests.log
echo.
echo Results saved to runtime\logs\tests.log
pause
