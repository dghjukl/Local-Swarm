@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m swarm.training_pool build --n 3000 --seed 20261003
) else (
  uv run python -m swarm.training_pool build --n 3000 --seed 20261003
)
if errorlevel 1 pause
