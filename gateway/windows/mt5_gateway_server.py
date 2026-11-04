"""
BITDEX Windows MT5 Gateway Service (Hardened Phase 2.3.1)
Runs on Windows VPS / Server alongside the Exness MetaTrader 5 Terminal.
Provides secure HTTP/TLS REST bridge communicating directly with MetaTrader5 Python IPC.

Security Hardening (Phase 2.3.1):
- Fail-closed startup: Requires a strong EXNESS_GATEWAY_AUTH_TOKEN (min 32 chars).
- Constant-time token verification on every endpoint via X-Gateway-Auth-Token header.
- Strict DEMO-only validation: Authoritative check on mt5.account_info().trade_mode == 0 (DEMO).
  Strictly rejects REAL (2), CONTEST (1), and UNKNOWN modes.
- Enforces expected_account_type == "DEMO", plus account login and server verification post-auth.
- Explicit 503 errors when MT5 terminal is unavailable (never returns empty 200).
- Margin calculation rejects missing ticks, non-positive prices, invalid order types, and out-of-bounds volumes.
- Network security: Client IP allowlisting, no wildcard CORS, loopback/private tunnel binding by default.
- Strict read/diagnostic bridge only: Zero order placement or execution endpoints.
"""

import os
import sys
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
    if token.strip().lower() in WEAK_SECRETS:
        raise RuntimeError(
            "CRITICAL SECURITY FAILURE: EXNESS_GATEWAY_AUTH_TOKEN is using a known weak or "
            "default value. You must generate a cryptographically strong secret."
        )
    return token.strip()


GATEWAY_AUTH_TOKEN = os.getenv("EXNESS_GATEWAY_AUTH_TOKEN")
# Validate on module load (can be overridden in tests via init_app or env)
if os.getenv("STRICT_STARTUP_CHECK", "true").lower() == "true":
    GATEWAY_AUTH_TOKEN = validate_gateway_token(GATEWAY_AUTH_TOKEN)
else:
    GATEWAY_AUTH_TOKEN = GATEWAY_AUTH_TOKEN or ""

GATEWAY_PORT = int(os.getenv("EXNESS_GATEWAY_PORT", "8095"))
# Secure default: bind to localhost / private tunnel interface, not open 0.0.0.0
GATEWAY_HOST = os.getenv("EXNESS_GATEWAY_HOST", "127.0.0.1")

# IP Allowlist: Allow loopback and configured staging backend IP
ALLOWED_CLIENT_IPS_RAW = os.getenv("ALLOWED_CLIENT_IPS", "127.0.0.1,::1,169.58.218.168")
ALLOWED_CLIENT_IPS = {ip.strip() for ip in ALLOWED_CLIENT_IPS_RAW.split(",") if ip.strip()}

# CORS Origins: Strict, no wildcard
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


