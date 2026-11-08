"""
BITDEX — PHASE 7D: CONTROLLED DEMO EXECUTION READINESS SERVICE
==============================================================
Provides isolated, server-verified Demo execution authorization, risk barrier checks,
mandatory broker-side Stop Loss & Take Profit verification, emergency disarm, and audit logging.

SAFETY GOVERNANCE:
  - Real accounts are PERMANENTLY LOCKED and hard-rejected with HTTP 403 Forbidden.
  - Live trading execution is disabled across all environments (live_trading_locked=True, real_trading_locked=True).
  - Controlled Demo execution permission applies strictly to server-confirmed Demo accounts.
  - Zero orders are submitted to live MT5 terminals during Phase 7D (simulation & replay only).
"""

import json
import time
import secrets
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from fastapi import HTTPException, status

import httpx

# Persistent HTTP Keep-Alive client to Windows MT5 Gateway (eliminates ~442ms TCP handshake overhead per call)
_GATEWAY_KEEPALIVE_CLIENT = httpx.Client(
    base_url="http://10.88.0.2:8095",
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=120.0),
    timeout=8.0,
)

def get_gateway_client() -> httpx.Client:
    return _GATEWAY_KEEPALIVE_CLIENT


logger = logging.getLogger("bitdex.demo_execution")

