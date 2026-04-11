param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
& "$ProjectRoot\.venv\Scripts\python.exe" -c "from engine.secret_ops import audit_secret_status; import json; print(json.dumps(audit_secret_status(), indent=2, ensure_ascii=False))"
