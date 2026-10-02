@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - sync models
echo.
echo  Gets the big comparison models ready:
echo    1. downloads the ones you do not have to D:\Available\Models
echo    2. backs up models that are only in this repo to D:\Available\Models\LocalSwarm-backup
echo    3. copies the needed ones from D: into this repos Models folder
echo  It checks free space on C: and D: and shows the plan before doing anything. Nothing is deleted.
echo  Options:  Sync-Models.bat check     (plan only)
echo            Sync-Models.bat download  (downloads only - fine while an evaluation is running)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_models.ps1" %1
echo.
pause