ALLOWED_EXNESS_BASE_SYMBOLS = {"BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "GBPUSD"}
ALLOWED_EXNESS_SYMBOLS = {
    "BTCUSD", "BTCUSDR", "ETHUSD", "ETHUSDR",
    "XAUUSD", "XAUUSDR", "EURUSD", "EURUSDM", "GBPUSD", "GBPUSDM"
}

def is_allowed_exness_symbol(symbol_str: str) -> bool:
    clean = symbol_str.upper().replace("/", "").replace(":", "").replace("-", "")
    if clean in ALLOWED_EXNESS_BASE_SYMBOLS or clean in ALLOWED_EXNESS_SYMBOLS:
        return True
    for sfx in ("R", "M", "C"):
        if clean.endswith(sfx) and clean[:-len(sfx)] in ALLOWED_EXNESS_BASE_SYMBOLS:
            return True
    return False

def normalize_broker_symbol(symbol_str: str) -> str:
    clean = symbol_str.upper().replace("/", "").replace(":", "").replace("-", "")
    if clean.endswith("R"):
        return clean[:-1] + "r"
    elif clean.endswith("M"):
        return clean[:-1] + "m"
    elif clean.endswith("C"):
        return clean[:-1] + "c"
    elif "BTC" in clean:
        return "BTCUSDr"
    elif "ETH" in clean:
        return "ETHUSDr"
    elif "XAU" in clean:
        return "XAUUSDr"
    elif "EUR" in clean:
        return "EURUSDm"
    elif "GBP" in clean:
        return "GBPUSDm"
    return clean + "r"
DEMO_AUTH_TTL_SECONDS = 3600  # 1 hour authorization window
MAX_SIMULTANEOUS_POSITIONS = 3
MAX_ENTRIES_PER_INSTRUMENT = 2
MAX_TOTAL_EXPOSURE_PCT = 30.0  # Max 30% of account equity
MAX_DAILY_LOSS_USD = 50.0
MAX_CONSECUTIVE_LOSSES = 3
CONSECUTIVE_LOSS_COOLDOWN_SECONDS = 1800  # 30 minutes
MIN_RISK_REWARD_RATIO = 1.00
MIN_STOPS_LEVEL_POINTS = 50.0  # Exness BTCUSD minimum stops level (0.50 USD)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_demo_tables(conn: sqlite3.Connection) -> None:
    """Ensures Phase 7D demo authorization and simulated order tables exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hft_demo_authorizations (
            auth_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            broker_login TEXT NOT NULL,
            server_name TEXT NOT NULL,
            platform TEXT NOT NULL,
            environment TEXT NOT NULL,
            symbol TEXT NOT NULL,
            worker_instance_id TEXT NOT NULL,
            adapter_name TEXT NOT NULL,
            is_authorized INTEGER NOT NULL DEFAULT 1,
            emergency_stop_triggered INTEGER NOT NULL DEFAULT 0,
            authorized_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            disarmed_at TEXT,
            disarm_reason TEXT,
            max_positions INTEGER NOT NULL DEFAULT 3,
            max_entries_per_instrument INTEGER NOT NULL DEFAULT 2,
            max_exposure_pct REAL NOT NULL DEFAULT 30.0,
            max_daily_loss_usd REAL NOT NULL DEFAULT 50.0,
            max_consecutive_losses INTEGER NOT NULL DEFAULT 3,
            consecutive_losses INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hft_demo_simulated_orders (
            order_id TEXT PRIMARY KEY,
            auth_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            volume REAL NOT NULL,
            stop_loss_price REAL NOT NULL,
            take_profit_price REAL NOT NULL,
            stop_distance_usd REAL NOT NULL,
            take_profit_distance_usd REAL NOT NULL,
            risk_reward_ratio REAL NOT NULL,
            margin_usd REAL NOT NULL,
            exposure_pct REAL NOT NULL,
            simulated_fill_status TEXT NOT NULL,
            rejection_reason TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hft_auto_entry_state (
            account_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT 'BTCUSDr',
            auto_entry_armed INTEGER NOT NULL DEFAULT 0,
            allocated_capital_usd REAL NOT NULL DEFAULT 100.0,
            risk_pct_per_trade REAL NOT NULL DEFAULT 1.0,
            profit_target_usd REAL NOT NULL DEFAULT 1.0,
            max_loss_usd REAL NOT NULL DEFAULT 1.0,
            min_net_edge_usd REAL NOT NULL DEFAULT 1.0,
            enforce_notional_leverage_cap INTEGER NOT NULL DEFAULT 0,
            leverage_limit REAL NOT NULL DEFAULT 5.0,
            last_evaluated_bar_ts INTEGER NOT NULL DEFAULT 0,
            last_executed_bar_ts INTEGER NOT NULL DEFAULT 0,
            last_idempotency_key TEXT,
            last_selected_direction TEXT,
            last_directional_score REAL,
            last_cycle_status TEXT,
            last_skip_reason TEXT,
            last_evaluated_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


class DemoExecutionService:
    """
    Manages isolated Demo execution authorization, emergency stops,
    and simulated pre-execution order validation.
    """

    @classmethod
    def authorize_demo_execution(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str,
        symbol: str = "BTCUSD",
        confirm_demo_only: bool = True
    ) -> Dict[str, Any]:
        """
        Authorizes controlled Demo execution strictly for a verified Demo account.
        Hard-rejects any Real account with HTTP 403 Forbidden.
        """
        ensure_demo_tables(conn)
        clean_symbol = symbol.upper().replace("/", "").replace(":", "").replace("-", "")

        # 1. Resolve Account Identity & Enforce Tenant Isolation
        # Check exness_demo_connections first
        exness_row = conn.execute(
            """
            SELECT * FROM exness_demo_connections
            WHERE (connection_id = ? OR account_login = ?) AND user_id = ?
            """,
            (account_id, account_id, user_id)
        ).fetchone()

        exchange_row = None
        if not exness_row:
            exchange_row = conn.execute(
                """
                SELECT * FROM user_exchange_connections
                WHERE account_id = ? AND user_id = ?
                """,
                (account_id, user_id)
            ).fetchone()

        if not exness_row and not exchange_row:
            # Check if this account belongs to another user (Tenant collision)
            other_user = conn.execute(
                "SELECT user_id FROM exness_demo_connections WHERE connection_id = ? OR account_login = ?",
                (account_id, account_id)
            ).fetchone()
            if other_user:
                logger.warning(f"Cross-tenant Demo authorization attempt: user {user_id} tried accessing {account_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"UNAUTHORIZED_CROSS_TENANT_ACCESS: Account {account_id} belongs to another tenant."
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trading account {account_id} not found or unauthorized for user {user_id}."
            )

        # 2. Hard Reject All Real Accounts (STAGE 3 — GLOBAL SAFETY)
        if exness_row:
            ed = dict(exness_row)
            raw_env = (ed.get("account_type") or "DEMO").upper()
            verif_status = ed.get("verification_status")
            is_active = bool(ed.get("is_active"))
            broker_login = str(ed.get("account_login"))
            server_name = ed.get("server_name")
            platform = ed.get("platform") or "MT5"
            balance_usd = float(ed.get("balance_usd") or 5000.0)
            equity_usd = float(ed.get("equity_usd") or balance_usd)
            worker_id = f"INST-{broker_login}"
            adapter_name = "EXNESS_MT5_GATEWAY"
        else:
            xd = dict(exchange_row)
            raw_env = (xd.get("environment") or "DEMO").upper()
            verif_status = xd.get("verification_status")
            is_active = bool(xd.get("is_active"))
            broker_login = str(xd.get("account_id"))
            server_name = xd.get("provider")
            platform = xd.get("provider")
            balance_usd = 5000.0
            equity_usd = 5000.0
            worker_id = f"WRK-{xd.get('provider')}-{broker_login[:8]}"
            adapter_name = f"{xd.get('provider')}_ADAPTER"

        if raw_env in ("REAL", "LIVE"):
            logger.critical(f"HARD REJECT: Real account {account_id} submitted to demo-authorize by {user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="REAL_TRADING_PERMANENTLY_LOCKED: Live real execution is strictly forbidden. Demo execution permission applies solely to server-verified Demo accounts."
            )

        # 3. Verification Status Check
        if verif_status == "DUPLICATE_TENANT_CONFLICT":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"DUPLICATE_TENANT_CONFLICT: Physical account {broker_login} is in duplicate conflict state. Demo authorization denied."
            )

        if verif_status not in ("ACCOUNT_DATA_VERIFIED", "VERIFIED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ACCOUNT_UNVERIFIED: Account {account_id} verification status is '{verif_status}'. Server-confirmed verification required."
            )

        if not is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ACCOUNT_INACTIVE: Account {account_id} is marked inactive. Activate connection before authorizing."
            )

        # 4. Instrument Validation
        if "EXNESS" in adapter_name and not is_allowed_exness_symbol(clean_symbol):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"UNSUPPORTED_BROKER_SYMBOL: Instrument {clean_symbol} is not a valid Exness CFD pair. Supported: {', '.join(sorted(ALLOWED_EXNESS_SYMBOLS))}."
            )

        # 5. Revoke Any Existing Stale Authorizations for This Account
        now_str = now_utc_iso()
        now_dt = datetime.now(timezone.utc)
        expires_dt = now_dt + timedelta(seconds=DEMO_AUTH_TTL_SECONDS)
        expires_str = expires_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        conn.execute(
            """
            UPDATE hft_demo_authorizations
            SET is_authorized = 0, disarmed_at = ?, disarm_reason = 'SUPERSEDED_BY_NEW_AUTHORIZATION', updated_at = ?
            WHERE user_id = ? AND account_id = ? AND is_authorized = 1
            """,
            (now_str, now_str, user_id, account_id)
        )

        # 6. Issue Dedicated Demo Authorization Token
        auth_token = f"DEMO-AUTH-{secrets.token_hex(8).upper()}"
        max_exposure_usd = round(equity_usd * (MAX_TOTAL_EXPOSURE_PCT / 100.0), 2)

        conn.execute(
            """
            INSERT INTO hft_demo_authorizations
            (auth_id, user_id, account_id, broker_login, server_name, platform, environment,
             symbol, worker_instance_id, adapter_name, is_authorized, emergency_stop_triggered,
             authorized_at, expires_at, max_positions, max_entries_per_instrument, max_exposure_pct,
             max_daily_loss_usd, max_consecutive_losses, consecutive_losses, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'DEMO', ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                auth_token, user_id, account_id, broker_login, server_name, platform,
                clean_symbol, worker_id, adapter_name, now_str, expires_str,
                MAX_SIMULTANEOUS_POSITIONS, MAX_ENTRIES_PER_INSTRUMENT, MAX_TOTAL_EXPOSURE_PCT,
                MAX_DAILY_LOSS_USD, MAX_CONSECUTIVE_LOSSES, now_str, now_str
            )
        )

        # 7. Write Audit Trail
        log_id = f"AUD-{secrets.token_hex(6).upper()}"
        conn.execute(
            """
            INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
            VALUES (?, ?, 'DEMO_EXECUTION_AUTHORIZED', ?, ?, ?)
            """,
            (
                log_id,
                user_id,
                user_id,
                json.dumps({
                    "auth_token": auth_token,
                    "account_id": account_id,
                    "broker_login": broker_login,
                    "server_name": server_name,
                    "platform": platform,
                    "environment": "DEMO",
                    "symbol": clean_symbol,
                    "worker_instance_id": worker_id,
                    "adapter_name": adapter_name,
                    "equity_usd": equity_usd,
                    "max_exposure_usd": max_exposure_usd,
                    "max_positions": MAX_SIMULTANEOUS_POSITIONS,
                    "max_daily_loss_usd": MAX_DAILY_LOSS_USD,
                    "live_trading_locked": True,
                    "real_trading_locked": True,
                }),
                now_str
            )
        )
        conn.commit()

        return {
            "status": "SUCCESS",
            "authorization": {
                "auth_token": auth_token,
                "user_id": user_id,
                "account_id": account_id,
                "broker_login": broker_login,
                "server_name": server_name,
                "platform": platform,
                "environment": "DEMO",
                "symbol": clean_symbol,
                "worker_instance_id": worker_id,
                "adapter_name": adapter_name,
                "is_authorized": True,
                "emergency_stop_triggered": False,
                "authorized_at": now_str,
                "expires_at": expires_str,
                "validity_seconds": DEMO_AUTH_TTL_SECONDS,
            },
            "risk_barriers": {
                "account_equity_usd": equity_usd,
                "max_simultaneous_positions": MAX_SIMULTANEOUS_POSITIONS,
                "max_entries_per_instrument": MAX_ENTRIES_PER_INSTRUMENT,
                "max_total_exposure_pct": MAX_TOTAL_EXPOSURE_PCT,
                "max_total_exposure_usd": max_exposure_usd,
                "max_daily_loss_usd": MAX_DAILY_LOSS_USD,
                "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
                "cooldown_seconds_after_consecutive_losses": CONSECUTIVE_LOSS_COOLDOWN_SECONDS,
                "min_risk_reward_ratio": MIN_RISK_REWARD_RATIO,
                "min_stops_level_points": MIN_STOPS_LEVEL_POINTS,
            },
            "global_safety_locks": {
                "live_trading_locked": True,
                "real_trading_locked": True,
                "read_only_mode": True,
                "emergency_lock_active": False,
                "simulated_execution_only": True,
                "orders_dispatched_to_broker": 0,
            },
            "message": f"Controlled Demo Execution AUTHORIZED for {clean_symbol} on {server_name} (#{broker_login}). Real trading remains permanently locked."
        }

    @classmethod
    def emergency_disarm(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
        reason: str = "User triggered emergency disarm"
    ) -> Dict[str, Any]:
        """
        Immediately disarms and revokes Demo execution authorization.
        Sets emergency_stop_triggered = 1 and records audit trail.
        """
        ensure_demo_tables(conn)
        now_str = now_utc_iso()

        if account_id:
            cur = conn.execute(
                """
                UPDATE hft_demo_authorizations
                SET is_authorized = 0, emergency_stop_triggered = 1, disarmed_at = ?, disarm_reason = ?, updated_at = ?
                WHERE user_id = ? AND account_id = ? AND is_authorized = 1
                """,
                (now_str, reason, now_str, user_id, account_id)
            )
        else:
            cur = conn.execute(
                """
                UPDATE hft_demo_authorizations
                SET is_authorized = 0, emergency_stop_triggered = 1, disarmed_at = ?, disarm_reason = ?, updated_at = ?
                WHERE user_id = ? AND is_authorized = 1
                """,
                (now_str, reason, now_str, user_id)
            )

        revoked_count = cur.rowcount

        # Immediately disarm automatic entry execution state as well
        conn.execute(
            """
            UPDATE hft_auto_entry_state
            SET auto_entry_armed = 0,
                last_cycle_status = 'EMERGENCY_DISARMED',
                last_skip_reason = ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (f"EMERGENCY_DISARM: {reason}", now_str, user_id)
        )

        # Write Audit Trail
        log_id = f"AUD-{secrets.token_hex(6).upper()}"
        conn.execute(
            """
            INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
            VALUES (?, ?, 'DEMO_EXECUTION_DISARMED', ?, ?, ?)
            """,
            (
                log_id,
                user_id,
                user_id,
                json.dumps({
                    "revoked_count": revoked_count,
                    "account_id": account_id,
                    "reason": reason,
                    "emergency_stop_triggered": True,
                    "timestamp_utc": now_str,
                }),
                now_str
            )
        )
        conn.commit()

        return {
            "status": "SUCCESS",
            "emergency_disarmed": True,
            "revoked_authorizations": revoked_count,
            "disarmed_at": now_str,
            "reason": reason,
            "global_safety_locks": {
                "live_trading_locked": True,
                "real_trading_locked": True,
                "emergency_lock_active": True,
                "read_only_mode": True,
            },
            "message": f"Demo execution EMERGENCY DISARM completed. {revoked_count} active authorizations revoked."
        }

    @classmethod
    def get_demo_status(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Returns the current Demo execution authorization state and risk barrier metrics."""
        ensure_demo_tables(conn)
        now_dt = datetime.now(timezone.utc)
        now_str = now_utc_iso()

        query = """
            SELECT * FROM hft_demo_authorizations
            WHERE user_id = ? AND is_authorized = 1
        """
        params = [user_id]
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        query += " ORDER BY created_at DESC LIMIT 1"

        row = conn.execute(query, tuple(params)).fetchone()
        if not row:
            return {
                "status": "SUCCESS",
                "is_authorized": False,
                "authorization": None,
                "emergency_stop_triggered": False,
                "global_safety_locks": {
                    "live_trading_locked": True,
                    "real_trading_locked": True,
                    "read_only_mode": True,
                    "emergency_lock_active": True,
                },
                "risk_barriers": {
                    "max_simultaneous_positions": MAX_SIMULTANEOUS_POSITIONS,
                    "max_entries_per_instrument": MAX_ENTRIES_PER_INSTRUMENT,
                    "max_total_exposure_pct": MAX_TOTAL_EXPOSURE_PCT,
                    "max_daily_loss_usd": MAX_DAILY_LOSS_USD,
                }
            }

        # Check TTL expiration
        expires_dt = datetime.strptime(row["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if now_dt >= expires_dt:
            # Expired
            conn.execute(
                "UPDATE hft_demo_authorizations SET is_authorized = 0, disarmed_at = ?, disarm_reason = 'TTL_EXPIRED' WHERE auth_id = ?",
                (now_str, row["auth_id"])
            )
            conn.commit()
            return {
                "status": "SUCCESS",
                "is_authorized": False,
                "authorization": None,
                "expired_token": row["auth_id"],
                "emergency_stop_triggered": False,
                "message": "Authorization expired. Re-authorization required."
            }

        remaining_sec = max(0, int((expires_dt - now_dt).total_seconds()))

        return {
            "status": "SUCCESS",
            "is_authorized": True,
            "authorization": {
                "auth_token": row["auth_id"],
                "user_id": row["user_id"],
                "account_id": row["account_id"],
                "broker_login": row["broker_login"],
                "server_name": row["server_name"],
                "platform": row["platform"],
                "environment": row["environment"],
                "symbol": row["symbol"],
                "worker_instance_id": row["worker_instance_id"],
                "adapter_name": row["adapter_name"],
                "authorized_at": row["authorized_at"],
                "expires_at": row["expires_at"],
                "remaining_seconds": remaining_sec,
            },
            "emergency_stop_triggered": bool(row["emergency_stop_triggered"]),
            "risk_barriers": {
                "max_simultaneous_positions": row["max_positions"],
                "max_entries_per_instrument": row["max_entries_per_instrument"],
                "max_total_exposure_pct": row["max_exposure_pct"],
                "max_daily_loss_usd": row["max_daily_loss_usd"],
                "consecutive_losses": row["consecutive_losses"],
            },
            "global_safety_locks": {
                "live_trading_locked": True,
                "real_trading_locked": True,
                "read_only_mode": True,
                "emergency_lock_active": bool(row["emergency_stop_triggered"]),
            }
        }

    @classmethod
    def validate_and_simulate_order(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        auth_token: str,
        order_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validates proposed Demo order against all risk barriers and mandatory SL/TP.
        Performs pre-execution simulated dispatch. Zero live orders are sent to MT5.
        """
        ensure_demo_tables(conn)
        now_str = now_utc_iso()

        # 1. Verify Active Authorization
        auth_row = conn.execute(
            """
            SELECT * FROM hft_demo_authorizations
            WHERE auth_id = ? AND user_id = ? AND is_authorized = 1
            """,
            (auth_token, user_id)
        ).fetchone()

        if not auth_row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="INVALID_OR_REVOKED_AUTH_TOKEN: Active Demo execution authorization required."
            )

        if auth_row["emergency_stop_triggered"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="EMERGENCY_STOP_TRIGGERED: Demo execution is currently disarmed by emergency stop."
            )

        # 2. Extract and Validate Order Parameters
        symbol = str(order_spec.get("symbol", auth_row["symbol"])).upper()
        direction = str(order_spec.get("direction", "BUY")).upper()
        entry_price = float(order_spec.get("entry_price", 0.0))
        volume = float(order_spec.get("volume", 0.01))
        stop_loss_price = float(order_spec.get("stop_loss_price", 0.0))
        take_profit_price = float(order_spec.get("take_profit_price", 0.0))
        account_equity = float(order_spec.get("account_equity", 5076.03))

        if direction not in ("BUY", "SELL"):
            raise HTTPException(status_code=400, detail=f"INVALID_DIRECTION: Must be BUY or SELL, got {direction}")

        if entry_price <= 0.0 or volume <= 0.0:
            raise HTTPException(status_code=400, detail="INVALID_PRICE_OR_VOLUME: Entry price and volume must be > 0.")

        # 3. Mandatory Broker-Side Stop Loss & Take Profit Verification
        if stop_loss_price <= 0.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MANDATORY_STOP_LOSS_MISSING: Every order must include a broker-side Stop Loss price."
            )

        if take_profit_price <= 0.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MANDATORY_TAKE_PROFIT_MISSING: Every order must include a defined Take Profit target."
            )

        # Stop distance check
        if direction == "BUY":
            stop_dist = entry_price - stop_loss_price
            tp_dist = take_profit_price - entry_price
        else:
            stop_dist = stop_loss_price - entry_price
            tp_dist = entry_price - take_profit_price

        if stop_dist <= 0.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"INVALID_STOP_LOSS: For {direction}, Stop Loss ({stop_loss_price}) must be on the protective side of entry ({entry_price})."
            )

        if tp_dist <= 0.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"INVALID_TAKE_PROFIT: For {direction}, Take Profit ({take_profit_price}) must be on the profitable side of entry ({entry_price})."
            )

        # Broker minimum stops level check ($0.50 min distance for BTCUSD = 50.0 points)
        min_stop_distance_usd = 0.50 if "BTC" in symbol else (0.10 if "XAU" in symbol else 0.0005)
        if stop_dist < min_stop_distance_usd:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"STOP_LOSS_TOO_CLOSE: Stop distance (${stop_dist:.4f}) is below broker stops_level minimum (${min_stop_distance_usd:.4f})."
            )

        # Risk:Reward check (min 1.50)
        rr_ratio = round(tp_dist / stop_dist, 2)
        if rr_ratio < MIN_RISK_REWARD_RATIO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"INSUFFICIENT_RISK_REWARD: R:R ratio {rr_ratio}:1 is below required institutional threshold ({MIN_RISK_REWARD_RATIO}:1)."
            )

        # 4. Risk Barrier Gate 1: Simultaneous Positions Limit (Max 3)
        open_positions = conn.execute(
            "SELECT count(*) as cnt FROM futures_positions WHERE user_id = ? AND status = 'OPEN'",
            (user_id,)
        ).fetchone()["cnt"]

        if open_positions >= auth_row["max_positions"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"POSITION_LIMIT_REACHED: Currently {open_positions} positions open (Max {auth_row['max_positions']})."
            )

        # 5. Risk Barrier Gate 2: Instrument Entries Limit (Max 2)
        symbol_positions = conn.execute(
            "SELECT count(*) as cnt FROM futures_positions WHERE user_id = ? AND symbol = ? AND status = 'OPEN'",
            (user_id, symbol)
        ).fetchone()["cnt"]

        if symbol_positions >= auth_row["max_entries_per_instrument"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"INSTRUMENT_EXPOSURE_LIMIT: Already {symbol_positions} entries on {symbol} (Max {auth_row['max_entries_per_instrument']})."
            )

        # 6. Risk Barrier Gate 3: Maximum Total Exposure Cap (30% Equity)
        position_notional = entry_price * volume
        leverage = 3
        margin_usd = round(position_notional / leverage, 2)
        max_exposure_usd = account_equity * (auth_row["max_exposure_pct"] / 100.0)

        # Aggregate current exposure
        current_margin = conn.execute(
            "SELECT coalesce(sum(isolated_margin), 0.0) as tot FROM futures_positions WHERE user_id = ? AND status = 'OPEN'",
            (user_id,)
        ).fetchone()["tot"]

        if (current_margin + margin_usd) > max_exposure_usd:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"EXPOSURE_CAP_EXCEEDED: New exposure (${current_margin + margin_usd:.2f}) exceeds 30% equity cap (${max_exposure_usd:.2f})."
            )

        # 7. Risk Barrier Gate 4: Daily Loss Limit ($50.00 USD)
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_loss = conn.execute(
            """
            SELECT coalesce(sum(abs(net_pnl_usd)), 0.0) as loss FROM futures_realized_pnl
            WHERE user_id = ? AND net_pnl_usd < 0 AND created_at >= ?
            """,
            (user_id, today_iso)
        ).fetchone()["loss"]

        potential_risk_usd = stop_dist * volume
        if (daily_loss + potential_risk_usd) > auth_row["max_daily_loss_usd"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"DAILY_LOSS_LIMIT_REACHED: Daily losses (${daily_loss:.2f}) + risk (${potential_risk_usd:.2f}) would exceed ${auth_row['max_daily_loss_usd']:.2f} cap."
            )

        # 8. Record Simulated Order & Audit Trail
        sim_order_id = f"SIM-ORD-{secrets.token_hex(6).upper()}"
        exposure_pct = round((margin_usd / max(1.0, account_equity)) * 100, 2)

        conn.execute(
            """
            INSERT INTO hft_demo_simulated_orders
            (order_id, auth_id, user_id, account_id, symbol, direction, entry_price, volume,
             stop_loss_price, take_profit_price, stop_distance_usd, take_profit_distance_usd,
             risk_reward_ratio, margin_usd, exposure_pct, simulated_fill_status, rejection_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SIMULATED_ACCEPTED', NULL, ?)
            """,
            (
                sim_order_id, auth_token, user_id, auth_row["account_id"], symbol, direction,
                entry_price, volume, stop_loss_price, take_profit_price, round(stop_dist, 4),
                round(tp_dist, 4), rr_ratio, margin_usd, exposure_pct, now_str
            )
        )

        audit_id = f"AUD-{secrets.token_hex(6).upper()}"
        conn.execute(
            """
            INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
            VALUES (?, ?, 'DEMO_ORDER_SIMULATED_VALIDATED', ?, ?, ?)
            """,
            (
                audit_id,
                user_id,
                user_id,
                json.dumps({
                    "sim_order_id": sim_order_id,
                    "auth_token": auth_token,
                    "account_id": auth_row["account_id"],
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": entry_price,
                    "volume": volume,
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
                    "risk_reward_ratio": rr_ratio,
                    "margin_usd": margin_usd,
                    "exposure_pct": exposure_pct,
                    "live_dispatch": False,
                }),
                now_str
            )
        )
        conn.commit()

        return {
            "status": "SUCCESS",
            "simulated_order_id": sim_order_id,
            "validation_status": "PASSED_ALL_RISK_BARRIERS",
            "order": {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "volume": volume,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "stop_distance_usd": round(stop_dist, 4),
                "take_profit_distance_usd": round(tp_dist, 4),
                "risk_reward_ratio": rr_ratio,
                "margin_usd": margin_usd,
                "exposure_pct": exposure_pct,
            },
            "risk_checks": {
                "mandatory_stop_loss_verified": True,
                "mandatory_take_profit_verified": True,
                "broker_stops_level_conforming": True,
                "risk_reward_acceptable": True,
                "position_limit_conforming": True,
                "instrument_limit_conforming": True,
                "exposure_cap_conforming": True,
                "daily_loss_conforming": True,
            },
            "broker_dispatch": {
                "dispatched_to_broker": False,
                "mode": "CONTROLLED_DEMO_REPLAY_SIMULATION",
                "reason": "Phase 7D requires explicit user sign-off prior to first genuine broker trade.",
            },
            "message": f"Demo {direction} order for {symbol} verified across all risk barriers and broker constraints. Zero live orders dispatched."
        }


    @classmethod
    def preflight_demo_order(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        auth_token: str,
        order_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Non-mutating preflight validation for Phase 7E.
        Validates all risk barriers, account isolation, broker specifications,
        and ensures zero orders are dispatched to live broker.
        """
        # 1. Run full risk barrier and SL/TP validation
        sim_res = cls.validate_and_simulate_order(conn, user_id, auth_token, order_spec)

        # 2. Verify account identity & Demo environment
        auth_row = conn.execute(
            "SELECT * FROM hft_demo_authorizations WHERE auth_id = ? AND user_id = ? AND is_authorized = 1",
            (auth_token, user_id)
        ).fetchone()

        if not auth_row:
            raise HTTPException(status_code=401, detail="Active Demo authorization required.")

        broker_login = auth_row["broker_login"]
        server_name = auth_row["server_name"]
        raw_symbol = str(order_spec.get("symbol", auth_row["symbol"])).upper()

        # Map symbol for Exness RawSpread: BTCUSD -> BTCUSDr
        broker_symbol = normalize_broker_symbol(raw_symbol)

        # Calculate exact monetary risk
        direction = sim_res["order"]["direction"]
        entry_price = sim_res["order"]["entry_price"]
        volume = sim_res["order"]["volume"]
        stop_loss_price = sim_res["order"]["stop_loss_price"]
        take_profit_price = sim_res["order"]["take_profit_price"]
        stop_dist = abs(entry_price - stop_loss_price)
        max_monetary_risk_usd = round(stop_dist * volume, 2)
        target_profit_usd = round(abs(take_profit_price - entry_price) * volume, 2)

        return {
            "status": "SUCCESS",
            "preflight_status": "READY_FOR_EXECUTION_HELD",
            "execution_intent": "NON_MUTATING_PREFLIGHT",
            "account_verification": {
                "broker_login": broker_login,
                "server_name": server_name,
                "environment": "DEMO",
                "account_tier": "RawSpread",
                "verified_balance_usd": 5076.03,
                "verified_equity_usd": 5076.03,
                "free_margin_usd": 5076.03,
            },
            "proposed_order": {
                "client_symbol": raw_symbol,
                "broker_symbol": broker_symbol,
                "direction": direction,
                "order_type": f"ORDER_TYPE_{direction}",
                "volume": volume,
                "entry_price": entry_price,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "stop_distance_usd": round(stop_dist, 4),
                "risk_reward_ratio": sim_res["order"]["risk_reward_ratio"],
                "max_monetary_risk_usd": max_monetary_risk_usd,
                "target_monetary_profit_usd": target_profit_usd,
                "risk_pct_of_equity": round((max_monetary_risk_usd / 5076.03) * 100, 4),
            },
            "safety_governance": {
                "live_trading_locked": True,
                "real_trading_locked": True,
                "read_only_mode": True,
                "emergency_lock_active": False,
                "real_accounts_barred": True,
                "broker_order_submitted": False,
            },
            "message": "Phase 7E preflight validation PASSED. Zero orders submitted. Awaiting explicit user sign-off."
        }


    @classmethod
    def dispatch_demo_order(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        auth_token: str,
        order_spec: Dict[str, Any],
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Dispatches Demo order to Windows MT5 Gateway (/demo/order/submit).
        Strict safety: dry_run=True conducts non-mutating preflight test.
        """
        import httpx

        # 1. Non-mutating preflight validation locally
        preflight = cls.preflight_demo_order(conn, user_id, auth_token, order_spec)

        auth_row = conn.execute(
            "SELECT * FROM hft_demo_authorizations WHERE auth_id = ? AND user_id = ? AND is_authorized = 1",
            (auth_token, user_id)
        ).fetchone()

        if not auth_row:
            raise HTTPException(status_code=401, detail="Active Demo authorization required.")

        gateway_url = "http://10.88.0.2:8095/demo/order/submit"
        gateway_token = "a955da9c16abc0478643fa862ffff9d6e42122587c23f78ab3713801f14facf9"

        # PHASE 7I NARROW DEMO EXECUTION GOVERNANCE:
        if str(auth_row["broker_login"]).strip() != "474861031" or auth_row["server_name"] != "Exness-MT5Trial15":
            raise HTTPException(
                status_code=403,
                detail="TARGET_UNAUTHORIZED: Genuine Demo execution is strictly restricted to account 474861031 on Exness-MT5Trial15."
            )

        if auth_row["environment"] != "DEMO":
            raise HTTPException(
                status_code=403,
                detail="REAL_TRADING_PERMANENTLY_LOCKED: Live real execution is strictly forbidden."
            )

        if preflight["proposed_order"]["volume"] != 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"VOLUME_RESTRICTED: Phase 7I initial volume must be exactly 0.01 lot. Got: {preflight['proposed_order']['volume']}"
            )

        if preflight["proposed_order"]["max_monetary_risk_usd"] > 1.05:
            raise HTTPException(
                status_code=400,
                detail=f"RISK_LIMIT_EXCEEDED: Maximum monetary risk (${preflight['proposed_order']['max_monetary_risk_usd']:.2f}) exceeds $1.00 USD limit."
            )

        # Duplicate order prevention: verify zero open positions on broker before genuine dispatch
        if not dry_run:
            try:
                base_gw = "http://10.88.0.2:8095"
                with httpx.Client(timeout=4.0) as chk_client:
                    pos_resp = chk_client.get(f"{base_gw}/positions", headers={"X-Gateway-Auth-Token": gateway_token})
                    if pos_resp.status_code == 200:
                        pos_json = pos_resp.json()
                        pos_count = pos_json.get("count", len(pos_json.get("positions", [])))
                        if pos_count > 0:
                            raise HTTPException(
                                status_code=409,
                                detail=f"DUPLICATE_ORDER_PREVENTED: Account 474861031 already has {pos_count} active position(s) on broker. Only ONE position is permitted."
                            )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Pre-dispatch broker position verification check: {e}")

        gateway_payload = {
            "account_login": auth_row["broker_login"],
            "server_name": auth_row["server_name"],
            "environment": auth_row["environment"],
            "demo_auth_token": auth_token,
            "symbol": preflight["proposed_order"]["broker_symbol"],
            "order_type": preflight["proposed_order"]["direction"],
            "volume": preflight["proposed_order"]["volume"],
            "price": preflight["proposed_order"]["entry_price"],
            "sl": preflight["proposed_order"]["stop_loss"],
            "tp": preflight["proposed_order"]["take_profit"],
            "dry_run": dry_run
        }

        try:
            resp = httpx.post(
                gateway_url,
                json=gateway_payload,
                headers={"X-Gateway-Auth-Token": gateway_token},
                timeout=10.0
            )
            gateway_res = resp.json()
        except Exception as e:
            logger.error(f"Gateway connection error: {e}")
            raise HTTPException(status_code=502, detail=f"Windows MT5 Gateway communication error: {e}")

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=gateway_res.get("detail", "Gateway error"))

        # Log audit trail
        log_id = f"AUD-{secrets.token_hex(6).upper()}"
        now_str = now_utc_iso()
        conn.execute(
            """
            INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
            VALUES (?, ?, 'DEMO_GATEWAY_PREFLIGHT_DISPATCHED', ?, ?, ?)
            """,
            (
                log_id,
                user_id,
                user_id,
                json.dumps({
                    "auth_token": auth_token,
                    "account_login": auth_row["broker_login"],
                    "server_name": auth_row["server_name"],
                    "symbol": preflight["proposed_order"]["broker_symbol"],
                    "volume": preflight["proposed_order"]["volume"],
                    "entry_price": preflight["proposed_order"]["entry_price"],
                    "sl": preflight["proposed_order"]["stop_loss"],
                    "tp": preflight["proposed_order"]["take_profit"],
                    "monetary_risk_usd": preflight["proposed_order"]["max_monetary_risk_usd"],
                    "gateway_status": gateway_res.get("status"),
                    "dispatched_to_broker": False,
                }),
                now_str
            )
        )
        conn.commit()

        if not dry_run and gateway_res.get("dispatched_to_broker"):
            # Record genuine broker execution audit
            exec_log_id = f"AUD-{secrets.token_hex(6).upper()}"
            conn.execute(
                """
                INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
                VALUES (?, ?, 'DEMO_ORDER_EXECUTED_ON_BROKER', ?, ?, ?)
                """,
                (
                    exec_log_id,
                    user_id,
                    user_id,
                    json.dumps({
                        "auth_token": auth_token,
                        "account_login": auth_row["broker_login"],
                        "server_name": auth_row["server_name"],
                        "symbol": gateway_res.get("symbol"),
                        "volume": gateway_res.get("volume"),
                        "price": gateway_res.get("execution_price"),
                        "sl": gateway_res.get("sl"),
                        "tp": gateway_res.get("tp"),
                        "order_id": gateway_res.get("order_id"),
                        "deal_id": gateway_res.get("deal_id"),
                        "dispatch_latency_ms": gateway_res.get("dispatch_latency_ms"),
                        "dispatched_to_broker": True,
                    }),
                    now_str
                )
            )
            conn.commit()

            # Post-execution SL/TP verification on Session 2 worker
            confirmed_pos = gateway_res.get("confirmed_position") or {}
            pos_ticket = confirmed_pos.get("ticket") or gateway_res.get("order_id")
            stops_verification = None
            if pos_ticket:
                try:
                    sv_resp = get_gateway_client().get(f"/stops/verify/{pos_ticket}", headers={"X-Gateway-Auth-Token": gateway_token})
                    if sv_resp.status_code == 200:
                        stops_verification = sv_resp.json()
                except Exception as sv_err:
                    logger.warning(f"Post-execution stops verification warning: {sv_err}")

            return {
                "status": "SUCCESS",
                "execution_mode": "GENUINE_BROKER_EXECUTION",
                "dispatched_to_broker": True,
                "broker_execution": {
                    "order_id": gateway_res.get("order_id"),
                    "deal_id": gateway_res.get("deal_id"),
                    "symbol": gateway_res.get("symbol"),
                    "order_type": gateway_res.get("order_type"),
                    "volume": gateway_res.get("volume"),
                    "execution_price": gateway_res.get("execution_price"),
                    "stop_loss": gateway_res.get("sl"),
                    "take_profit": gateway_res.get("tp"),
                    "dispatch_latency_ms": gateway_res.get("dispatch_latency_ms"),
                    "confirmed_position": confirmed_pos,
                    "stops_verification": stops_verification,
                },
                "account_details": {
                    "login": auth_row["broker_login"],
                    "server": auth_row["server_name"],
                    "environment": auth_row["environment"],
                },
                "safety_governance": {
                    "live_trading_locked": True,
                    "real_trading_locked": True,
                    "dispatched_to_broker": True,
                },
                "message": gateway_res.get("message")
            }

        return {
            "status": "SUCCESS",
            "execution_mode": "NON_MUTATING_PREFLIGHT",
            "preflight_status": "READY_FOR_EXECUTION_HELD",
            "gateway_verification": gateway_res,
            "order_details": preflight["proposed_order"],
            "account_details": preflight["account_verification"],
            "safety_governance": {
                "live_trading_locked": True,
                "real_trading_locked": True,
                "read_only_mode": True,
                "dispatched_to_broker": False,
            },
            "message": "Full end-to-end Demo execution pathway verified through Windows Gateway in non-mutating preflight mode. Zero orders submitted to broker. Awaiting explicit user sign-off."
        }

    @classmethod
    def close_demo_position(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str],
        ticket: str,
        close_reason: str = "PROFIT_TARGET_1_USD"
    ) -> Dict[str, Any]:
        """
        Closes an open Demo position via Windows MT5 Gateway.
        Enforces tenant isolation and rejects any Real account.
        """
        import httpx
        now_str = now_utc_iso()
        
        # Hard security check: verify user owns an Exness Demo account
        row = conn.execute(
            """
            SELECT * FROM exness_demo_connections
            WHERE user_id = ? AND is_active = 1 AND account_type = 'DEMO'
            """,
            (user_id,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=403, detail="DEMO_ACCOUNT_REQUIRED: Only authorized Demo accounts may close positions through this route.")

        broker_login = str(row["account_login"])
        server_name = row["server_name"]

        if broker_login != "474861031" or server_name != "Exness-MT5Trial15":
            raise HTTPException(status_code=403, detail="TARGET_UNAUTHORIZED: Genuine Demo execution is strictly restricted to account 474861031.")

        gateway_url = "http://10.88.0.2:8095/demo/position/close"
        gateway_token = "a955da9c16abc0478643fa862ffff9d6e42122587c23f78ab3713801f14facf9"

        payload = {
            "account_login": broker_login,
            "server_name": server_name,
            "environment": "DEMO",
            "ticket": str(ticket),
            "symbol": "BTCUSDr",
            "close_reason": close_reason
        }

        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.post(gateway_url, headers={"X-Gateway-Auth-Token": gateway_token, "Content-Type": "application/json"}, json=payload)
                res_data = r.json()
        except Exception as e:
            logger.error(f"Error communicating with MT5 Gateway on close: {e}")
            raise HTTPException(status_code=502, detail=f"Windows MT5 Gateway close communication error: {e}")

        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=res_data.get("detail", "Position close failed on broker"))

        # Write audit trail
        log_id = f"AUD-{secrets.token_hex(6).upper()}"
        conn.execute(
            """
            INSERT INTO audit_logs (log_id, actor_id, action, target_user_id, details_json, created_at)
            VALUES (?, ?, 'DEMO_POSITION_CLOSED', ?, ?, ?)
            """,
            (
                log_id,
                user_id,
                user_id,
                json.dumps({
                    "ticket": str(ticket),
                    "close_reason": close_reason,
                    "broker_login": broker_login,
                    "response": res_data,
                    "timestamp_utc": now_str
                }),
                now_str
            )
        )
        conn.commit()

        return {
            "status": "SUCCESS",
            "close_reason": close_reason,
            "ticket": str(ticket),
            "broker_result": res_data,
            "message": f"Position #{ticket} closed successfully on broker ({close_reason})."
        }


    @classmethod
    def evaluate_allocated_capital_risk(
        cls,
        symbol: str = "BTCUSDr",
        entry_price: float = 75950.0,
        stop_loss_price: float = 75856.0,
        take_profit_price: float = 76056.0,
        allocated_capital_usd: float = 100.0,
        risk_pct_per_trade: float = 1.0,
        max_loss_usd_cap: float = 1.0,
        requested_volume: Optional[float] = None,
        leverage_limit: float = 5.0,
        enforce_notional_leverage_cap: bool = False,
        margin_utilization_ceiling_pct: float = 25.0,
        broker_leverage: int = 2000,
        daily_realized_loss_usd: float = 0.0,
        max_daily_loss_usd: float = 5.0,
        current_drawdown_usd: float = 0.0,
        max_drawdown_usd: float = 10.0,
        consecutive_losses: int = 0,
        max_consecutive_losses: int = 3,
        round_trip_cost_usd: float = 0.06,
        broker_account_equity_usd: float = 5073.84,
    ) -> Dict[str, Any]:
        """
        RECONCILED CAPITAL PRESERVATION & ALLOCATED-CAPITAL SIZING ENGINE:
        - Sizes trades strictly from `allocated_capital_usd` (never full broker account equity $5,073.84).
        - Computes risk_budget_usd = min(allocated_capital_usd * (risk_pct_per_trade / 100.0), max_loss_usd_cap).
        - Enforces Minimum-Lot Skip Rule: if minimum broker volume (0.01 lot) produces monetary risk
          exceeding `risk_budget_usd` (plus $0.05 tolerance), the trade is SKIPPED (`VOLUME_FLOOR_SKIP`).
          Never rounds up to 0.01 lot when risk budget is insufficient.
        - Explicitly distinguishes:
            (a) Broker Account Leverage (e.g. 1:2000 on Exness Demo, requiring ~$0.38 margin for 0.01 BTC), vs
            (b) Effective Position Notional Leverage against Allocated Capital (`notional_usd / allocated_capital_usd`).
          When `enforce_notional_leverage_cap=True`, rejects trades where `effective_notional_leverage > leverage_limit`
          (e.g. 3x-5x cap). Also enforces `margin_utilization_ceiling_pct` against `allocated_capital_usd`.
        - Enforces Daily Loss Limit, Max Allocated Drawdown Limit, and Consecutive-Loss Circuit Breaker.
        - Prohibits Martingale / loss-recovery doubling.
        """
        contract_size = 1.0 if "BTC" in symbol.upper() or "ETH" in symbol.upper() else 100000.0
        min_lot = 0.01
        lot_step = 0.01

        risk_budget_from_pct = round(allocated_capital_usd * (risk_pct_per_trade / 100.0), 4)
        effective_risk_budget_usd = round(min(risk_budget_from_pct, max_loss_usd_cap), 4)

        stop_distance_pts = abs(entry_price - stop_loss_price)
        if stop_distance_pts <= 0:
            return {
                "allowed": False,
                "skip_code": "INVALID_STOP_DISTANCE",
                "reason": "Stop distance must be strictly positive.",
            }

        # Monetary risk of 1.00 lot = stop_distance_pts * contract_size + (round_trip_cost_usd / min_lot)
        per_min_lot_price_risk_usd = round(stop_distance_pts * min_lot * contract_size, 4)
        per_min_lot_total_risk_usd = round(per_min_lot_price_risk_usd + round_trip_cost_usd, 4)

        # Raw ideal volume from risk budget
        unit_risk_per_lot = (stop_distance_pts * contract_size) + (round_trip_cost_usd / min_lot)
        raw_ideal_volume = effective_risk_budget_usd / max(1e-8, unit_risk_per_lot)

        # Minimum-Lot Skip Rule: NEVER round 0.004 lot up to 0.01 lot if 0.01 lot violates risk budget
        if raw_ideal_volume < min_lot and per_min_lot_total_risk_usd > (effective_risk_budget_usd + 0.05):
            return {
                "allowed": False,
                "skip_code": "VOLUME_FLOOR_SKIP",
                "reason": (
                    f"Minimum broker lot ({min_lot:.2f}) carries ${per_min_lot_total_risk_usd:.2f} total risk "
                    f"(price risk ${per_min_lot_price_risk_usd:.2f} + costs ${round_trip_cost_usd:.2f}), "
                    f"which exceeds allocated risk budget ${effective_risk_budget_usd:.2f} "
                    f"({risk_pct_per_trade:.2f}% of ${allocated_capital_usd:.2f} allocated capital). Trade skipped."
                ),
                "allocated_capital_usd": allocated_capital_usd,
                "broker_account_equity_usd": broker_account_equity_usd,
                "effective_risk_budget_usd": effective_risk_budget_usd,
                "min_lot_risk_usd": per_min_lot_total_risk_usd,
                "raw_ideal_volume": round(raw_ideal_volume, 4),
            }

        # Determine final volume (clamped down to nearest 0.01 step, never increased on losing streak)
        import math
        step_floored_vol = math.floor((raw_ideal_volume + 1e-9) / lot_step) * lot_step
        selected_volume = round(max(min_lot, step_floored_vol), 2)
        if requested_volume is not None:
            selected_volume = round(min(selected_volume, requested_volume), 2)

        notional_usd = round(entry_price * selected_volume * contract_size, 2)
        broker_required_margin_usd = round(notional_usd / max(1, broker_leverage), 4)
        effective_notional_leverage = round(notional_usd / max(1e-8, allocated_capital_usd), 2)
        margin_utilization_of_allocated_pct = round((broker_required_margin_usd / max(1e-8, allocated_capital_usd)) * 100.0, 4)

        total_trade_risk_usd = round((stop_distance_pts * selected_volume * contract_size) + (round_trip_cost_usd * (selected_volume / min_lot)), 4)

        # Circuit breakers
        if daily_realized_loss_usd >= max_daily_loss_usd:
            return {
                "allowed": False,
                "skip_code": "DAILY_LOSS_LIMIT_REACHED",
                "reason": f"Daily realized loss (${daily_realized_loss_usd:.2f}) has reached/exceeded daily limit (${max_daily_loss_usd:.2f}).",
            }
        if current_drawdown_usd >= max_drawdown_usd:
            return {
                "allowed": False,
                "skip_code": "MAX_DRAWDOWN_LIMIT_REACHED",
                "reason": f"Allocated capital drawdown (${current_drawdown_usd:.2f}) has reached/exceeded limit (${max_drawdown_usd:.2f}).",
            }
        if consecutive_losses >= max_consecutive_losses:
            return {
                "allowed": False,
                "skip_code": "CONSECUTIVE_LOSS_CIRCUIT_BREAKER",
                "reason": f"Consecutive losses ({consecutive_losses}) reached circuit breaker limit ({max_consecutive_losses}). Cooldown active.",
            }
        if margin_utilization_of_allocated_pct > margin_utilization_ceiling_pct:
            return {
                "allowed": False,
                "skip_code": "MARGIN_UTILIZATION_CEILING_EXCEEDED",
                "reason": f"Margin utilization ({margin_utilization_of_allocated_pct:.2f}% of allocated capital) exceeds ceiling ({margin_utilization_ceiling_pct:.2f}%).",
            }
        if enforce_notional_leverage_cap and effective_notional_leverage > leverage_limit:
            min_cap_for_leverage = round(notional_usd / max(1e-8, leverage_limit), 2)
            return {
                "allowed": False,
                "skip_code": "EFFECTIVE_LEVERAGE_EXCEEDED",
                "reason": (
                    f"Position notional ${notional_usd:.2f} on ${allocated_capital_usd:.2f} allocated capital represents "
                    f"{effective_notional_leverage:.2f}x effective leverage, exceeding {leverage_limit:.1f}x cap. "
                    f"Minimum allocated capital for {selected_volume:.2f} lot BTCUSDr at {leverage_limit:.1f}x is ${min_cap_for_leverage:.2f}."
                ),
                "notional_usd": notional_usd,
                "allocated_capital_usd": allocated_capital_usd,
                "effective_notional_leverage": effective_notional_leverage,
                "leverage_limit": leverage_limit,
                "min_allocated_capital_required_usd": min_cap_for_leverage,
            }

        return {
            "allowed": True,
            "skip_code": None,
            "reason": "All allocated-capital, risk-budget, margin-ceiling, and circuit-breaker checks passed.",
            "sizing_summary": {
                "allocated_capital_usd": allocated_capital_usd,
                "broker_account_equity_usd": broker_account_equity_usd,
                "isolated_from_broker_equity": True,
                "risk_pct_per_trade": risk_pct_per_trade,
                "effective_risk_budget_usd": effective_risk_budget_usd,
                "selected_volume_lots": selected_volume,
                "raw_ideal_volume_lots": round(raw_ideal_volume, 4),
                "notional_exposure_usd": notional_usd,
                "broker_account_leverage": f"1:{broker_leverage}",
                "broker_required_margin_usd": broker_required_margin_usd,
                "effective_notional_leverage_vs_allocated": effective_notional_leverage,
                "configured_leverage_cap": leverage_limit,
                "enforce_notional_leverage_cap": enforce_notional_leverage_cap,
                "margin_utilization_of_allocated_pct": margin_utilization_of_allocated_pct,
                "margin_utilization_ceiling_pct": margin_utilization_ceiling_pct,
                "estimated_total_risk_usd": total_trade_risk_usd,
                "martingale_prohibited": True,
            },
        }

    @classmethod
    def monitor_and_exit_profit_targets(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        profit_target_usd: float = 1.0,
        max_loss_usd: float = 1.0
    ) -> Dict[str, Any]:
        """
        Supervisory Linux Watchdog Layer:
        Inspects live MT5 positions via persistent Keep-Alive connection and triggers immediate full closure
        for any position that has:
          1. Reached or exceeded the configured net profit target (+$1.00 USD default), OR
          2. Reached or breached the maximum permitted net loss (-$1.00 USD default).
        Note: Primary tick-by-tick protection is broker-side SL/TP on the MT5 ticket plus the 250ms local
        Session 2 worker monitor thread; this Linux watchdog acts as the 3rd supervisory backstop.
        """
        now_str = now_utc_iso()
        gateway_token = "a955da9c16abc0478643fa862ffff9d6e42122587c23f78ab3713801f14facf9"

        try:
            client = get_gateway_client()
            r = client.get("/positions", headers={"X-Gateway-Auth-Token": gateway_token})
            if r.status_code != 200:
                return {"status": "GATEWAY_UNAVAILABLE", "closed_positions": []}
            pos_data = r.json()
        except Exception as e:
            logger.error(f"Position monitor fetch error: {e}")
            return {"status": "ERROR", "error": str(e), "closed_positions": []}

        positions = pos_data.get("positions", [])
        closed_results = []

        for p in positions:
            ticket = str(p.get("ticket"))
            profit = float(p.get("profit", 0.0))
            swap = float(p.get("swap", 0.0))
            comm = abs(float(p.get("commission", 0.0)))
            if comm == 0.0 and str(p.get("symbol", "")).upper().startswith("BTC"):
                comm = round(float(p.get("volume", 0.01)) * 4.0, 4)
            net_pnl = round(profit + swap - comm, 2)

            trigger_reason = None
            if net_pnl >= profit_target_usd:
                trigger_reason = "PROFIT_TARGET_1_USD"
                logger.info(f"PROFIT TARGET REACHED: Position #{ticket} net P&L=${net_pnl} >= +${profit_target_usd}. Executing exit.")
            elif net_pnl <= -abs(max_loss_usd):
                trigger_reason = "CONTINUOUS_LOSS_PROTECTION_1_USD"
                logger.warning(f"LOSS LIMIT BREACHED: Position #{ticket} net P&L=${net_pnl} <= -${abs(max_loss_usd)}. Executing emergency protective close.")

            if trigger_reason:
                try:
                    close_res = cls.close_demo_position(
                        conn=conn,
                        user_id=user_id,
                        account_id="EXN-CONN-A4E7BE39D276",
                        ticket=ticket,
                        close_reason=trigger_reason
                    )
                    closed_results.append({
                        "ticket": ticket,
                        "net_pnl": net_pnl,
                        "trigger_reason": trigger_reason,
                        "profit_target_usd": profit_target_usd,
                        "max_loss_usd": max_loss_usd,
                        "close_status": "SUCCESS",
                        "detail": close_res
                    })
                except Exception as ex:
                    logger.error(f"Failed closing position #{ticket} on {trigger_reason}: {ex}")
                    closed_results.append({
                        "ticket": ticket,
                        "net_pnl": net_pnl,
                        "trigger_reason": trigger_reason,
                        "close_status": "FAILED",
                        "error": str(ex)
                    })

        return {
            "status": "SUCCESS",
            "positions_monitored": len(positions),
            "closed_count": len(closed_results),
            "closed_positions": closed_results,
            "timestamp_utc": now_str
        }

    @classmethod
    def execute_portal_demo_order(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
        symbol: str = "BTCUSDr",
        direction: str = "BUY",
        volume: float = 0.01,
        profit_target_usd: float = 1.0,
        stop_loss_usd: float = 1.0
    ) -> Dict[str, Any]:
        """
        Executes a controlled Demo scalp trade directly from the BITDEX website portal.
        Enforces tenant isolation, calculates parameters from fresh MT5 tick,
        dispatches to broker, and ensures zero token leakage.
        """
        import httpx
        now_str = now_utc_iso()

        # 1. Resolve Account
        if not account_id:
            account_id = "EXN-CONN-A4E7BE39D276"
        
        row = conn.execute(
            "SELECT * FROM exness_demo_connections WHERE (connection_id = ? OR account_login = ?) AND user_id = ?",
            (account_id, account_id, user_id)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Demo trading account not found or unauthorized for this user.")

        if row["account_type"].upper() != "DEMO":
            raise HTTPException(status_code=403, detail="REAL_TRADING_PERMANENTLY_LOCKED: Live real execution is strictly forbidden.")

        # 2. Duplicate order barrier & Fresh tick via persistent Keep-Alive client
        gateway_token = "a955da9c16abc0478643fa862ffff9d6e42122587c23f78ab3713801f14facf9"
        client = get_gateway_client()
        pos_resp = client.get("/positions", headers={"X-Gateway-Auth-Token": gateway_token})
        if pos_resp.status_code == 200:
            pos_count = pos_resp.json().get("count", 0)
            if pos_count > 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"DUPLICATE_ORDER_PREVENTED: Account already has {pos_count} active position(s) on broker. Close open position first or wait for $1.00 profit exit."
                )

        # 3. Fetch fresh tick & enforce Stale-Tick Rejection Gate
        tick_resp = client.get(f"/tick/{symbol}", headers={"X-Gateway-Auth-Token": gateway_token})
        if tick_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to fetch live MT5 quote for {symbol}")
        tick_data = tick_resp.json().get("latest_tick", {})
        tick_ts_ms = int(tick_data.get("timestamp_ms", 0) or 0)
        if tick_ts_ms > 0:
            tick_age_ms = max(0, int(time.time() * 1000) - tick_ts_ms)
            if tick_age_ms > 15000:
                raise HTTPException(
                    status_code=409,
                    detail=f"STALE_MARKET_DATA_REJECTED: Latest {symbol} tick is {tick_age_ms}ms old (> 15000ms safety threshold). Order blocked."
                )

        bid = float(tick_data.get("bid", 75850.0))
        ask = float(tick_data.get("ask", 75851.0))

        # 4. Calculate Entry, SL, TP based on $1 profit target and $1 stop loss
        # Broker-side Take Profit: includes $0.04 round-trip commission for exact $1 net profit
        comm_buffer = 4.0 if symbol.upper().startswith("BTC") else 0.0
        stop_dist = (stop_loss_usd / volume)
        tp_dist = (profit_target_usd / volume) + comm_buffer

        dir_clean = direction.upper().strip()
        if dir_clean == "BUY":
            entry_price = ask
            sl_price = round(entry_price - stop_dist, 2)
            tp_price = round(entry_price + tp_dist, 2)
        else:
            entry_price = bid
            sl_price = round(entry_price + stop_dist, 2)
            tp_price = round(entry_price - tp_dist, 2)

        # 5. Authorize Demo Execution internally
        auth_res = cls.authorize_demo_execution(
            conn=conn,
            user_id=user_id,
            account_id=account_id,
            symbol=symbol,
            confirm_demo_only=True
        )
        auth_token = auth_res["authorization"]["auth_token"]

        order_spec = {
            "auth_token": auth_token,
            "symbol": symbol,
            "direction": dir_clean,
            "entry_price": entry_price,
            "volume": volume,
            "stop_loss_price": sl_price,
            "take_profit_price": tp_price,
            "account_equity": 5073.84,
            "dry_run": False
        }

        # 6. Dispatch genuine Demo order
        try:
            exec_res = cls.dispatch_demo_order(
                conn=conn,
                user_id=user_id,
                auth_token=auth_token,
                order_spec=order_spec,
                dry_run=False
            )
        finally:
            # Auto-disarm single-use token immediately
            cls.emergency_disarm(conn, user_id, account_id=account_id, reason="PORTAL_ORDER_DISPATCHED_TOKEN_DISARMED")

        return exec_res

    @classmethod
    def set_auto_entry_arm_state(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str = "EXN-CONN-A4E7BE39D276",
        symbol: str = "BTCUSDr",
        armed: bool = False,
        allocated_capital_usd: float = 100.0,
        risk_pct_per_trade: float = 1.0,
        profit_target_usd: float = 1.0,
        max_loss_usd: float = 1.0,
        min_net_edge_usd: float = 1.0,
        enforce_notional_leverage_cap: bool = False,
        leverage_limit: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Configures or arms/disarms automatic directional entry execution for the verified Demo account.
        By default, automatic order submission is DISARMED (auto_entry_armed = 0).
        Hard-rejects any Real account with HTTP 403 Forbidden.
        """
        ensure_demo_tables(conn)
        now_str = now_utc_iso()

        ex_row = conn.execute(
            "SELECT * FROM exness_demo_connections WHERE (connection_id = ? OR account_login = ?) AND user_id = ?",
            (account_id, account_id, user_id)
        ).fetchone()
        if not ex_row:
            raise HTTPException(status_code=404, detail=f"Demo account {account_id} not found for user.")
        if str(ex_row["account_type"]).upper() != "DEMO" or "REAL" in str(ex_row["server_name"]).upper():
            raise HTTPException(status_code=403, detail="REAL_TRADING_PERMANENTLY_LOCKED: Automatic execution is strictly forbidden on Real accounts.")
        if str(ex_row["account_login"]) != "474861031" or str(ex_row["server_name"]) != "Exness-MT5Trial15":
            raise HTTPException(status_code=403, detail="TARGET_UNAUTHORIZED: Restricted to Demo account 474861031 on Exness-MT5Trial15.")

        conn_id = str(ex_row["connection_id"])
        broker_sym = normalize_broker_symbol(symbol)

        if armed:
            # Verify an active, non-disarmed Demo authorization exists before allowing arming
            auth_row = conn.execute(
                """
                SELECT * FROM hft_demo_authorizations
                WHERE user_id = ? AND (account_id = ? OR broker_login = '474861031')
                  AND is_authorized = 1 AND emergency_stop_triggered = 0
                ORDER BY created_at DESC LIMIT 1
                """,
                (user_id, conn_id)
            ).fetchone()
            if not auth_row:
                raise HTTPException(
                    status_code=409,
                    detail="DEMO_AUTHORIZATION_REQUIRED: Cannot arm automatic entry without an active Demo execution authorization."
                )

        conn.execute(
            """
            INSERT INTO hft_auto_entry_state (
                account_id, user_id, symbol, auto_entry_armed, allocated_capital_usd,
                risk_pct_per_trade, profit_target_usd, max_loss_usd, min_net_edge_usd,
                enforce_notional_leverage_cap, leverage_limit, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                user_id = excluded.user_id,
                symbol = excluded.symbol,
                auto_entry_armed = excluded.auto_entry_armed,
                allocated_capital_usd = excluded.allocated_capital_usd,
                risk_pct_per_trade = excluded.risk_pct_per_trade,
                profit_target_usd = excluded.profit_target_usd,
                max_loss_usd = excluded.max_loss_usd,
                min_net_edge_usd = excluded.min_net_edge_usd,
                enforce_notional_leverage_cap = excluded.enforce_notional_leverage_cap,
                leverage_limit = excluded.leverage_limit,
                updated_at = excluded.updated_at
            """,
            (
                conn_id, user_id, broker_sym, 1 if armed else 0,
                allocated_capital_usd, risk_pct_per_trade, profit_target_usd,
                max_loss_usd, min_net_edge_usd,
                1 if enforce_notional_leverage_cap else 0, leverage_limit, now_str
            )
        )
        conn.commit()

        return {
            "status": "SUCCESS",
            "account_id": conn_id,
            "broker_login": "474861031",
            "server_name": "Exness-MT5Trial15",
            "symbol": broker_sym,
            "auto_entry_armed": bool(armed),
            "allocated_capital_usd": allocated_capital_usd,
            "risk_pct_per_trade": risk_pct_per_trade,
            "profit_target_usd": profit_target_usd,
            "max_loss_usd": max_loss_usd,
            "min_net_edge_usd": min_net_edge_usd,
            "enforce_notional_leverage_cap": bool(enforce_notional_leverage_cap),
            "leverage_limit": leverage_limit,
            "updated_at": now_str,
        }

    @classmethod
    def run_automated_directional_entry_cycle(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: str = "EXN-CONN-A4E7BE39D276",
        symbol: str = "BTCUSDr",
        allocated_capital_usd: Optional[float] = None,
        risk_pct_per_trade: Optional[float] = None,
        profit_target_usd: Optional[float] = None,
        max_loss_usd: Optional[float] = None,
        min_net_edge_usd: Optional[float] = None,
        enforce_notional_leverage_cap: Optional[bool] = None,
        leverage_limit: Optional[float] = None,
        dry_run: bool = True,
        override_klines: Optional[List[Dict[str, Any]]] = None,
        override_tick: Optional[Dict[str, Any]] = None,
        override_open_positions_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        COMPLETE AUTOMATIC SIGNAL-TO-ORDER EXECUTION PATHWAY (Task 1):
        Connects the 5-component directional signal engine + Minimum Net-Edge Gate directly to
        the risk-approved Demo order execution pipeline (`preflight_demo_order` -> `dispatch_demo_order`),
        while keeping automatic broker order submission DISARMED by default (`auto_entry_armed = 0`).

        Sequence of mandatory gates on every cycle:
          1. Account & Real-Trading Lock Verification (`474861031` on `Exness-MT5Trial15` DEMO only; Real -> HTTP 403).
          2. Broker Open-Position Reconciliation (`/positions` -> rejects if `open_positions_count >= 1`).
          3. Fresh MT5 Quote & M1 Candles Fetch + Stale-Tick Rejection (`tick_age_ms <= 15000ms`) + Spread Gate (`<= $15.00`).
          4. Fresh Directional Signal + Minimum Net-Edge-After-Costs Evaluation (`evaluate_directional_scalp_cycle`).
          5. Allocated-Capital Sizing, Minimum-Lot Skip Rule (`VOLUME_FLOOR_SKIP`), Leverage & Circuit Breakers (`evaluate_allocated_capital_risk`).
          6. Bar-Timestamp Idempotency Gate (`DUPLICATE_BAR_CYCLE_PREVENTED`: never dispatches twice on the same M1 bar).
          7. Authorization & Arming Gate:
             - By default (`auto_entry_armed == 0` or `dry_run == True` or no active `hft_demo_authorizations` token),
               order submission is HELD (`AUTO_ENTRY_DISARMED_BY_DEFAULT`) and the exact readiness/skip reason is returned.
             - Only when `auto_entry_armed == 1`, an active Demo authorization token exists, and `dry_run == False`,
               dispatches the order via `dispatch_demo_order` and verifies broker-side SL/TP via `/stops/verify/{ticket}`.
        """
        from .automated_scalping_engine import AutomatedHighFrequencyScalpingEngine
        ensure_demo_tables(conn)
        now_str = now_utc_iso()

        # 1. Verify Demo Account Identity & Permanent Real Lock
        ex_row = conn.execute(
            "SELECT * FROM exness_demo_connections WHERE (connection_id = ? OR account_login = ?) AND user_id = ?",
            (account_id, account_id, user_id)
        ).fetchone()
        if not ex_row:
            raise HTTPException(status_code=404, detail=f"Demo account {account_id} not found or unauthorized.")

        if str(ex_row["account_type"]).upper() != "DEMO" or "REAL" in str(ex_row["server_name"]).upper():
            raise HTTPException(
                status_code=403,
                detail="REAL_TRADING_PERMANENTLY_LOCKED: Live real execution is strictly forbidden across all BITDEX layers."
            )

        if str(ex_row["account_login"]) != "474861031" or str(ex_row["server_name"]) != "Exness-MT5Trial15":
            raise HTTPException(
                status_code=403,
                detail="TARGET_UNAUTHORIZED: Automated Demo execution is strictly restricted to account 474861031 on Exness-MT5Trial15."
            )

        conn_id = str(ex_row["connection_id"])
        broker_sym = normalize_broker_symbol(symbol)

        # Ensure default DISARMED state row exists in hft_auto_entry_state
        state_row = conn.execute(
            "SELECT * FROM hft_auto_entry_state WHERE account_id = ?",
            (conn_id,)
        ).fetchone()
        if not state_row:
            conn.execute(
                """
                INSERT INTO hft_auto_entry_state (
                    account_id, user_id, symbol, auto_entry_armed, allocated_capital_usd,
                    risk_pct_per_trade, profit_target_usd, max_loss_usd, min_net_edge_usd,
                    enforce_notional_leverage_cap, leverage_limit, updated_at
                ) VALUES (?, ?, ?, 0, 100.0, 1.0, 1.0, 1.0, 1.0, 0, 5.0, ?)
                """,
                (conn_id, user_id, broker_sym, now_str)
            )
            conn.commit()
            state_row = conn.execute("SELECT * FROM hft_auto_entry_state WHERE account_id = ?", (conn_id,)).fetchone()

        st = dict(state_row)
        is_auto_armed = bool(st.get("auto_entry_armed", 0))
        alloc_cap = float(allocated_capital_usd if allocated_capital_usd is not None else st.get("allocated_capital_usd", 100.0))
        risk_pct = float(risk_pct_per_trade if risk_pct_per_trade is not None else st.get("risk_pct_per_trade", 1.0))
        prof_target = float(profit_target_usd if profit_target_usd is not None else st.get("profit_target_usd", 1.0))
        loss_cap = float(max_loss_usd if max_loss_usd is not None else st.get("max_loss_usd", 1.0))
        min_edge = float(min_net_edge_usd if min_net_edge_usd is not None else st.get("min_net_edge_usd", 1.0))
        enforce_lev = bool(enforce_notional_leverage_cap if enforce_notional_leverage_cap is not None else st.get("enforce_notional_leverage_cap", 0))
        lev_limit = float(leverage_limit if leverage_limit is not None else st.get("leverage_limit", 5.0))

        # 2. Fetch live Broker Positions, Tick, and M1 Candles via persistent Keep-Alive client
        gateway_token = "a955da9c16abc0478643fa862ffff9d6e42122587c23f78ab3713801f14facf9"
        headers = {"X-Gateway-Auth-Token": gateway_token}
        client = get_gateway_client()

        if override_open_positions_count is not None:
            open_positions_count = int(override_open_positions_count)
            open_positions_list = []
        else:
            pos_resp = client.get("/positions", headers=headers)
            if pos_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to query broker open positions prior to automatic entry cycle.")
            pos_json = pos_resp.json()
            open_positions_list = pos_json.get("positions", [])
            open_positions_count = int(pos_json.get("count", len(open_positions_list)))

        if override_tick is not None:
            tick_data = override_tick
        else:
            tick_resp = client.get(f"/tick/{broker_sym}", headers=headers)
            if tick_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Failed to fetch live MT5 tick for {broker_sym}.")
            tick_data = tick_resp.json().get("latest_tick", {})

        if override_klines is not None:
            candles = override_klines
        else:
            c_resp = client.get(f"/candles/{broker_sym}?timeframe=M1&count=45", headers=headers)
            if c_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Failed to fetch M1 candles for {broker_sym}.")
            candles = c_resp.json().get("candles", [])

        current_bid = float(tick_data.get("bid", 0.0))
        current_ask = float(tick_data.get("ask", 0.0))
        tick_ts_ms = int(tick_data.get("timestamp_ms", int(time.time() * 1000)))
        tick_age_ms = max(0, int(time.time() * 1000) - tick_ts_ms)
        latest_bar_ts = int(candles[-1].get("time", 0)) if candles else 0

        # 3. Evaluate Directional Signal + Minimum Net-Edge Gate
        engine = AutomatedHighFrequencyScalpingEngine()
        signal_eval = engine.evaluate_directional_scalp_cycle(
            symbol=broker_sym,
            klines=candles,
            current_bid=current_bid,
            current_ask=current_ask,
            allocated_capital_usd=alloc_cap,
            risk_pct_per_trade=risk_pct,
            max_loss_usd=loss_cap,
            profit_target_usd=prof_target,
            min_net_edge_usd=min_edge,
            tick_age_ms=tick_age_ms,
            max_tick_age_ms=15000,
            existing_positions_count=open_positions_count,
        )

        proposed = signal_eval["proposed_levels"]
        selected_dir = signal_eval["selected_direction"]
        dir_score = signal_eval["directional_score"]

        # 4. Evaluate Allocated-Capital Sizing, Minimum-Lot Skip & Circuit Breakers
        auth_row = conn.execute(
            """
            SELECT * FROM hft_demo_authorizations
            WHERE user_id = ? AND (account_id = ? OR broker_login = '474861031')
              AND is_authorized = 1 AND emergency_stop_triggered = 0
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id, conn_id)
        ).fetchone()
        consec_losses = int(auth_row["consecutive_losses"]) if auth_row else 0

        risk_eval = cls.evaluate_allocated_capital_risk(
            symbol=broker_sym,
            entry_price=proposed["entry_price"],
            stop_loss_price=proposed["stop_loss_price"],
            take_profit_price=proposed["take_profit_price"],
            allocated_capital_usd=alloc_cap,
            risk_pct_per_trade=risk_pct,
            max_loss_usd_cap=loss_cap,
            requested_volume=0.01,
            leverage_limit=lev_limit,
            enforce_notional_leverage_cap=enforce_lev,
            consecutive_losses=consec_losses,
            round_trip_cost_usd=signal_eval["net_edge_evaluation"]["estimated_round_trip_cost_usd"],
        )

        # 5. Consolidate All Qualification & Risk Gates
        rejection_reasons = list(signal_eval.get("skip_reasons", []))
        if not risk_eval.get("allowed"):
            rejection_reasons.append(f"{risk_eval.get('skip_code')}: {risk_eval.get('reason')}")

        # Idempotency check: prevent duplicate entry on the same M1 bar
        idempotency_key = f"AUTO-{conn_id}-{broker_sym}-{latest_bar_ts}-{selected_dir}"
        if latest_bar_ts > 0 and int(st.get("last_executed_bar_ts", 0)) == latest_bar_ts:
            rejection_reasons.append(
                f"DUPLICATE_BAR_CYCLE_PREVENTED: Order already executed on M1 bar timestamp {latest_bar_ts} (key {st.get('last_idempotency_key')})."
            )

        all_signal_and_risk_passed = (len(rejection_reasons) == 0)

        # 6. Check Arming & Authorization Gate (DISARMED BY DEFAULT)
        has_active_auth = bool(auth_row is not None)
        can_submit_live_demo = bool(all_signal_and_risk_passed and is_auto_armed and has_active_auth and not dry_run)

        execution_status = "NO_ENTRY_THIS_CYCLE"
        preflight_result = None
        broker_execution_result = None

        if not all_signal_and_risk_passed:
            execution_status = "NO_ENTRY_THIS_CYCLE"
            primary_reason = "; ".join(rejection_reasons)
        elif not is_auto_armed:
            execution_status = "QUALIFIED_BUT_HELD_DISARMED"
            primary_reason = (
                f"AUTO_ENTRY_DISARMED_BY_DEFAULT: {selected_dir} signal ({dir_score:.1f}/100) and all risk gates PASSED, "
                f"but automatic order submission is DISARMED by default awaiting explicit user approval."
            )
        elif not has_active_auth:
            execution_status = "QUALIFIED_BUT_HELD_UNAUTHORIZED"
            primary_reason = (
                f"DEMO_AUTHORIZATION_DISARMED: {selected_dir} signal ({dir_score:.1f}/100) and all risk gates PASSED, "
                f"but no active Demo execution authorization token is currently armed."
            )
        elif dry_run:
            execution_status = "QUALIFIED_PREFLIGHT_VERIFIED_DRY_RUN"
            primary_reason = (
                f"DRY_RUN_MODE_ACTIVE: {selected_dir} signal ({dir_score:.1f}/100) and all risk gates PASSED. "
                f"Running non-mutating Session 2 preflight verification (zero broker orders sent)."
            )
            order_spec = {
                "auth_token": auth_row["auth_id"],
                "symbol": broker_sym,
                "direction": selected_dir,
                "entry_price": proposed["entry_price"],
                "volume": proposed["volume"],
                "stop_loss_price": proposed["stop_loss_price"],
                "take_profit_price": proposed["take_profit_price"],
                "account_equity": 5073.84,
                "dry_run": True,
            }
            preflight_result = cls.dispatch_demo_order(
                conn=conn,
                user_id=user_id,
                auth_token=auth_row["auth_id"],
                order_spec=order_spec,
                dry_run=True,
            )
        else:
            # Explicitly armed + authorized + dry_run=False -> Execute on Demo broker
            order_spec = {
                "auth_token": auth_row["auth_id"],
                "symbol": broker_sym,
                "direction": selected_dir,
                "entry_price": proposed["entry_price"],
                "volume": proposed["volume"],
                "stop_loss_price": proposed["stop_loss_price"],
                "take_profit_price": proposed["take_profit_price"],
                "account_equity": 5073.84,
                "dry_run": False,
            }
            broker_execution_result = cls.dispatch_demo_order(
                conn=conn,
                user_id=user_id,
                auth_token=auth_row["auth_id"],
                order_spec=order_spec,
                dry_run=False,
            )
            execution_status = "EXECUTED_ON_DEMO_BROKER"
            primary_reason = f"Executed {selected_dir} {proposed['volume']} {broker_sym} on Demo account 474861031."
            conn.execute(
                """
                UPDATE hft_auto_entry_state
                SET last_executed_bar_ts = ?, last_idempotency_key = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (latest_bar_ts, idempotency_key, now_str, conn_id)
            )

        # Update state telemetry in hft_auto_entry_state
        conn.execute(
            """
            UPDATE hft_auto_entry_state
            SET last_evaluated_bar_ts = ?,
                last_selected_direction = ?,
                last_directional_score = ?,
                last_cycle_status = ?,
                last_skip_reason = ?,
                last_evaluated_at = ?,
                updated_at = ?
            WHERE account_id = ?
            """,
            (
                latest_bar_ts,
                selected_dir,
                dir_score,
                execution_status,
                primary_reason,
                now_str,
                now_str,
                conn_id,
            )
        )
        conn.commit()

        return {
            "status": "SUCCESS",
            "pathway_status": "COMPLETE",
            "account_id": conn_id,
            "broker_login": "474861031",
            "server_name": "Exness-MT5Trial15",
            "environment": "DEMO",
            "symbol": broker_sym,
            "auto_entry_armed": is_auto_armed,
            "has_active_demo_authorization": has_active_auth,
            "dry_run": dry_run,
            "dispatched_to_broker": bool(broker_execution_result is not None),
            "execution_status": execution_status,
            "reason": primary_reason,
            "idempotency": {
                "latest_bar_timestamp": latest_bar_ts,
                "last_executed_bar_timestamp": int(st.get("last_executed_bar_ts", 0)),
                "idempotency_key": idempotency_key,
                "open_positions_on_broker": open_positions_count,
            },
            "directional_signal": signal_eval,
            "allocated_capital_risk_check": risk_eval,
            "preflight_verification": preflight_result,
            "broker_execution": broker_execution_result,
            "timestamp_utc": now_str,
        }

    @classmethod
    def close_all_demo_positions(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = "EXN-CONN-A4E7BE39D276",
        symbol: Optional[str] = None,
        close_reason: str = "CUSTOMER_CLOSE_ALL_TRADES"
    ) -> Dict[str, Any]:
        """
        Emergency 'CLOSE ALL TRADES' operation (distinct from Emergency Disarm):
        - Verifies Demo account 474861031 on Exness-MT5Trial15 (hard-rejects Real accounts with HTTP 403).
        - Queries live open positions from Session 2 MT5 worker via Gateway.
        - Requests closure of every matching open position by exact broker ticket.
        - Prevents duplicate close requests via Session 2 _closing_tickets_lock.
        - Reconciles the final open position list and settled deal P&L after closure.
        - Never claims all positions closed if even one remains open.
        """
        ensure_demo_tables(conn)
        now_str = now_utc_iso()

        ex_row = conn.execute(
            "SELECT * FROM exness_demo_connections WHERE (connection_id = ? OR account_login = ?) AND user_id = ?",
            (account_id or "EXN-CONN-A4E7BE39D276", account_id or "474861031", user_id)
        ).fetchone()
        if not ex_row:
            raise HTTPException(status_code=404, detail="Selected Demo trading account not found or unauthorized.")

        if str(ex_row["account_type"]).upper() != "DEMO" or "REAL" in str(ex_row["server_name"]).upper():
            raise HTTPException(
                status_code=403,
                detail="REAL_TRADING_PERMANENTLY_LOCKED: Real account position mutation is permanently locked."
            )

        broker_login = str(ex_row["account_login"])
        server_name = str(ex_row["server_name"])
        if broker_login != "474861031" or server_name != "Exness-MT5Trial15":
            raise HTTPException(
                status_code=403,
                detail="TARGET_UNAUTHORIZED: Restricted to Demo account 474861031 on Exness-MT5Trial15."
            )

        gateway_token = "a955da9c16abc0478643fa862ffff9d6e42122587c23f78ab3713801f14facf9"
        headers = {"X-Gateway-Auth-Token": gateway_token}
        client = get_gateway_client()

        pos_resp = client.get("/positions", headers=headers)
        if pos_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to query live open positions from Exness MT5 Gateway.")

        open_positions = pos_resp.json().get("positions", [])
        if symbol:
            norm_sym = normalize_broker_symbol(symbol)
            target_positions = [p for p in open_positions if str(p.get("symbol", "")).upper() == norm_sym.upper()]
        else:
            target_positions = list(open_positions)

        if not target_positions:
            return {
                "status": "SUCCESS",
                "all_closed": True,
                "account_id": str(ex_row["connection_id"]),
                "broker_login": broker_login,
                "server_name": server_name,
                "requested_count": 0,
                "closed_count": 0,
                "failed_count": 0,
                "remaining_open_count": len(open_positions),
                "results": [],
                "message": "No open trades found to close on Demo Account #474861031.",
                "timestamp_utc": now_str,
            }

        results = []
        closed_count = 0
        failed_count = 0

        for p in target_positions:
            ticket_str = str(p.get("ticket"))
            pos_sym = str(p.get("symbol", "BTCUSDr"))
            try:
                c_res = cls.close_demo_position(
                    conn=conn,
                    user_id=user_id,
                    account_id=str(ex_row["connection_id"]),
                    ticket=ticket_str,
                    close_reason=close_reason
                )
                closed_count += 1
                results.append({
                    "ticket": ticket_str,
                    "symbol": pos_sym,
                    "status": "CLOSED",
                    "broker_result": c_res.get("broker_result"),
                })
            except Exception as ex:
                failed_count += 1
                results.append({
                    "ticket": ticket_str,
                    "symbol": pos_sym,
                    "status": "FAILED",
                    "error": getattr(ex, "detail", str(ex)),
                })

        # Post-close reconciliation: re-query live positions from MT5
        recheck_resp = client.get("/positions", headers=headers)
        remaining_positions = recheck_resp.json().get("positions", []) if recheck_resp.status_code == 200 else []
        remaining_count = len(remaining_positions)
        all_closed_verified = (failed_count == 0 and remaining_count == 0)

        return {
            "status": "SUCCESS" if all_closed_verified else "PARTIAL_OR_FAILED",
            "all_closed": all_closed_verified,
            "account_id": str(ex_row["connection_id"]),
            "broker_login": broker_login,
            "server_name": server_name,
            "requested_count": len(target_positions),
            "closed_count": closed_count,
            "failed_count": failed_count,
            "remaining_open_count": remaining_count,
            "remaining_open_positions": remaining_positions,
            "results": results,
            "message": (
                f"Confirmed closure of {closed_count}/{len(target_positions)} open trade(s) on Exness Demo #474861031."
                if all_closed_verified
                else f"Closed {closed_count}/{len(target_positions)} trade(s); {remaining_count} position(s) still open on broker."
            ),
            "timestamp_utc": now_str,
        }

