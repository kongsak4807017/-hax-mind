param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
& "$ProjectRoot\.venv\Scripts\python.exe" -c "from engine.production_ops import create_backup_bundle; path=create_backup_bundle(); print(path)"
