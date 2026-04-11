param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$RestartWaitSeconds = 12,
    [switch]$ForceRecoverySimulation
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$startupLauncher = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\HAX-Mind-Telegram-Bot.cmd"
$pidFile = Join-Path $ProjectRoot "runtime\telegram_bot.pid"
$supervisorPidFile = Join-Path $ProjectRoot "runtime\telegram_bot_supervisor.pid"

function New-StepResult {
    param([string]$Name, [bool]$Success, [string]$Detail)
    return [ordered]@{ name = $Name; success = $Success; detail = $Detail }
}

function Test-BotRunning {
    if (-not (Test-Path $pidFile)) { return $false }
    $pidValue = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if (-not $pidValue) { return $false }
    try {
        $null = Get-Process -Id ([int]$pidValue) -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Stop-IfExists {
    param([string]$PathToPid)
    if (-not (Test-Path $PathToPid)) { return }
    $pidValue = (Get-Content -LiteralPath $PathToPid -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($pidValue) {
        Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PathToPid -Force -ErrorAction SilentlyContinue
}

$steps = New-Object System.Collections.Generic.List[object]

# Step 1: startup launcher / recovery validation
$oldPid = if (Test-Path $pidFile) { (Get-Content -LiteralPath $pidFile | Select-Object -First 1).Trim() } else { "" }
if ($ForceRecoverySimulation) {
    Stop-IfExists -PathToPid $pidFile
    Stop-IfExists -PathToPid $supervisorPidFile
    Start-Sleep -Seconds 2
    cmd /c "`"$startupLauncher`"" | Out-Null
    Start-Sleep -Seconds $RestartWaitSeconds
    $newPid = if (Test-Path $pidFile) { (Get-Content -LiteralPath $pidFile | Select-Object -First 1).Trim() } else { "" }
    $botRecovered = (Test-BotRunning) -and $newPid -and ($newPid -ne $oldPid)
    $steps.Add((New-StepResult -Name "startup_launcher_recovery" -Success $botRecovered -Detail "simulated old_pid=$oldPid new_pid=$newPid"))
} else {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\ensure-telegram-bot.ps1") | Out-Null
    Start-Sleep -Seconds 2
    $newPid = if (Test-Path $pidFile) { (Get-Content -LiteralPath $pidFile | Select-Object -First 1).Trim() } else { "" }
    $botHealthy = Test-BotRunning
    $steps.Add((New-StepResult -Name "startup_launcher_recovery" -Success $botHealthy -Detail "validated current supervised state old_pid=$oldPid new_pid=$newPid"))
}

# Step 2: tool ingest
$ingestOutput = cmd /c run-ingest-tools.cmd 2>&1 | Out-String
$ingestOk = $LASTEXITCODE -eq 0
$steps.Add((New-StepResult -Name "tool_ingest_job" -Success $ingestOk -Detail ($ingestOutput.Trim() -replace '\s+', ' ')))

# Step 3: nightly
$nightlyOutput = cmd /c run-nightly.cmd 2>&1 | Out-String
$nightlyOk = $LASTEXITCODE -eq 0
$steps.Add((New-StepResult -Name "nightly_job" -Success $nightlyOk -Detail ($nightlyOutput.Trim() -replace '\s+', ' ')))

# Cleanup duplicate low-value pending proposals created by nightly validation
$env:PYTHONIOENCODING = "utf-8"
$archiveOutput = & $python -c "import json; from pathlib import Path; from engine.proposal_engine import archive_duplicate_pending_proposals, update_proposal_status; result=archive_duplicate_pending_proposals(); [update_proposal_status(p['id'], 'archived_duplicate') for p in [json.loads(x.read_text(encoding='utf-8')) for x in Path('runtime/proposals').glob('*.json')] if p.get('status')=='pending' and p.get('title')=='Promote external tool repos into canonical memory']; print(result['archived_count'])" 2>&1
$archiveOk = $LASTEXITCODE -eq 0
$steps.Add((New-StepResult -Name "proposal_queue_cleanup" -Success $archiveOk -Detail ('archived_duplicates=' + (($archiveOutput | Out-String).Trim()))))

# Step 4: morning
$morningOutput = cmd /c run-morning.cmd 2>&1 | Out-String
$morningOk = $LASTEXITCODE -eq 0
$steps.Add((New-StepResult -Name "morning_job" -Success $morningOk -Detail ($morningOutput.Split([Environment]::NewLine)[0] -replace '\s+', ' ')))

$stepsJson = $steps | ConvertTo-Json -Depth 6 -Compress
$env:VALIDATION_STEPS = $stepsJson
$env:PYTHONIOENCODING = "utf-8"
& $python -c "import json, os; from engine.local_validation import build_validation_payload, save_local_daily_driver_validation; steps=json.loads(os.environ['VALIDATION_STEPS']); payload=build_validation_payload(steps); paths=save_local_daily_driver_validation(payload); print(paths['markdown_path']); print(paths['json_path']); print(payload['success'])"
