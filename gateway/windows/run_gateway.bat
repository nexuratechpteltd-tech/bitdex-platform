@echo off
title BITDEX Exness MT5 Gateway Daemon (Production Phase 4.3)
echo ======================================================================
echo Starting BITDEX Exness MT5 Gateway Daemon (Phase 4.3)...
echo Dual-Environment Support: DEMO Mode + REAL Read-Only Monitoring
echo ======================================================================

if "%EXNESS_GATEWAY_AUTH_TOKEN%"=="" (
    echo [ERROR] EXNESS_GATEWAY_AUTH_TOKEN environment variable is not set!
    echo Please set EXNESS_GATEWAY_AUTH_TOKEN to a strong secret of at least 32 characters.
    echo Example: set EXNESS_GATEWAY_AUTH_TOKEN=your_64_character_hex_secret_here
    pause
    exit /b 1
)

if "%EXNESS_GATEWAY_PORT%"=="" (
    set EXNESS_GATEWAY_PORT=8095
)

if "%EXNESS_GATEWAY_HOST%"=="" (
    set EXNESS_GATEWAY_HOST=0.0.0.0
)

python mt5_gateway_server.py
pause
