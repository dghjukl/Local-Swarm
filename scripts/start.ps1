$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
. (Join-Path $PSScriptRoot 'env.ps1')
$Uv = Join-Path $Repo 'tools\uv\uv.exe'
$Py = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path $Uv) -or -not (Test-Path $Py)) {
  Write-Host 'Local Swarm is not set up yet. Run Setup.bat first.' -ForegroundColor Yellow
  exit 1
}
Write-Host 'Checking packages...'
& $Uv sync --quiet
if ($LASTEXITCODE -ne 0) { Write-Host 'Package install failed.' -ForegroundColor Red; exit 1 }
& $Py -m swarm @args
exit $LASTEXITCODE
