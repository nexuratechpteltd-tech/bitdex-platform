"""
BITDEX Futures SQLite Database Layer & Migration Foundation (Phase 3 Enhanced)
=============================================================================
Manages tables, repeatable migrations, queries, and mutations for Binance USD(S)-M Futures.

Tables:
- futures_accounts: Isolated margin, balances, leverage caps, kill switch states
- futures_orders: Execution orders with lifecycle status, protective stop links
- futures_positions: Position tracking, mark prices, liquidation prices, realized PnL, entry fees
- futures_fills: Individual fill records from exchange acknowledgments
- futures_risk_decisions: Pre-trade risk evaluations (APPROVED / REJECTED)
- futures_realized_pnl: Realized profit and loss ledger entries with round-trip fee audit
- futures_funding_records: Funding fee receipts and debits
- futures_reconciliation_events: State mismatch audits between internal ledger and exchange
- futures_scalp_runs: Autonomous scalping bot state and lifecycle persistence
- futures_scalp_signals: Recorded market signals, scores, regimes, and rejections
- futures_scalp_trades: Scalping execution history, holding duration, and $1 net target tracking
"""

import sqlite3
import json
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


FUTURES_DDL = """
-- 1. Futures Accounts
CREATE TABLE IF NOT EXISTS futures_accounts (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    exchange_connection_id TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'testnet',
    margin_asset TEXT NOT NULL DEFAULT 'USDT',
    wallet_balance REAL NOT NULL DEFAULT 0.0,
    available_balance REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    margin_balance REAL NOT NULL DEFAULT 0.0,
    default_margin_type TEXT NOT NULL DEFAULT 'ISOLATED',
    default_leverage INTEGER NOT NULL DEFAULT 3,
    max_leverage_limit INTEGER NOT NULL DEFAULT 10,
    trading_locked INTEGER NOT NULL DEFAULT 0,
    kill_switch_active INTEGER NOT NULL DEFAULT 0,
    engine_b_enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_accounts_user ON futures_accounts(user_id);

-- 2. Futures Orders
CREATE TABLE IF NOT EXISTS futures_orders (
    order_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    client_order_id TEXT UNIQUE NOT NULL,
    exchange_order_id INTEGER,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    position_side TEXT NOT NULL DEFAULT 'BOTH',
    order_type TEXT NOT NULL,
    intent TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL,
    stop_price REAL,
    time_in_force TEXT DEFAULT 'GTC',
    reduce_only INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING_RISK',
    rejection_reason TEXT,
    risk_decision_id TEXT,
    executed_qty REAL NOT NULL DEFAULT 0.0,
    cumulative_quote_qty REAL NOT NULL DEFAULT 0.0,
    avg_fill_price REAL DEFAULT 0.0,
    is_exchange_confirmed INTEGER NOT NULL DEFAULT 0,
    protective_stop_order_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_orders_user ON futures_orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_futures_orders_coid ON futures_orders(client_order_id);
CREATE INDEX IF NOT EXISTS idx_futures_orders_symbol ON futures_orders(symbol, status);

-- 3. Futures Positions
CREATE TABLE IF NOT EXISTS futures_positions (
    position_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    position_side TEXT NOT NULL DEFAULT 'BOTH',
    margin_type TEXT NOT NULL DEFAULT 'ISOLATED',
    leverage INTEGER NOT NULL DEFAULT 3,
    quantity REAL NOT NULL DEFAULT 0.0,
    entry_price REAL NOT NULL DEFAULT 0.0,
    mark_price REAL NOT NULL DEFAULT 0.0,
    liquidation_price REAL DEFAULT 0.0,
    isolated_margin REAL NOT NULL DEFAULT 0.0,
    entry_fee_usd REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'OPEN',
    active_stop_loss_order_id TEXT,
    stop_exchange_order_id INTEGER,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_positions_user ON futures_positions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_futures_positions_sym ON futures_positions(symbol, status);

-- 4. Futures Fills
CREATE TABLE IF NOT EXISTS futures_fills (
    fill_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    exchange_trade_id INTEGER,
    exchange_order_id INTEGER,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity REAL NOT NULL,
    fee_amount REAL NOT NULL DEFAULT 0.0,
    fee_asset TEXT NOT NULL DEFAULT 'USDT',
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    is_maker INTEGER DEFAULT 0,
    trade_time_utc TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_fills_order ON futures_fills(order_id);
CREATE INDEX IF NOT EXISTS idx_futures_fills_user ON futures_fills(user_id);

-- 5. Futures Risk Decisions
CREATE TABLE IF NOT EXISTS futures_risk_decisions (
    decision_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    intent TEXT NOT NULL,
    requested_quantity REAL NOT NULL,
    requested_price REAL,
    requested_leverage INTEGER NOT NULL,
    estimated_margin_required REAL NOT NULL,
    estimated_notional REAL NOT NULL,
    available_balance REAL NOT NULL,
    decision TEXT NOT NULL,
    rejection_code TEXT,
    rejection_reason TEXT,
    risk_metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_risk_user ON futures_risk_decisions(user_id, created_at);

-- 6. Futures Realized PnL
CREATE TABLE IF NOT EXISTS futures_realized_pnl (
    pnl_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    position_id TEXT,
    closing_order_id TEXT,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    closed_qty REAL NOT NULL,
    gross_pnl_usd REAL NOT NULL,
    total_fees_usd REAL NOT NULL DEFAULT 0.0,
    net_pnl_usd REAL NOT NULL,
    funding_fee_total_usd REAL NOT NULL DEFAULT 0.0,
    source TEXT NOT NULL DEFAULT 'INTERNAL',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_realized_pnl_user ON futures_realized_pnl(user_id, symbol);

-- 7. Futures Funding Records
CREATE TABLE IF NOT EXISTS futures_funding_records (
    funding_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange_tran_id INTEGER UNIQUE,
    funding_rate REAL NOT NULL,
    position_qty_at_funding REAL NOT NULL,
    payment_amount_usd REAL NOT NULL,
    funding_time_utc TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_funding_user ON futures_funding_records(user_id, symbol);

-- 8. Futures Reconciliation Events
CREATE TABLE IF NOT EXISTS futures_reconciliation_events (
    event_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    symbol TEXT,
    internal_value TEXT,
    exchange_value TEXT,
    discrepancy_details_json TEXT NOT NULL DEFAULT '{}',
    resolution_status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_recon_user ON futures_reconciliation_events(user_id, resolution_status);

-- 9. Futures Scalp Runs
CREATE TABLE IF NOT EXISTS futures_scalp_runs (
    run_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL DEFAULT 'SCALP_ONE_DOLLAR',
    status TEXT NOT NULL DEFAULT 'IDLE',
    state_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_scalp_runs_user ON futures_scalp_runs(user_id, status);

-- 10. Futures Scalp Signals
CREATE TABLE IF NOT EXISTS futures_scalp_signals (
    signal_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    market_price REAL NOT NULL,
    entry_price REAL NOT NULL,
    stop_price REAL NOT NULL,
    target_exit_price REAL NOT NULL,
    expected_gross_pnl REAL NOT NULL,
    estimated_fees REAL NOT NULL,
    expected_net_pnl REAL NOT NULL,
    signal_score REAL NOT NULL,
    regime TEXT NOT NULL,
    status TEXT NOT NULL,
    rejection_reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_scalp_signals_user ON futures_scalp_signals(user_id, symbol, created_at);

-- 11. Futures Scalp Trades
CREATE TABLE IF NOT EXISTS futures_scalp_trades (
    trade_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL DEFAULT 'SCALP_ONE_DOLLAR',
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_order_id TEXT NOT NULL,
    exit_order_id TEXT,
    protective_stop_order_id TEXT,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    holding_duration_seconds REAL,
    exit_reason TEXT,
    gross_pnl_usd REAL,
    total_fees_usd REAL,
    net_pnl_usd REAL,
    target_hit INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_futures_scalp_trades_user ON futures_scalp_trades(user_id, symbol, created_at);

CREATE TABLE IF NOT EXISTS futures_strategy_configs (
    config_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'AUTO',
    margin_allocation_usd REAL NOT NULL DEFAULT 50.0,
    leverage INTEGER NOT NULL DEFAULT 3,
    net_profit_target_pct REAL NOT NULL DEFAULT 0.6,
    max_loss_pct REAL NOT NULL DEFAULT 0.9,
    max_holding_duration_seconds INTEGER NOT NULL DEFAULT 900,
    session_mode TEXT NOT NULL DEFAULT 'SINGLE_CYCLE',
    daily_loss_limit_usd REAL NOT NULL DEFAULT 20.0,
    max_daily_trades INTEGER NOT NULL DEFAULT 10,
    status TEXT NOT NULL DEFAULT 'CONFIGURED',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fsc_user_symbol ON futures_strategy_configs(user_id, symbol);

"""


