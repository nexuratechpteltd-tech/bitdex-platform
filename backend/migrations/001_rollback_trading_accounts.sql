-- BITDEX Commercial Multi-Tenant Trading Platform
-- Rollback: 001_rollback_trading_accounts.sql
-- Description: Safely drops indexes, tables, and foreign keys introduced in 001_create_trading_accounts.sql.

DROP INDEX IF EXISTS idx_trading_accounts_tenant_login;
DROP INDEX IF EXISTS idx_trading_accounts_worker;
DROP INDEX IF EXISTS idx_trading_accounts_user;
DROP TABLE IF EXISTS trading_accounts;
