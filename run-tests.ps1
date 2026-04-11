Set-ExecutionPolicy -Scope Process Bypass
Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m pytest tests
