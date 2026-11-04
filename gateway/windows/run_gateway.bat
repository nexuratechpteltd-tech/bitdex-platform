@echo off
title BITDEX Exness MT5 Gateway Daemon
echo ======================================================================
echo Starting BITDEX Exness MT5 Gateway Daemon...
echo Enforcing DEMO mode only. Real accounts will be rejected.
echo ======================================================================

set EXNESS_GATEWAY_AUTH_TOKEN=bitdex_mt5_gateway_secure_ipc_token_2026
set EXNESS_GATEWAY_PORT=8095
set EXNESS_GATEWAY_HOST=0.0.0.0

python mt5_gateway_server.py
pause
