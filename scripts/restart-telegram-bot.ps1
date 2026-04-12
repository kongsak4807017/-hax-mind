param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$DelaySeconds = 2
)

$ErrorActionPreference = "Stop"

$pidFile = Join-Path $ProjectRoot "runtime\telegram_bot.pid"
$supervisorPidFile = Join-Path $ProjectRoot "runtime\telegram_bot_supervisor.pid"
$supervisorScript = Join-Path $ProjectRoot "scripts\run-telegram-bot-supervisor.ps1"
$logFile = Join-Path $ProjectRoot "runtime\logs\telegram_bot_recovery.log"

New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

function Write-RestartLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -LiteralPath $logFile -Value "[$timestamp] $Message"
}

function Get-BotProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python(\.exe)?$' -and
            $_.CommandLine -match 'telegram_bot\.py'
        }
}

function Get-SupervisorProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^powershell(\.exe)?$' -and
            $_.CommandLine -match 'run-telegram-bot-supervisor\.ps1'
        }
}

Set-Location $ProjectRoot
Write-RestartLog "Restart requested; waiting $DelaySeconds seconds before recycle."
Start-Sleep -Seconds $DelaySeconds

$supervisors = Get-SupervisorProcesses
foreach ($proc in $supervisors) {
    if ($proc -and $proc.ProcessId) {
        Write-RestartLog "Stopping supervisor process $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$bots = Get-BotProcesses
foreach ($proc in $bots) {
    if ($proc -and $proc.ProcessId) {
        Write-RestartLog "Stopping bot process $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Remove-Item -LiteralPath $pidFile,$supervisorPidFile -Force -ErrorAction SilentlyContinue
Write-RestartLog "Starting fresh supervisor."
Start-Process -FilePath powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$supervisorScript`"" -WindowStyle Hidden
Write-RestartLog "Restart flow completed."
