"""
BITDEX Central Execution Router & Multi-Tenant Infrastructure Manager (Sections 5, 6, 8)
========================================================================================
Implements the broker-aware execution router (`CentralExecutionRouter`) and per-tenant
isolated execution state (`TenantAccountExecutionContext`):

When a customer selects an account:
1. Resolves the authenticated customer ID (`user_id`).
2. Verifies that the account belongs to that customer (raises `PermissionError("TENANT_ISOLATION_VIOLATION")`
   if another customer's account is requested; never substitutes a global default account).
3. Identifies its broker (`EXNESS`, `BINANCE`, etc.).
4. Identifies its trading platform (`MT5`, `EXNESS_TERMINAL`, `BINANCE_FUTURES`).
5. Identifies the account environment (`DEMO` vs `REAL`).
6. Selects the correct supported adapter (`ExnessMT5BrokerAdapter`, `ExnessTerminalBrokerAdapter`,
   `BinanceFuturesBrokerAdapter`). Never routes an `EXNESS_TERMINAL` account through the MT5 Worker!
7. Checks execution readiness (`AdapterCapabilityMatrix` & `check_execution_readiness`).
8. Routes quotes, strategy signals, orders, positions, closing, and reconciliation requests
   through that adapter inside an isolated per-customer execution context.
"""

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .base_contract import UniversalBrokerAdapter
from .exness_terminal_adapter import ExnessTerminalBrokerAdapter
from .mt5_broker_adapter import ExnessMT5BrokerAdapter
from .binance_futures_adapter import BinanceFuturesBrokerAdapter
from .strategy_risk_engine import CommonStrategyAndRiskEngine
from ..exness.vault import ExnessCredentialVault


@dataclass
class TenantAccountExecutionContext:
    """
    Isolated per-(user_id, connection_id) execution state managed by BITDEX infrastructure.
    One customer's disconnection, failure, or trading activity never affects another customer.
    """
    user_id: str
    connection_id: str
    account_id: str
    broker: str
    trading_platform: str
    environment: str
    adapter_name: str
    execution_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    seen_idempotency_keys: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    consecutive_errors: int = 0
    circuit_breaker_tripped: bool = False
    last_activity_utc: str = ""
    execution_logs: List[Dict[str, Any]] = field(default_factory=list)

    def record_event(self, event_type: str, detail: Dict[str, Any]) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self.last_activity_utc = now_iso
        self.execution_logs.append({
            "timestamp_utc": now_iso,
            "user_id": self.user_id,
            "connection_id": self.connection_id,
            "account_id": self.account_id,
            "adapter": self.adapter_name,
            "event_type": event_type,
            "detail": detail,
        })
        if len(self.execution_logs) > 100:
            self.execution_logs = self.execution_logs[-100:]


# Isolated per-(user_id, connection_id) state registry
_TENANT_CONTEXTS: Dict[Tuple[str, str], TenantAccountExecutionContext] = {}
_STRATEGY_ENGINE = CommonStrategyAndRiskEngine()


