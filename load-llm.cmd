@echo off
setlocal

if "%~1"=="" (
    echo Usage: load-llm.cmd default ^| companion
    echo.
    echo   default   : Qwen3.5-9B
    echo   companion : MemoryPal emotional companion
    exit /b 2
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\lmstudio\load-memorypal-model.ps1" -Persona "%~1"
exit /b %ERRORLEVEL%
