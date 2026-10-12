@echo off
setlocal
set "APP=%~dp0"
for %%I in ("%APP%..\..") do set "ROOT=%%~fI"
for %%I in ("%ROOT%\..") do set "GITHUB=%%~fI"
set "TAG=%~1"
if "%TAG%"=="" set "TAG=forecast-base-0"
shift
set "PINNED=%GITHUB%\Local Swarm_pinned\%TAG%"
if not exist "%PINNED%\.git" (
  git -C "%ROOT%" worktree add --detach "%PINNED%" "%TAG%"
  if errorlevel 1 exit /b 1
)
set "PYTHONPATH=%PINNED%;%APP%;%PYTHONPATH%"
cd /d "%APP%"
python -m swarm_forecast %*
exit /b %ERRORLEVEL%
