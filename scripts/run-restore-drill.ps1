param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
& "$ProjectRoot\.venv\Scripts\python.exe" -c "from engine.production_ops import run_restore_drill; result=run_restore_drill(); print(result['destination']); print(result['success'])"
