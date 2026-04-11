param(
    [string[]]$TaskNames = @("HAX-Mind-Telegram-Bot", "HAX-Mind-Tool-Ingest", "HAX-Mind-Nightly", "HAX-Mind-Morning", "HAX-Mind-Production-Status", "HAX-Mind-Alerts")
)

$ErrorActionPreference = "Stop"
$startupLauncher = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\HAX-Mind-Telegram-Bot.cmd"

$rows = foreach ($taskName in $TaskNames) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) {
        [pscustomobject]@{
            TaskName     = $taskName
            Registered   = $false
            State        = "missing"
            LastRunTime  = $null
            NextRunTime  = $null
            StartupFallback = $(if ($taskName -eq "HAX-Mind-Telegram-Bot" -and (Test-Path $startupLauncher)) { "present" } else { "" })
        }
        continue
    }

    $info = Get-ScheduledTaskInfo -TaskName $taskName
    [pscustomobject]@{
        TaskName     = $taskName
        Registered   = $true
        State        = $task.State
        LastRunTime  = $info.LastRunTime
        NextRunTime  = $info.NextRunTime
        StartupFallback = ""
    }
}

$rows | Format-Table -AutoSize
