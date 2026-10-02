$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
. (Join-Path $PSScriptRoot 'env.ps1')

$UvVersion = '0.12.0'
$UvDir = Join-Path $Repo 'tools\uv'
$UvExe = Join-Path $UvDir 'uv.exe'

"== step 1: repo-local uv $UvVersion"
if (-not (Test-Path $UvExe)) {
  New-Item -ItemType Directory -Force $UvDir | Out-Null
  $zip = Join-Path $env:TEMP "uv-$UvVersion.zip"
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip
  Expand-Archive -Force $zip $UvDir
  Remove-Item $zip
}
& $UvExe --version

"== step 2: repo-local Python 3.13"
& $UvExe python install 3.13
if ($LASTEXITCODE -ne 0) { throw "python install failed" }

"== step 3: create .venv and install packages"
& $UvExe sync
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
& (Join-Path $Repo '.venv\Scripts\python.exe') -c "import sys; print('python', sys.version); print('exe', sys.executable)"

"== step 4: self test (GPU model server)"
& (Join-Path $Repo '.venv\Scripts\python.exe') -m swarm.selftest
if ($LASTEXITCODE -ne 0) { throw "self test failed" }
"== all steps OK"
