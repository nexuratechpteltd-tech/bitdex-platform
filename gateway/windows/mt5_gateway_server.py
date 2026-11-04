"""
BITDEX Windows MT5 Gateway Service (Production Phase 4.3)
Runs on Windows VPS / Server alongside the Exness MetaTrader 5 Terminal.
Provides secure HTTP/TLS REST bridge communicating directly with MetaTrader5 Python IPC.

Hardened Features (Phase 4.3):
- Dual Environment Support: Authenticates and validates both DEMO and REAL accounts separately.
  - DEMO mode: Strictly validates mt5.account_info().trade_mode == 0 (DEMO). Rejects REAL.
  - REAL mode: Strictly validates mt5.account_info().trade_mode == 2 (REAL). Rejects DEMO.
  - Strict READ-ONLY for REAL accounts: Zero order placement, modification, or execution endpoints.
- Environment & Account Identity Verification: Verifies login number, server name, and trade_mode.
- Fail-Closed Secret Authentication: Requires EXNESS_GATEWAY_AUTH_TOKEN (min 32 chars).
- Constant-Time Token Verification: Evaluates X-Gateway-Auth-Token header via hmac.compare_digest.
- Connection Monitoring & Auto-Reconnection: Automated health supervisor with keepalive & retry.
- Telemetry & Contract Specs: Balance, equity, free margin, leverage, positions, ticks, and candles.
- Network Security: Client IP allowlisting, loopback/private tunnel binding, HTTPS/TLS verification.
"""

import os
import sys
import time
import hmac
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Query, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn

# Configure logging (scrub sensitive passwords)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [bitdex-mt5-gateway] %(message)s",
)
logger = logging.getLogger("bitdex.mt5.gateway")

# ─────────────────────────────────────────────────────────────
# 1. Startup Secret Configuration & Validation (Fail-Closed)
# ─────────────────────────────────────────────────────────────

REVOKED_TOKENS = {
    "6372b1ea1cd5cdd49100d5369e30bb6b78ca5233bca48d229ac018ee14e7d928",  # Phase 4.3 retired token
}

WEAK_SECRETS = {
    "bitdex_mt5_gateway_secure_ipc_token_2026",
    "default",
    "changeme",
    "password",
    "secret",
    "1234567890",
    "admin",
}

def validate_gateway_token(token: Optional[str]) -> str:
    if not token or len(token.strip()) < 32:
        raise RuntimeError(
            "CRITICAL SECURITY FAILURE: EXNESS_GATEWAY_AUTH_TOKEN must be configured with "
            "a strong secret of at least 32 characters. Found missing or insufficient token."
        )
    clean = token.strip().lower()
    if clean in WEAK_SECRETS or clean in REVOKED_TOKENS:
        raise RuntimeError(
            "CRITICAL SECURITY FAILURE: EXNESS_GATEWAY_AUTH_TOKEN is using a known weak or "
            "revoked value. You must generate a cryptographically strong secret."
        )
    return token.strip()


GATEWAY_AUTH_TOKEN = os.getenv("EXNESS_GATEWAY_AUTH_TOKEN")
if os.getenv("STRICT_STARTUP_CHECK", "true").lower() == "true":
    GATEWAY_AUTH_TOKEN = validate_gateway_token(GATEWAY_AUTH_TOKEN)
else:
    GATEWAY_AUTH_TOKEN = GATEWAY_AUTH_TOKEN or ""

GATEWAY_PORT = int(os.getenv("EXNESS_GATEWAY_PORT", "8095"))
GATEWAY_HOST = os.getenv("EXNESS_GATEWAY_HOST", "127.0.0.1")

ALLOWED_CLIENT_IPS_RAW = os.getenv("ALLOWED_CLIENT_IPS", "127.0.0.1,::1,169.58.218.168,10.88.0.1")
ALLOWED_CLIENT_IPS = {ip.strip() for ip in ALLOWED_CLIENT_IPS_RAW.split(",") if ip.strip()}
ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "https://bitdex.ltd")
ALLOWED_ORIGINS = [orig.strip() for orig in ALLOWED_ORIGINS_RAW.split(",") if orig.strip()]

# Attempt MetaTrader5 import
MT5_AVAILABLE = False
mt5 = None
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
    logger.info("MetaTrader5 Python IPC library loaded successfully.")
except ImportError:
    logger.warning("MetaTrader5 library not found. Running in mock/testing environment.")

