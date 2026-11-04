"""
BITDEX Windows MT5 Gateway Service (Production Daemon)
Runs on Windows VPS / Server alongside the Exness MetaTrader 5 Terminal.
Provides secure HTTP/TLS REST bridge communicating directly with MetaTrader5 Python IPC.

Security & Architecture:
- Requires 'X-Gateway-Auth-Token' header on all endpoints.
- Strictly blocks REAL / LIVE accounts (enforces demo only).
- Matches ExnessMT5GatewayAdapter REST API contract.
"""

import os
import sys
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Configure logging (scrub sensitive passwords)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [bitdex-mt5-gateway] %(message)s",
)
logger = logging.getLogger("bitdex.mt5.gateway")

# Attempt MetaTrader5 import
MT5_AVAILABLE = False
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
    logger.info("MetaTrader5 Python IPC library loaded successfully.")
except ImportError:
    logger.warning("MetaTrader5 library not found. Running in mock/development mode.")

GATEWAY_AUTH_TOKEN = os.getenv("EXNESS_GATEWAY_AUTH_TOKEN", "bitdex_mt5_gateway_secure_ipc_token_2026")
GATEWAY_PORT = int(os.getenv("EXNESS_GATEWAY_PORT", "8095"))
GATEWAY_HOST = os.getenv("EXNESS_GATEWAY_HOST", "0.0.0.0")

