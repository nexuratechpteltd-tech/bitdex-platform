import sqlite3
import os
import json
import logging
import secrets
import time
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
import httpx

logger = logging.getLogger("bitdex.ledger_db")

def get_db_path() -> str:
    try:
        from ..config import settings
        data_dir = os.path.join(settings.platform_root, "backend", "data")
    except Exception:
        data_dir = "/opt/tauric-platform-staging/backend/data"
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "tauric_saas.db")

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    return conn

def init_ledger_tables():
    """Initializes permanent database ledger tables and indexes with institutional schema."""
    with get_db_connection() as conn:
        # 1. exchange_orders
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                internal_order_id TEXT UNIQUE NOT NULL,
                client_order_id TEXT NOT NULL,
                exchange_order_id TEXT,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'BINANCE',
                environment TEXT NOT NULL DEFAULT 'DEMO',
                symbol TEXT NOT NULL,
                display_pair TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                requested_price REAL DEFAULT 0.0,
                avg_fill_price REAL DEFAULT 0.0,
                orig_qty REAL NOT NULL,
                executed_qty REAL NOT NULL DEFAULT 0.0,
                remaining_qty REAL NOT NULL DEFAULT 0.0,
                cummulative_quote_qty REAL DEFAULT 0.0,
                status TEXT NOT NULL,
                time_in_force TEXT DEFAULT 'GTC',
                commission_total REAL DEFAULT 0.0,
                commission_asset TEXT,
                verification_status TEXT DEFAULT 'EXCHANGE_VERIFIED',
                execution_type TEXT DEFAULT 'REAL_EXCHANGE_DEMO',
                is_exchange_confirmed INTEGER DEFAULT 1,
                exchange_created_at_ms INTEGER,
                exchange_updated_at_ms INTEGER,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                raw_json TEXT
            );
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_env ON exchange_orders (user_id, environment);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_account ON exchange_orders (account_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_exch_id ON exchange_orders (exchange_order_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_client_id ON exchange_orders (client_order_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_symbol ON exchange_orders (symbol);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON exchange_orders (status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON exchange_orders (created_at_utc);")

        # 2. exchange_order_fills
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_order_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fill_id TEXT UNIQUE NOT NULL,
                exchange_trade_id TEXT NOT NULL,
                exchange_order_id TEXT NOT NULL,
                internal_order_id TEXT,
                client_order_id TEXT,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'BINANCE',
                environment TEXT NOT NULL DEFAULT 'DEMO',
                symbol TEXT NOT NULL,
                display_pair TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                qty REAL NOT NULL,
                quote_qty REAL NOT NULL,
                commission REAL NOT NULL DEFAULT 0.0,
                commission_asset TEXT NOT NULL,
                is_buyer INTEGER DEFAULT 1,
                is_maker INTEGER DEFAULT 0,
                trade_time_ms INTEGER NOT NULL,
                trade_time_utc TEXT NOT NULL,
                verification_status TEXT DEFAULT 'EXCHANGE_VERIFIED',
                raw_json TEXT,
                created_at_utc TEXT NOT NULL
            );
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_fills_user_env ON exchange_order_fills (user_id, environment);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fills_order ON exchange_order_fills (exchange_order_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fills_trade ON exchange_order_fills (exchange_trade_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fills_symbol ON exchange_order_fills (symbol);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fills_time ON exchange_order_fills (trade_time_utc);")

        # 3. exchange_audit_events
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                internal_order_id TEXT,
                exchange_order_id TEXT,
                event_type TEXT NOT NULL,
                lifecycle_step TEXT NOT NULL,
                message TEXT NOT NULL,
                payload TEXT,
                created_at_utc TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_order ON exchange_audit_events (exchange_order_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON exchange_audit_events (user_id);")

        # 4. spot_asset_snapshots
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spot_asset_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'BINANCE',
                environment TEXT NOT NULL DEFAULT 'DEMO',
                asset TEXT NOT NULL,
                free REAL NOT NULL,
                locked REAL NOT NULL DEFAULT 0.0,
                total REAL NOT NULL,
                valuation_usd REAL DEFAULT 0.0,
                avg_cost_basis REAL DEFAULT 0.0,
                updated_at_utc TEXT NOT NULL,
                UNIQUE(account_id, environment, asset)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_account ON spot_asset_snapshots (account_id, environment);")


def format_display_pair(symbol: str) -> str:
    s = symbol.upper().replace("/", "").replace("-", "").strip()
    quotes = ["USDT", "USDC", "BUSD", "BTC", "ETH", "EUR", "USD"]
    for q in quotes:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[:-len(q)]}/{q}"
    return s


def upsert_exchange_order(order_data: dict) -> dict:
    """Upserts an exchange order into exchange_orders idempotently."""
    init_ledger_tables()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db_connection() as conn:
        # Check if exists by provider, account_id, exchange_order_id or internal_order_id
        existing = None
        if order_data.get("exchange_order_id"):
            existing = conn.execute(
                "SELECT * FROM exchange_orders WHERE provider = ? AND account_id = ? AND exchange_order_id = ?",
                (order_data.get("provider", "BINANCE"), order_data.get("account_id"), str(order_data["exchange_order_id"]))
            ).fetchone()
        if not existing and order_data.get("internal_order_id"):
            existing = conn.execute(
                "SELECT * FROM exchange_orders WHERE internal_order_id = ?",
                (order_data["internal_order_id"],)
            ).fetchone()

        disp_pair = order_data.get("display_pair") or format_display_pair(order_data.get("symbol", ""))
        orig_qty = float(order_data.get("orig_qty", 0.0))
        exec_qty = float(order_data.get("executed_qty", 0.0))
        rem_qty = max(0.0, orig_qty - exec_qty)

        if existing:
            conn.execute("""
                UPDATE exchange_orders SET
                    exchange_order_id = COALESCE(?, exchange_order_id),
                    status = ?,
                    avg_fill_price = ?,
                    orig_qty = ?,
                    executed_qty = ?,
                    remaining_qty = ?,
                    cummulative_quote_qty = ?,
                    commission_total = ?,
                    commission_asset = COALESCE(?, commission_asset),
                    verification_status = ?,
                    exchange_updated_at_ms = ?,
                    updated_at_utc = ?,
                    raw_json = COALESCE(?, raw_json)
                WHERE id = ?
            """, (
                str(order_data.get("exchange_order_id")) if order_data.get("exchange_order_id") else None,
                order_data.get("status", existing["status"]),
                float(order_data.get("avg_fill_price", existing["avg_fill_price"])),
                orig_qty,
                exec_qty,
                rem_qty,
                float(order_data.get("cummulative_quote_qty", existing["cummulative_quote_qty"])),
                float(order_data.get("commission_total", existing["commission_total"])),
                order_data.get("commission_asset"),
                order_data.get("verification_status", existing["verification_status"]),
                order_data.get("exchange_updated_at_ms"),
                now_iso,
                json.dumps(order_data.get("raw_json")) if isinstance(order_data.get("raw_json"), dict) else order_data.get("raw_json"),
                existing["id"]
            ))
            order_id = existing["id"]
        else:
            int_id = order_data.get("internal_order_id") or f"INT-BIN-{secrets.token_hex(6).upper()}"
            cur = conn.execute("""
                INSERT INTO exchange_orders (
                    internal_order_id, client_order_id, exchange_order_id,
                    user_id, account_id, provider, environment,
                    symbol, display_pair, side, order_type,
                    requested_price, avg_fill_price, orig_qty, executed_qty, remaining_qty,
                    cummulative_quote_qty, status, time_in_force,
                    commission_total, commission_asset, verification_status,
                    execution_type, is_exchange_confirmed,
                    exchange_created_at_ms, exchange_updated_at_ms,
                    created_at_utc, updated_at_utc, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int_id,
                order_data.get("client_order_id", f"ORD-DEMO-BIN-{secrets.token_hex(6).upper()}"),
                str(order_data.get("exchange_order_id")) if order_data.get("exchange_order_id") else None,
                order_data.get("user_id", ""),
                order_data.get("account_id", ""),
                order_data.get("provider", "BINANCE"),
                order_data.get("environment", "DEMO"),
                order_data.get("symbol", "").upper(),
                disp_pair,
                order_data.get("side", "BUY").upper(),
                order_data.get("order_type", "LIMIT").upper(),
                float(order_data.get("requested_price", 0.0)),
                float(order_data.get("avg_fill_price", 0.0)),
                orig_qty,
                exec_qty,
                rem_qty,
                float(order_data.get("cummulative_quote_qty", 0.0)),
                order_data.get("status", "NEW").upper(),
                order_data.get("time_in_force", "GTC"),
                float(order_data.get("commission_total", 0.0)),
                order_data.get("commission_asset"),
                order_data.get("verification_status", "EXCHANGE_VERIFIED"),
                order_data.get("execution_type", "REAL_EXCHANGE_DEMO"),
                1 if order_data.get("is_exchange_confirmed", True) else 0,
                order_data.get("exchange_created_at_ms"),
                order_data.get("exchange_updated_at_ms"),
                order_data.get("created_at_utc", now_iso),
                now_iso,
                json.dumps(order_data.get("raw_json")) if isinstance(order_data.get("raw_json"), dict) else order_data.get("raw_json")
            ))
            order_id = cur.lastrowid

        saved = conn.execute("SELECT * FROM exchange_orders WHERE id = ?", (order_id,)).fetchone()
        return dict(saved)


def upsert_exchange_fill(fill_data: dict) -> dict:
    """Upserts an exchange fill into exchange_order_fills idempotently."""
    init_ledger_tables()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM exchange_order_fills WHERE provider = ? AND account_id = ? AND exchange_trade_id = ?",
            (fill_data.get("provider", "BINANCE"), fill_data.get("account_id"), str(fill_data["exchange_trade_id"]))
        ).fetchone()

        disp_pair = fill_data.get("display_pair") or format_display_pair(fill_data.get("symbol", ""))

        if existing:
            conn.execute("""
                UPDATE exchange_order_fills SET
                    price = ?, qty = ?, quote_qty = ?,
                    commission = ?, commission_asset = ?,
                    raw_json = COALESCE(?, raw_json)
                WHERE id = ?
            """, (
                float(fill_data.get("price", existing["price"])),
                float(fill_data.get("qty", existing["qty"])),
                float(fill_data.get("quote_qty", existing["quote_qty"])),
                float(fill_data.get("commission", existing["commission"])),
                fill_data.get("commission_asset", existing["commission_asset"]),
                json.dumps(fill_data.get("raw_json")) if isinstance(fill_data.get("raw_json"), dict) else fill_data.get("raw_json"),
                existing["id"]
            ))
            fill_id = existing["id"]
        else:
            fid = fill_data.get("fill_id") or f"FILL-BIN-{fill_data.get('exchange_trade_id')}"
            trade_ts_ms = fill_data.get("trade_time_ms") or int(time.time() * 1000)
            trade_ts_utc = fill_data.get("trade_time_utc") or datetime.fromtimestamp(trade_ts_ms / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            cur = conn.execute("""
                INSERT INTO exchange_order_fills (
                    fill_id, exchange_trade_id, exchange_order_id,
                    internal_order_id, client_order_id,
                    user_id, account_id, provider, environment,
                    symbol, display_pair, side,
                    price, qty, quote_qty, commission, commission_asset,
                    is_buyer, is_maker, trade_time_ms, trade_time_utc,
                    verification_status, raw_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fid,
                str(fill_data["exchange_trade_id"]),
                str(fill_data["exchange_order_id"]),
                fill_data.get("internal_order_id"),
                fill_data.get("client_order_id"),
                fill_data.get("user_id", ""),
                fill_data.get("account_id", ""),
                fill_data.get("provider", "BINANCE"),
                fill_data.get("environment", "DEMO"),
                fill_data.get("symbol", "").upper(),
                disp_pair,
                fill_data.get("side", "BUY").upper(),
                float(fill_data.get("price", 0.0)),
                float(fill_data.get("qty", 0.0)),
                float(fill_data.get("quote_qty", 0.0)),
                float(fill_data.get("commission", 0.0)),
                fill_data.get("commission_asset", "USDT"),
                1 if fill_data.get("is_buyer", True) else 0,
                1 if fill_data.get("is_maker", False) else 0,
                trade_ts_ms,
                trade_ts_utc,
                fill_data.get("verification_status", "EXCHANGE_VERIFIED"),
                json.dumps(fill_data.get("raw_json")) if isinstance(fill_data.get("raw_json"), dict) else fill_data.get("raw_json"),
                now_iso
            ))
            fill_id = cur.lastrowid

        saved = conn.execute("SELECT * FROM exchange_order_fills WHERE id = ?", (fill_id,)).fetchone()
        return dict(saved)


def record_audit_event(
    user_id: str,
    account_id: str,
    event_type: str,
    lifecycle_step: str,
    message: str,
    internal_order_id: Optional[str] = None,
    exchange_order_id: Optional[str] = None,
    payload: Optional[dict] = None
):
    init_ledger_tables()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO exchange_audit_events (
                event_id, user_id, account_id,
                internal_order_id, exchange_order_id,
                event_type, lifecycle_step, message, payload, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"EVT-{secrets.token_hex(6).upper()}",
            user_id,
            account_id,
            internal_order_id,
            str(exchange_order_id) if exchange_order_id else None,
            event_type,
            lifecycle_step,
            message,
            json.dumps(payload) if payload else None,
            now_iso
        ))


def upsert_spot_asset_snapshot(snapshot: dict):
    init_ledger_tables()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO spot_asset_snapshots (
                user_id, account_id, provider, environment,
                asset, free, locked, total, valuation_usd, avg_cost_basis, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, environment, asset) DO UPDATE SET
                free = excluded.free,
                locked = excluded.locked,
                total = excluded.total,
                valuation_usd = excluded.valuation_usd,
                avg_cost_basis = excluded.avg_cost_basis,
                updated_at_utc = excluded.updated_at_utc
        """, (
            snapshot.get("user_id", ""),
            snapshot.get("account_id", ""),
            snapshot.get("provider", "BINANCE"),
            snapshot.get("environment", "DEMO"),
            snapshot.get("asset", "").upper(),
            float(snapshot.get("free", 0.0)),
            float(snapshot.get("locked", 0.0)),
            float(snapshot.get("total", 0.0)),
            float(snapshot.get("valuation_usd", 0.0)),
            float(snapshot.get("avg_cost_basis", 0.0)),
            now_iso
        ))


async def sync_binance_account(account_id: str, user_id: str, tracked_symbols: Optional[List[str]] = None) -> dict:
    """
    Directly queries Binance Mock Trading REST endpoints:
    1. GET /api/v3/account -> Spot Asset Holdings
    2. GET /api/v3/openOrders -> Working Orders
    3. GET /api/v3/allOrders -> Order History for tracked symbols
    4. GET /api/v3/myTrades -> Granular Trade Fills
    5. GET /api/v3/ticker/price -> Real-time valuations
    Persists everything to permanent SQLite ledger with strict duplicate prevention.
    """
    init_ledger_tables()
    from app.routes.saas_customer import _decrypt_credentials_payload

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT account_id, provider, environment, label, encrypted_credentials FROM user_exchange_connections WHERE account_id = ?",
            (account_id,)
        ).fetchone()

    if not row:
        raise ValueError(f"Exchange connection {account_id} not found.")

    creds = _decrypt_credentials_payload(row["encrypted_credentials"])
    api_key = creds.get("api_key") or creds.get("apiKey")
    api_secret = creds.get("api_secret") or creds.get("secret") or creds.get("secretKey")
    if not api_key or not api_secret:
        raise ValueError(f"No API key/secret found for connection {account_id}.")

    base_url = "https://demo-api.binance.com/api/v3"
    headers = {"X-MBX-APIKEY": api_key}
    synced_orders = 0
    synced_fills = 0
    synced_assets = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Fetch Balances
        ts = int(time.time() * 1000)
        q = f"timestamp={ts}"
        sig = hmac.new(api_secret.encode("utf-8"), q.encode("utf-8"), hashlib.sha256).hexdigest()
        r_acc = await client.get(f"{base_url}/account?{q}&signature={sig}", headers=headers)
        
        asset_balances = {}
        if r_acc.status_code == 200:
            acc_data = r_acc.json()
            # Fetch tickers for valuations
            r_prices = await client.get(f"{base_url}/ticker/price")
            prices_map = {}
            if r_prices.status_code == 200:
                for item in r_prices.json():
                    prices_map[item["symbol"]] = float(item["price"])

            for b in acc_data.get("balances", []):
                free_val = float(b["free"])
                locked_val = float(b["locked"])
                total_val = free_val + locked_val
                asset = b["asset"].upper()
                if total_val > 0.00000001:
                    # Calculate USD valuation
                    val_usd = 0.0
                    if asset in ("USDT", "USDC", "USD", "BUSD"):
                        val_usd = total_val
                    elif f"{asset}USDT" in prices_map:
                        val_usd = total_val * prices_map[f"{asset}USDT"]
                    elif f"{asset}USDC" in prices_map:
                        val_usd = total_val * prices_map[f"{asset}USDC"]
                    elif f"{asset}BTC" in prices_map and "BTCUSDT" in prices_map:
                        val_usd = total_val * prices_map[f"{asset}BTC"] * prices_map["BTCUSDT"]

                    upsert_spot_asset_snapshot({
                        "user_id": user_id,
                        "account_id": account_id,
                        "provider": "BINANCE",
                        "environment": "DEMO",
                        "asset": asset,
                        "free": free_val,
                        "locked": locked_val,
                        "total": total_val,
                        "valuation_usd": round(val_usd, 4),
                        "avg_cost_basis": 0.0
                    })
                    synced_assets += 1
                    asset_balances[asset] = total_val

        # 2. Fetch Open Orders
        ts2 = int(time.time() * 1000)
        q2 = f"timestamp={ts2}"
        sig2 = hmac.new(api_secret.encode("utf-8"), q2.encode("utf-8"), hashlib.sha256).hexdigest()
        r_open = await client.get(f"{base_url}/openOrders?{q2}&signature={sig2}", headers=headers)
        if r_open.status_code == 200:
            for o in r_open.json():
                orig_qty = float(o.get("origQty", 0.0))
                exec_qty = float(o.get("executedQty", 0.0))
                t_ms = o.get("time") or int(time.time() * 1000)
                t_utc = datetime.fromtimestamp(t_ms / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                upsert_exchange_order({
                    "internal_order_id": f"INT-BIN-{o.get('orderId')}",
                    "client_order_id": o.get("clientOrderId"),
                    "exchange_order_id": str(o.get("orderId")),
                    "user_id": user_id,
                    "account_id": account_id,
                    "provider": "BINANCE",
                    "environment": "DEMO",
                    "symbol": o.get("symbol"),
                    "display_pair": format_display_pair(o.get("symbol")),
                    "side": o.get("side"),
                    "order_type": o.get("type"),
                    "requested_price": float(o.get("price", 0.0)),
                    "avg_fill_price": 0.0,
                    "orig_qty": orig_qty,
                    "executed_qty": exec_qty,
                    "remaining_qty": max(0.0, orig_qty - exec_qty),
                    "cummulative_quote_qty": float(o.get("cummulativeQuoteQty", 0.0)),
                    "status": o.get("status"),
                    "time_in_force": o.get("timeInForce", "GTC"),
                    "verification_status": "EXCHANGE_VERIFIED",
                    "execution_type": "REAL_EXCHANGE_DEMO",
                    "is_exchange_confirmed": 1,
                    "exchange_created_at_ms": t_ms,
                    "exchange_updated_at_ms": o.get("updateTime", t_ms),
                    "created_at_utc": t_utc,
                    "raw_json": o
                })
                synced_orders += 1

        # 3. Tracked symbols for historical orders & fills
        target_symbols = set(tracked_symbols or [])
        # Always include active assets and major pairs
        default_pairs = ["BCHUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "BNBUSDT", "XRPUSDT"]
        for p in default_pairs:
            target_symbols.add(p)
        for a in asset_balances.keys():
            if a not in ("USDT", "USDC", "USD", "BUSD"):
                target_symbols.add(f"{a}USDT")

        for sym in target_symbols:
            # Query allOrders for symbol
            ts3 = int(time.time() * 1000)
            q3 = f"symbol={sym}&timestamp={ts3}"
            sig3 = hmac.new(api_secret.encode("utf-8"), q3.encode("utf-8"), hashlib.sha256).hexdigest()
            r_all = await client.get(f"{base_url}/allOrders?{q3}&signature={sig3}", headers=headers)
            
            order_trades_map = {}
            # Query myTrades for symbol
            ts4 = int(time.time() * 1000)
            q4 = f"symbol={sym}&timestamp={ts4}"
            sig4 = hmac.new(api_secret.encode("utf-8"), q4.encode("utf-8"), hashlib.sha256).hexdigest()
            r_trades = await client.get(f"{base_url}/myTrades?{q4}&signature={sig4}", headers=headers)
            
            if r_trades.status_code == 200:
                for t in r_trades.json():
                    t_order_id = str(t.get("orderId"))
                    if t_order_id not in order_trades_map:
                        order_trades_map[t_order_id] = []
                    order_trades_map[t_order_id].append(t)

                    t_ms = t.get("time") or int(time.time() * 1000)
                    t_utc = datetime.fromtimestamp(t_ms / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    fill_obj = upsert_exchange_fill({
                        "fill_id": f"FILL-BIN-{t.get('id')}",
                        "exchange_trade_id": str(t.get("id")),
                        "exchange_order_id": t_order_id,
                        "internal_order_id": f"INT-BIN-{t_order_id}",
                        "user_id": user_id,
                        "account_id": account_id,
                        "provider": "BINANCE",
                        "environment": "DEMO",
                        "symbol": sym,
                        "display_pair": format_display_pair(sym),
                        "side": "BUY" if t.get("isBuyer") else "SELL",
                        "price": float(t.get("price", 0.0)),
                        "qty": float(t.get("qty", 0.0)),
                        "quote_qty": float(t.get("quoteQty", float(t.get("price", 0.0)) * float(t.get("qty", 0.0)))),
                        "commission": float(t.get("commission", 0.0)),
                        "commission_asset": t.get("commissionAsset", "USDT"),
                        "is_buyer": 1 if t.get("isBuyer") else 0,
                        "is_maker": 1 if t.get("isMaker") else 0,
                        "trade_time_ms": t_ms,
                        "trade_time_utc": t_utc,
                        "verification_status": "EXCHANGE_VERIFIED",
                        "raw_json": t
                    })
                    synced_fills += 1

            if r_all.status_code == 200:
                for o in r_all.json():
                    o_id_str = str(o.get("orderId"))
                    trades_for_o = order_trades_map.get(o_id_str, [])
                    tot_comm = sum(float(tr.get("commission", 0.0)) for tr in trades_for_o)
                    comm_asset = trades_for_o[0].get("commissionAsset") if trades_for_o else None

                    orig_qty = float(o.get("origQty", 0.0))
                    exec_qty = float(o.get("executedQty", 0.0))
                    cum_quote = float(o.get("cummulativeQuoteQty", 0.0))
                    avg_px = (cum_quote / exec_qty) if exec_qty > 0 else float(o.get("price", 0.0))

                    t_ms = o.get("time") or int(time.time() * 1000)
                    t_utc = datetime.fromtimestamp(t_ms / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                    upsert_exchange_order({
                        "internal_order_id": f"INT-BIN-{o_id_str}",
                        "client_order_id": o.get("clientOrderId"),
                        "exchange_order_id": o_id_str,
                        "user_id": user_id,
                        "account_id": account_id,
                        "provider": "BINANCE",
                        "environment": "DEMO",
                        "symbol": o.get("symbol"),
                        "display_pair": format_display_pair(o.get("symbol")),
                        "side": o.get("side"),
                        "order_type": o.get("type"),
                        "requested_price": float(o.get("price", 0.0)),
                        "avg_fill_price": round(avg_px, 8),
                        "orig_qty": orig_qty,
                        "executed_qty": exec_qty,
                        "remaining_qty": max(0.0, orig_qty - exec_qty),
                        "cummulative_quote_qty": cum_quote,
                        "status": o.get("status"),
                        "time_in_force": o.get("timeInForce", "GTC"),
                        "commission_total": tot_comm,
                        "commission_asset": comm_asset,
                        "verification_status": "EXCHANGE_VERIFIED",
                        "execution_type": "REAL_EXCHANGE_DEMO",
                        "is_exchange_confirmed": 1,
                        "exchange_created_at_ms": t_ms,
                        "exchange_updated_at_ms": o.get("updateTime", t_ms),
                        "created_at_utc": t_utc,
                        "raw_json": o
                    })
                    synced_orders += 1

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record_audit_event(
        user_id=user_id,
        account_id=account_id,
        event_type="EXCHANGE_RECONCILED",
        lifecycle_step="RECONCILIATION_SYNC",
        message=f"Synchronized with Binance Mock Trading: {synced_orders} orders, {synced_fills} fills, {synced_assets} asset balances."
    )

    return {
        "status": "SUCCESS",
        "synced_orders": synced_orders,
        "synced_fills": synced_fills,
        "synced_assets": synced_assets,
        "last_sync_utc": now_iso
    }


def query_open_orders(user_id: str, account_id: Optional[str] = None, environment: Optional[str] = None, symbol: Optional[str] = None) -> List[dict]:
    """Retrieves genuinely working orders (NEW, PARTIALLY_FILLED)."""
    init_ledger_tables()
    query = "SELECT * FROM exchange_orders WHERE status IN ('NEW', 'PARTIALLY_FILLED')"
    params = []

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if account_id:
        query += " AND account_id = ?"
        params.append(account_id)
    if environment and environment.upper() != "ALL":
        query += " AND environment = ?"
        params.append(environment.upper())
    if symbol:
        clean_s = symbol.upper().replace("/", "").replace("-", "").strip()
        query += " AND (symbol = ? OR display_pair = ?)"
        params.extend([clean_s, symbol.upper()])

    query += " ORDER BY exchange_created_at_ms DESC, created_at_utc DESC"

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def query_order_history(
    user_id: str,
    environment: Optional[str] = None,
    exchange: Optional[str] = None,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    start_time_utc: Optional[str] = None,
    end_time_utc: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[dict], int]:
    """Retrieves permanent order instruction history with combinatorial filters."""
    init_ledger_tables()
    where = ["1=1"]
    params = []

    if user_id:
        where.append("user_id = ?")
        params.append(user_id)
    if environment and environment.upper() != "ALL":
        where.append("environment = ?")
        params.append(environment.upper())
    if exchange and exchange.upper() != "ALL":
        where.append("provider = ?")
        params.append(exchange.upper())
    if account_id and account_id.upper() != "ALL":
        where.append("account_id = ?")
        params.append(account_id)
    if symbol and symbol.upper() != "ALL":
        clean_s = symbol.upper().replace("/", "").replace("-", "").strip()
        where.append("(symbol = ? OR display_pair = ?)")
        params.extend([clean_s, symbol.upper()])
    if side and side.upper() != "ALL":
        where.append("side = ?")
        params.append(side.upper())
    if status_filter and status_filter.upper() != "ALL":
        where.append("status = ?")
        params.append(status_filter.upper())
    if start_time_utc:
        where.append("created_at_utc >= ?")
        params.append(start_time_utc)
    if end_time_utc:
        where.append("created_at_utc <= ?")
        params.append(end_time_utc)

    if search:
        s_term = search.strip()
        where.append("(exchange_order_id = ? OR client_order_id LIKE ? OR symbol LIKE ? OR display_pair LIKE ?)")
        params.extend([s_term, f"%{s_term}%", f"%{s_term}%", f"%{s_term}%"])

    where_clause = " AND ".join(where)

    with get_db_connection() as conn:
        count_row = conn.execute(f"SELECT COUNT(*) as total FROM exchange_orders WHERE {where_clause}", params).fetchone()
        total_count = count_row["total"] if count_row else 0

        paged_params = list(params) + [limit, offset]
        rows = conn.execute(
            f"SELECT * FROM exchange_orders WHERE {where_clause} ORDER BY exchange_created_at_ms DESC, created_at_utc DESC LIMIT ? OFFSET ?",
            paged_params
        ).fetchall()
        orders = [dict(r) for r in rows]

        # Attach nested fills for each order
        for o in orders:
            fills = conn.execute(
                "SELECT * FROM exchange_order_fills WHERE exchange_order_id = ? ORDER BY trade_time_ms ASC",
                (o["exchange_order_id"],)
            ).fetchall()
            o["fills"] = [dict(f) for f in fills]

        return orders, total_count


def query_trade_history(
    user_id: str,
    environment: Optional[str] = None,
    exchange: Optional[str] = None,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    search: Optional[str] = None,
    start_time_utc: Optional[str] = None,
    end_time_utc: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[dict], int]:
    """Retrieves permanent granular execution fills ledger with combinatorial filters."""
    init_ledger_tables()
    where = ["1=1"]
    params = []

    if user_id:
        where.append("user_id = ?")
        params.append(user_id)
    if environment and environment.upper() != "ALL":
        where.append("environment = ?")
        params.append(environment.upper())
    if exchange and exchange.upper() != "ALL":
        where.append("provider = ?")
        params.append(exchange.upper())
    if account_id and account_id.upper() != "ALL":
        where.append("account_id = ?")
        params.append(account_id)
    if symbol and symbol.upper() != "ALL":
        clean_s = symbol.upper().replace("/", "").replace("-", "").strip()
        where.append("(symbol = ? OR display_pair = ?)")
        params.extend([clean_s, symbol.upper()])
    if side and side.upper() != "ALL":
        where.append("side = ?")
        params.append(side.upper())
    if start_time_utc:
        where.append("trade_time_utc >= ?")
        params.append(start_time_utc)
    if end_time_utc:
        where.append("trade_time_utc <= ?")
        params.append(end_time_utc)

    if search:
        s_term = search.strip()
        where.append("(exchange_trade_id = ? OR exchange_order_id = ? OR client_order_id LIKE ? OR symbol LIKE ? OR display_pair LIKE ?)")
        params.extend([s_term, s_term, f"%{s_term}%", f"%{s_term}%", f"%{s_term}%"])

    where_clause = " AND ".join(where)

    with get_db_connection() as conn:
        count_row = conn.execute(f"SELECT COUNT(*) as total FROM exchange_order_fills WHERE {where_clause}", params).fetchone()
        total_count = count_row["total"] if count_row else 0

        paged_params = list(params) + [limit, offset]
        rows = conn.execute(
            f"SELECT * FROM exchange_order_fills WHERE {where_clause} ORDER BY trade_time_ms DESC, trade_time_utc DESC LIMIT ? OFFSET ?",
            paged_params
        ).fetchall()
        fills = [dict(r) for r in rows]

        # Calculate net wallet settlement for each fill
        for f in fills:
            base_sym = f["display_pair"].split("/")[0] if "/" in f["display_pair"] else f["symbol"].replace("USDT", "")
            quote_sym = f["display_pair"].split("/")[1] if "/" in f["display_pair"] else "USDT"
            
            qty = f["qty"]
            quote_val = f["quote_qty"]
            comm = f["commission"]
            comm_asset = f["commission_asset"]

            if f["side"] == "BUY":
                if comm_asset == base_sym:
                    net_base = qty - comm
                    f["net_impact_str"] = f"+{net_base:.8f} {base_sym} / -{quote_val:.2f} {quote_sym}"
                else:
                    f["net_impact_str"] = f"+{qty:.8f} {base_sym} / -{quote_val + comm:.2f} {quote_sym}"
            else:
                if comm_asset == quote_sym:
                    net_quote = quote_val - comm
                    f["net_impact_str"] = f"-{qty:.8f} {base_sym} / +{net_quote:.2f} {quote_sym}"
                else:
                    f["net_impact_str"] = f"-{qty + comm:.8f} {base_sym} / +{quote_val:.2f} {quote_sym}"

        return fills, total_count


def query_spot_holdings(user_id: str, account_id: Optional[str] = None, environment: Optional[str] = None) -> List[dict]:
    """Retrieves dedicated Spot Asset Holdings from verified snapshots."""
    init_ledger_tables()
    where = ["total > 0.00000001"]
    params = []

    if user_id:
        where.append("user_id = ?")
        params.append(user_id)
    if account_id and account_id.upper() != "ALL":
        where.append("account_id = ?")
        params.append(account_id)
    if environment and environment.upper() != "ALL":
        where.append("environment = ?")
        params.append(environment.upper())

    where_clause = " AND ".join(where)

    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM spot_asset_snapshots WHERE {where_clause} ORDER BY valuation_usd DESC, total DESC",
            params
        ).fetchall()
        return [dict(r) for r in rows]


def get_order_audit_dossier(user_id: str, order_id_or_client_id: str) -> Optional[dict]:
    """Retrieves complete 5-section execution audit dossier for an individual order."""
    init_ledger_tables()
    with get_db_connection() as conn:
        order_row = conn.execute(
            """SELECT * FROM exchange_orders 
               WHERE (exchange_order_id = ? OR client_order_id = ? OR internal_order_id = ?) 
               ORDER BY id DESC LIMIT 1""",
            (order_id_or_client_id, order_id_or_client_id, order_id_or_client_id)
        ).fetchone()

        if not order_row:
            return None

        order = dict(order_row)
        fills = conn.execute(
            "SELECT * FROM exchange_order_fills WHERE exchange_order_id = ? ORDER BY trade_time_ms ASC",
            (order["exchange_order_id"],)
        ).fetchall()
        order["fills"] = [dict(f) for f in fills]

        # Audit events timeline
        events = conn.execute(
            """SELECT * FROM exchange_audit_events 
               WHERE (exchange_order_id = ? OR internal_order_id = ?)
               ORDER BY id ASC""",
            (order["exchange_order_id"], order["internal_order_id"])
        ).fetchall()
        order["audit_events"] = [dict(e) for e in events]

        # Account details
        conn_row = conn.execute(
            "SELECT label, provider, environment FROM user_exchange_connections WHERE account_id = ?",
            (order["account_id"],)
        ).fetchone()
        order["account_label"] = conn_row["label"] if conn_row else order["account_id"]

        # Double-entry calculation
        base_sym = order["display_pair"].split("/")[0] if "/" in order["display_pair"] else order["symbol"].replace("USDT", "")
        quote_sym = order["display_pair"].split("/")[1] if "/" in order["display_pair"] else "USDT"
        
        orig_qty = order["orig_qty"]
        exec_qty = order["executed_qty"]
        cum_quote = order["cummulative_quote_qty"]
        comm = order["commission_total"]
        comm_asset = order["commission_asset"] or "USDT"

        if order["side"] == "BUY":
            if comm_asset == base_sym:
                order["net_settlement_base"] = f"+{(exec_qty - comm):.8f} {base_sym}"
                order["net_settlement_quote"] = f"-{cum_quote:.4f} {quote_sym}"
            else:
                order["net_settlement_base"] = f"+{exec_qty:.8f} {base_sym}"
                order["net_settlement_quote"] = f"-{(cum_quote + comm):.4f} {quote_sym}"
        else:
            order["net_settlement_base"] = f"-{exec_qty:.8f} {base_sym}"
            order["net_settlement_quote"] = f"+{(cum_quote - comm):.4f} {quote_sym}"

        return order
