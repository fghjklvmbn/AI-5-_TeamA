@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-sidecar.ps1"
exit /b %errorlevel%
