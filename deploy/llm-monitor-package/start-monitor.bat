@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-monitor.ps1" %*
exit /b %ERRORLEVEL%
