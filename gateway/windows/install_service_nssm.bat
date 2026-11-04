@echo off
title BITDEX Exness MT5 Gateway - NSSM Service Installer
echo ======================================================================
echo BITDEX Exness MT5 Gateway Windows Service Setup
echo Installs bitdex-mt5-gateway as an automatic Windows Service via NSSM
echo ======================================================================

:: Check Administrator Privileges
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
set LOG_DIR=%APP_DIR%\logs

if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
)

where nssm >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARNING] NSSM (Non-Sucking Service Manager) not found in system PATH.
    echo Looking for nssm.exe in current directory...
    if not exist "%APP_DIR%\nssm.exe" (
        echo [ERROR] nssm.exe not found!
        echo Please download NSSM from https://nssm.cc/download and place nssm.exe in %APP_DIR%
        pause
        exit /b 1
    )
    set NSSM_CMD="%APP_DIR%\nssm.exe"
) else (
    set NSSM_CMD=nssm
)

echo.
echo Installing %SERVICE_NAME%...
%NSSM_CMD% install %SERVICE_NAME% "python.exe" "%APP_DIR%\mt5_gateway_server.py"
%NSSM_CMD% set %SERVICE_NAME% AppDirectory "%APP_DIR%"
%NSSM_CMD% set %SERVICE_NAME% Description "BITDEX Exness MT5 Gateway Service (Fail-Closed DEMO API)"
%NSSM_CMD% set %SERVICE_NAME% Start SERVICE_AUTO_START
%NSSM_CMD% set %SERVICE_NAME% AppStdout "%LOG_DIR%\gateway_stdout.log"
%NSSM_CMD% set %SERVICE_NAME% AppStderr "%LOG_DIR%\gateway_stderr.log"
%NSSM_CMD% set %SERVICE_NAME% AppRotateFiles 1
%NSSM_CMD% set %SERVICE_NAME% AppRotateOnline 1
%NSSM_CMD% set %SERVICE_NAME% AppRotateSeconds 86400
%NSSM_CMD% set %SERVICE_NAME% AppRotateBytes 10485760

echo.
echo Service %SERVICE_NAME% installed successfully!
echo To start the service, run: net start %SERVICE_NAME%
echo Or: %NSSM_CMD% start %SERVICE_NAME%
echo.
pause
