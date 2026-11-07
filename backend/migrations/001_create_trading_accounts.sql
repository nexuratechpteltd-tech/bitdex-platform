-- BITDEX Commercial Multi-Tenant Trading Platform
-- Migration: 001_create_trading_accounts.sql
-- Status: UNAPPLIED (Architecture Blueprint Specification for Phase 7C)
-- DO NOT APPLY ON STAGING OR PRODUCTION WITHOUT EXPLICIT AUTHORIZATION

CREATE TABLE IF NOT EXISTS trading_accounts (
    account_id TEXT PRIMARY KEY,                 -- Internal UUID: ACC-A4E7BE39D276
    user_id TEXT NOT NULL,                        -- Tenant ID: USR-ADM-B022F490
    broker_name TEXT NOT NULL DEFAULT 'EXNESS',  -- EXNESS, BINANCE, BYBIT
    platform TEXT NOT NULL,                       -- EXNESS_TERMINAL, MT5, MT4, BINANCE_PERP
    environment TEXT NOT NULL,                    -- DEMO, REAL, PAPER
    broker_login TEXT NOT NULL,                   -- Broker Login ID: 474861031, 16000629657
    server_name TEXT NOT NULL,                    -- Exness-MT5Trial15, https://api.exness.com
    account_tier TEXT DEFAULT 'STANDARD',         -- Standard, RawSpread, Pro, Zero
    currency TEXT NOT NULL DEFAULT 'USD',
    leverage INTEGER NOT NULL DEFAULT 2000,
    
    -- Connection & Verification Lifecycle
    connection_status TEXT NOT NULL DEFAULT 'DISCONNECTED', 
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED', 
    is_active INTEGER NOT NULL DEFAULT 1,
    is_preferred INTEGER NOT NULL DEFAULT 0,
    
    -- Telemetry Cache (Updated via delta streams / worker heartbeats)
    balance_usd REAL DEFAULT 0.0,
    equity_usd REAL DEFAULT 0.0,
    margin_used REAL DEFAULT 0.0,
    margin_free REAL DEFAULT 0.0,
    floating_pnl REAL DEFAULT 0.0,
    
    -- Worker Assignment (For MT5 Gateway Instances)
    worker_node_id TEXT,                          -- e.g. WIN-NODE-01
    worker_instance_id TEXT,                      -- e.g. INST-474861031
    worker_port INTEGER,                          -- e.g. 8095
    
    -- Cryptographic Credential Vault Reference
    vault_credential_ref TEXT NOT NULL,           -- VLT-SEC-XXXXX (Envelope Key Ref)
    real_consent_id TEXT,                         -- CNS-57D834752F5F (if REAL)
    
    -- Audit & Timestamps
    last_connected_at TEXT,
    last_synced_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (real_consent_id) REFERENCES real_trading_consents(consent_id)
);

CREATE INDEX IF NOT EXISTS idx_trading_accounts_user ON trading_accounts(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_trading_accounts_worker ON trading_accounts(worker_node_id, worker_instance_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trading_accounts_tenant_login ON trading_accounts(user_id, broker_login, server_name);
