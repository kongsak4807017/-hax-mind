Set-ExecutionPolicy -Scope Process Bypass
Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" jobs\ingest_tool_repos.py
