param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
& "$ProjectRoot\.venv\Scripts\python.exe" -c "from engine.production_ops import generate_production_status, write_production_dashboard; payload=generate_production_status(); dashboard=write_production_dashboard(payload=payload); print('production_status.json'); print(dashboard)"