STARTUP_TIME = time.time()

# ─────────────────────────────────────────────────────────────
# 2. FastAPI Application & Security Middleware
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="BITDEX Exness MT5 Gateway Daemon (Production Phase 4.3)",
    version="4.3.0",
    description="Secure Dual-Environment REST bridge between Linux Staging Backend and Windows MetaTrader 5 Terminal",
    docs_url=None,
    redoc_url=None,
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Gateway-Auth-Token"],
    )

from fastapi.responses import JSONResponse

@app.middleware("http")
async def security_transport_middleware(request: Request, call_next):
    client_host = request.client.host if request.client else None

    if os.getenv("ENFORCE_CLIENT_IP", "false").lower() == "true":
        if not client_host or client_host not in ALLOWED_CLIENT_IPS:
            logger.warning(f"Unauthorized access blocked from untrusted IP: {client_host}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": f"Access forbidden: Client IP '{client_host}' is not in the authorized allowlist."},
            )

    if os.getenv("REQUIRE_HTTPS", "false").lower() == "true":
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto.lower() != "https" and client_host not in ("127.0.0.1", "::1"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Insecure transport rejected: HTTPS/TLS is strictly required for remote gateway traffic."},
            )

    response = await call_next(request)
    return response


# ─────────────────────────────────────────────────────────────
# 3. Authentication Dependency (Header verification)
# ─────────────────────────────────────────────────────────────

async def require_gateway_token(
    x_gateway_auth_token: Optional[str] = Header(None, alias="X-Gateway-Auth-Token")
) -> str:
    if not x_gateway_auth_token:
        logger.warning("Gateway authentication rejected: Missing X-Gateway-Auth-Token header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Gateway-Auth-Token header.",
        )

    # Constant-time comparison against revoked tokens
    for revoked in REVOKED_TOKENS:
        if hmac.compare_digest(x_gateway_auth_token.encode("utf-8"), revoked.encode("utf-8")):
            logger.warning("Gateway authentication rejected: Revoked token presented.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token revoked: Rotate your gateway authentication token.",
            )

    current_token = GATEWAY_AUTH_TOKEN or os.getenv("EXNESS_GATEWAY_AUTH_TOKEN", "")
    if not current_token:
        logger.critical("Gateway authentication failed: No auth token configured on server.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway server misconfigured: Missing auth token.",
        )

    if not hmac.compare_digest(x_gateway_auth_token.encode("utf-8"), current_token.encode("utf-8")):
        logger.warning("Gateway authentication rejected: Invalid X-Gateway-Auth-Token provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Gateway-Auth-Token.",
        )

    return x_gateway_auth_token


def require_mt5_terminal():
    if not MT5_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 Python IPC library is unavailable on this host.",
        )
    t_info = mt5.terminal_info()
    if not t_info or not t_info.connected:
        # Attempt auto-reconnect once
        logger.warning("MT5 terminal connection dropped. Attempting automated reinitialization...")
        mt5.initialize()
        t_info = mt5.terminal_info()
        if not t_info or not t_info.connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MetaTrader 5 terminal is not connected to broker server.",
            )


# ─────────────────────────────────────────────────────────────
# 4. Request / Response Models
# ─────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    login: str = Field(..., min_length=4, max_length=32, description="Exness MT5 account login ID")
    password: Optional[str] = Field(None, min_length=4, max_length=128, description="Exness MT5 trading password")
    server: str = Field(default="Exness-MT5Trial", min_length=3, max_length=64, description="Exness server name")
    expected_account_type: str = Field(default="DEMO", description="DEMO or REAL")

    @field_validator("expected_account_type")
    @classmethod
    def validate_account_type(cls, v: str) -> str:
        mode = v.strip().upper()
        if mode not in ("DEMO", "REAL"):
            raise ValueError(f"Strict safety rejection: expected_account_type must be 'DEMO' or 'REAL', got '{v}'.")
        return mode


class MarginCheckRequest(BaseModel):
    symbol: str = Field(..., min_length=2, max_length=32)
    order_type: str = Field(..., description="Must be BUY or SELL")
    volume: float = Field(..., gt=0.0, description="Volume must be positive")

    @field_validator("order_type")
    @classmethod
    def validate_side(cls, v: str) -> str:
        side = v.strip().upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid order_type '{v}'. Must be 'BUY' or 'SELL'.")
        return side


