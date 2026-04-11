Set-ExecutionPolicy -Scope Process Bypass
Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" bot\telegram_bot.py
