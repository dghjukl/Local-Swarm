@echo off
setlocal
set "APP=%~dp0"
for %%I in ("%APP%..\..") do set "ROOT=%%~fI"
for %%I in ("%ROOT%\..") do set "GITHUB=%%~fI"
set "TAG=%~1"
if "%TAG%"=="" set "TAG=forecast-base-0"
set "ARGS=%*"
set "ARGS=%ARGS:* =%"
set "PINNED=%GITHUB%\Local Swarm_pinned\%TAG%"
if not exist "%PINNED%\.git" (
  git -C "%ROOT%" worktree add --detach "%PINNED%" "%TAG%"
  if errorlevel 1 exit /b 1
)
if not exist "%PINNED%\Bin" mklink /J "%PINNED%\Bin" "%ROOT%\Bin" >nul
if errorlevel 1 exit /b 1
if not exist "%PINNED%\Models\MiMo-V2.6-Distill-Qwen-9B" mklink /J "%PINNED%\Models\MiMo-V2.6-Distill-Qwen-9B" "%ROOT%\Models\MiMo-V2.6-Distill-Qwen-9B" >nul
if errorlevel 1 exit /b 1
if not exist "%PINNED%\Models\Granite-4.1-3B" mklink /J "%PINNED%\Models\Granite-4.1-3B" "%ROOT%\Models\Granite-4.1-3B" >nul
if errorlevel 1 exit /b 1
if not exist "%PINNED%\Models\Qwen3.5-4B" mklink /J "%PINNED%\Models\Qwen3.5-4B" "%ROOT%\Models\Qwen3.5-4B" >nul
if errorlevel 1 exit /b 1
if not exist "%PINNED%\Models\Gemma-4-E4B-it" mklink /J "%PINNED%\Models\Gemma-4-E4B-it" "%ROOT%\Models\Gemma-4-E4B-it" >nul
if errorlevel 1 exit /b 1
set "PYTHONPATH=%PINNED%;%APP%;%PYTHONPATH%"
cd /d "%APP%"
python -m swarm_forecast %ARGS%
exit /b %ERRORLEVEL%