# ─────────────────────────────────────────────────────────────
# 2. FastAPI Application & Security Middleware
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="BITDEX Exness MT5 Gateway Daemon (Hardened)",
    version="2.3.1",
    description="Secure REST bridge between Linux Staging Backend and Windows MetaTrader 5 Terminal",
    docs_url=None,  # Disable Swagger UI in production
    redoc_url=None,  # Disable ReDoc in production
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
    """
    Enforces network-level client IP restriction and optional HTTPS/TLS header verification.
    """
    client_host = request.client.host if request.client else None

    # Check client IP if enforcement is active
    if os.getenv("ENFORCE_CLIENT_IP", "false").lower() == "true":
        if client_host and client_host not in ALLOWED_CLIENT_IPS:
            logger.warning(f"Unauthorized access blocked from untrusted IP: {client_host}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": f"Access forbidden: Client IP '{client_host}' is not in the authorized allowlist."},
            )

    # Check TLS requirement if configured
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
    """
    Validates X-Gateway-Auth-Token using constant-time comparison.
    Header parameter is explicitly typed as str.
    """
    if not x_gateway_auth_token:
        logger.warning("Gateway authentication rejected: Missing X-Gateway-Auth-Token header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Gateway-Auth-Token header.",
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
    """
    Validates that the MT5 library and terminal are operational.
    Fails closed with 503 Service Unavailable if MT5 is offline.
    """
    if not MT5_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 Python IPC library is unavailable on this host.",
        )
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
    expected_account_type: str = Field(default="DEMO", description="Must be DEMO")

    @field_validator("expected_account_type")
    @classmethod
    def validate_account_type(cls, v: str) -> str:
        if v.strip().upper() != "DEMO":
            raise ValueError(f"Strict safety rejection: Only 'DEMO' is accepted, got '{v}'.")
        return v.strip().upper()


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
    """Returns gateway service status and verified MT5 terminal build info."""
    terminal_connected = False
    terminal_build = 0
    trade_mode = None

    if MT5_AVAILABLE:
        t_info = mt5.terminal_info()
        if t_info:
            terminal_connected = bool(t_info.connected)
            terminal_build = int(t_info.build)
        acct = mt5.account_info()
        if acct:
            trade_mode = acct.trade_mode

    return {
        "status": "HEALTHY",
        "service": "BITDEX Windows MT5 Gateway",
        "version": "2.3.1",
        "mt5_available": MT5_AVAILABLE,
        "terminal_connected": terminal_connected,
        "terminal_build": terminal_build,
        "active_trade_mode": trade_mode,
        "environment": "DEMO_ONLY",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/connect", dependencies=[Depends(require_gateway_token)])
async def connect_mt5(req: ConnectRequest):
    """
    Authenticates with MT5 terminal and enforces strict DEMO verification.
    Rejects REAL, LIVE, CONTEST, and UNKNOWN account types.
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
    # STRICT DEMO-ONLY ACCOUNT VALIDATION:
    # 0 = ACCOUNT_TRADE_MODE_DEMO
    # 1 = ACCOUNT_TRADE_MODE_CONTEST
    # 2 = ACCOUNT_TRADE_MODE_REAL
    # ─────────────────────────────────────────────────────────────
    if acct_info.trade_mode != 0:
        mt5.shutdown()
        mode_names = {1: "CONTEST", 2: "REAL"}
        detected_mode = mode_names.get(acct_info.trade_mode, f"UNKNOWN({acct_info.trade_mode})")
        logger.critical(
            f"CRITICAL REJECTION: Account {req.login} has trade_mode={detected_mode}. "
            f"Only verified DEMO accounts (trade_mode=0) are authorized on staging."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"CRITICAL REJECTION: Account type '{detected_mode}' is strictly prohibited on staging. "
                f"Only verified DEMO accounts (trade_mode=0) are authorized."
            ),
        )

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

    return {
        "status": "CONNECTED",
        "account_id": str(acct_info.login),
        "login": str(acct_info.login),
        "server": acct_info.server,
        "account_type": "DEMO",
        "is_demo": True,
        "broker_authenticated": True,
        "terminal_connected": True,
        "currency": acct_info.currency,
        "balance": float(acct_info.balance),
        "equity": float(acct_info.equity),
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
async def get_account():
    """Retrieves authoritative broker account telemetry. Never returns empty 200."""
    require_mt5_terminal()

    acct = mt5.account_info()
    if not acct:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MT5 terminal not logged in or account telemetry unavailable.",
        )

    # Authoritative demo confirmation
    if acct.trade_mode != 0:
        mt5.shutdown()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Non-demo account detected during account query. Disconnected.",
        )

    return {
        "account_id": str(acct.login),
        "server": acct.server,
        "currency": acct.currency,
        "leverage": int(acct.leverage),
        "balance": float(acct.balance),
        "equity": float(acct.equity),
        "used_margin": float(acct.margin),
        "free_margin": float(acct.margin_free),
        "margin_level": float(acct.margin_level) if acct.margin > 0 else 0.0,
        "open_positions_count": int(mt5.positions_total() or 0),
        "is_demo": True,
        "broker_mode": "EXNESS_MT5_GATEWAY",
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.get("/symbols", dependencies=[Depends(require_gateway_token)])
async def get_symbols():
    """Returns list of visible tradable symbols. Fails closed with 503 if MT5 unavailable."""
    require_mt5_terminal()

    symbols = mt5.symbols_get()
    if symbols is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to query symbols from MT5 terminal.",
        )

    names = [s.name for s in symbols if s.visible]
    return {"symbols": names, "count": len(names)}


@app.get("/symbol/{symbol}", dependencies=[Depends(require_gateway_token)])
async def get_symbol_spec(symbol: str):
    """Returns contract specification and tick data for symbol."""
    require_mt5_terminal()

    s = mt5.symbol_info(symbol)
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found on broker.",
        )

    tick = mt5.symbol_info_tick(symbol)
    latest_tick_data = None
    if tick and tick.bid > 0 and tick.ask > 0:
        latest_tick_data = {
            "symbol": symbol,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "last": float(tick.last),
            "spread": float(tick.ask - tick.bid),
            "time_utc": datetime.fromtimestamp(tick.time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "is_mock": False,
        }

    return {
        "symbol_info": {
            "broker_symbol": s.name,
            "canonical_symbol": s.name,
            "name": s.description,
            "product_type": "FOREX_CFD",
            "contract_size": float(s.trade_contract_size),
            "min_volume": float(s.volume_min),
            "max_volume": float(s.volume_max),
            "volume_step": float(s.volume_step),
            "tick_size": float(s.trade_tick_size),
            "tick_value": float(s.trade_tick_value),
            "digits": int(s.digits),
            "typical_spread": float(s.spread),
            "stops_level": int(s.trade_stops_level),
            "leverage": 2000,
            "margin_initial_pct": float(s.margin_initial),
            "is_tradable": bool(s.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL),
        },
        "latest_tick": latest_tick_data,
    }


@app.get("/tick/{symbol}", dependencies=[Depends(require_gateway_token)])
async def get_tick(symbol: str):
    """Returns real-time bid/ask quote. Fails closed with 503/404 if data missing."""
    require_mt5_terminal()

    s = mt5.symbol_info(symbol)
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found on broker.",
        )

    tick = mt5.symbol_info_tick(symbol)
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live tick quote unavailable for symbol '{symbol}'.",
        )

    return {
        "latest_tick": {
            "symbol": symbol,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "last": float(tick.last),
            "spread": float(tick.ask - tick.bid),
            "time_utc": datetime.fromtimestamp(tick.time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp_ms": int(tick.time_msc),
            "is_mock": False,
        }
    }


@app.get("/candles/{symbol}", dependencies=[Depends(require_gateway_token)])
async def get_candles(
    symbol: str,
    tf: str = "M1",
    count: int = Query(100, ge=1, le=1000),
):
    """Retrieves historical OHLCV bars. Fails closed with 503 if data unavailable."""
    require_mt5_terminal()

    s = mt5.symbol_info(symbol)
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found on broker.",
        )

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "D1": mt5.TIMEFRAME_D1,
    }
    mt5_tf = tf_map.get(tf.upper())
    if mt5_tf is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported timeframe '{tf}'. Supported: M1, M5, M15, H1, D1.",
        )

    rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
    if rates is None or len(rates) == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to retrieve candle history for '{symbol}' from MT5.",
        )

    candles = []
    for r in rates:
        candles.append({
            "time": datetime.fromtimestamp(r["time"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["tick_volume"]),
        })

    return {"candles": candles, "count": len(candles)}


@app.post("/margin/calculate", dependencies=[Depends(require_gateway_token)])
async def calculate_margin(req: MarginCheckRequest):
    """
    Calculates required margin on broker terminal with rigorous parameter and market validation.
    Rejects missing ticks, non-positive prices, invalid order types, and out-of-bounds volumes.
    """
    require_mt5_terminal()

    # 1. Validate symbol
    s = mt5.symbol_info(req.symbol)
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{req.symbol}' not found on broker.",
        )
    if not s.visible or s.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Symbol '{req.symbol}' is not currently tradable on broker.",
        )

    # 2. Validate volume bounds
    if req.volume < s.volume_min:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Volume {req.volume} is below broker minimum {s.volume_min} for {req.symbol}.",
        )
    if req.volume > s.volume_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Volume {req.volume} exceeds broker maximum {s.volume_max} for {req.symbol}.",
        )

    # 3. Validate live market tick
    tick = mt5.symbol_info_tick(req.symbol)
    if not tick:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live tick quote unavailable for symbol '{req.symbol}'. Cannot calculate margin.",
        )

    action = mt5.ORDER_TYPE_BUY if req.order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    price = float(tick.ask) if req.order_type.upper() == "BUY" else float(tick.bid)

    if price <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Non-positive quote price ({price}) for '{req.symbol}'. Cannot calculate margin.",
        )

    # 4. Authoritative broker margin calculation
    margin = mt5.order_calc_margin(action, req.symbol, req.volume, price)
    if margin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Broker failed to calculate margin for {req.order_type} {req.volume} {req.symbol}.",
        )

    acct = mt5.account_info()
    free_margin = float(acct.margin_free) if acct else 0.0

    return {
        "margin_check": {
            "symbol": req.symbol,
            "order_type": req.order_type.upper(),
            "volume": req.volume,
            "price": price,
            "required_margin_usd": float(margin),
            "current_free_margin_usd": free_margin,
            "is_affordable": free_margin >= float(margin),
            "status": "APPROVED" if free_margin >= float(margin) else "REJECTED",
        }
    }


@app.get("/positions", dependencies=[Depends(require_gateway_token)])
async def get_positions():
    """Retrieves authoritative open positions from broker. Fails closed with 503 if MT5 down."""
    require_mt5_terminal()

    pos = mt5.positions_get()
    if pos is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to query open positions from MT5 broker terminal.",
        )

    result = []
    for p in pos:
        result.append({
            "ticket": str(p.ticket),
            "symbol": p.symbol,
            "side": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": float(p.volume),
            "price_open": float(p.price_open),
            "sl": float(p.sl),
            "tp": float(p.tp),
            "profit": float(p.profit),
            "time_utc": datetime.fromtimestamp(p.time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    return {"positions": result, "count": len(result)}


@app.get("/orders/history", dependencies=[Depends(require_gateway_token)])
async def get_orders_history(limit: int = 100):
    """Retrieves historical orders. Fails closed with 503 if terminal unavailable."""
    require_mt5_terminal()

    orders = mt5.history_orders_get(0, datetime.now())
    if orders is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to query historical orders from MT5 broker terminal.",
        )

    items = [{"ticket": str(o.ticket), "symbol": o.symbol, "volume": float(o.volume_initial)} for o in orders[-limit:]]
    return {"orders": items, "count": len(items)}


@app.get("/trades/history", dependencies=[Depends(require_gateway_token)])
async def get_trades_history(limit: int = 100):
    """Retrieves historical deals/trades. Fails closed with 503 if terminal unavailable."""
    require_mt5_terminal()

    deals = mt5.history_deals_get(0, datetime.now())
    if deals is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to query trade deals history from MT5 broker terminal.",
        )

    items = [{"deal": str(d.ticket), "order": str(d.order), "symbol": d.symbol, "profit": float(d.profit)} for d in deals[-limit:]]
    return {"trades": items, "count": len(items)}


@app.get("/stops/verify/{ticket}", dependencies=[Depends(require_gateway_token)])
async def verify_stop(ticket: str):
    """Verifies broker-side stop-loss and take-profit for a ticket."""
    require_mt5_terminal()

    try:
        t_int = int(ticket.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Ticket must be numeric integer.")

    pos = mt5.positions_get(ticket=t_int)
    if not pos:
        return {"ticket": ticket, "broker_stop_active": False, "reason": "POSITION_NOT_FOUND"}

    p = pos[0]
    return {
        "ticket": str(p.ticket),
        "broker_stop_active": bool(p.sl > 0),
        "stop_loss_price": float(p.sl),
        "take_profit_price": float(p.tp),
    }


@app.post("/reconcile", dependencies=[Depends(require_gateway_token)])
async def reconcile_account_endpoint(req: ReconcileRequest):
    """Performs multi-field reconciliation comparing local positions with broker positions."""
    require_mt5_terminal()

    broker_positions = mt5.positions_get()
    if broker_positions is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to query broker positions for reconciliation.",
        )

    broker_map = {str(p.ticket): p for p in broker_positions}
    local_map = {str(pos.get("broker_ticket", "")): pos for pos in req.local_positions}

    discrepancies = []

    # 1. Untracked broker positions
    for ticket, b_pos in broker_map.items():
        if ticket not in local_map:
            discrepancies.append({
                "type": "UNTRACKED_BROKER_POSITION",
                "ticket": ticket,
                "symbol": b_pos.symbol,
                "direction": "BUY" if b_pos.type == 0 else "SELL",
                "volume": float(b_pos.volume),
            })
        else:
            loc = local_map[ticket]
            # Symbol check
            if b_pos.symbol != loc.get("symbol"):
                discrepancies.append({
                    "type": "SYMBOL_MISMATCH",
                    "ticket": ticket,
                    "broker_symbol": b_pos.symbol,
                    "local_symbol": loc.get("symbol"),
                })
            # Side check
            b_side = "BUY" if b_pos.type == 0 else "SELL"
            l_side = loc.get("order_side", "").upper()
            if b_side != l_side:
                discrepancies.append({
                    "type": "DIRECTION_MISMATCH",
                    "ticket": ticket,
                    "broker_direction": b_side,
                    "local_direction": l_side,
                })
            # Volume check
            if round(b_pos.volume, 4) != round(float(loc.get("volume", 0)), 4):
                discrepancies.append({
                    "type": "VOLUME_MISMATCH",
                    "ticket": ticket,
                    "broker_volume": float(b_pos.volume),
                    "local_volume": float(loc.get("volume", 0)),
                })

    # 2. Orphan local positions
    for ticket, loc in local_map.items():
        if ticket and ticket not in broker_map:
            discrepancies.append({
                "type": "ORPHAN_LOCAL_POSITION",
                "ticket": ticket,
                "local_symbol": loc.get("symbol"),
                "local_volume": loc.get("volume"),
            })

    acct = mt5.account_info()
    status_str = "RECONCILED" if len(discrepancies) == 0 else "DISCREPANCY_DETECTED"

    return {
        "status": status_str,
        "reconciliation_source": "EXNESS_MT5_GATEWAY",
        "is_mock": False,
        "account_id": req.account_id,
        "broker_positions_count": len(broker_positions),
        "local_positions_count": len(req.local_positions),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
        "equity": float(acct.equity) if acct else 0.0,
        "balance": float(acct.balance) if acct else 0.0,
        "used_margin": float(acct.margin) if acct else 0.0,
        "free_margin": float(acct.margin_free) if acct else 0.0,
        "reconciled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


if __name__ == "__main__":
    GATEWAY_AUTH_TOKEN = validate_gateway_token(os.getenv("EXNESS_GATEWAY_AUTH_TOKEN"))
    logger.info(f"Starting BITDEX Exness MT5 Gateway on {GATEWAY_HOST}:{GATEWAY_PORT}...")
    uvicorn.run("mt5_gateway_server:app", host=GATEWAY_HOST, port=GATEWAY_PORT, reload=False)