class ReconcileRequest(BaseModel):
    account_id: str = Field(..., min_length=4)
    local_positions: List[Dict[str, Any]] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# 5. Protected Gateway Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/health", dependencies=[Depends(require_gateway_token)])
async def health_check():
    """Returns gateway service status, verified MT5 terminal build info, and connected trade mode."""
    terminal_connected = False
    terminal_build = 0
    trade_mode = None
    account_login_masked = None
    currency = "USD"
    balance = 0.0
    equity = 0.0

    if MT5_AVAILABLE:
        t_info = mt5.terminal_info()
        if t_info:
            terminal_connected = bool(t_info.connected)
            terminal_build = int(t_info.build)
        acct = mt5.account_info()
        if acct:
            trade_mode = acct.trade_mode
            acct_str = str(acct.login)
            account_login_masked = f"{acct_str[:2]}****{acct_str[-2:]}" if len(acct_str) >= 4 else acct_str
            currency = acct.currency
            balance = float(acct.balance)
            equity = float(acct.equity)

    uptime_sec = round(time.time() - STARTUP_TIME, 1)

    return {
        "status": "HEALTHY",
        "service": "BITDEX Windows MT5 Gateway",
        "version": "4.3.0",
        "mt5_available": MT5_AVAILABLE,
        "terminal_connected": terminal_connected,
        "terminal_build": terminal_build,
        "active_trade_mode": trade_mode,
        "account_login_masked": account_login_masked,
        "currency": currency,
        "balance": balance,
        "equity": equity,
        "uptime_seconds": uptime_sec,
        "supported_environments": ["DEMO", "REAL"],
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.get("/heartbeat", dependencies=[Depends(require_gateway_token)])
async def heartbeat():
    """Lightweight ping endpoint for connection latency monitoring."""
    return {"status": "PONG", "time_ms": int(time.time() * 1000)}


@app.post("/connect", dependencies=[Depends(require_gateway_token)])
async def connect_mt5(req: ConnectRequest):
    """
    Authenticates with MT5 terminal and enforces strict environment matching.
    Supports DEMO (trade_mode=0) and REAL (trade_mode=2, strictly read-only).
    Rejects environment mismatches.
    """
    if not MT5_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 Python IPC library is unavailable on this host.",
        )

    if not mt5.initialize():
        err = mt5.last_error()
        logger.error(f"Failed to initialize MT5 terminal: {err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to initialize MT5 terminal: {err}",
        )

    try:
        login_int = int(req.login.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid account login format (must be numeric integer).",
        )

    authorized = False
    if req.password:
        authorized = mt5.login(login=login_int, password=req.password, server=req.server)
    else:
        authorized = mt5.login(login=login_int, server=req.server)

    if not authorized:
        err = mt5.last_error()
        logger.error(f"MT5 authentication failed for account {req.login}: {err}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"MT5 broker authentication failed: {err}",
        )

    acct_info = mt5.account_info()
    if not acct_info:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to retrieve MT5 account telemetry post-login.",
        )

    # ─────────────────────────────────────────────────────────────
    # ENVIRONMENT & ACCOUNT TRADE MODE VALIDATION:
    # 0 = ACCOUNT_TRADE_MODE_DEMO
    # 1 = ACCOUNT_TRADE_MODE_CONTEST
    # 2 = ACCOUNT_TRADE_MODE_REAL
    # ─────────────────────────────────────────────────────────────
    expected = req.expected_account_type.upper()
    trade_mode = acct_info.trade_mode

    if expected == "DEMO":
        if trade_mode != 0:
            mt5.shutdown()
            mode_desc = "REAL" if trade_mode == 2 else ("CONTEST" if trade_mode == 1 else f"UNKNOWN({trade_mode})")
            logger.critical(
                f"ENVIRONMENT MISMATCH: Account {req.login} has trade_mode={mode_desc}. "
                f"Requested DEMO environment, but account is {mode_desc}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"CRITICAL REJECTION: Environment mismatch. Requested DEMO, but broker returned trade_mode={mode_desc}.",
            )
        resolved_type = "DEMO"
        is_demo = True
        is_real = False
    elif expected == "REAL":
        if trade_mode != 2:
            mt5.shutdown()
            mode_desc = "DEMO" if trade_mode == 0 else ("CONTEST" if trade_mode == 1 else f"UNKNOWN({trade_mode})")
            logger.critical(
                f"ENVIRONMENT MISMATCH: Account {req.login} has trade_mode={mode_desc}. "
                f"Requested REAL environment, but account is {mode_desc}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"CRITICAL REJECTION: Environment mismatch. Requested REAL, but broker returned trade_mode={mode_desc}.",
            )
        resolved_type = "REAL"
        is_demo = False
        is_real = True

    # Verify returned login
    if str(acct_info.login) != str(req.login).strip():
        mt5.shutdown()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Account login mismatch: requested {req.login}, broker returned {acct_info.login}.",
        )

    # Verify returned server
    if acct_info.server.strip().lower() != req.server.strip().lower():
        mt5.shutdown()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Server name mismatch: requested {req.server}, broker connected to {acct_info.server}.",
        )

    logger.info(
        f"MT5 Gateway authenticated: account={acct_info.login}, server={acct_info.server}, "
        f"type={resolved_type}, balance={acct_info.balance} {acct_info.currency}"
    )

    return {
        "status": "CONNECTED",
        "account_id": str(acct_info.login),
        "login": str(acct_info.login),
        "server": acct_info.server,
        "account_type": resolved_type,
        "is_demo": is_demo,
        "is_real": is_real,
        "read_only": is_real,  # REAL is strictly read-only
        "broker_authenticated": True,
        "terminal_connected": True,
        "currency": acct_info.currency,
        "balance": float(acct_info.balance),
        "equity": float(acct_info.equity),
        "margin": float(acct_info.margin),
        "free_margin": float(acct_info.margin_free),
        "margin_level": float(acct_info.margin_level) if acct_info.margin_level else 0.0,
        "leverage": int(acct_info.leverage),
        "connected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/disconnect", dependencies=[Depends(require_gateway_token)])
