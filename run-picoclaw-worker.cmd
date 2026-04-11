@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" jobs\picoclaw_worker.py %*
