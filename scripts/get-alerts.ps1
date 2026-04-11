param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
& "$ProjectRoot\.venv\Scripts\python.exe" -c "from engine.alerting import evaluate_alerts, render_alert_summary; print(render_alert_summary(evaluate_alerts()))"
