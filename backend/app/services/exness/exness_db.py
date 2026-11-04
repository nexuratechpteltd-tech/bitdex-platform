"""
Exness Database Migration and Data Layer (Hardened Phase 2.2)
Additive schema definitions, adapter persistence, and safe key rotation/rollback.
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
        adapter_mode TEXT DEFAULT 'DETERMINISTIC_MOCK_DEMO',
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
    # 8. Exness Payments API Customer Transfers
    """
    CREATE TABLE IF NOT EXISTS exness_transfers (
        transfer_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        transfer_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        destination_id TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD',
        status TEXT NOT NULL,
        idempotency_key TEXT UNIQUE NOT NULL,
        broker_transfer_id TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    );
    """,
]

EXNESS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_exness_conn_user ON exness_demo_connections(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_exness_inst_conn ON exness_discovered_instruments(connection_id);",
    "CREATE INDEX IF NOT EXISTS idx_exness_basket_user ON exness_hft_baskets(user_id, status);",
    "CREATE INDEX IF NOT EXISTS idx_exness_legs_basket ON exness_hft_orders_and_legs(basket_id);",
    "CREATE INDEX IF NOT EXISTS idx_exness_events_user ON exness_hft_execution_events(user_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_exness_transfers_user ON exness_transfers(user_id, created_at);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_exness_transfers_idemp ON exness_transfers(idempotency_key);",
]


def apply_exness_migrations(conn: sqlite3.Connection) -> None:
    """Applies all additive Exness tables, columns, and indexes."""
    with conn:
        for stmt in EXNESS_DDL_STATEMENTS:
            conn.execute(stmt)
        for idx in EXNESS_INDEXES:
            conn.execute(idx)

        # Additive check: add adapter_mode column if table was previously created without it
        cursor = conn.execute("PRAGMA table_info(exness_demo_connections);")
        columns = [row[1] for row in cursor.fetchall()]
        if "adapter_mode" not in columns:
            conn.execute(
                "ALTER TABLE exness_demo_connections ADD COLUMN adapter_mode TEXT DEFAULT 'DETERMINISTIC_MOCK_DEMO';"
            )
            logger.info("Added adapter_mode column to exness_demo_connections.")

    logger.info("Successfully verified and applied additive Exness schema migrations.")


def get_user_exness_connection(conn: sqlite3.Connection, user_id: str, account_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the active Exness connection for a user. Supports DEMO and REAL filtering."""
    if account_type:
        row = conn.execute(
            "SELECT * FROM exness_demo_connections WHERE user_id = ? AND account_type = ? AND is_active = 1 ORDER BY updated_at DESC LIMIT 1",
            (user_id, account_type.upper()),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM exness_demo_connections WHERE user_id = ? AND is_active = 1 ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_all_user_exness_connections(conn: sqlite3.Connection, user_id: str) -> List[Dict[str, Any]]:
    """Retrieves all active Exness connections (Demo and Real) for a user."""
    rows = conn.execute(
        "SELECT * FROM exness_demo_connections WHERE user_id = ? AND is_active = 1 ORDER BY account_type ASC, updated_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_exness_connection(
    conn: sqlite3.Connection,
    user_id: str,
    login: str,
    server: str,
    enc_credentials: Dict[str, Any],
    adapter_mode: str = "DETERMINISTIC_MOCK_DEMO",
    account_type: str = "DEMO",
    balance: float = 5000.0,
    equity: float = 5000.0,
    leverage: int = 2000,
    currency: str = "USD",
) -> str:
    """Creates or updates an Exness connection with explicit adapter_mode and account_type persistence."""
    conn_id = f"EXN-CONN-{secrets.token_hex(6).upper()}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    acct_type = (account_type or "DEMO").upper()

    with conn:
        conn.execute(
            "UPDATE exness_demo_connections SET is_active = 0 WHERE user_id = ? AND account_type = ?",
            (user_id, acct_type),
        )
        conn.execute(
            """
            INSERT INTO exness_demo_connections (
                connection_id, user_id, account_login, server_name, account_type,
                adapter_mode, encrypted_credentials, is_active, is_read_only, balance_usd,
                equity_usd, leverage, currency, last_reconciled_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conn_id,
                user_id,
                login,
                server,
                acct_type,
                adapter_mode,
                json.dumps(enc_credentials),
                balance,
                equity,
                leverage,
                currency,
                now,
                now,
                now,
            ),
        )
    return conn_id


def create_exness_transfer(
    conn: sqlite3.Connection,
    user_id: str,
    transfer_type: str,
    source_id: str,
    destination_id: str,
    amount: float,
    currency: str,
    idempotency_key: str,
    status: str = "PENDING",
    broker_transfer_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Records an Exness Payments API customer transfer with idempotency key."""
    transfer_id = f"TRF-{secrets.token_hex(6).upper()}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:
        conn.execute(
            """
            INSERT INTO exness_transfers (
                transfer_id, user_id, transfer_type, source_id, destination_id,
                amount, currency, status, idempotency_key, broker_transfer_id,
                error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transfer_id,
                user_id,
                transfer_type,
                source_id,
                destination_id,
                amount,
                currency,
                status,
                idempotency_key,
                broker_transfer_id,
                error_message,
                now,
                now,
            ),
        )
    return {
        "transfer_id": transfer_id,
        "user_id": user_id,
        "transfer_type": transfer_type,
        "source_id": source_id,
        "destination_id": destination_id,
        "amount": amount,
        "currency": currency,
        "status": status,
        "idempotency_key": idempotency_key,
        "broker_transfer_id": broker_transfer_id,
        "error_message": error_message,
        "created_at": now,
        "updated_at": now,
    }


def get_exness_transfer_by_idempotency(
    conn: sqlite3.Connection, idempotency_key: str
) -> Optional[Dict[str, Any]]:
    """Retrieves an existing transfer by unique idempotency key to prevent double transfers."""
    row = conn.execute(
        "SELECT * FROM exness_transfers WHERE idempotency_key = ? LIMIT 1",
        (idempotency_key,),
    ).fetchone()
    return dict(row) if row else None


def get_user_exness_transfers(
    conn: sqlite3.Connection, user_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieves customer transfer history."""
    rows = conn.execute(
        "SELECT * FROM exness_transfers WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def update_exness_transfer_status(
    conn: sqlite3.Connection,
    transfer_id: str,
    status: str,
    broker_transfer_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> bool:
    """Updates status and broker details of an initiated transfer."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:
        cursor = conn.execute(
            """
            UPDATE exness_transfers
            SET status = ?, broker_transfer_id = COALESCE(?, broker_transfer_id),
                error_message = COALESCE(?, error_message), updated_at = ?
            WHERE transfer_id = ?
            """,
            (status, broker_transfer_id, error_message, now, transfer_id),
        )
        return cursor.rowcount > 0


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
    new_version: int = 2,
) -> int:
    """
    Atomically rotates the AES-256-GCM vault encryption key for all stored credentials in database.
    Operates within a single transaction to guarantee zero data loss.
    Updates key_version metadata to new_version.
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
                new_key_version=new_version,
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

    logger.info(f"Successfully rotated vault encryption key for {rotated_count} stored connections to v{new_version}.")
    return rotated_count


def rollback_database_vault_keys(
    conn: sqlite3.Connection,
    current_key_hex: str,
    previous_key_hex: str,
    previous_version: int = 1,
) -> int:
    """
    Safely rolls back database credentials to previous key and version tag if rotation verification fails.
    """
    current_key = bytes.fromhex(current_key_hex.strip())
    prev_key = bytes.fromhex(previous_key_hex.strip())
    if len(current_key) != 32 or len(prev_key) != 32:
        raise ValueError("Both current_key and previous_key must be exactly 32 bytes.")

    rows = conn.execute(
        "SELECT connection_id, user_id, account_login, server_name, encrypted_credentials FROM exness_demo_connections"
    ).fetchall()

    rolled_back_count = 0
    with conn:
        for r in rows:
            enc_creds = json.loads(r["encrypted_credentials"])
            new_payload = ExnessCredentialVault.rollback_credentials(
                user_id=r["user_id"],
                login=r["account_login"],
                server=r["server_name"],
                enc_payload=enc_creds,
                current_key=current_key,
                previous_key=prev_key,
                previous_key_version=previous_version,
            )
            conn.execute(
                "UPDATE exness_demo_connections SET encrypted_credentials = ?, updated_at = ? WHERE connection_id = ?",
                (
                    json.dumps(new_payload),
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    r["connection_id"],
                ),
            )
            rolled_back_count += 1

    logger.info(f"Successfully rolled back vault encryption key for {rolled_back_count} stored connections to v{previous_version}.")
    return rolled_back_count
