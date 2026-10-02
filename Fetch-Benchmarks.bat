@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - fetch benchmarks
echo.
echo  Downloads the established benchmark questions into runtime\benchmarks (never committed):
echo    - FRAMES: 100 random questions (public)
echo    - GAIA: text-only questions, levels 1-2 (gated: accept the terms on
echo      huggingface.co/datasets/gaia-benchmark/GAIA and put a free read token in
echo      runtime\secrets.json as "HF_TOKEN")
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.benchmarks fetch all"
echo.
pause