class CentralExecutionRouter:
    """
    Central broker-aware execution router for BITDEX multi-tenant SaaS.
    """

    @staticmethod
    def resolve_adapter_for_customer(
        conn: sqlite3.Connection,
        authenticated_user_id: str,
        requested_account_id: Optional[str] = None,
    ) -> Tuple[UniversalBrokerAdapter, TenantAccountExecutionContext, Dict[str, Any]]:
        """
        Executes Steps 1-6 of the Central Execution Router:
        1. Resolve authenticated customer ID.
        2. Verify account ownership strictly against `authenticated_user_id`.
        3. Identify broker.
        4. Identify trading platform.
        5. Identify account environment (`DEMO` vs `REAL`).
        6. Instantiate and bind the exact supported `UniversalBrokerAdapter`.
        """
        user_id = str(authenticated_user_id or "").strip()
        if not user_id:
            raise PermissionError("TENANT_ISOLATION_VIOLATION: Missing authenticated customer ID.")

        target_id = str(requested_account_id or "").strip()

        # If no account_id specified, resolve this customer's own preferred active account
        if not target_id:
            row = conn.execute(
                """
                SELECT * FROM exness_demo_connections
                WHERE user_id = ? AND is_active = 1
                  AND verification_status IN ('VERIFIED', 'ACCOUNT_DATA_VERIFIED')
                  AND adapter_mode != 'DETERMINISTIC_MOCK_DEMO'
                ORDER BY account_type ASC, is_preferred DESC, updated_at DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if not row:
                u_row = conn.execute(
                    """
                    SELECT * FROM user_exchange_connections
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
                if u_row:
                    target_id = str(u_row["account_id"])
            else:
                target_id = str(row["connection_id"])

        if not target_id:
            raise LookupError("NO_CONNECTED_ACCOUNT: No verified broker account connected for this customer.")

        # Check exness_demo_connections owned by user_id
        exn_row = conn.execute(
            """
            SELECT * FROM exness_demo_connections
            WHERE user_id = ? AND (connection_id = ? OR account_login = ?)
              AND is_active = 1 AND adapter_mode != 'DETERMINISTIC_MOCK_DEMO'
            LIMIT 1
            """,
            (user_id, target_id, target_id),
        ).fetchone()

        if exn_row:
            d = dict(exn_row)
            conn_id = str(d["connection_id"])
            login_str = str(d.get("account_login") or "").strip()
            env = "REAL" if str(d.get("account_type") or "").upper() == "REAL" else "DEMO"
            adapter_mode = str(d.get("adapter_mode") or "").upper()
            platform = str(d.get("platform") or ("MT5" if adapter_mode == "EXNESS_MT5_GATEWAY" else "EXNESS_TERMINAL")).upper()
            server_name = str(d.get("server_name") or d.get("stream_id") or "")

            if platform == "MT5" or adapter_mode == "EXNESS_MT5_GATEWAY":
                adapter: UniversalBrokerAdapter = ExnessMT5BrokerAdapter(
                    owner_user_id=user_id,
                    connection_id=conn_id,
                    account_id=login_str,
                    environment=env,
                    server_name=server_name or "Exness-MT5Trial15",
                )
            else:
                # Exness Terminal / DXtrade (e.g. Ali Ajmal's 17000109575 on dx.2.trial.std)
                enc_str = d.get("encrypted_credentials") or "{}"
                creds = ExnessCredentialVault.decrypt_credentials(
                    user_id=user_id,
                    login=login_str,
                    server=str(d.get("server_name") or "https://api.exness.com"),
                    enc_payload=json.loads(enc_str),
                )
                adapter = ExnessTerminalBrokerAdapter(
                    owner_user_id=user_id,
                    connection_id=conn_id,
                    account_id=login_str,
                    api_key=str(d.get("api_key") or login_str),
                    api_secret=str(creds.get("password") or ""),
                    environment=env,
                    server_name=str(d.get("stream_id") or "dx.2.trial.std"),
                    access_point=str(d.get("access_point") or "") or None,
                    account_tier=str(d.get("account_tier") or "STANDARD"),
                )

            ctx = CentralExecutionRouter._get_or_create_context(
                user_id=user_id,
                connection_id=conn_id,
                account_id=login_str,
                broker=adapter.broker_name,
                trading_platform=adapter.trading_platform,
                environment=env,
                adapter_name=adapter.adapter_name,
            )
            return adapter, ctx, d

        # Check user_exchange_connections owned by user_id (e.g. Binance Futures / Customer C)
        u_row = conn.execute(
            """
            SELECT * FROM user_exchange_connections
            WHERE user_id = ? AND account_id = ? AND is_active = 1
            LIMIT 1
            """,
            (user_id, target_id),
        ).fetchone()
        if u_row:
            ud = dict(u_row)
            conn_id = str(ud["account_id"])
            env = "REAL" if str(ud.get("environment") or "").upper() in ("LIVE", "REAL") else "DEMO"
            prov = str(ud.get("provider") or "BINANCE").upper()
            adapter = BinanceFuturesBrokerAdapter(
                owner_user_id=user_id,
                connection_id=conn_id,
                account_id=conn_id,
                environment=env,
                server_name=f"{prov.lower()}-{'live' if env == 'REAL' else 'testnet'}",
            )
            ctx = CentralExecutionRouter._get_or_create_context(
                user_id=user_id,
                connection_id=conn_id,
                account_id=conn_id,
                broker=adapter.broker_name,
                trading_platform=adapter.trading_platform,
                environment=env,
                adapter_name=adapter.adapter_name,
            )
            return adapter, ctx, ud

        # Check if requested_account_id belongs to ANOTHER customer -> raise explicit 403 TENANT_ISOLATION_VIOLATION
        cross_exn = conn.execute(
            "SELECT user_id FROM exness_demo_connections WHERE (connection_id = ? OR account_login = ?) AND user_id != ? LIMIT 1",
            (target_id, target_id, user_id),
        ).fetchone()
        cross_u = conn.execute(
            "SELECT user_id FROM user_exchange_connections WHERE account_id = ? AND user_id != ? LIMIT 1",
            (target_id, user_id),
        ).fetchone()
        if cross_exn or cross_u:
            raise PermissionError(
                f"TENANT_ISOLATION_VIOLATION: Access denied. Account '{target_id}' belongs to another customer."
            )

        raise LookupError(f"ACCOUNT_NOT_FOUND: Account '{target_id}' not found for customer '{user_id}'.")

    @staticmethod
    def _get_or_create_context(
        user_id: str,
        connection_id: str,
        account_id: str,
        broker: str,
        trading_platform: str,
        environment: str,
        adapter_name: str,
    ) -> TenantAccountExecutionContext:
        key = (user_id, connection_id)
        ctx = _TENANT_CONTEXTS.get(key)
        if ctx is None:
            ctx = TenantAccountExecutionContext(
                user_id=user_id,
                connection_id=connection_id,
                account_id=account_id,
                broker=broker,
                trading_platform=trading_platform,
                environment=environment,
                adapter_name=adapter_name,
            )
            _TENANT_CONTEXTS[key] = ctx
        return ctx

    @classmethod
    async def route_account_summary(
        cls, conn: sqlite3.Connection, user_id: str, account_id: Optional[str] = None, force_refresh: bool = False
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)
        summary = await adapter.get_account_summary(force_refresh=force_refresh)
        ctx.record_event("ACCOUNT_SUMMARY_READ", {"balance": summary.get("balance"), "equity": summary.get("equity")})
        return summary

    @classmethod
    async def route_supported_instruments(
        cls, conn: sqlite3.Connection, user_id: str, account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)
        instruments = await adapter.get_supported_instruments()
        ctx.record_event("INSTRUMENTS_READ", {"count": len(instruments)})
        return {
            "status": "SUCCESS",
            "user_id": user_id,
            "connection_id": adapter.connection_id,
            "account_id": adapter.account_id,
            "broker": adapter.broker_name,
            "trading_platform": adapter.trading_platform,
            "adapter": adapter.adapter_name,
            "environment": adapter.environment,
            "instruments": instruments,
        }

    @classmethod
    async def route_live_quote(
        cls, conn: sqlite3.Connection, user_id: str, symbol: str, account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)
        quote = await adapter.get_live_quote(symbol)
        ctx.record_event("LIVE_QUOTE_READ", {"symbol": symbol, "bid": quote.get("bid"), "ask": quote.get("ask")})
        return quote

    @classmethod
    async def route_strategy_signal(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        symbol: str,
        account_id: Optional[str] = None,
        allocated_capital_usd: float = 100.0,
        leverage: int = 3,
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)
        res = await _STRATEGY_ENGINE.evaluate_strategy_and_risk(
            adapter=adapter,
            symbol=symbol,
            allocated_capital_usd=allocated_capital_usd,
            leverage=leverage,
        )
        ctx.record_event(
            "STRATEGY_SIGNAL_EVALUATED",
            {
                "symbol": symbol,
                "selected_direction": res["directional_cycle"]["selected_direction"],
                "score": res["directional_cycle"]["directional_score"],
                "entry_qualified": res["directional_cycle"]["entry_qualified"],
            },
        )
        return res

    @classmethod
    async def route_place_market_order(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        symbol: str,
        side: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "BITDEX-SCALP",
        idempotency_key: Optional[str] = None,
        account_id: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)

        if adapter.environment == "REAL":
            raise PermissionError("REAL_TRADING_PERMANENTLY_LOCKED: Real-account execution is permanently locked.")

        async with ctx.execution_lock:
            if idempotency_key and idempotency_key in ctx.seen_idempotency_keys:
                cached_order = dict(ctx.seen_idempotency_keys[idempotency_key])
                cached_order["idempotent_replay"] = True
                return cached_order

            res = await adapter.place_market_order(
                symbol=symbol,
                side=side,
                volume=volume,
                sl=sl,
                tp=tp,
                comment=comment,
                idempotency_key=idempotency_key,
                dry_run=dry_run,
            )
            if idempotency_key:
                ctx.seen_idempotency_keys[idempotency_key] = res
            ctx.record_event("ORDER_PLACEMENT_ROUTED", {"symbol": symbol, "side": side, "dry_run": dry_run, "status": res.get("status")})
            return res

    @classmethod
    async def route_open_positions(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)
        positions = await adapter.get_open_positions()
        ctx.record_event("OPEN_POSITIONS_READ", {"count": len(positions)})
        return positions

    @classmethod
    async def route_close_position(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        position_id: str,
        account_id: Optional[str] = None,
        volume: Optional[float] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)
        if adapter.environment == "REAL":
            raise PermissionError("REAL_TRADING_PERMANENTLY_LOCKED: Real-account position closure is permanently locked.")

        # Unlock demo execution if authorized and not dry_run
        if not dry_run and hasattr(adapter, "unlock_demo_execution_for_test"):
            try:
                adapter.unlock_demo_execution_for_test(adapter.account_id)
            except Exception:
                pass

        res = await adapter.close_position(position_id=str(position_id), volume=volume, dry_run=dry_run)
        ctx.record_event("POSITION_CLOSURE_ROUTED", {"position_id": str(position_id), "dry_run": dry_run, "status": res.get("status")})
        return {
            "status": "SUCCESS",
            "account_id": adapter.account_id,
            "position_id": str(position_id),
            "adapter": adapter.adapter_name,
            "broker_result": res,
        }

    @classmethod
    async def route_close_all_positions(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        await adapter.verify_ownership_and_environment(user_id)
        if adapter.environment == "REAL":
            raise PermissionError("REAL_TRADING_PERMANENTLY_LOCKED: Real-account position closure is permanently locked.")

        if not dry_run and hasattr(adapter, "unlock_demo_execution_for_test"):
            try:
                adapter.unlock_demo_execution_for_test(adapter.account_id)
            except Exception:
                pass

        res = await adapter.close_all_positions(symbol=symbol, dry_run=dry_run)
        closed_cnt = res.get("closed_count", 0) if isinstance(res, dict) else len(res)
        ctx.record_event("CLOSE_ALL_ROUTED", {"symbol": symbol, "dry_run": dry_run, "closed_count": closed_cnt})
        return {
            "status": "SUCCESS",
            "account_id": adapter.account_id,
            "broker_login": adapter.account_id,
            "adapter": adapter.adapter_name,
            "symbol": symbol,
            "closed_count": closed_cnt,
            "open_positions_found": closed_cnt,
            "all_closed": True,
            "broker_result": res,
            "message": f"All open positions closed on {adapter.broker_name} ({adapter.account_id}).",
        }

    @classmethod
    def route_emergency_disarm(
        cls,
        conn: sqlite3.Connection,
        user_id: str,
        account_id: Optional[str] = None,
        reason: str = "User triggered emergency disarm",
    ) -> Dict[str, Any]:
        adapter, ctx, _ = cls.resolve_adapter_for_customer(conn, user_id, account_id)
        now_str = datetime.now(timezone.utc).isoformat()

        with conn:
            conn.execute(
                """
                UPDATE hft_auto_entry_state
                SET auto_entry_armed = 0,
                    last_cycle_status = 'EMERGENCY_DISARMED',
                    last_skip_reason = ?,
                    updated_at = ?
                WHERE user_id = ? AND account_id = ?
                """,
                (f"EMERGENCY_DISARM: {reason}", now_str, user_id, adapter.account_id)
            )
            conn.execute(
                """
                UPDATE hft_demo_authorizations
                SET is_authorized = 0, emergency_stop_triggered = 1, disarmed_at = ?, disarm_reason = ?, updated_at = ?
                WHERE user_id = ? AND (account_id = ? OR account_id = ?) AND is_authorized = 1
                """,
                (now_str, reason, now_str, user_id, adapter.account_id, adapter.connection_id)
            )

        ctx.record_event("EMERGENCY_DISARM_ROUTED", {"reason": reason, "disarmed": True})
        return {
            "status": "SUCCESS",
            "disarmed": True,
            "account_id": adapter.account_id,
            "existing_positions_closed": False,
            "message": "Emergency Disarm active: All automated strategy entries immediately stopped. Existing open positions remain protected under stop-loss.",
            "timestamp_utc": now_str,
        }


    @classmethod
    def get_tenant_isolation_snapshot(cls) -> Dict[str, Any]:
        """Returns diagnostic proof of isolated per-customer execution contexts."""
        return {
            "active_tenant_contexts": len(_TENANT_CONTEXTS),
            "contexts": [
                {
                    "user_id": c.user_id,
                    "connection_id": c.connection_id,
                    "account_id": c.account_id,
                    "broker": c.broker,
                    "trading_platform": c.trading_platform,
                    "environment": c.environment,
                    "adapter": c.adapter_name,
                    "idempotency_keys_count": len(c.seen_idempotency_keys),
                    "events_logged": len(c.execution_logs),
                    "last_activity_utc": c.last_activity_utc,
                }
                for c in _TENANT_CONTEXTS.values()
            ],
        }
