@powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0notify.ps1" -Job "%~1" -Code %~2 -Summary "%~3"
