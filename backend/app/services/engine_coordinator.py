"""
BITDEX Dual-Engine Coordinator & Symbol Mutual-Exclusivity Lease Manager.
Governs execution coordination, symbol exclusivity, and aggregate exposure limits
between Engine A (Spot/Swing Long-Term) and Engine B (High-Frequency Futures).
"""

import json
import logging
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger("bitdex.engine_coordinator")


class EngineCoordinator:
    """
    Manages symbol mutual exclusivity leases, aggregate account exposure gates,
    and engine-specific order ownership.
    """

    DEFAULT_LEASE_DURATION_SECONDS = 600  # 10 minutes default lease
    MAX_AGGREGATE_EXPOSURE_RATIO = 0.50  # 50% max margin exposure across both engines

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def clean_expired_leases(cls, conn: sqlite3.Connection) -> int:
        """
        Mark all expired leases whose status is ACTIVE as EXPIRED.
        Compares expires_at against UTC current time.
        """
        now_str = cls.now_iso()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE futures_symbol_leases
            SET status = 'EXPIRED'
            WHERE status = 'ACTIVE' AND expires_at <= ?
            """,
            (now_str,)
        )
        return cursor.rowcount

    @classmethod
    def get_symbol_active_lease(cls, conn: sqlite3.Connection, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Query any valid active unexpired lease for a symbol across all accounts.
        Lazily transitions expired active rows to EXPIRED.
        """
        sym = symbol.upper()
        now_str = cls.now_iso()
        cursor = conn.cursor()

        # Lazy expiration of stale leases on this symbol
        cursor.execute(
            """
            UPDATE futures_symbol_leases
            SET status = 'EXPIRED'
            WHERE symbol = ? AND status = 'ACTIVE' AND expires_at <= ?
            """,
            (sym, now_str)
        )

        row = cursor.execute(
            """
            SELECT account_id, symbol, engine_id, lease_token, acquired_at, expires_at, status, metadata_json
            FROM futures_symbol_leases
            WHERE symbol = ? AND status = 'ACTIVE' AND expires_at > ?
            ORDER BY acquired_at DESC
            LIMIT 1
            """,
            (sym, now_str)
        ).fetchone()

        if not row:
            return None

        return {
            "account_id": row[0],
            "symbol": row[1],
            "engine_id": row[2],
            "lease_token": row[3],
            "acquired_at": row[4],
            "expires_at": row[5],
            "status": row[6],
            "metadata": json.loads(row[7] or "{}")
        }

    @classmethod
    def is_engine_b_enabled(cls, conn: sqlite3.Connection, account_id: str) -> bool:
        """
        Engine B is strictly DEFAULT OFF.
        Must be explicitly enabled per account in futures_accounts.
        """
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT engine_b_enabled FROM futures_accounts WHERE account_id = ?",
            (account_id,)
        ).fetchone()
        if not row:
            return False
        return bool(row[0])

    @classmethod
    def set_engine_b_status(cls, conn: sqlite3.Connection, account_id: str, enabled: bool) -> bool:
        """Enable or disable Engine B for an account."""
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE futures_accounts SET engine_b_enabled = ?, updated_at = ? WHERE account_id = ?",
            (1 if enabled else 0, cls.now_iso(), account_id)
        )
        return cursor.rowcount > 0

    @classmethod
    def acquire_lease(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        symbol: str,
        engine_id: str,
        duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Attempt to acquire an atomic mutual-exclusivity lease for (account_id, symbol).
        Returns (success, lease_token, rejection_reason).
        """
        sym = symbol.upper()
        eng = engine_id.upper()
        if eng not in ("ENGINE_A", "ENGINE_B"):
            return False, None, f"Invalid engine_id {engine_id}. Must be ENGINE_A or ENGINE_B."

        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        expires = now + timedelta(seconds=duration_seconds)
        expires_str = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
        new_token = f"LSE-{secrets.token_hex(8)}"
        meta_str = json.dumps(metadata or {})

        cursor = conn.cursor()

        # 1. Check cross-account symbol exclusivity
        active_sym_lease = cls.get_symbol_active_lease(conn, sym)
        if active_sym_lease and active_sym_lease["account_id"] != account_id:
            reason = (
                f"Symbol {sym} is currently locked by another account ({active_sym_lease['account_id']}) "
                f"under {active_sym_lease['engine_id']} (expires {active_sym_lease['expires_at']}). Collision prevented."
            )
            logger.warning("[COLLISION_PREVENTED] Cross-account collision: %s", reason)
            return False, None, reason

        # 2. Check existing lease for this account and symbol
        existing = cursor.execute(
            """
            SELECT engine_id, lease_token, expires_at, status
            FROM futures_symbol_leases
            WHERE account_id = ? AND symbol = ?
            """,
            (account_id, sym)
        ).fetchone()

        if existing:
            curr_engine, curr_token, curr_expires_str, curr_status = existing
            try:
                curr_expires = datetime.strptime(curr_expires_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except Exception:
                curr_expires = now - timedelta(seconds=1)

            # If existing lease is ACTIVE and has not expired
            if curr_status == "ACTIVE" and now < curr_expires:
                if curr_engine == eng:
                    # Same engine already owns lease -> extend / renew
                    cursor.execute(
                        """
                        UPDATE futures_symbol_leases
                        SET expires_at = ?, metadata_json = ?
                        WHERE account_id = ? AND symbol = ? AND lease_token = ?
                        """,
                        (expires_str, meta_str, account_id, sym, curr_token)
                    )
                    return True, curr_token, None
                else:
                    # Competing engine owns active lease -> REJECT
                    reason = (
                        f"Symbol {sym} is currently locked by {curr_engine} "
                        f"(lease expires at {curr_expires_str}). Collision prevented."
                    )
                    logger.warning("[COLLISION_PREVENTED] %s %s on account %s", eng, reason, account_id)
                    return False, None, reason

            # Existing lease is EXPIRED or RELEASED -> overwrite/reclaim
            cursor.execute(
                """
                UPDATE futures_symbol_leases
                SET engine_id = ?, lease_token = ?, acquired_at = ?, expires_at = ?, status = 'ACTIVE', metadata_json = ?
                WHERE account_id = ? AND symbol = ?
                """,
                (eng, new_token, now_str, expires_str, meta_str, account_id, sym)
            )
            return True, new_token, None

        # No lease exists -> insert new
        cursor.execute(
            """
            INSERT INTO futures_symbol_leases
            (account_id, symbol, engine_id, lease_token, acquired_at, expires_at, status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            """,
            (account_id, sym, eng, new_token, now_str, expires_str, meta_str)
        )
        return True, new_token, None

    @classmethod
    def release_lease(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        symbol: str,
        engine_id: str,
        lease_token: str
    ) -> bool:
        """Release an active lease upon position closure."""
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE futures_symbol_leases
            SET status = 'RELEASED'
            WHERE account_id = ? AND symbol = ? AND engine_id = ? AND lease_token = ?
            """,
            (account_id, symbol.upper(), engine_id.upper(), lease_token)
        )
        return cursor.rowcount > 0

    @classmethod
    def get_active_lease(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        symbol: str
    ) -> Optional[Dict[str, Any]]:
        """Query the active lease for a symbol if unexpired."""
        cursor = conn.cursor()
        now_str = cls.now_iso()

        # Lazy expiration
        cursor.execute(
            """
            UPDATE futures_symbol_leases
            SET status = 'EXPIRED'
            WHERE account_id = ? AND symbol = ? AND status = 'ACTIVE' AND expires_at <= ?
            """,
            (account_id, symbol.upper(), now_str)
        )

        row = cursor.execute(
            """
            SELECT account_id, symbol, engine_id, lease_token, acquired_at, expires_at, status, metadata_json
            FROM futures_symbol_leases
            WHERE account_id = ? AND symbol = ? AND status = 'ACTIVE' AND expires_at > ?
            """,
            (account_id, symbol.upper(), now_str)
        ).fetchone()

        if not row:
            return None

        return {
            "account_id": row[0],
            "symbol": row[1],
            "engine_id": row[2],
            "lease_token": row[3],
            "acquired_at": row[4],
            "expires_at": row[5],
            "status": row[6],
            "metadata": json.loads(row[7] or "{}")
        }

    @classmethod
    def check_aggregate_exposure(
        cls,
        conn: sqlite3.Connection,
        account_id: str,
        new_margin_usd: float,
        max_exposure_ratio: float = MAX_AGGREGATE_EXPOSURE_RATIO
    ) -> Tuple[bool, float, float, Optional[str]]:
        """
        Verify that total margin across all open positions (Engine A + Engine B)
        plus the proposed new margin does not exceed max_exposure_ratio of account equity.
        Returns (is_approved, current_margin, proposed_total_margin, rejection_reason).
        """
        cursor = conn.cursor()

        # Get wallet balance / equity
        acc = cursor.execute(
            "SELECT wallet_balance FROM futures_accounts WHERE account_id = ?",
            (account_id,)
        ).fetchone()
        if not acc:
            return False, 0.0, new_margin_usd, f"Futures account {account_id} not found."

        wallet_balance = float(acc[0])
        if wallet_balance <= 0:
            return False, 0.0, new_margin_usd, "Account balance is zero or negative."

        # Sum current margin of open positions
        pos_row = cursor.execute(
            """
            SELECT COALESCE(SUM(isolated_margin), 0.0)
            FROM futures_positions
            WHERE account_id = ? AND status = 'OPEN'
            """,
            (account_id,)
        ).fetchone()
        current_margin = float(pos_row[0]) if pos_row else 0.0

        proposed_total_margin = current_margin + new_margin_usd
        max_allowed_margin = wallet_balance * max_exposure_ratio
        current_ratio = proposed_total_margin / wallet_balance

        if proposed_total_margin > max_allowed_margin:
            reason = (
                f"PORTFOLIO_EXPOSURE_SATURATED: Proposed total margin ${proposed_total_margin:.2f} "
                f"({current_ratio*100:.1f}%) exceeds maximum allowable {max_exposure_ratio*100:.0f}% "
                f"of equity (${max_allowed_margin:.2f})."
            )
            return False, current_margin, proposed_total_margin, reason

        return True, current_margin, proposed_total_margin, None

    @classmethod
    def validate_order_ownership(
        cls,
        client_order_id: str,
        acting_engine_id: str
    ) -> bool:
        """
        Enforce strict order ownership scoping based on client order ID prefix.
        Engine A orders: EA-*
        Engine B orders: EB-*
        """
        coid = client_order_id.upper()
        eng = acting_engine_id.upper()
        if eng == "ENGINE_A" and not (coid.startswith("EA-") or coid.startswith("FO-")):
            return False
        if eng == "ENGINE_B" and not (coid.startswith("EB-") or coid.startswith("EBS-")):
            return False
        return True
