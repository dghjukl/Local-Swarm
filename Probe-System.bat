@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\probe" mkdir "runtime\probe"
echo Probing this PC (takes about 30-60 seconds)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\probe.ps1" > "runtime\probe\system_probe.txt" 2>&1
echo.
echo Done. Results saved to runtime\probe\system_probe.txt
echo You can close this window and tell Claude it finished.
pause
