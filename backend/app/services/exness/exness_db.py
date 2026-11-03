"""
Exness Database Migration and Data Layer (Hardened Phase 2.1)
Additive schema definitions, local position tracking, and atomic key rotation for Exness MT5 HFT.
Specification reference: Master Exness HFT Implementation Specification, Part 8.
"""

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from .vault import ExnessCredentialVault

logger = logging.getLogger("bitdex.exness.db")

EXNESS_DDL_STATEMENTS = [
    # 1. Exness Demo Connections
    """
    CREATE TABLE IF NOT EXISTS exness_demo_connections (
        connection_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        account_login TEXT NOT NULL,
        server_name TEXT NOT NULL,
        account_type TEXT DEFAULT 'DEMO',
        encrypted_credentials TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        is_read_only INTEGER DEFAULT 0,
        balance_usd REAL DEFAULT 5000.0,
        equity_usd REAL DEFAULT 5000.0,
        leverage INTEGER DEFAULT 2000,
        currency TEXT DEFAULT 'USD',
        last_reconciled_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    );
    """,
    # 2. Exness Discovered Instruments
    """
    CREATE TABLE IF NOT EXISTS exness_discovered_instruments (
        instrument_id TEXT PRIMARY KEY,
        connection_id TEXT NOT NULL,
        broker_symbol TEXT NOT NULL,
        canonical_symbol TEXT NOT NULL,
        product_type TEXT NOT NULL,
        contract_size REAL NOT NULL,
        min_volume REAL NOT NULL,
        max_volume REAL NOT NULL,
        volume_step REAL NOT NULL,
        tick_size REAL NOT NULL,
        tick_value REAL NOT NULL,
        spread_typical REAL,
        commission_per_lot REAL DEFAULT 0.0,
        swap_long REAL DEFAULT 0.0,
        swap_short REAL DEFAULT 0.0,
        margin_initial REAL NOT NULL,
        is_tradable INTEGER DEFAULT 1,
        eligibility_status TEXT DEFAULT 'PENDING_GATES',
        blocked_reason TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(connection_id) REFERENCES exness_demo_connections(connection_id)
    );
    """,
    # 3. Exness HFT Baskets
    """
    CREATE TABLE IF NOT EXISTS exness_hft_baskets (
        basket_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        connection_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        regime_at_entry TEXT,
        status TEXT NOT NULL,
        buy_ticket TEXT,
        sell_ticket TEXT,
        lot_size REAL NOT NULL,
        target_profit_usd REAL NOT NULL,
        hard_stop_loss_usd REAL NOT NULL,
        realized_pnl_usd REAL DEFAULT 0.0,
        unrealized_pnl_usd REAL DEFAULT 0.0,
        commissions_usd REAL DEFAULT 0.0,
        swap_usd REAL DEFAULT 0.0,
        net_basket_pnl_usd REAL DEFAULT 0.0,
        opened_at TEXT NOT NULL,
        closed_at TEXT,
        holding_seconds INTEGER DEFAULT 0,
        closure_reason TEXT,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(connection_id) REFERENCES exness_demo_connections(connection_id)
    );
    """,
    # 4. Exness HFT Orders and Legs
    """
    CREATE TABLE IF NOT EXISTS exness_hft_orders_and_legs (
        leg_id TEXT PRIMARY KEY,
        basket_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        broker_ticket TEXT,
        order_side TEXT NOT NULL,
        order_type TEXT NOT NULL,
        volume REAL NOT NULL,
        requested_price REAL,
        fill_price REAL,
        stop_loss REAL,
        take_profit REAL,
        broker_stop_confirmed INTEGER DEFAULT 0,
        commission REAL DEFAULT 0.0,
        status TEXT NOT NULL,
        idempotency_key TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL,
        closed_at TEXT,
        FOREIGN KEY(basket_id) REFERENCES exness_hft_baskets(basket_id),
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    );
    """,
    # 5. Exness HFT Execution Events
    """
    CREATE TABLE IF NOT EXISTS exness_hft_execution_events (
        event_id TEXT PRIMARY KEY,
        basket_id TEXT,
        user_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    );
    """,
    # 6. Exness HFT Reconciliation Logs
    """
    CREATE TABLE IF NOT EXISTS exness_hft_reconciliation_logs (
        log_id TEXT PRIMARY KEY,
        connection_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        discrepancy_count INTEGER DEFAULT 0,
        broker_positions_count INTEGER DEFAULT 0,
        local_positions_count INTEGER DEFAULT 0,
        details_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(connection_id) REFERENCES exness_demo_connections(connection_id),
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    );
    """,
    # 7. Exness HFT Risk Events
    """
    CREATE TABLE IF NOT EXISTS exness_hft_risk_events (
        risk_event_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        connection_id TEXT NOT NULL,
        rule_breached TEXT NOT NULL,
        action_taken TEXT NOT NULL,
        details_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(connection_id) REFERENCES exness_demo_connections(connection_id)
    );
    """,
]

