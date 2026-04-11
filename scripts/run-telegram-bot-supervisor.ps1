param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$RestartDelaySeconds = 10
)

$ErrorActionPreference = "Stop"

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$botScript = Join-Path $ProjectRoot "bot\telegram_bot.py"
$pidFile = Join-Path $ProjectRoot "runtime\telegram_bot.pid"
$supervisorPidFile = Join-Path $ProjectRoot "runtime\telegram_bot_supervisor.pid"
$logFile = Join-Path $ProjectRoot "runtime\logs\telegram_bot_supervisor.log"

New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

function Write-SupervisorLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -LiteralPath $logFile -Value "[$timestamp] $Message"
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
        $process = Get-Process -Id ([int]$pidValue) -ErrorAction Stop
        if ($process) {
            return $true
        }
    } catch {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    return $false
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
        $process = Get-Process -Id ([int]$pidValue) -ErrorAction Stop
        if ($process -and [int]$pidValue -ne $PID) {
            return $true
        }
    } catch {
        Remove-Item -LiteralPath $supervisorPidFile -Force -ErrorAction SilentlyContinue
    }
    return $false
}

Set-Location $ProjectRoot

if (Test-SupervisorRunning) {
    Write-SupervisorLog "Another supervisor is already running; exiting."
    exit 0
}

Set-Content -LiteralPath $supervisorPidFile -Value $PID -Encoding ASCII

if (Test-BotRunning) {
    Write-SupervisorLog "Bot already running; supervisor will exit."
    Remove-Item -LiteralPath $supervisorPidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

Write-SupervisorLog "Supervisor started."

while ($true) {
    Write-SupervisorLog "Launching telegram bot."
    & $python $botScript 2>&1 | Tee-Object -FilePath $logFile -Append
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        Write-SupervisorLog "Bot exited normally; supervisor stopping."
        break
    }
    Write-SupervisorLog "Bot crashed with exit code $exitCode. Restarting in $RestartDelaySeconds seconds."
    Start-Sleep -Seconds $RestartDelaySeconds
}

Remove-Item -LiteralPath $supervisorPidFile -Force -ErrorAction SilentlyContinue
