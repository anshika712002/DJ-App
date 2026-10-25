$ErrorActionPreference = "Stop"

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$PYTHON = Join-Path $REPO_ROOT ".venv\Scripts\python.exe"
$STARTER = Join-Path $PSScriptRoot "start_backend.py"

if (-not (Test-Path -LiteralPath $PYTHON -PathType Leaf)) {
    throw "The project virtual environment was not found at '$PYTHON'."
}

& $PYTHON $STARTER --postgres-only
if ($LASTEXITCODE -ne 0) {
    throw "The existing PostgreSQL cluster failed to start."
}