EXNESS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_exness_conn_user ON exness_demo_connections(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_exness_inst_conn ON exness_discovered_instruments(connection_id);",
    "CREATE INDEX IF NOT EXISTS idx_exness_basket_user ON exness_hft_baskets(user_id, status);",
    "CREATE INDEX IF NOT EXISTS idx_exness_legs_basket ON exness_hft_orders_and_legs(basket_id);",
    "CREATE INDEX IF NOT EXISTS idx_exness_events_user ON exness_hft_execution_events(user_id, created_at);",
]


def apply_exness_migrations(conn: sqlite3.Connection) -> None:
    """Applies all additive Exness tables and indexes."""
    with conn:
        for stmt in EXNESS_DDL_STATEMENTS:
            conn.execute(stmt)
        for idx in EXNESS_INDEXES:
            conn.execute(idx)
    logger.info("Successfully verified and applied additive Exness schema migrations.")


def get_user_exness_connection(conn: sqlite3.Connection, user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves the active Exness connection for a user."""
    row = conn.execute(
        "SELECT * FROM exness_demo_connections WHERE user_id = ? AND is_active = 1 LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def save_exness_connection(
    conn: sqlite3.Connection,
    user_id: str,
    login: str,
    server: str,
    enc_credentials: Dict[str, str],
    balance: float = 5000.0,
    equity: float = 5000.0,
    leverage: int = 2000,
) -> str:
    """Creates or updates an Exness demo connection."""
    conn_id = f"EXN-CONN-{secrets.token_hex(6).upper()}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with conn:
        conn.execute("UPDATE exness_demo_connections SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.execute(
            """
            INSERT INTO exness_demo_connections (
                connection_id, user_id, account_login, server_name, account_type,
                encrypted_credentials, is_active, is_read_only, balance_usd, equity_usd,
                leverage, currency, last_reconciled_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'DEMO', ?, 1, 0, ?, ?, ?, 'USD', ?, ?, ?)
            """,
            (
                conn_id,
                user_id,
                login,
                server,
                json.dumps(enc_credentials),
                balance,
                equity,
                leverage,
                now,
                now,
                now,
            ),
        )
    return conn_id


def get_active_local_positions(conn: sqlite3.Connection, user_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves active local open orders/legs from database for independent reconciliation.
    Never assumes broker state matches local state.
    """
    rows = conn.execute(
        """
        SELECT leg_id, basket_id, user_id, broker_ticket, order_side, order_type,
               volume, fill_price, stop_loss, take_profit, broker_stop_confirmed,
               commission, status, created_at
        FROM exness_hft_orders_and_legs
        WHERE user_id = ? AND status = 'FILLED' AND closed_at IS NULL
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def log_reconciliation(
    conn: sqlite3.Connection,
    connection_id: str,
    user_id: str,
    discrepancy_count: int,
    broker_count: int,
    local_count: int,
    details: Dict[str, Any],
) -> str:
    """
    Authoritative reconciliation logger.
    Accurately records separate broker_count and local_count without self-comparison.
    """
    log_id = f"REC-{secrets.token_hex(6).upper()}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:
        conn.execute(
            """
            INSERT INTO exness_hft_reconciliation_logs (
                log_id, connection_id, user_id, discrepancy_count,
                broker_positions_count, local_positions_count, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                connection_id,
                user_id,
                discrepancy_count,
                broker_count,
                local_count,
                json.dumps(details),
                now,
            ),
        )
        conn.execute(
            "UPDATE exness_demo_connections SET last_reconciled_at = ? WHERE connection_id = ?",
            (now, connection_id),
        )
    return log_id


def rotate_database_vault_keys(
    conn: sqlite3.Connection,
    old_key_hex: str,
    new_key_hex: str,
) -> int:
    """
    Atomically rotates the AES-256-GCM vault encryption key for all stored credentials in database.
    Operates within a single transaction to guarantee zero data loss.
    Returns the count of successfully rotated connection credentials.
    """
    old_key = bytes.fromhex(old_key_hex.strip())
    new_key = bytes.fromhex(new_key_hex.strip())
    if len(old_key) != 32 or len(new_key) != 32:
        raise ValueError("Both old_key and new_key must be exactly 32 bytes.")

    rows = conn.execute(
        "SELECT connection_id, user_id, account_login, server_name, encrypted_credentials FROM exness_demo_connections"
    ).fetchall()

    rotated_count = 0
    with conn:
        for r in rows:
            enc_creds = json.loads(r["encrypted_credentials"])
            new_payload = ExnessCredentialVault.rotate_credentials(
                user_id=r["user_id"],
                login=r["account_login"],
                server=r["server_name"],
                enc_payload=enc_creds,
                current_key=old_key,
                new_key=new_key,
            )
            conn.execute(
                "UPDATE exness_demo_connections SET encrypted_credentials = ?, updated_at = ? WHERE connection_id = ?",
                (
                    json.dumps(new_payload),
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    r["connection_id"],
                ),
            )
            rotated_count += 1

    logger.info(f"Successfully rotated vault encryption key for {rotated_count} stored connections.")
    return rotated_count
