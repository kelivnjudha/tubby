@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
if errorlevel 1 (
    echo.
    echo Tubby setup failed.
    exit /b 1
)

endlocal
