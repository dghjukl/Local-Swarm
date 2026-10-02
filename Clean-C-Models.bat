@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - clean model files off C:
echo.
echo  Finds .gguf model files on C: outside this repo, copies any that D: does not already have
echo  to D:\Available\Models\FromC, checks each copy is complete, then deletes it from C:.
echo  It shows everything it found and asks before copying or deleting anything.
echo  Clean-C-Models.bat check   (list only)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\clean_c_models.ps1" %1
echo.
pause
