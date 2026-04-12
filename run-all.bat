@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo HAX-Mind visible one-click startup
echo Project: %cd%
echo ========================================

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python virtual environment not found at .venv\Scripts\python.exe
  echo Run setup first:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

if not exist ".env" if not exist ".env.txt" (
  echo [WARN] No .env or .env.txt file found.
  echo Telegram bot will not start until TELEGRAM_BOT_TOKEN is configured.
  echo Copy .env.example to .env and add your secret values first.
  echo.
)

echo [1/4] Stopping any existing background bot/supervisor...
powershell -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "$root=(Get-Location).Path;" ^
  "$pidFile=Join-Path $root 'runtime\telegram_bot.pid';" ^
  "$supervisorPidFile=Join-Path $root 'runtime\telegram_bot_supervisor.pid';" ^
  "$botProcs=Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(\.exe)?$' -and $_.CommandLine -match 'telegram_bot\.py' };" ^
  "$supProcs=Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^powershell(\.exe)?$' -and $_.CommandLine -match 'run-telegram-bot-supervisor\.ps1' };" ^
  "foreach($proc in @($botProcs + $supProcs)){" ^
  "  if($proc -and $proc.ProcessId){" ^
  "    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue;" ^
  "  }" ^
  "};" ^
  "foreach($file in @($pidFile,$supervisorPidFile)){" ^
  "  if(Test-Path $file){" ^
  "    $pid=(Get-Content -LiteralPath $file | Select-Object -First 1).Trim();" ^
  "    if($pid){" ^
  "      Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue;" ^
  "    }" ^
  "    Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue;" ^
  "  }" ^
  "}"
if errorlevel 1 (
  echo [WARN] Could not fully clean up old PID files or processes.
)

echo.
echo [2/4] Running local health check...
call "%~dp0run-health.cmd"
if errorlevel 1 (
  echo [WARN] Local health check reported an issue.
)

echo.
echo [3/4] Generating production status snapshot...
call "%~dp0run-production-status.cmd"
if errorlevel 1 (
  echo [WARN] Production status snapshot reported an issue.
)

if exist "runtime\dashboard\index.html" (
  echo.
  echo Opening local dashboard...
  start "" "%cd%\runtime\dashboard\index.html"
)

echo.
echo [4/4] Launching Telegram bot in this visible window...
echo Keep this terminal open while HAX-Mind is running.
echo Press Ctrl+C in this window to stop the visible bot.
echo.
".venv\Scripts\python.exe" bot\telegram_bot.py
set "BOT_EXIT=%ERRORLEVEL%"

echo.
echo Visible bot stopped with exit code %BOT_EXIT%.
if not "%BOT_EXIT%"=="0" (
  echo [ERROR] HAX-Mind bot exited with a non-zero code.
  exit /b 1
)

echo.
echo HAX-Mind visible session finished.
echo - Main one-click launcher: run-all.bat
echo - Background/supervised    : run-recover.cmd
echo - Foreground bot only      : run-bot.cmd
echo - Health only             : run-health.cmd
exit /b 0
