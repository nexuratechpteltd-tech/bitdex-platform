"""
BITDEX Persistent Account-Scoped Trading State & Capital Protection Manager
==========================================================================
Manages persistent state across process restarts:
1. Consecutive loss tracking & 60-minute circuit breaker cooldown
2. 3.0% maximum daily realized loss limit from starting daily equity
3. Setup fingerprinting and 60-minute invalidation memory after stop-outs
4. Tenant-isolated, account-scoped database persistence
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("bitdex.trading_state_manager")


class TradingStateManager:
    """
    Thread-safe, process-persistent state manager backed by SQLite.
    """

    MAX_CONSECUTIVE_LOSSES: int = 3
    COOLDOWN_MINUTES: int = 60
    MAX_DAILY_LOSS_PCT: float = 0.03  # 3.0% maximum daily loss
    SETUP_INVALIDATION_TTL_MINUTES: int = 60

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        """Ensures the state tables exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_trading_state (
                account_id TEXT PRIMARY KEY,
                consecutive_losses INTEGER DEFAULT 0,
                last_loss_timestamp TEXT,
                cooldown_until TEXT,
                daily_starting_equity REAL DEFAULT 0.0,
                daily_equity_date TEXT,
                daily_realized_pnl REAL DEFAULT 0.0,
                updated_at TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invalidated_setups (
                fingerprint TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                invalidated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                reason TEXT NOT NULL
            );
        """)

    @classmethod
    def get_or_init_account_state(
        cls, conn: sqlite3.Connection, account_id: str, current_equity: float
    ) -> Dict[str, Any]:
        cls.ensure_schema(conn)
        now_utc = datetime.now(timezone.utc)
        today_date = now_utc.strftime("%Y-%m-%d")
        now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        row = conn.execute(
            "SELECT * FROM account_trading_state WHERE account_id = ?", (str(account_id),)
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO account_trading_state 
                (account_id, consecutive_losses, last_loss_timestamp, cooldown_until, daily_starting_equity, daily_equity_date, daily_realized_pnl, updated_at)
                VALUES (?, 0, NULL, NULL, ?, ?, 0.0, ?)
                """,
                (str(account_id), current_equity, today_date, now_iso),
            )
            return {
                "account_id": str(account_id),
                "consecutive_losses": 0,
                "last_loss_timestamp": None,
                "cooldown_until": None,
                "daily_starting_equity": current_equity,
                "daily_equity_date": today_date,
                "daily_realized_pnl": 0.0,
                "updated_at": now_iso,
            }

        state = dict(row)
        # Check if UTC calendar date rolled over
        if state.get("daily_equity_date") != today_date:
            conn.execute(
                """
                UPDATE account_trading_state
                SET daily_starting_equity = ?, daily_equity_date = ?, daily_realized_pnl = 0.0, updated_at = ?
                WHERE account_id = ?
                """,
                (current_equity, today_date, now_iso, str(account_id)),
            )
            state["daily_starting_equity"] = current_equity
            state["daily_equity_date"] = today_date
            state["daily_realized_pnl"] = 0.0
            state["updated_at"] = now_iso

        return state

    @classmethod
    def check_cooldown(
        cls, conn: sqlite3.Connection, account_id: str
    ) -> Tuple[bool, Optional[str], int]:
        """
        Returns (is_in_cooldown, cooldown_until_iso, remaining_seconds).
        """
        cls.ensure_schema(conn)
        row = conn.execute(
            "SELECT cooldown_until, consecutive_losses FROM account_trading_state WHERE account_id = ?",
            (str(account_id),),
        ).fetchone()
        if not row or not row["cooldown_until"]:
            return False, None, 0

        cooldown_until_str = row["cooldown_until"]
        try:
            cooldown_dt = datetime.fromisoformat(cooldown_until_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if now_dt < cooldown_dt:
                rem_sec = int((cooldown_dt - now_dt).total_seconds())
                return True, cooldown_until_str, rem_sec
            else:
                # Cooldown expired, clear cooldown_until
                conn.execute(
                    "UPDATE account_trading_state SET cooldown_until = NULL WHERE account_id = ?",
                    (str(account_id),),
                )
                return False, None, 0
        except Exception as e:
            logger.error(f"Error parsing cooldown_until for {account_id}: {e}")
            return False, None, 0

    @classmethod
    def record_trade_result(
        cls, conn: sqlite3.Connection, account_id: str, pnl_usd: float, current_equity: float
    ) -> Dict[str, Any]:
        """
        Updates consecutive losses and daily realized PnL.
        Trips 60-minute cooldown if consecutive_losses >= 3.
        """
        state = cls.get_or_init_account_state(conn, account_id, current_equity)
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        new_daily_pnl = float(state.get("daily_realized_pnl", 0.0)) + float(pnl_usd)

        if pnl_usd < 0:
            new_losses = int(state.get("consecutive_losses", 0)) + 1
            last_loss_ts = now_iso
            cooldown_until = state.get("cooldown_until")

            if new_losses >= cls.MAX_CONSECUTIVE_LOSSES:
                cooldown_dt = now_utc + timedelta(minutes=cls.COOLDOWN_MINUTES)
                cooldown_until = cooldown_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                logger.warning(
                    f"CIRCUIT BREAKER TRIPPED for account {account_id}: "
                    f"{new_losses} consecutive losses. Cooldown until {cooldown_until}"
                )

            conn.execute(
                """
                UPDATE account_trading_state
                SET consecutive_losses = ?, last_loss_timestamp = ?, cooldown_until = ?,
                    daily_realized_pnl = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (new_losses, last_loss_ts, cooldown_until, new_daily_pnl, now_iso, str(account_id)),
            )
            state["consecutive_losses"] = new_losses
            state["last_loss_timestamp"] = last_loss_ts
            state["cooldown_until"] = cooldown_until
            state["daily_realized_pnl"] = new_daily_pnl
            state["updated_at"] = now_iso
        else:
            # Winning trade: reset consecutive losses to 0
            conn.execute(
                """
                UPDATE account_trading_state
                SET consecutive_losses = 0, cooldown_until = NULL,
                    daily_realized_pnl = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (new_daily_pnl, now_iso, str(account_id)),
            )
            state["consecutive_losses"] = 0
            state["cooldown_until"] = None
            state["daily_realized_pnl"] = new_daily_pnl
            state["updated_at"] = now_iso

        return state

    @classmethod
    def check_daily_loss_limit(
        cls, conn: sqlite3.Connection, account_id: str, current_equity: float
    ) -> Tuple[bool, float, float, float]:
        """
        Returns (limit_exceeded, daily_realized_pnl, max_allowed_loss, starting_equity).
        """
        state = cls.get_or_init_account_state(conn, account_id, current_equity)
        starting_equity = float(state.get("daily_starting_equity") or current_equity)
        daily_pnl = float(state.get("daily_realized_pnl", 0.0))
        max_allowed_loss = starting_equity * cls.MAX_DAILY_LOSS_PCT  # e.g. 5000 * 0.03 = 150 USD

        limit_exceeded = daily_pnl <= -abs(max_allowed_loss)
        return limit_exceeded, daily_pnl, max_allowed_loss, starting_equity

    @classmethod
    def compute_setup_fingerprint(
        cls, symbol: str, direction: str, trigger_candle_time: Any, entry_price: float
    ) -> str:
        """
        Generates deterministic fingerprint for a market setup.
        Rounds entry_price to 1.0 point band to prevent micro-fluctuation bypass.
        """
        entry_band = round(float(entry_price), 0)
        t_str = str(trigger_candle_time)
        raw = f"{symbol.upper()}:{direction.upper()}:{t_str}:{entry_band}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def is_setup_invalidated(
        cls, conn: sqlite3.Connection, account_id: str, fingerprint: str
    ) -> Tuple[bool, Optional[str]]:
        cls.ensure_schema(conn)
        row = conn.execute(
            """
            SELECT expires_at, reason FROM invalidated_setups
            WHERE account_id = ? AND fingerprint = ?
            """,
            (str(account_id), fingerprint),
        ).fetchone()

        if not row:
            return False, None

        exp_str = row["expires_at"]
        try:
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < exp_dt:
                return True, row["reason"]
            else:
                # Expired: clean up
                conn.execute(
                    "DELETE FROM invalidated_setups WHERE account_id = ? AND fingerprint = ?",
                    (str(account_id), fingerprint),
                )
                return False, None
        except Exception:
            return False, None

    @classmethod
    def invalidate_setup(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        symbol: str,
        direction: str,
        fingerprint: str,
        reason: str = "STOPPED_OUT",
        ttl_minutes: Optional[int] = None,
    ) -> None:
        cls.ensure_schema(conn)
        ttl = ttl_minutes or cls.SETUP_INVALIDATION_TTL_MINUTES
        now_dt = datetime.now(timezone.utc)
        exp_dt = now_dt + timedelta(minutes=ttl)
        now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        exp_iso = exp_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        conn.execute(
            """
            INSERT OR REPLACE INTO invalidated_setups
            (fingerprint, account_id, symbol, direction, invalidated_at, expires_at, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fingerprint, str(account_id), symbol, direction, now_iso, exp_iso, reason),
        )
        logger.info(
            f"Invalidated setup {fingerprint} ({symbol} {direction}) for account {account_id} until {exp_iso}. Reason: {reason}"
        )