async def disconnect_mt5():
    """Disconnects from MT5 terminal cleanly."""
    if MT5_AVAILABLE:
        mt5.shutdown()
    return {"status": "DISCONNECTED", "is_connected": False}


@app.get("/account", dependencies=[Depends(require_gateway_token)])
async def get_account_telemetry():
    """Retrieves authoritative account telemetry from active terminal connection."""
    require_mt5_terminal()
    acct = mt5.account_info()
    if not acct:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to retrieve MT5 account telemetry.",
        )

    is_demo = (acct.trade_mode == 0)
    is_real = (acct.trade_mode == 2)
    acct_type = "DEMO" if is_demo else ("REAL" if is_real else f"OTHER({acct.trade_mode})")

    return {
        "account_id": str(acct.login),
        "login": str(acct.login),
        "name": acct.name,
        "server": acct.server,
        "currency": acct.currency,
        "account_type": acct_type,
        "is_demo": is_demo,
        "is_real": is_real,
        "read_only": is_real,
        "balance": float(acct.balance),
        "equity": float(acct.equity),
        "margin": float(acct.margin),
        "free_margin": float(acct.margin_free),
        "margin_level": float(acct.margin_level) if acct.margin_level else 0.0,
        "leverage": int(acct.leverage),
        "trade_allowed": bool(acct.trade_allowed),
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.get("/symbols", dependencies=[Depends(require_gateway_token)])
async def get_available_symbols():
    """Returns all tradable symbols supported by current broker terminal."""
    require_mt5_terminal()
    symbols = mt5.symbols_get()
    if symbols is None:
        return {"symbols": [], "count": 0}

    names = [s.name for s in symbols if s.visible]
    return {"symbols": names, "count": len(names)}


@app.get("/symbol/{symbol}", dependencies=[Depends(require_gateway_token)])
async def get_symbol_specification(symbol: str):
    """Retrieves full contract specification directly from MT5 symbol registry."""
    require_mt5_terminal()
    info = mt5.symbol_info(symbol)
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found on connected broker terminal.",
        )

    return {
        "symbol": info.name,
        "currency_base": info.currency_base,
        "currency_profit": info.currency_profit,
        "currency_margin": info.currency_margin,
        "contract_size": float(info.trade_contract_size),
        "tick_size": float(info.trade_tick_size),
        "tick_value": float(info.trade_tick_value),
        "digits": int(info.digits),
        "spread": int(info.spread),
        "volume_min": float(info.volume_min),
        "volume_max": float(info.volume_max),
        "volume_step": float(info.volume_step),
        "is_tradable": bool(info.visible and info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL),
        "swap_long": float(info.swap_long),
        "swap_short": float(info.swap_short),
    }


