@echo off
title BITDEX Exness MT5 Gateway Daemon (Hardened Phase 2.3.1)
echo ======================================================================
echo Starting BITDEX Exness MT5 Gateway Daemon...
echo Enforcing DEMO mode only. Real accounts will be rejected.
echo ======================================================================

if "%EXNESS_GATEWAY_AUTH_TOKEN%"=="" (
    echo [ERROR] EXNESS_GATEWAY_AUTH_TOKEN environment variable is not set!
    echo Please set EXNESS_GATEWAY_AUTH_TOKEN to a strong secret of at least 32 characters.
    echo Example: set EXNESS_GATEWAY_AUTH_TOKEN=your_32_character_secret_here
    pause
    exit /b 1
)

if "%EXNESS_GATEWAY_PORT%"=="" (
    set EXNESS_GATEWAY_PORT=8095
)

if "%EXNESS_GATEWAY_HOST%"=="" (
    set EXNESS_GATEWAY_HOST=127.0.0.1
)

python mt5_gateway_server.py
pause
