param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$WaitSeconds = 5
)

$ErrorActionPreference = "Stop"

$pidFile = Join-Path $ProjectRoot "runtime\telegram_bot.pid"
$supervisorPidFile = Join-Path $ProjectRoot "runtime\telegram_bot_supervisor.pid"
$supervisorScript = Join-Path $ProjectRoot "scripts\run-telegram-bot-supervisor.ps1"
$recoveryLog = Join-Path $ProjectRoot "runtime\logs\telegram_bot_recovery.log"

New-Item -ItemType Directory -Force -Path (Split-Path $recoveryLog) | Out-Null

function Write-RecoveryLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -LiteralPath $recoveryLog -Value "[$timestamp] $Message"
}

function Test-BotRunning {
    if (-not (Test-Path $pidFile)) {
        return $false
    }

    $pidValue = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if (-not $pidValue) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        return $false
    }

    try {
        $null = Get-Process -Id ([int]$pidValue) -ErrorAction Stop
        return $true
    } catch {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        return $false
    }
}

function Test-SupervisorRunning {
    if (-not (Test-Path $supervisorPidFile)) {
        return $false
    }

    $pidValue = (Get-Content -LiteralPath $supervisorPidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if (-not $pidValue) {
        Remove-Item -LiteralPath $supervisorPidFile -Force -ErrorAction SilentlyContinue
        return $false
    }

    try {
        $null = Get-Process -Id ([int]$pidValue) -ErrorAction Stop
        return $true
    } catch {
        Remove-Item -LiteralPath $supervisorPidFile -Force -ErrorAction SilentlyContinue
        return $false
    }
}

Set-Location $ProjectRoot

if (Test-BotRunning) {
    if (Test-SupervisorRunning) {
        Write-RecoveryLog "Bot already running; no recovery needed."
        Write-Host "Bot already running." -ForegroundColor Green
        exit 0
    }

    $botPid = (Get-Content -LiteralPath $pidFile | Select-Object -First 1).Trim()
    Write-RecoveryLog "Bot is running without supervisor; restarting under supervision."
    Stop-Process -Id ([int]$botPid) -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

if (Test-SupervisorRunning) {
    Write-RecoveryLog "Supervisor already running; waiting for bot to recover."
    Start-Sleep -Seconds $WaitSeconds
    if (Test-BotRunning) {
        $botPid = Get-Content -LiteralPath $pidFile | Select-Object -First 1
        Write-RecoveryLog "Bot recovered under existing supervisor with pid=$botPid."
        Write-Host "Bot recovered under existing supervisor. PID: $botPid" -ForegroundColor Green
        exit 0
    }
}

Write-RecoveryLog "Bot not running; starting supervisor."
Start-Process -FilePath powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$supervisorScript`"" -WindowStyle Hidden
Start-Sleep -Seconds $WaitSeconds

if (Test-BotRunning) {
    $botPid = Get-Content -LiteralPath $pidFile | Select-Object -First 1
    Write-RecoveryLog "Recovery successful; bot running with pid=$botPid."
    Write-Host "Recovery successful. Bot PID: $botPid" -ForegroundColor Green
    exit 0
}

Write-RecoveryLog "Recovery failed; bot still not running after supervisor launch."
Write-Error "Recovery failed. Bot is still not running."
exit 1
