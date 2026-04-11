param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$EnableWorkerPump
)

$ErrorActionPreference = "Stop"

function Install-StartupLauncher {
    $startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    $launcherPath = Join-Path $startupDir "HAX-Mind-Telegram-Bot.cmd"
    $launcherContent = @"
@echo off
cd /d "$ProjectRoot"
start "" /min powershell.exe -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\run-telegram-bot-supervisor.ps1"
"@
    Set-Content -LiteralPath $launcherPath -Value $launcherContent -Encoding ASCII
    Write-Host "Installed Startup launcher fallback: $launcherPath" -ForegroundColor Yellow
}

$botAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\run-telegram-bot-supervisor.ps1`""
$botLogonTrigger = New-ScheduledTaskTrigger -AtLogOn
$botSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
try {
    Register-ScheduledTask -TaskName "HAX-Mind-Telegram-Bot" -Action $botAction -Trigger $botLogonTrigger -Settings $botSettings -Description "HAX-Mind Telegram bot supervisor" -Force | Out-Null
} catch {
    Install-StartupLauncher
}

$ingestAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\run-ingest-tools.ps1`""
$ingestTrigger = New-ScheduledTaskTrigger -Daily -At 1:30AM
Register-ScheduledTask -TaskName "HAX-Mind-Tool-Ingest" -Action $ingestAction -Trigger $ingestTrigger -Description "HAX-Mind tool memory ingestion" -Force | Out-Null

$nightlyAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\run-nightly.ps1`""
$nightlyTrigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
Register-ScheduledTask -TaskName "HAX-Mind-Nightly" -Action $nightlyAction -Trigger $nightlyTrigger -Description "HAX-Mind nightly improvement job" -Force | Out-Null

$morningAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\run-morning.ps1`""
$morningTrigger = New-ScheduledTaskTrigger -Daily -At 7:00AM
Register-ScheduledTask -TaskName "HAX-Mind-Morning" -Action $morningAction -Trigger $morningTrigger -Description "HAX-Mind morning report job" -Force | Out-Null

$statusAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\get-production-status.ps1`""
$statusTrigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
Register-ScheduledTask -TaskName "HAX-Mind-Production-Status" -Action $statusAction -Trigger $statusTrigger -Description "HAX-Mind production status snapshot" -Force | Out-Null

$alertsAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\get-alerts.ps1`""
$alertsTrigger = New-ScheduledTaskTrigger -Daily -At 8:05AM
Register-ScheduledTask -TaskName "HAX-Mind-Alerts" -Action $alertsAction -Trigger $alertsTrigger -Description "HAX-Mind alert evaluation" -Force | Out-Null

if ($EnableWorkerPump) {
    $workerAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ProjectRoot\run-picoclaw-worker.ps1`""
    $workerTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date
    $workerTrigger.RepetitionInterval = "PT15M"
    $workerTrigger.RepetitionDuration = "P1D"
    Register-ScheduledTask -TaskName "HAX-Mind-PicoClaw-Worker" -Action $workerAction -Trigger $workerTrigger -Description "HAX-Mind PicoClaw worker heartbeat/job pump" -Force | Out-Null
}

Write-Host "Registered HAX-Mind scheduled tasks for $ProjectRoot" -ForegroundColor Green
