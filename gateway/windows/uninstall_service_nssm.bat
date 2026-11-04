@echo off
title BITDEX Exness MT5 Gateway - NSSM Service Uninstaller
echo ======================================================================
echo Uninstalling BITDEX Exness MT5 Gateway Windows Service
echo ======================================================================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Administrator privileges required!
    echo Please right-click this script and select 'Run as administrator'.
    pause
    exit /b 1
)

set SERVICE_NAME=BITDEX_Exness_MT5_Gateway
set APP_DIR=%~dp0
set APP_DIR=%APP_DIR:~0,-1%

where nssm >nul 2>&1
if %errorLevel% neq 0 (
    if not exist "%APP_DIR%\nssm.exe" (
        echo [ERROR] nssm.exe not found!
        pause
        exit /b 1
    )
    set NSSM_CMD="%APP_DIR%\nssm.exe"
) else (
    set NSSM_CMD=nssm
)

echo Stopping %SERVICE_NAME%...
%NSSM_CMD% stop %SERVICE_NAME%

echo Removing %SERVICE_NAME%...
%NSSM_CMD% remove %SERVICE_NAME% confirm

echo.
echo Service %SERVICE_NAME% uninstalled cleanly.
pause
