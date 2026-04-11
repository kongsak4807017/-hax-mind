param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$env:PYTHONIOENCODING = "utf-8"
& "$ProjectRoot\.venv\Scripts\python.exe" -c "from engine.local_health import render_local_health_summary; print(render_local_health_summary())"

Write-Host ""
Write-Host "Recovery:" -ForegroundColor Cyan
Write-Host "- Run .\run-recover.cmd if the bot is not running." -ForegroundColor Yellow
Write-Host ""
Write-Host "Scheduled Tasks:" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\get-scheduled-tasks-status.ps1"