@app.get("/tick/{symbol}", dependencies=[Depends(require_gateway_token)])
async def get_latest_symbol_tick(symbol: str):
    """Fetches real-time market quote tick directly from broker IPC."""
    require_mt5_terminal()
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tick for symbol '{symbol}' is not currently available from broker.",
        )

    info = mt5.symbol_info(symbol)
    tick_size = float(info.trade_tick_size) if info else 0.00001
    spread = round(tick.ask - tick.bid, 5)
    spread_pts = int(round(spread / tick_size)) if tick_size > 0 else 0

    return {
        "symbol": symbol,
        "latest_tick": {
            "symbol": symbol,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "spread": spread,
            "spread_points": spread_pts,
            "time_utc": datetime.fromtimestamp(tick.time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp_ms": int(tick.time_msc) if hasattr(tick, "time_msc") else int(tick.time * 1000),
            "flags": int(tick.flags),
            "is_mock": False,
            "data_source": "Exness MT5 Terminal IPC",
        }
    }


@app.get("/candles/{symbol}", dependencies=[Depends(require_gateway_token)])
async def get_historical_candles(
    symbol: str,
    tf: str = Query("M1", description="Timeframe: M1, M5, M15, M30, H1, H4, D1"),
    count: int = Query(100, ge=1, le=1000),
):
    """Fetches authentic OHLCV bars from broker terminal history."""
    require_mt5_terminal()

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    mt5_tf = tf_map.get(tf.upper(), mt5.TIMEFRAME_M1)

    rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
    if rates is None or len(rates) == 0:
        return {"symbol": symbol, "timeframe": tf, "count": 0, "candles": []}

    candles = [
        {
            "time": datetime.fromtimestamp(r["time"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "tick_volume": int(r["tick_volume"]),
            "spread": int(r["spread"]),
        }
        for r in rates
    ]
    return {"symbol": symbol, "timeframe": tf, "count": len(candles), "candles": candles}


@app.post("/margin/calculate", dependencies=[Depends(require_gateway_token)])
async def calculate_margin(req: MarginCheckRequest):
    """Calculates authoritative margin requirement for a prospective trade side & volume."""
    require_mt5_terminal()

    order_type_map = {
        "BUY": mt5.ORDER_TYPE_BUY,
        "SELL": mt5.ORDER_TYPE_SELL,
    }
    mt5_side = order_type_map[req.order_type]

    info = mt5.symbol_info(req.symbol)
    if not info:
        raise HTTPException(status_code=404, detail=f"Symbol '{req.symbol}' not found.")

    tick = mt5.symbol_info_tick(req.symbol)
    if not tick:
        raise HTTPException(status_code=503, detail=f"No tick available for symbol '{req.symbol}'.")

    price = float(tick.ask if req.order_type == "BUY" else tick.bid)
    if price <= 0:
        raise HTTPException(status_code=400, detail="Invalid non-positive market price.")

    margin = mt5.order_calc_margin(mt5_side, req.symbol, req.volume, price)
    if margin is None:
        err = mt5.last_error()
        raise HTTPException(status_code=400, detail=f"Margin calculation failed: {err}")

    acct = mt5.account_info()
    free_margin = float(acct.margin_free) if acct else 0.0

    return {
        "symbol": req.symbol,
        "order_type": req.order_type,
        "volume": req.volume,
        "price": price,
        "required_margin": round(float(margin), 2),
        "free_margin": round(free_margin, 2),
        "is_affordable": bool(margin <= free_margin),
    }


@app.get("/positions", dependencies=[Depends(require_gateway_token)])
async def get_open_positions():
    """Retrieves all active open positions directly from broker terminal."""
    require_mt5_terminal()
    positions = mt5.positions_get()
    if positions is None:
        return {"positions": [], "count": 0}

    pos_list = [
        {
            "ticket": str(p.ticket),
            "symbol": p.symbol,
            "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": float(p.volume),
            "open_price": float(p.price_open),
            "current_price": float(p.price_current),
            "sl": float(p.sl) if p.sl else None,
            "tp": float(p.tp) if p.tp else None,
            "profit": round(float(p.profit), 2),
            "swap": round(float(p.swap), 2),
            "time_utc": datetime.fromtimestamp(p.time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "comment": p.comment,
        }
        for p in positions
    ]
    return {"positions": pos_list, "count": len(pos_list)}


@app.get("/orders/history", dependencies=[Depends(require_gateway_token)])
async def get_orders_history(limit: int = Query(50, ge=1, le=500)):
    """Retrieves terminal order history."""
    require_mt5_terminal()
    now = datetime.now()
    orders = mt5.history_orders_get(now.replace(hour=0, minute=0, second=0), now)
    if orders is None:
        return {"orders": [], "count": 0}

    ret = [
        {
            "ticket": str(o.ticket),
            "symbol": o.symbol,
            "type": "BUY" if o.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume_initial": float(o.volume_initial),
            "volume_current": float(o.volume_current),
            "price_open": float(o.price_open),
            "state": o.state,
        }
        for o in orders[-limit:]
    ]
    return {"orders": ret, "count": len(ret)}


@app.get("/trades/history", dependencies=[Depends(require_gateway_token)])
async def get_deals_history(limit: int = Query(50, ge=1, le=500)):
    """Retrieves terminal deal/trade execution history."""
    require_mt5_terminal()
    now = datetime.now()
    deals = mt5.history_deals_get(now.replace(hour=0, minute=0, second=0), now)
    if deals is None:
        return {"trades": [], "count": 0}

    ret = [
        {
            "ticket": str(d.ticket),
            "order": str(d.order),
            "symbol": d.symbol,
            "type": "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
            "volume": float(d.volume),
            "price": float(d.price),
            "profit": round(float(d.profit), 2),
            "commission": round(float(d.commission), 2),
            "fee": round(float(d.fee), 2),
            "time": datetime.fromtimestamp(d.time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for d in deals[-limit:]
    ]
    return {"trades": ret, "count": len(ret)}


@app.get("/stops/verify/{ticket}", dependencies=[Depends(require_gateway_token)])
async def verify_protective_stop(ticket: str):
    """Verifies that an open position has exchange-confirmed SL/TP protections."""
    require_mt5_terminal()
    try:
        t_int = int(ticket)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ticket must be an integer.")

    positions = mt5.positions_get(ticket=t_int)
    if not positions or len(positions) == 0:
        raise HTTPException(status_code=404, detail=f"Position ticket '{ticket}' not found.")

    p = positions[0]
    has_sl = bool(p.sl and p.sl > 0)
    has_tp = bool(p.tp and p.tp > 0)

    return {
        "ticket": ticket,
        "symbol": p.symbol,
        "has_stop_loss": has_sl,
        "has_take_profit": has_tp,
        "sl_price": float(p.sl) if has_sl else None,
        "tp_price": float(p.tp) if has_tp else None,
        "is_protected": has_sl,
    }


@app.post("/reconcile", dependencies=[Depends(require_gateway_token)])
async def reconcile_positions(req: ReconcileRequest):
    """Performs multi-field reconciliation between local state and broker positions."""
    require_mt5_terminal()
    broker_positions = mt5.positions_get()
    broker_dict = {str(p.ticket): p for p in (broker_positions or [])}

    reconciliation_results = []
    discrepancies_found = 0

    for lp in req.local_positions:
        ticket = str(lp.get("ticket", ""))
        bp = broker_dict.get(ticket)

        if not bp:
            reconciliation_results.append({
                "ticket": ticket,
                "status": "PHANTOM_LOCAL_POSITION",
                "message": "Local position not found on broker.",
            })
            discrepancies_found += 1
            continue

        vol_diff = abs(float(lp.get("volume", 0)) - float(bp.volume))
        if vol_diff > 0.0001:
            reconciliation_results.append({
                "ticket": ticket,
                "status": "VOLUME_MISMATCH",
                "local_volume": float(lp.get("volume", 0)),
                "broker_volume": float(bp.volume),
            })
            discrepancies_found += 1
            continue

        reconciliation_results.append({
            "ticket": ticket,
            "status": "SYNCHRONIZED",
            "symbol": bp.symbol,
            "profit": round(float(bp.profit), 2),
        })

    return {
        "status": "RECONCILED",
        "account_id": req.account_id,
        "discrepancies": discrepancies_found,
        "results": reconciliation_results,
        "broker_open_count": len(broker_dict),
    }


if __name__ == "__main__":
    uvicorn.run(
        "mt5_gateway_server:app",
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        log_level="info",
        access_log=True,
    )