def apply_futures_migrations(conn: sqlite3.Connection):
    """Apply all Futures DDL schemas to SQLite database with idempotent column migrations."""
    conn.executescript(FUTURES_DDL)
    
    # Idempotent column additions for existing installations
    pos_cols = [r[1] for r in conn.execute("PRAGMA table_info(futures_positions)").fetchall()]
    if "entry_fee_usd" not in pos_cols:
        conn.execute("ALTER TABLE futures_positions ADD COLUMN entry_fee_usd REAL NOT NULL DEFAULT 0.0")
    if "stop_exchange_order_id" not in pos_cols:
        conn.execute("ALTER TABLE futures_positions ADD COLUMN stop_exchange_order_id INTEGER")
        
    acc_cols = [r[1] for r in conn.execute("PRAGMA table_info(futures_accounts)").fetchall()]
    if "engine_b_enabled" not in acc_cols:
        conn.execute("ALTER TABLE futures_accounts ADD COLUMN engine_b_enabled INTEGER NOT NULL DEFAULT 0")
        
    conn.commit()


# ─────────────────────────────────────────────────────────────
# Account Management
# ─────────────────────────────────────────────────────────────

def get_or_create_futures_account(
    conn: sqlite3.Connection,
    user_id: str,
    exchange_connection_id: str,
    environment: str = "testnet",
    initial_balance: float = 1000.0,
    default_leverage: int = 3,
) -> Dict[str, Any]:
    """Retrieve or initialize a futures account for a customer."""
    row = conn.execute(
        "SELECT * FROM futures_accounts WHERE user_id = ? AND environment = ?",
        (user_id, environment)
    ).fetchone()
    
    if row:
        return dict(row)
    
    account_id = f"FACC-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_accounts (
            account_id, user_id, exchange_connection_id, environment,
            margin_asset, wallet_balance, available_balance, unrealized_pnl,
            margin_balance, default_margin_type, default_leverage, max_leverage_limit,
            trading_locked, kill_switch_active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'USDT', ?, ?, 0.0, ?, 'ISOLATED', ?, 10, 0, 0, ?, ?)""",
        (account_id, user_id, exchange_connection_id, environment,
         initial_balance, initial_balance, initial_balance, default_leverage, now, now)
    )
    conn.commit()
    
    new_row = conn.execute("SELECT * FROM futures_accounts WHERE account_id = ?", (account_id,)).fetchone()
    return dict(new_row)


def get_futures_account(conn: sqlite3.Connection, user_id: str, account_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve futures account enforcing tenant isolation."""
    if account_id:
        row = conn.execute(
            "SELECT * FROM futures_accounts WHERE user_id = ? AND account_id = ?",
            (user_id, account_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM futures_accounts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()
    return dict(row) if row else None


def update_futures_account_balances(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    wallet_balance: float,
    available_balance: float,
    unrealized_pnl: float = 0.0,
    margin_balance: Optional[float] = None,
):
    """Update balances after fills or reconciliation."""
    if margin_balance is None:
        margin_balance = wallet_balance + unrealized_pnl
    now = utc_now_iso()
    conn.execute(
        """UPDATE futures_accounts 
           SET wallet_balance = ?, available_balance = ?, unrealized_pnl = ?, margin_balance = ?, updated_at = ?
           WHERE user_id = ? AND account_id = ?""",
        (wallet_balance, available_balance, unrealized_pnl, margin_balance, now, user_id, account_id)
    )
    conn.commit()


def set_futures_kill_switch(conn: sqlite3.Connection, user_id: str, account_id: str, active: bool):
    """Enable or disable emergency kill switch."""
    now = utc_now_iso()
    val = 1 if active else 0
    conn.execute(
        "UPDATE futures_accounts SET kill_switch_active = ?, updated_at = ? WHERE user_id = ? AND account_id = ?",
        (val, now, user_id, account_id)
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────
# Orders Management
# ─────────────────────────────────────────────────────────────

def create_futures_order(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    client_order_id: str,
    symbol: str,
    side: str,
    order_type: str,
    intent: str,
    quantity: float,
    price: Optional[float] = None,
    stop_price: Optional[float] = None,
    time_in_force: str = "GTC",
    reduce_only: bool = False,
    position_side: str = "BOTH",
    status: str = "PENDING_RISK",
    risk_decision_id: Optional[str] = None
) -> Dict[str, Any]:
    """Insert an order record with initial state."""
    order_id = f"FORD-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_orders (
            order_id, user_id, account_id, client_order_id,
            symbol, side, position_side, order_type, intent,
            quantity, price, stop_price, time_in_force, reduce_only,
            status, risk_decision_id, executed_qty, cumulative_quote_qty,
            avg_fill_price, is_exchange_confirmed, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 0, ?, ?)""",
        (order_id, user_id, account_id, client_order_id,
         symbol.upper(), side.upper(), position_side.upper(), order_type.upper(), intent.upper(),
         quantity, price, stop_price, time_in_force, 1 if reduce_only else 0,
         status, risk_decision_id, now, now)
    )
    conn.commit()
    return get_futures_order(conn, user_id, order_id=order_id)


def get_futures_order(
    conn: sqlite3.Connection,
    user_id: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Retrieve an order enforcing user isolation."""
    if order_id:
        row = conn.execute(
            "SELECT * FROM futures_orders WHERE user_id = ? AND order_id = ?",
            (user_id, order_id)
        ).fetchone()
    elif client_order_id:
        row = conn.execute(
            "SELECT * FROM futures_orders WHERE user_id = ? AND client_order_id = ?",
            (user_id, client_order_id)
        ).fetchone()
    else:
        return None
    return dict(row) if row else None


def update_futures_order_status(
    conn: sqlite3.Connection,
    user_id: str,
    order_id: str,
    status: str,
    exchange_order_id: Optional[int] = None,
    executed_qty: Optional[float] = None,
    cumulative_quote_qty: Optional[float] = None,
    avg_fill_price: Optional[float] = None,
    rejection_reason: Optional[str] = None,
    is_exchange_confirmed: Optional[bool] = None,
    protective_stop_order_id: Optional[str] = None,
):
    """Update order lifecycle status."""
    now = utc_now_iso()
    updates = ["status = ?", "updated_at = ?"]
    params = [status, now]
    
    if exchange_order_id is not None:
        updates.append("exchange_order_id = ?")
        params.append(exchange_order_id)
    if executed_qty is not None:
        updates.append("executed_qty = ?")
        params.append(executed_qty)
    if cumulative_quote_qty is not None:
        updates.append("cumulative_quote_qty = ?")
        params.append(cumulative_quote_qty)
    if avg_fill_price is not None:
        updates.append("avg_fill_price = ?")
        params.append(avg_fill_price)
    if rejection_reason is not None:
        updates.append("rejection_reason = ?")
        params.append(rejection_reason)
    if is_exchange_confirmed is not None:
        updates.append("is_exchange_confirmed = ?")
        params.append(1 if is_exchange_confirmed else 0)
    if protective_stop_order_id is not None:
        updates.append("protective_stop_order_id = ?")
        params.append(protective_stop_order_id)

    params.extend([user_id, order_id])
    sql = f"UPDATE futures_orders SET {', '.join(updates)} WHERE user_id = ? AND order_id = ?"
    conn.execute(sql, tuple(params))
    conn.commit()


# ─────────────────────────────────────────────────────────────
# Positions Management
# ─────────────────────────────────────────────────────────────

def get_open_futures_position(
    conn: sqlite3.Connection,
    user_id: str,
    symbol: str,
    position_side: str = "BOTH"
) -> Optional[Dict[str, Any]]:
    """Retrieve active open position for symbol."""
    row = conn.execute(
        """SELECT * FROM futures_positions 
           WHERE user_id = ? AND symbol = ? AND position_side = ? AND status = 'OPEN'""",
        (user_id, symbol.upper(), position_side.upper())
    ).fetchone()
    return dict(row) if row else None


def list_open_futures_positions(conn: sqlite3.Connection, user_id: str) -> List[Dict[str, Any]]:
    """List all open positions for a tenant."""
    rows = conn.execute(
        "SELECT * FROM futures_positions WHERE user_id = ? AND status = 'OPEN' ORDER BY opened_at DESC",
        (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_futures_position(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    symbol: str,
    quantity: float,
    entry_price: float,
    mark_price: float,
    leverage: int,
    isolated_margin: float,
    liquidation_price: float = 0.0,
    unrealized_pnl: float = 0.0,
    position_side: str = "BOTH",
    active_stop_loss_order_id: Optional[str] = None,
    stop_exchange_order_id: Optional[int] = None,
    entry_fee_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """Create or update position state with entry commission persistence."""
    sym = symbol.upper()
    pside = position_side.upper()
    now = utc_now_iso()
    existing = get_open_futures_position(conn, user_id, sym, pside)
    
    if existing:
        pos_id = existing["position_id"]
        # If position is closed (quantity drops to 0)
        if abs(quantity) < 1e-8:
            conn.execute(
                """UPDATE futures_positions 
                   SET quantity = 0.0, status = 'CLOSED', closed_at = ?, updated_at = ?
                   WHERE user_id = ? AND position_id = ?""",
                (now, now, user_id, pos_id)
            )
        else:
            updates = [
                "quantity = ?", "entry_price = ?", "mark_price = ?", "leverage = ?",
                "isolated_margin = ?", "liquidation_price = ?", "unrealized_pnl = ?", "updated_at = ?"
            ]
            params = [quantity, entry_price, mark_price, leverage, isolated_margin, liquidation_price, unrealized_pnl, now]
            if active_stop_loss_order_id is not None:
                updates.append("active_stop_loss_order_id = ?")
                params.append(active_stop_loss_order_id)
            if stop_exchange_order_id is not None:
                updates.append("stop_exchange_order_id = ?")
                params.append(stop_exchange_order_id)
            if entry_fee_usd is not None:
                updates.append("entry_fee_usd = ?")
                params.append(entry_fee_usd)
            params.extend([user_id, pos_id])
            conn.execute(f"UPDATE futures_positions SET {', '.join(updates)} WHERE user_id = ? AND position_id = ?", tuple(params))
        conn.commit()
        row = conn.execute("SELECT * FROM futures_positions WHERE position_id = ?", (pos_id,)).fetchone()
        return dict(row) if row else {}
    else:
        if abs(quantity) < 1e-8:
            return {}
        pos_id = f"FPOS-{secrets.token_hex(6).upper()}"
        fee_init = entry_fee_usd if entry_fee_usd is not None else 0.0
        conn.execute(
            """INSERT INTO futures_positions (
                position_id, user_id, account_id, symbol, position_side,
                margin_type, leverage, quantity, entry_price, mark_price,
                liquidation_price, isolated_margin, entry_fee_usd, unrealized_pnl, realized_pnl,
                status, active_stop_loss_order_id, stop_exchange_order_id, opened_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'ISOLATED', ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 'OPEN', ?, ?, ?, ?)""",
            (pos_id, user_id, account_id, sym, pside, leverage, quantity, entry_price,
             mark_price, liquidation_price, isolated_margin, fee_init,
             active_stop_loss_order_id, stop_exchange_order_id, now, now)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM futures_positions WHERE position_id = ?", (pos_id,)).fetchone()
        return dict(row) if row else {}


# ─────────────────────────────────────────────────────────────
# Fills & Realized PnL Management
# ─────────────────────────────────────────────────────────────

def record_futures_fill(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    order_id: str,
    client_order_id: str,
    symbol: str,
    side: str,
    price: float,
    quantity: float,
    fee_amount: float = 0.0,
    fee_asset: str = "USDT",
    realized_pnl: float = 0.0,
    exchange_trade_id: Optional[int] = None,
    exchange_order_id: Optional[int] = None,
    is_maker: bool = False,
    trade_time_utc: Optional[str] = None
) -> Dict[str, Any]:
    """Record an executed fill."""
    fill_id = f"FILL-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    trade_time = trade_time_utc or now
    conn.execute(
        """INSERT INTO futures_fills (
            fill_id, user_id, account_id, order_id, client_order_id,
            exchange_trade_id, exchange_order_id, symbol, side,
            price, quantity, fee_amount, fee_asset, realized_pnl,
            is_maker, trade_time_utc, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fill_id, user_id, account_id, order_id, client_order_id,
         exchange_trade_id, exchange_order_id, symbol.upper(), side.upper(),
         price, quantity, fee_amount, fee_asset, realized_pnl,
         1 if is_maker else 0, trade_time, now)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM futures_fills WHERE fill_id = ?", (fill_id,)).fetchone()
    return dict(row)


def record_realized_pnl(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    symbol: str,
    entry_price: float,
    exit_price: float,
    closed_qty: float,
    gross_pnl_usd: float,
    total_fees_usd: float,
    net_pnl_usd: float,
    position_id: Optional[str] = None,
    closing_order_id: Optional[str] = None,
    funding_fee_total_usd: float = 0.0,
    source: str = "INTERNAL"
) -> Dict[str, Any]:
    """Durable record of closed trade PnL with round-trip fee audit."""
    pnl_id = f"PNL-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_realized_pnl (
            pnl_id, user_id, account_id, symbol, position_id, closing_order_id,
            entry_price, exit_price, closed_qty, gross_pnl_usd, total_fees_usd,
            net_pnl_usd, funding_fee_total_usd, source, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pnl_id, user_id, account_id, symbol.upper(), position_id, closing_order_id,
         entry_price, exit_price, closed_qty, gross_pnl_usd, total_fees_usd,
         net_pnl_usd, funding_fee_total_usd, source, now)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM futures_realized_pnl WHERE pnl_id = ?", (pnl_id,)).fetchone()
    return dict(row)


# ─────────────────────────────────────────────────────────────
# Risk Decision Auditing
# ─────────────────────────────────────────────────────────────

def record_risk_decision(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    client_order_id: str,
    symbol: str,
    side: str,
    intent: str,
    requested_quantity: float,
    requested_price: Optional[float],
    requested_leverage: int,
    estimated_margin_required: float,
    estimated_notional: float,
    available_balance: float,
    decision: str,
    rejection_code: Optional[str] = None,
    rejection_reason: Optional[str] = None,
    risk_metrics: Optional[Dict[str, Any]] = None
) -> str:
    """Record an audit entry for pre-trade risk evaluation."""
    decision_id = f"RSK-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_risk_decisions (
            decision_id, user_id, account_id, client_order_id,
            symbol, side, intent, requested_quantity, requested_price,
            requested_leverage, estimated_margin_required, estimated_notional,
            available_balance, decision, rejection_code, rejection_reason,
            risk_metrics_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (decision_id, user_id, account_id, client_order_id,
         symbol.upper(), side.upper(), intent.upper(), requested_quantity, requested_price,
         requested_leverage, estimated_margin_required, estimated_notional,
         available_balance, decision.upper(), rejection_code, rejection_reason,
         json.dumps(risk_metrics or {}), now)
    )
    conn.commit()
    return decision_id


# ─────────────────────────────────────────────────────────────
# Funding & Reconciliation
# ─────────────────────────────────────────────────────────────

def record_funding_payment(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    symbol: str,
    funding_rate: float,
    position_qty_at_funding: float,
    payment_amount_usd: float,
    exchange_tran_id: Optional[int] = None,
    funding_time_utc: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Store funding fee credit/debit. Avoids duplicate processing via exchange_tran_id."""
    now = utc_now_iso()
    funding_id = f"FND-{secrets.token_hex(6).upper()}"
    ftime = funding_time_utc or now
    try:
        conn.execute(
            """INSERT INTO futures_funding_records (
                funding_id, user_id, account_id, symbol, exchange_tran_id,
                funding_rate, position_qty_at_funding, payment_amount_usd,
                funding_time_utc, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (funding_id, user_id, account_id, symbol.upper(), exchange_tran_id,
             funding_rate, position_qty_at_funding, payment_amount_usd, ftime, now)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM futures_funding_records WHERE funding_id = ?", (funding_id,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        return None


def record_reconciliation_event(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    event_type: str,
    severity: str,
    symbol: Optional[str] = None,
    internal_value: Optional[str] = None,
    exchange_value: Optional[str] = None,
    discrepancy_details: Optional[Dict[str, Any]] = None
) -> str:
    """Log an audit event whenever reconciliation encounters a mismatch."""
    event_id = f"RCN-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_reconciliation_events (
            event_id, user_id, account_id, event_type, severity,
            symbol, internal_value, exchange_value, discrepancy_details_json,
            resolution_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
        (event_id, user_id, account_id, event_type.upper(), severity.upper(),
         symbol.upper() if symbol else None, internal_value, exchange_value,
         json.dumps(discrepancy_details or {}), now)
    )
    conn.commit()
    return event_id


# ─────────────────────────────────────────────────────────────
# Scalp Runs, Signals & Trades Management
# ─────────────────────────────────────────────────────────────

def get_or_create_scalp_run(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    strategy_name: str = "SCALP_ONE_DOLLAR",
) -> Dict[str, Any]:
    """Retrieve or initialize an autonomous scalping run."""
    row = conn.execute(
        "SELECT * FROM futures_scalp_runs WHERE user_id = ? AND strategy_name = ?",
        (user_id, strategy_name)
    ).fetchone()
    if row:
        return dict(row)
        
    run_id = f"RUN-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_scalp_runs (
            run_id, user_id, account_id, strategy_name, status, state_json, started_at, updated_at
        ) VALUES (?, ?, ?, ?, 'IDLE', '{}', ?, ?)""",
        (run_id, user_id, account_id, strategy_name, now, now)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM futures_scalp_runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row)


def update_scalp_run_state(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    state_dict: Dict[str, Any],
    stopped_at: Optional[str] = None
):
    """Update running state of the scalper."""
    now = utc_now_iso()
    if stopped_at:
        conn.execute(
            "UPDATE futures_scalp_runs SET status = ?, state_json = ?, stopped_at = ?, updated_at = ? WHERE run_id = ?",
            (status, json.dumps(state_dict), stopped_at, now, run_id)
        )
    else:
        conn.execute(
            "UPDATE futures_scalp_runs SET status = ?, state_json = ?, updated_at = ? WHERE run_id = ?",
            (status, json.dumps(state_dict), now, run_id)
        )
    conn.commit()


def record_scalp_signal(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    symbol: str,
    direction: str,
    market_price: float,
    entry_price: float,
    stop_price: float,
    target_exit_price: float,
    expected_gross_pnl: float,
    estimated_fees: float,
    expected_net_pnl: float,
    signal_score: float,
    regime: str,
    status: str,
    rejection_reason: Optional[str] = None
) -> Dict[str, Any]:
    """Record generated scalp candidate signals."""
    signal_id = f"SIG-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_scalp_signals (
            signal_id, user_id, account_id, symbol, direction,
            market_price, entry_price, stop_price, target_exit_price,
            expected_gross_pnl, estimated_fees, expected_net_pnl,
            signal_score, regime, status, rejection_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (signal_id, user_id, account_id, symbol.upper(), direction.upper(),
         market_price, entry_price, stop_price, target_exit_price,
         expected_gross_pnl, estimated_fees, expected_net_pnl,
         signal_score, regime.upper(), status.upper(), rejection_reason, now)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM futures_scalp_signals WHERE signal_id = ?", (signal_id,)).fetchone()
    return dict(row)


def record_scalp_trade(
    conn: sqlite3.Connection,
    user_id: str,
    account_id: str,
    symbol: str,
    direction: str,
    entry_order_id: str,
    quantity: float,
    entry_price: float,
    protective_stop_order_id: Optional[str] = None,
    strategy_name: str = "SCALP_ONE_DOLLAR"
) -> Dict[str, Any]:
    """Record an opened scalping trade."""
    trade_id = f"SCLP-{secrets.token_hex(6).upper()}"
    now = utc_now_iso()
    conn.execute(
        """INSERT INTO futures_scalp_trades (
            trade_id, user_id, account_id, strategy_name, symbol, direction,
            entry_order_id, protective_stop_order_id, quantity, entry_price,
            entry_time, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trade_id, user_id, account_id, strategy_name, symbol.upper(), direction.upper(),
         entry_order_id, protective_stop_order_id, quantity, entry_price, now, now)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM futures_scalp_trades WHERE trade_id = ?", (trade_id,)).fetchone()
    return dict(row)


def complete_scalp_trade(
    conn: sqlite3.Connection,
    trade_id: str,
    exit_order_id: str,
    exit_price: float,
    exit_reason: str,
    gross_pnl_usd: float,
    total_fees_usd: float,
    net_pnl_usd: float,
    target_hit: bool,
    holding_duration_seconds: float
) -> Dict[str, Any]:
    """Complete a scalping trade with actual accounting and target-hit verification."""
    now = utc_now_iso()
    conn.execute(
        """UPDATE futures_scalp_trades 
           SET exit_order_id = ?, exit_price = ?, exit_time = ?,
               holding_duration_seconds = ?, exit_reason = ?,
               gross_pnl_usd = ?, total_fees_usd = ?, net_pnl_usd = ?,
               target_hit = ?
           WHERE trade_id = ?""",
        (exit_order_id, exit_price, now, holding_duration_seconds, exit_reason,
         gross_pnl_usd, total_fees_usd, net_pnl_usd, 1 if target_hit else 0, trade_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM futures_scalp_trades WHERE trade_id = ?", (trade_id,)).fetchone()
    return dict(row)



# ─────────────────────────────────────────────────────────────
# Strategy Configuration Management
# ─────────────────────────────────────────────────────────────

def upsert_futures_strategy_config(
    conn: sqlite3.Connection,
    user_id: str,
    symbol: str,
    direction: str = "AUTO",
    margin_allocation_usd: float = 50.0,
    leverage: int = 3,
    net_profit_target_pct: float = 0.6,
    max_loss_pct: float = 0.9,
    max_holding_duration_seconds: int = 900,
    session_mode: str = "SINGLE_CYCLE",
    daily_loss_limit_usd: float = 20.0,
    max_daily_trades: int = 10,
    status: str = "CONFIGURED",
) -> Dict[str, Any]:
    """Persist or update customer HFT strategy configuration."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_symbol = symbol.upper().replace("/", "").replace(":", "").replace("-", "")
    config_id = f"CFG-{user_id[:8]}-{clean_symbol}"

    conn.execute(
        """
        INSERT INTO futures_strategy_configs (
            config_id, user_id, symbol, direction, margin_allocation_usd,
            leverage, net_profit_target_pct, max_loss_pct, max_holding_duration_seconds,
            session_mode, daily_loss_limit_usd, max_daily_trades, status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(config_id) DO UPDATE SET
            direction = excluded.direction,
            margin_allocation_usd = excluded.margin_allocation_usd,
            leverage = excluded.leverage,
            net_profit_target_pct = excluded.net_profit_target_pct,
            max_loss_pct = excluded.max_loss_pct,
            max_holding_duration_seconds = excluded.max_holding_duration_seconds,
            session_mode = excluded.session_mode,
            daily_loss_limit_usd = excluded.daily_loss_limit_usd,
            max_daily_trades = excluded.max_daily_trades,
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        (
            config_id, user_id, clean_symbol, direction, margin_allocation_usd,
            leverage, net_profit_target_pct, max_loss_pct, max_holding_duration_seconds,
            session_mode, daily_loss_limit_usd, max_daily_trades, status,
            now, now
        )
    )
    conn.commit()
    row = conn.execute("SELECT * FROM futures_strategy_configs WHERE config_id = ?", (config_id,)).fetchone()
    return dict(row) if row else {}


def get_futures_strategy_config(
    conn: sqlite3.Connection,
    user_id: str,
    symbol: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Retrieve persisted customer HFT strategy configuration."""
    if symbol:
        clean_symbol = symbol.upper().replace("/", "").replace(":", "").replace("-", "")
        row = conn.execute(
            "SELECT * FROM futures_strategy_configs WHERE user_id = ? AND symbol = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id, clean_symbol)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM futures_strategy_configs WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()
    return dict(row) if row else None
