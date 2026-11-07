import sqlite3
import os
import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("bitdex.saas_db")

def get_db_path() -> str:
    try:
        from ..config import settings
        data_dir = os.path.join(settings.platform_root, "backend", "data")
    except Exception:
        data_dir = "/opt/tauric-platform-staging/backend/data"
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "tauric_saas.db")

DB_PATH = get_db_path()

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    return conn

def safe_add_column(conn: sqlite3.Connection, table: str, col_def: str):
    """Safely adds a column to an existing table if it does not already exist."""
    col_name = col_def.split()[0].strip()
    cursor = conn.execute(f"PRAGMA table_info({table});")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if col_name not in existing_cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def};")
        logger.info(f"Added column '{col_name}' to table '{table}'.")

def init_saas_db():
    """Initializes and migrates the multi-tenant Bitdex SaaS schema with tables, indexes, and immutability triggers."""
    conn = get_db_connection()
    try:
        with conn:
            # 1. Users Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'CUSTOMER',  -- CUSTOMER, ADMIN, OWNER
                    status TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE, BLOCKED, SUSPENDED
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    kyc_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED', -- NOT_REQUIRED, REQUESTED, PENDING, APPROVED, REJECTED
                    kyc_provider_ref TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # Safe column additions for User Profiles, Username, Security, 2FA, Email OTP & Invitations
            safe_add_column(conn, "users", "username TEXT DEFAULT ''")
            safe_add_column(conn, "users", "first_name TEXT DEFAULT ''")
            safe_add_column(conn, "users", "last_name TEXT DEFAULT ''")
            safe_add_column(conn, "users", "country TEXT DEFAULT ''")
            safe_add_column(conn, "users", "two_factor_secret TEXT DEFAULT ''")
            safe_add_column(conn, "users", "two_factor_enabled INTEGER DEFAULT 0")
            safe_add_column(conn, "users", "must_change_password INTEGER DEFAULT 0")
            safe_add_column(conn, "users", "email_verification_token TEXT DEFAULT ''")
            safe_add_column(conn, "users", "password_reset_token TEXT DEFAULT ''")
            safe_add_column(conn, "users", "password_reset_expires TEXT DEFAULT ''")
            safe_add_column(conn, "users", "email_otp_hash TEXT DEFAULT ''")
            safe_add_column(conn, "users", "email_otp_expires_at TEXT DEFAULT ''")
            safe_add_column(conn, "users", "email_otp_attempts INTEGER DEFAULT 0")
            safe_add_column(conn, "users", "email_otp_sent_at TEXT DEFAULT ''")
            safe_add_column(conn, "users", "invitation_token TEXT DEFAULT ''")
            safe_add_column(conn, "users", "invitation_expires_at TEXT DEFAULT ''")
            safe_add_column(conn, "users", "failed_attempts INTEGER DEFAULT 0")
            safe_add_column(conn, "users", "last_failed_login TEXT DEFAULT ''")
            safe_add_column(conn, "users", "is_fee_exempt INTEGER DEFAULT 0")

            # Login OTP Challenges Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS login_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    otp_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts_left INTEGER NOT NULL DEFAULT 3,
                    resend_after TEXT NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)
            safe_add_column(conn, "login_challenges", "otp_salt TEXT DEFAULT ''")

            # Password Reset OTP Challenges Table (Single-use, Salted SHA-256, 5-min expiry, attempt-limited)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    otp_salt TEXT NOT NULL,
                    otp_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts_left INTEGER NOT NULL DEFAULT 3,
                    resend_after TEXT NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0,
                    used INTEGER NOT NULL DEFAULT 0,
                    reset_session_token_hash TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)
            safe_add_column(conn, "password_reset_challenges", "reset_token_hash TEXT DEFAULT ''")

            # Email Change OTP Challenges Table (New email verification)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_change_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    old_email TEXT NOT NULL,
                    new_email TEXT NOT NULL,
                    otp_salt TEXT NOT NULL,
                    otp_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts_left INTEGER NOT NULL DEFAULT 3,
                    resend_after TEXT NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # Email Dispatches & Audit Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_dispatches (
                    dispatch_id TEXT PRIMARY KEY,
                    recipient_email TEXT NOT NULL,
                    email_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    details_json TEXT,
                    created_at TEXT NOT NULL
                );
            """)

            # 2. Sessions Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # 3. User Exchange Connections (Provider-neutral, tenant-isolated API keys)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_exchange_connections (
                    account_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    label TEXT NOT NULL,
                    environment TEXT NOT NULL DEFAULT 'DEMO', -- DEMO, LIVE
                    product_type TEXT NOT NULL DEFAULT 'SPOT', -- SPOT, FUTURES, FOREX
                    encrypted_credentials TEXT NOT NULL,
                    connection_status TEXT NOT NULL DEFAULT 'SAVED',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_verified_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)
            safe_add_column(conn, "user_exchange_connections", "exchange_name TEXT DEFAULT ''")
            safe_add_column(conn, "user_exchange_connections", "adapter_id TEXT DEFAULT ''")
            safe_add_column(conn, "user_exchange_connections", "verification_status TEXT DEFAULT 'UNVERIFIED'")
            safe_add_column(conn, "user_exchange_connections", "capabilities_json TEXT DEFAULT '[]'")
            safe_add_column(conn, "user_exchange_connections", "permissions_json TEXT DEFAULT '[]'")
            safe_add_column(conn, "user_exchange_connections", "sanitized_error TEXT DEFAULT ''")
            safe_add_column(conn, "user_exchange_connections", "key_fingerprint TEXT DEFAULT ''")

            # 4. Platform Global Pricing Config Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS platform_pricing_config (
                    config_key TEXT PRIMARY KEY,
                    ai_analysis_price_usd REAL NOT NULL DEFAULT 1.00,
                    ai_analysis_price_cents INTEGER NOT NULL DEFAULT 100,
                    default_execution_fee_usd REAL NOT NULL DEFAULT 0.30,
                    default_activation_fee_usd REAL NOT NULL DEFAULT 20.00,
                    updated_by TEXT,
                    updated_at TEXT NOT NULL
                );
            """)
            safe_add_column(conn, "platform_pricing_config", "admin_fee_waiver_enabled INTEGER DEFAULT 1")
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute("""
                INSERT OR IGNORE INTO platform_pricing_config (
                    config_key, ai_analysis_price_usd, ai_analysis_price_cents,
                    default_execution_fee_usd, default_activation_fee_usd, updated_by, updated_at
                ) VALUES ('GLOBAL_DEFAULT', 1.00, 100, 0.30, 20.00, 'SYSTEM', ?)
            """, (now_iso,))

            # 4b. Non-Custodial Wallet Watcher Connections Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_wallet_connections (
                    wallet_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    address TEXT NOT NULL,
                    network TEXT NOT NULL DEFAULT 'ETHEREUM',
                    environment TEXT NOT NULL DEFAULT 'LIVE',
                    connection_mode TEXT NOT NULL DEFAULT 'WATCH_ONLY',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_synced_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # 5. Fee Policies (Per-customer configurable)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fee_policies (
                    policy_id TEXT PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    activation_fee_enabled INTEGER NOT NULL DEFAULT 1,
                    activation_fee_usd REAL NOT NULL DEFAULT 20.0,
                    activation_fee_charged INTEGER NOT NULL DEFAULT 0,
                    execution_fee_enabled INTEGER NOT NULL DEFAULT 1,
                    execution_fee_usd REAL NOT NULL DEFAULT 0.30,
                    fee_waived INTEGER NOT NULL DEFAULT 0,
                    waiver_reason TEXT,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # Safe column additions for AI research fees (both USD decimal and exact cents)
            safe_add_column(conn, "fee_policies", "ai_research_fee_enabled INTEGER DEFAULT 1")
            safe_add_column(conn, "fee_policies", "ai_research_fee_usd REAL DEFAULT 1.00")
            safe_add_column(conn, "fee_policies", "ai_research_fee_cents INTEGER DEFAULT 100")
            safe_add_column(conn, "fee_policies", "ai_research_fee_waived INTEGER DEFAULT 0")
            safe_add_column(conn, "fee_policies", "is_fee_exempt INTEGER DEFAULT 0")
            safe_add_column(conn, "fee_policies", "gas_fee_rate REAL DEFAULT 0.50")
            safe_add_column(conn, "fee_policies", "platform_fee_usd REAL DEFAULT 20.00")
            safe_add_column(conn, "billing_accounts", "admin_held_amount REAL DEFAULT 0.0")
            safe_add_column(conn, "exness_demo_connections", "admin_held_amount REAL DEFAULT 0.0")

            # 6. Billing Accounts (Prepaid credit balances)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS billing_accounts (
                    account_id TEXT PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL,
                    prepaid_credits_usd REAL NOT NULL DEFAULT 0.0,
                    total_deposited_usd REAL NOT NULL DEFAULT 0.0,
                    total_fees_paid_usd REAL NOT NULL DEFAULT 0.0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # 7. Invoices Table (Checkout & automated billing orders)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    invoice_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    invoice_type TEXT NOT NULL, -- ACTIVATION_FEE, PREPAID_TOPUP
                    amount_usd REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USDT',
                    provider TEXT NOT NULL, -- BINANCE_PAY, STRIPE, HITPAY, CRYPTO_WALLET
                    provider_order_id TEXT,
                    checkout_url TEXT,
                    qr_content TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, PAID, EXPIRED, CANCELLED
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)
            safe_add_column(conn, "invoices", "network TEXT DEFAULT 'BEP20'")
            safe_add_column(conn, "invoices", "deposit_address TEXT DEFAULT ''")
            safe_add_column(conn, "invoices", "crypto_amount REAL DEFAULT 0.0")
            safe_add_column(conn, "invoices", "tx_hash TEXT DEFAULT ''")
            safe_add_column(conn, "invoices", "confirmations INTEGER DEFAULT 0")
            safe_add_column(conn, "invoices", "required_confirmations INTEGER DEFAULT 1")
            safe_add_column(conn, "invoices", "expires_at TEXT DEFAULT ''")
            safe_add_column(conn, "invoices", "paid_at TEXT DEFAULT ''")

            # 8. Billing Ledger (Immutable, auditable financial events)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS billing_ledger (
                    entry_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    entry_type TEXT NOT NULL, -- CREDIT_TOPUP, ACTIVATION_FEE, EXECUTION_FEE, AI_RESEARCH_FEE, AI_RESEARCH_REFUND, REFUND, ADJUSTMENT
                    amount_usd REAL NOT NULL,
                    balance_after_usd REAL NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    billable_order_ref TEXT,
                    fill_ref TEXT,
                    evidence_source TEXT,
                    policy_version INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'POSTED', -- POSTED, PENDING, REVERSED
                    description TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # 9. AI Analysis Runs Table (Tracks explicit pay-per-use AI runs, idempotency, customer fee vs actual token telemetry)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL DEFAULT 'CRYPTO',
                    timeframe TEXT NOT NULL DEFAULT '1h',
                    model_id TEXT NOT NULL DEFAULT 'deepseek-v4-flash',
                    status TEXT NOT NULL DEFAULT 'RUNNING', -- RUNNING, COMPLETED, FAILED_REFUNDED, REJECTED_PREFLIGHT
                    customer_price_usd REAL NOT NULL DEFAULT 0.0,
                    customer_price_cents INTEGER NOT NULL DEFAULT 0,
                    provider_tokens_used INTEGER NOT NULL DEFAULT 0,
                    provider_estimated_cost_usd REAL DEFAULT 0.0,
                    ledger_entry_id TEXT,
                    refund_entry_id TEXT,
                    result_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # 10. Customer Support Tickets & Messages Tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'GENERAL',
                    priority TEXT NOT NULL DEFAULT 'NORMAL',
                    status TEXT NOT NULL DEFAULT 'Open', -- Open, In Progress, Waiting for Customer, Resolved, Closed
                    attachment_name TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS support_ticket_messages (
                    message_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    sender_user_id TEXT NOT NULL,
                    sender_role TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    body TEXT NOT NULL,
                    is_internal_note INTEGER NOT NULL DEFAULT 0,
                    attachment_name TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id) ON DELETE CASCADE
                );
            """)

            # 11. Security and Administrative Audit Logs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_user_id TEXT,
                    details_json TEXT,
                    created_at TEXT NOT NULL
                );
            """)

            # 12. KYC Records
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kyc_records (
                    record_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_session_id TEXT,
                    verification_hash TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            # Backfill usernames for existing users if empty
            conn.execute("""
                UPDATE users
                SET username = CASE
                    WHEN first_name != '' AND last_name != '' THEN first_name || ' ' || last_name
                    WHEN first_name != '' THEN first_name
                    ELSE substr(email, 1, instr(email, '@') - 1)
                END
                WHERE username IS NULL OR username = '';
            """)

            # Indexes for performance and isolation
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_user_id ON user_exchange_connections(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_invoices_provider_order ON invoices(provider_order_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_user_id ON billing_ledger(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_idempotency ON billing_ledger(idempotency_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_runs_user_id ON ai_analysis_runs(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_runs_idempotency ON ai_analysis_runs(idempotency_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user_id ON support_tickets(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_msgs_ticket_id ON support_ticket_messages(ticket_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_logs(target_user_id);")

            # Database-Level Immutability Enforcement Triggers
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_block_ledger_update
                BEFORE UPDATE ON billing_ledger
                BEGIN
                    SELECT RAISE(ABORT, 'IMMUTABILITY VIOLATION: billing_ledger entries are strictly append-only and cannot be modified.');
                END;
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_block_ledger_delete
                BEFORE DELETE ON billing_ledger
                BEGIN
                    SELECT RAISE(ABORT, 'IMMUTABILITY VIOLATION: billing_ledger entries are strictly append-only and cannot be deleted.');
                END;
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_block_audit_update
                BEFORE UPDATE ON audit_logs
                BEGIN
                    SELECT RAISE(ABORT, 'IMMUTABILITY VIOLATION: audit_logs entries are strictly append-only and cannot be modified.');
                END;
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_block_audit_delete
                BEFORE DELETE ON audit_logs
                BEGIN
                    SELECT RAISE(ABORT, 'IMMUTABILITY VIOLATION: audit_logs entries are strictly append-only and cannot be deleted.');
                END;
            """)

            # Supported Brokers Registry (Diagram 2 SSOT)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS supported_brokers (
                    broker_id TEXT PRIMARY KEY,
                    broker_name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    adapter_class TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    supported_platforms TEXT NOT NULL DEFAULT '["MT5","EXNESS_TERMINAL"]',
                    supported_environments TEXT NOT NULL DEFAULT '["DEMO","REAL"]',
                    created_at TEXT NOT NULL
                );
            """)

            # Seed supported brokers registry
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            brokers_seed = [
                ('EXNESS', 'Exness Technologies', 'Exness MT5 & Terminal', 'ExnessMT5GatewayAdapter', 1, '["MT5","EXNESS_TERMINAL"]', '["DEMO","REAL"]', now_iso),
                ('FUTURE_BROKER_SLOT', 'Universal Broker Slot', 'Universal Plug-and-Play Slot', 'UniversalBrokerAdapter', 0, '["MT5","REST"]', '["DEMO","REAL"]', now_iso),
                ('BINANCE', 'Binance', 'Binance Crypto Futures & Spot', 'BinanceSpotAdapter', 1, '["BINANCE_PERP","BINANCE_SPOT"]', '["DEMO","LIVE"]', now_iso),
                ('BYBIT', 'Bybit', 'Bybit Derivatives', 'BybitSpotAdapter', 1, '["BYBIT_PERP"]', '["DEMO","LIVE"]', now_iso),
            ]
            for b in brokers_seed:
                conn.execute("""
                    INSERT OR IGNORE INTO supported_brokers (broker_id, broker_name, display_name, adapter_class, is_active, supported_platforms, supported_environments, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, b)

            # Broker Sub-Accounts Table (Diagram 2 Universal Multi-Broker Account Registry)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS broker_sub_accounts (
                    sub_account_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    broker_id TEXT NOT NULL,
                    account_number TEXT NOT NULL,
                    account_tier TEXT DEFAULT 'STANDARD',
                    mode TEXT NOT NULL DEFAULT 'DEMO',
                    balance REAL DEFAULT 0.0,
                    equity REAL DEFAULT 0.0,
                    free_margin REAL DEFAULT 0.0,
                    admin_held_amount REAL DEFAULT 0.0,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    server_name TEXT NOT NULL,
                    is_connected INTEGER NOT NULL DEFAULT 1,
                    verification_status TEXT NOT NULL DEFAULT 'VERIFIED',
                    last_synced_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (broker_id) REFERENCES supported_brokers(broker_id)
                );
            """)

            # Sync active verified Exness accounts into broker_sub_accounts
            conn.execute("""
                INSERT OR REPLACE INTO broker_sub_accounts (
                    sub_account_id, user_id, broker_id, account_number, account_tier, mode,
                    balance, equity, free_margin, admin_held_amount, currency, server_name,
                    is_connected, verification_status, last_synced_at, created_at
                )
                SELECT connection_id, user_id, 'EXNESS', account_login, COALESCE(account_tier, 'STANDARD'),
                       CASE WHEN UPPER(account_type) = 'REAL' THEN 'LIVE' ELSE 'DEMO' END,
                       COALESCE(balance_usd, 0.0), COALESCE(equity_usd, 0.0), COALESCE(margin_free, balance_usd, 0.0),
                       COALESCE(admin_held_amount, 0.0), COALESCE(currency, 'USD'), COALESCE(server_name, 'Exness-MT5Trial15'),
                       1, verification_status, updated_at, created_at
                FROM exness_demo_connections
                WHERE verification_status IN ('VERIFIED', 'ACCOUNT_DATA_VERIFIED');
            """)

        logger.info("Bitdex SaaS database schema, support tickets, AI analysis runs, and immutability triggers initialized successfully.")
    finally:
        conn.close()

if __name__ == "__main__":
    init_saas_db()
    print("Initialized saas_db at:", get_db_path())
