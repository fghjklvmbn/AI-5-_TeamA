@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-monitor.ps1" %*
exit /b %ERRORLEVEL%
