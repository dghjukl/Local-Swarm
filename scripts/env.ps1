# Keep every tool inside the repo; never use system Python or caches.
$Repo = Split-Path -Parent $PSScriptRoot
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Repo 'runtime\python'
$env:UV_CACHE_DIR = Join-Path $Repo 'runtime\uv-cache'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $Repo '.venv'
$env:UV_TOOL_DIR = Join-Path $Repo 'runtime\uv-tools'
$env:UV_PYTHON_BIN_DIR = Join-Path $Repo 'runtime\python-bin'
$env:PYTHONNOUSERSITE = '1'
$env:PIP_REQUIRE_VIRTUALENV = '1'
