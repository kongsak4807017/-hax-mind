@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python "%~dp0scripts\setup_haxmind.py" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 "%~dp0scripts\setup_haxmind.py" %*
  exit /b %ERRORLEVEL%
)

echo [ERROR] Python 3 was not found on PATH.
echo Install Python 3.11+ and run setup-haxmind.cmd again.
exit /b 1
