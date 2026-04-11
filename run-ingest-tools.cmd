@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" jobs\ingest_tool_repos.py