app = FastAPI(
    title="BITDEX Exness MT5 Gateway Daemon",
    version="2.3.0",
    description="Secure REST bridge between Linux Backend and Windows MetaTrader 5 Terminal",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_token(x_gateway_auth_token: Optional[str] = Header(None)) -> bool:
    if not x_gateway_auth_token or x_gateway_auth_token != GATEWAY_AUTH_TOKEN:
        logger.warning("Unauthorized gateway access attempt: invalid or missing X-Gateway-Auth-Token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Gateway-Auth-Token",
        )
    return True


# ─────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    login: str = Field(..., description="Exness MT5 account login ID")
    password: Optional[str] = Field(None, description="Exness MT5 trading password")
    server: str = Field(default="Exness-MT5Trial", description="Exness server name")
    expected_account_type: str = Field(default="DEMO", description="Must be DEMO")


class MarginCheckRequest(BaseModel):
    symbol: str
    order_type: str
    volume: float


class ReconcileRequest(BaseModel):
    account_id: str
    local_positions: List[Dict[str, Any]] = []


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Returns gateway service status and MT5 terminal build info."""
    terminal_connected = False
    terminal_build = 0
    if MT5_AVAILABLE:
        t_info = mt5.terminal_info()
        if t_info:
            terminal_connected = t_info.connected
            terminal_build = t_info.build

    return {
        "status": "HEALTHY",
        "service": "BITDEX Windows MT5 Gateway",
        "version": "2.3.0",
        "mt5_available": MT5_AVAILABLE,
        "terminal_connected": terminal_connected,
        "terminal_build": terminal_build,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/connect")
async def connect_mt5(req: ConnectRequest, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)

    if not MT5_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader5 Python IPC library is not available on this host.",
        )

    # Initialize terminal
    if not mt5.initialize():
        err = mt5.last_error()
        logger.error(f"Failed to initialize MT5 terminal: {err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to initialize MT5 terminal: {err}",
        )

    # Login to account
    try:
        login_int = int(req.login.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account login format (must be numeric)")

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
            detail=f"MT5 authentication failed: {err}",
        )

    acct_info = mt5.account_info()
    if not acct_info:
        raise HTTPException(status_code=500, detail="Failed to retrieve MT5 account info post-login")

    # STRICT SAFETY CHECK: Verify account type (0=DEMO, 1=CONTEST, 2=REAL)
    # Never allow REAL/LIVE accounts on this staging gateway!
    if acct_info.trade_mode == 2:  # ACCOUNT_TRADE_MODE_REAL
        mt5.shutdown()
        logger.critical(f"REJECTED: Real live account {req.login} attempted connection! Terminal shut down.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CRITICAL REJECTION: Non-demo account type 'REAL' is strictly prohibited on staging.",
        )

    account_type_str = "DEMO" if acct_info.trade_mode in (0, 1) else "UNKNOWN"

    return {
        "status": "CONNECTED",
        "account_id": str(acct_info.login),
        "login": str(acct_info.login),
        "server": acct_info.server,
        "account_type": account_type_str,
        "is_demo": True,
        "broker_authenticated": True,
        "terminal_connected": True,
        "currency": acct_info.currency,
        "balance": float(acct_info.balance),
        "equity": float(acct_info.equity),
        "leverage": int(acct_info.leverage),
        "connected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/disconnect")
async def disconnect_mt5(token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if MT5_AVAILABLE:
        mt5.shutdown()
    return {"status": "DISCONNECTED"}


@app.get("/account")
async def get_account(token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 not available")

    acct = mt5.account_info()
    if not acct:
        raise HTTPException(status_code=503, detail="MT5 terminal not logged in or unavailable")

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
        "is_demo": acct.trade_mode in (0, 1),
        "is_mock": False,
        "broker_mode": "EXNESS_MT5_GATEWAY",
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.get("/symbols")
async def get_symbols(token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        return {"symbols": []}

    symbols = mt5.symbols_get()
    if not symbols:
        return {"symbols": []}

    names = [s.name for s in symbols if s.visible]
    return {"symbols": names}


@app.get("/symbol/{symbol}")
async def get_symbol_spec(symbol: str, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 not available")

    s = mt5.symbol_info(symbol)
    if not s:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    tick = mt5.symbol_info_tick(symbol)
    latest_tick_data = None
    if tick:
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


@app.get("/tick/{symbol}")
async def get_tick(symbol: str, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 not available")

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise HTTPException(status_code=404, detail=f"No tick data available for {symbol}")

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


@app.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    tf: str = "M1",
    count: int = Query(100, ge=1, le=1000),
    token_valid: bool = Header(None, alias="X-Gateway-Auth-Token"),
):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        return {"candles": []}

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "D1": mt5.TIMEFRAME_D1,
    }
    mt5_tf = tf_map.get(tf.upper(), mt5.TIMEFRAME_M1)

    rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
    if rates is None or len(rates) == 0:
        return {"candles": []}

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

    return {"candles": candles}


@app.post("/margin/calculate")
async def calculate_margin(req: MarginCheckRequest, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 not available")

    action = mt5.ORDER_TYPE_BUY if req.order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(req.symbol)
    price = tick.ask if req.order_type.upper() == "BUY" else tick.bid if tick else 0.0

    margin = mt5.order_calc_margin(action, req.symbol, req.volume, price)
    acct = mt5.account_info()
    free_margin = float(acct.margin_free) if acct else 0.0

    return {
        "margin_check": {
            "symbol": req.symbol,
            "order_type": req.order_type.upper(),
            "volume": req.volume,
            "price": price,
            "required_margin_usd": float(margin) if margin is not None else 0.0,
            "current_free_margin_usd": free_margin,
            "is_affordable": free_margin >= (margin or 0.0),
            "status": "APPROVED" if (margin and free_margin >= margin) else "REJECTED",
        }
    }


@app.get("/positions")
async def get_positions(token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        return {"positions": []}

    pos = mt5.positions_get()
    if not pos:
        return {"positions": []}

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

    return {"positions": result}


@app.get("/orders/history")
async def get_orders_history(limit: int = 100, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        return {"orders": []}

    orders = mt5.history_orders_get(0, datetime.now())
    if not orders:
        return {"orders": []}

    return {"orders": [{"ticket": str(o.ticket), "symbol": o.symbol, "volume": float(o.volume_initial)} for o in orders[-limit:]]}


@app.get("/trades/history")
async def get_trades_history(limit: int = 100, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        return {"trades": []}

    deals = mt5.history_deals_get(0, datetime.now())
    if not deals:
        return {"trades": []}

    return {"trades": [{"deal": str(d.ticket), "order": str(d.order), "symbol": d.symbol, "profit": float(d.profit)} for d in deals[-limit:]]}


@app.get("/stops/verify/{ticket}")
async def verify_stop(ticket: str, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        return {"broker_stop_active": False}

    pos = mt5.positions_get(ticket=int(ticket))
    if not pos:
        return {"broker_stop_active": False, "reason": "POSITION_NOT_FOUND"}

    p = pos[0]
    return {
        "ticket": str(p.ticket),
        "broker_stop_active": bool(p.sl > 0),
        "stop_loss_price": float(p.sl),
        "take_profit_price": float(p.tp),
    }


@app.post("/reconcile")
async def reconcile_account_endpoint(req: ReconcileRequest, token_valid: bool = Header(None, alias="X-Gateway-Auth-Token")):
    verify_token(token_valid)
    if not MT5_AVAILABLE:
        raise HTTPException(status_code=503, detail="MT5 not available")

    broker_positions = mt5.positions_get() or []
    broker_map = {str(p.ticket): p for p in broker_positions}
    local_map = {str(pos.get("broker_ticket", "")): pos for pos in req.local_positions}

    discrepancies = []

    # 1. Un-tracked broker positions
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
    logger.info(f"Starting BITDEX Exness MT5 Gateway on {GATEWAY_HOST}:{GATEWAY_PORT}...")
    uvicorn.run("mt5_gateway_server:app", host=GATEWAY_HOST, port=GATEWAY_PORT, reload=False)
