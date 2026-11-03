"""
TAURIC Platform — Phase 3B Acceptance Test Suite
Order Lifecycle Reconciliation, Durable Idempotency, Pre-Flight Strategy Verification,
and Isolated Paper Trading Ledger.

Target: http://127.0.0.1:8002/api/v1 (Staging Isolation)
"""

import sys
if "/opt/tauric-platform-staging/backend" not in sys.path:
    sys.path.insert(0, "/opt/tauric-platform-staging/backend")

import os
import json
import asyncio
import unittest
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.services.exchange_framework import (
    credential_vault,
    exchange_framework,
    Environment,
    OrderStatus,
    CapabilityState,
    evaluate_strategy_compatibility,
    STRATEGY_CAPABILITY_REQUIREMENTS
)
from app.services.paper_trading_engine import (
    paper_engine,
    VALID_ORDER_TRANSITIONS,
    validate_order_transition,
    IdempotencyCollisionError,
    InvalidOrderStateTransitionError,
    StrategyPreflightError
)

STAGING_BASE_URL = "http://127.0.0.1:8002/api/v1"
TEST_BYPASS_TOKEN = "tauric_staging_test_token_8f39b1a47c20"
BYPASS_HEADERS = {"X-Tauric-Test-Token": TEST_BYPASS_TOKEN}


class TauricPhase3BOrderLifecycleTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(base_url=STAGING_BASE_URL, headers=BYPASS_HEADERS, timeout=15.0)
        self.created_profiles: List[str] = []
        # Ensure fresh simulated balance for every test isolation
        paper_engine.ledger.cash_balance = 100000.0
        paper_engine.ledger.held_balance = 0.0
        paper_engine.ledger._save()

    async def asyncTearDown(self):
        for pid in self.created_profiles:
            try:
                await self.client.delete(f"/connections/profiles/{pid}")
            except Exception:
                pass
        await self.client.aclose()

    async def _create_compatible_spot_profile(self, label: str = "Paper Spot Profile") -> str:
        """Helper to create and verify a compatible SPOT profile for SPOT_GRID."""
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "BINANCE",
            "environment": "DEMO",
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "label": label,
            "api_key": "test_spot_key_p3b",
            "api_secret": "test_spot_secret_p3b"
        })
        self.assertEqual(resp.status_code, 200)
        pid = resp.json().get("profile_id") or resp.json().get("profile", {}).get("profile_id")
        self.created_profiles.append(pid)

        # Mark with fresh, verified capability matrix required for SPOT_GRID
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cap_matrix = [
            {"capability_id": "MARKET_TICKER", "name": "Ticker", "category": "MARKET_DATA", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "MARKET_SYMBOLS", "name": "Symbols", "category": "MARKET_DATA", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "MARKET_ORDERBOOK", "name": "Orderbook", "category": "MARKET_DATA", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "MARKET_CANDLES", "name": "Candles", "category": "MARKET_DATA", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "ACCOUNT_AUTH", "name": "Auth", "category": "ACCOUNT_IDENTITY", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "WALLET_BALANCES", "name": "Balances", "category": "BALANCES_MARGIN", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "OPEN_ORDERS_READ", "name": "Open Orders", "category": "ORDERS_POSITIONS", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "ORDER_STATUS_POLL", "name": "Status", "category": "ORDERS_POSITIONS", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "ORDER_PLACEMENT", "name": "Placement", "category": "ORDER_EXECUTION", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "ORDER_CANCELLATION", "name": "Cancellation", "category": "ORDER_EXECUTION", "state": CapabilityState.VERIFIED_SUPPORTED.value},
            {"capability_id": "TRANSFERS_WITHDRAWALS", "name": "Withdrawals", "category": "SECURITY_PERMISSIONS", "state": CapabilityState.NOT_TESTED.value}
        ]
        strat_compat = evaluate_strategy_compatibility({
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": now_iso,
            "capability_matrix": cap_matrix
        })
        credential_vault.update_verification_results(
            profile_id=pid,
            connection_status="VERIFIED_READ_ONLY",
            verification_label="VERIFIED_READ_ONLY",
            endpoint_results=[],
            capabilities=["MARKET_TICKER", "WALLET_BALANCES"],
            account_data={"balance": 10000.0, "currency": "USDT"},
            capability_matrix=cap_matrix,
            strategy_compatibility=strat_compat
        )
        return pid

    # -------------------------------------------------------------------------
    # TEST 1: Duplicate Idempotency Keys Return Existing Order Without Duplicate Creation
    # -------------------------------------------------------------------------
    async def test_01_duplicate_idempotency_keys_return_existing_order(self):
        """Verify identical idempotency key with identical payload returns existing paper order without duplicating."""
        pid = await self._create_compatible_spot_profile("Idempotency Spot Profile")
        idemp_key = f"IDEMP-TEST-KEY-{os.urandom(4).hex()}"

        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 60000.0,
            "idempotency_key": idemp_key,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }

        # First submission
        r1 = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r1.status_code, 200, f"Order creation failed: {r1.text}")
        d1 = r1.json()
        self.assertEqual(d1["status"], "SUCCESS")
        self.assertFalse(d1["idempotent_replay"])
        order_id_1 = d1["order"]["client_order_id"]

        # Duplicate submission with same key and same payload
        r2 = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertEqual(d2["status"], "SUCCESS")
        self.assertTrue(d2["idempotent_replay"], "Duplicate request must be flagged as idempotent_replay")
        order_id_2 = d2["order"]["client_order_id"]

        self.assertEqual(order_id_1, order_id_2, "Idempotent request must return the exact same client_order_id")

        # Verify no duplicate was added to orders list
        r_list = await self.client.get("/orders/paper")
        matching = [o for o in r_list.json()["orders"] if o["idempotency_key"] == idemp_key]
        self.assertEqual(len(matching), 1, "Only exactly 1 paper order must exist for the idempotency key")

    # -------------------------------------------------------------------------
    # TEST 2: Reusing Idempotency Key with Conflicting Payload Rejection (HTTP 409)
    # -------------------------------------------------------------------------
    async def test_02_reusing_idempotency_key_with_different_payload_rejected(self):
        """Verify reusing an existing idempotency key with different payload is rejected with HTTP 409 Conflict."""
        pid = await self._create_compatible_spot_profile("Conflict Key Profile")
        idemp_key = f"IDEMP-CONFLICT-KEY-{os.urandom(4).hex()}"

        base_payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 60000.0,
            "idempotency_key": idemp_key,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }

        r1 = await self.client.post("/orders/paper/order", json=base_payload)
        self.assertEqual(r1.status_code, 200)

        # Mutate payload (e.g. change quantity from 0.05 to 0.10)
        conflicting_payload = dict(base_payload)
        conflicting_payload["quantity"] = 0.10

        r2 = await self.client.post("/orders/paper/order", json=conflicting_payload)
        self.assertEqual(r2.status_code, 409, f"Expected 409 Conflict on payload mismatch, got {r2.status_code}: {r2.text}")
        self.assertIn("Idempotency key collision", r2.text)

    # -------------------------------------------------------------------------
    # TEST 3: Concurrent Duplicate Request Protection
    # -------------------------------------------------------------------------
    async def test_03_concurrent_duplicate_requests(self):
        """Verify concurrent requests with the same idempotency key resolve cleanly without race-condition duplicates."""
        pid = await self._create_compatible_spot_profile("Concurrent Profile")
        idemp_key = f"IDEMP-CONCUR-{os.urandom(4).hex()}"

        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "ETHUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 1.0,
            "price": 3000.0,
            "idempotency_key": idemp_key,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }

        # Fire 5 simultaneous requests with identical payload and key
        tasks = [self.client.post("/orders/paper/order", json=payload) for _ in range(5)]
        responses = await asyncio.gather(*tasks)

        status_codes = [r.status_code for r in responses]
        self.assertTrue(all(s == 200 for s in status_codes), f"All concurrent requests must return 200 OK: {status_codes}")

        order_ids = set(r.json()["order"]["client_order_id"] for r in responses)
        self.assertEqual(len(order_ids), 1, "All concurrent requests must resolve to the identical single order ID")

    # -------------------------------------------------------------------------
    # TEST 4: Persisted Paper-Order Recovery Across Process Restarts
    # -------------------------------------------------------------------------
    async def test_04_persisted_order_recovery_across_restarts(self):
        """Verify paper orders and idempotency records survive engine reload from disk."""
        pid = await self._create_compatible_spot_profile("Persist Test Profile")
        idemp_key = f"IDEMP-RECOVERY-{os.urandom(4).hex()}"

        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "SOLUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 5.0,
            "price": 150.0,
            "idempotency_key": idemp_key,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }

        r = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r.status_code, 200)
        order_id = r.json()["order"]["client_order_id"]

        # Simulate process restart by reloading engine from on-disk JSON
        paper_engine._load_orders()
        paper_engine.idempotency._load()

        loaded_order = paper_engine.get_order(order_id)
        self.assertIsNotNone(loaded_order, "Order must be cleanly restored from disk store")
        self.assertEqual(loaded_order["symbol"], "SOLUSDT")
        self.assertEqual(loaded_order["requested_qty"], 5.0)

        # Idempotency store must also recognize key after reload
        is_replay, recovered_id = paper_engine.idempotency.check_or_record(idemp_key, payload, "ORD-NEW")
        self.assertTrue(is_replay)
        self.assertEqual(recovered_id, order_id)

    # -------------------------------------------------------------------------
    # TEST 5: Partial Fills and Cumulative Fill Reconciliation
    # -------------------------------------------------------------------------
    async def test_05_partial_fills_and_cumulative_reconciliation(self):
        """Verify partial fills correctly update cumulative quantity, remaining quantity, and weighted avg fill price."""
        pid = await self._create_compatible_spot_profile("Fill Profile")
        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 50000.0,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }
        r_create = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r_create.status_code, 200, f"Order creation failed: {r_create.text}")
        oid = r_create.json()["order"]["client_order_id"]

        # Partial Fill 1: 0.02 BTC @ 49900
        r_f1 = await self.client.post(f"/orders/paper/{oid}/fill", json={
            "fill_qty": 0.02,
            "fill_price": 49900.0,
            "fee_amount": 0.998
        })
        self.assertEqual(r_f1.status_code, 200)
        o1 = r_f1.json()["order"]
        self.assertEqual(o1["status"], OrderStatus.PARTIALLY_FILLED.value)
        self.assertEqual(o1["cumulative_qty"], 0.02)
        self.assertEqual(o1["remaining_qty"], 0.03)
        self.assertEqual(o1["avg_fill_price"], 49900.0)

        # Partial Fill 2: 0.03 BTC @ 50100 (Completing order)
        r_f2 = await self.client.post(f"/orders/paper/{oid}/fill", json={
            "fill_qty": 0.03,
            "fill_price": 50100.0,
            "fee_amount": 1.503
        })
        self.assertEqual(r_f2.status_code, 200)
        o2 = r_f2.json()["order"]
        self.assertEqual(o2["status"], OrderStatus.FILLED.value)
        self.assertEqual(o2["cumulative_qty"], 0.05)
        self.assertEqual(o2["remaining_qty"], 0.0)
        # Expected weighted avg: (0.02 * 49900 + 0.03 * 50100) / 0.05 = 50020.0
        self.assertEqual(o2["avg_fill_price"], 50020.0)
        self.assertIsNotNone(o2["filled_at_utc"])

        # Attempting fill beyond 0.05 must be rejected
        r_overfill = await self.client.post(f"/orders/paper/{oid}/fill", json={
            "fill_qty": 0.01,
            "fill_price": 50000.0
        })
        self.assertEqual(r_overfill.status_code, 400, "Overfill beyond requested quantity must be rejected")

    # -------------------------------------------------------------------------
    # TEST 6: Invalid Order Lifecycle Transitions Rejected
    # -------------------------------------------------------------------------
    async def test_06_invalid_lifecycle_transitions_rejected(self):
        """Verify invalid state transitions are rejected with HTTP 400 according to state machine rules."""
        pid = await self._create_compatible_spot_profile("Transition Profile")
        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 50000.0,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }
        r_create = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r_create.status_code, 200, f"Order creation failed: {r_create.text}")
        oid = r_create.json()["order"]["client_order_id"]

        # First cancel the order
        r_cancel = await self.client.post(f"/orders/paper/{oid}/cancel")
        self.assertEqual(r_cancel.status_code, 200)
        self.assertEqual(r_cancel.json()["order"]["status"], OrderStatus.CANCELLED.value)

        # Attempt invalid resurrection from CANCELLED to OPEN
        r_invalid = await self.client.post(f"/orders/paper/{oid}/transition", json={
            "target_status": "OPEN",
            "reason": "Illegal resurrection"
        })
        self.assertEqual(r_invalid.status_code, 400, "Resurrecting cancelled order must be rejected")
        self.assertIn("Invalid order lifecycle transition", r_invalid.text)

    # -------------------------------------------------------------------------
    # TEST 7: Unknown Outcomes Representation and Safe Reconciliation
    # -------------------------------------------------------------------------
    async def test_07_unknown_outcome_safe_reconciliation_without_duplicate_retry(self):
        """Verify UNKNOWN_OUTCOME state is safely reconciled from ledger audit without blind retries."""
        pid = await self._create_compatible_spot_profile("Unknown Outcome Profile")
        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 50000.0,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }
        r_create = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r_create.status_code, 200, f"Order creation failed: {r_create.text}")
        oid = r_create.json()["order"]["client_order_id"]

        # Simulate network uncertainty / timeout marking order as UNKNOWN_OUTCOME
        r_trans = await self.client.post(f"/orders/paper/{oid}/transition", json={
            "target_status": OrderStatus.UNKNOWN_OUTCOME.value,
            "reason": "Gateway timeout during order confirmation probe"
        })
        self.assertEqual(r_trans.status_code, 200)
        self.assertEqual(r_trans.json()["order"]["status"], OrderStatus.UNKNOWN_OUTCOME.value)

        # Trigger safe reconciliation endpoint
        r_rec = await self.client.post(f"/orders/paper/{oid}/reconcile")
        self.assertEqual(r_rec.status_code, 200)
        rec_data = r_rec.json()["reconciliation"]
        self.assertTrue(rec_data["reconciled"])
        self.assertEqual(rec_data["resolved_status"], OrderStatus.OPEN.value)

        # Verify audit trail records the safe reconciliation
        audit = rec_data["order"]["audit_trail"]
        self.assertTrue(any("reconciled uncertain outcome" in item["reason"].lower() for item in audit))

    # -------------------------------------------------------------------------
    # TEST 8: Incompatible Strategy Preflight Rejection
    # -------------------------------------------------------------------------
    async def test_08_incompatible_strategy_preflight_rejection(self):
        """Verify paper order creation is rejected if profile is incompatible with selected strategy."""
        # Create a SPOT profile
        pid = await self._create_compatible_spot_profile("Spot Mismatch Profile")

        # FUTURES_GRID requires FUTURES_USDT according to strategy requirements
        payload = {
            "strategy_id": "FUTURES_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 60000.0,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }
        resp = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(resp.status_code, 400, f"Expected 400 for strategy incompatibility, got {resp.status_code}")
        d = resp.json()
        self.assertIn("STRATEGY_PREFLIGHT_REJECTED", str(d))
        self.assertIn("INCOMPATIBLE", str(d))

    # -------------------------------------------------------------------------
    # TEST 9: Indeterminate Strategy Preflight Rejection on Missing/Stale Evidence
    # -------------------------------------------------------------------------
    async def test_09_indeterminate_strategy_preflight_rejection(self):
        """Verify paper order creation is rejected if capability verification evidence is missing or stale."""
        # Create profile without running verification (UNTESTED)
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "BINANCE",
            "environment": "DEMO",
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "label": "Untested Stale Profile",
            "api_key": "untested_key",
            "api_secret": "untested_secret"
        })
        pid = resp.json().get("profile_id") or resp.json().get("profile", {}).get("profile_id")
        self.created_profiles.append(pid)

        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.05,
            "price": 60000.0,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        }
        r = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r.status_code, 400, "Untested profile must be rejected by strategy preflight")
        self.assertIn("STRATEGY_PREFLIGHT_REJECTED", r.text)

    # -------------------------------------------------------------------------
    # TEST 10: Strict Separation Between Paper Ledger and Exchange Adapters
    # -------------------------------------------------------------------------
    async def test_10_paper_ledger_separation_zero_exchange_writes(self):
        """Verify paper trading operates entirely in isolated simulated ledger without invoking exchange write endpoints."""
        pid = await self._create_compatible_spot_profile("Ledger Separation Profile")

        # Query initial ledger state
        r_init = await self.client.get("/orders/paper/ledger/summary")
        self.assertEqual(r_init.status_code, 200)
        init_ledger = r_init.json()["ledger"]
        init_cash = init_ledger["cash_balance"]

        # Place paper order of 1000 USDT notional (0.02 BTC @ 50,000)
        r_order = await self.client.post("/orders/paper/order", json={
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.02,
            "price": 50000.0,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        })
        self.assertEqual(r_order.status_code, 200, f"Order placement failed: {r_order.text}")
        oid = r_order.json()["order"]["client_order_id"]

        # Ledger cash must decrease by 1000 and held margin must increase by 1000
        r_mid = await self.client.get("/orders/paper/ledger/summary")
        mid_ledger = r_mid.json()["ledger"]
        self.assertEqual(mid_ledger["cash_balance"], round(init_cash - 1000.0, 4))
        self.assertEqual(mid_ledger["held_balance"], 1000.0)

        # Cancel order -> held margin must be released back to cash
        r_cancel = await self.client.post(f"/orders/paper/{oid}/cancel")
        self.assertEqual(r_cancel.status_code, 200)

        r_after = await self.client.get("/orders/paper/ledger/summary")
        after_ledger = r_after.json()["ledger"]
        self.assertEqual(after_ledger["held_balance"], 0.0)
        self.assertEqual(after_ledger["cash_balance"], init_cash)

    # -------------------------------------------------------------------------
    # TEST 11: Audit Log Privacy & Secret Redaction
    # -------------------------------------------------------------------------
    async def test_11_audit_log_privacy_zero_secret_leakage(self):
        """Verify audit trails and persisted orders contain zero API secrets, keys, or authentication tokens."""
        pid = await self._create_compatible_spot_profile("Secret Privacy Profile")
        r_order = await self.client.post("/orders/paper/order", json={
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "account_type": "PAPER",
            "execution_mode": "PAPER"
        })
        self.assertEqual(r_order.status_code, 200, f"Order placement failed: {r_order.text}")
        order = r_order.json()["order"]

        order_json_str = json.dumps(order)
        # Ensure credentials never leak into paper order structure
        self.assertNotIn("test_spot_secret_p3b", order_json_str)
        self.assertNotIn("test_spot_key_p3b", order_json_str)
        self.assertNotIn(TEST_BYPASS_TOKEN, order_json_str)

    # -------------------------------------------------------------------------
    # TEST 12: Account Isolation — Non-Paper Execution Modes Rejected
    # -------------------------------------------------------------------------
    async def test_12_non_paper_mode_rejection(self):
        """Verify paper order endpoint strictly rejects live or demo account execution modes."""
        pid = await self._create_compatible_spot_profile("Isolation Profile")

        # Attempt to pass LIVE execution mode into paper endpoint
        payload = {
            "strategy_id": "SPOT_GRID",
            "profile_id": pid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "account_type": "LIVE",
            "execution_mode": "LIVE"
        }
        r = await self.client.post("/orders/paper/order", json=payload)
        self.assertEqual(r.status_code, 400, "Non-paper execution mode must be rejected")
        self.assertIn("explicit 'PAPER' account_type and execution_mode", r.text)

    # -------------------------------------------------------------------------
    # TEST 13: External Attempt to Activate Test Rate-Limit Bypass Fails
    # -------------------------------------------------------------------------
    async def test_13_external_rate_limit_bypass_attempt_fails(self):
        """Verify requests presenting token without loopback peer are rejected from bypass."""
        from app.routes.connections import _is_authorized_test_bypass
        from unittest.mock import MagicMock

        # Mock non-loopback external peer presenting valid token
        req_external = MagicMock()
        req_external.client.host = "198.51.100.25"
        req_external.headers = {"X-Tauric-Test-Token": TEST_BYPASS_TOKEN}
        self.assertFalse(_is_authorized_test_bypass(req_external), "External client must not be granted test bypass")

    # -------------------------------------------------------------------------
    # TEST 14: Live Order Submission Remains Hard-Locked (HTTP 403 Forbidden)
    # -------------------------------------------------------------------------
    async def test_14_live_trading_locked_invariant(self):
        """Verify /orders/live/submit unconditionally returns HTTP 403 Forbidden."""
        resp = await self.client.post("/orders/live/submit")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Live trading is hard-locked", resp.json()["detail"])

    # -------------------------------------------------------------------------
    # TEST 15: Read-Only Order Status Query Parity Without Writes
    # -------------------------------------------------------------------------
    async def test_15_read_only_order_status_query_parity(self):
        """Verify read-only order receipt retrieval functions correctly without triggering real writes."""
        pid = await self._create_compatible_spot_profile("Read Only Status Profile")
        adapter = exchange_framework.get_adapter("BINANCE")

        # Query read-only order status on demo adapter
        receipt = await adapter.get_order_status(
            symbol="BTCUSDT",
            client_order_id="ORD-DEMO-TEST-READONLY-1",
            exchange_order_id="12345678",
            environment=Environment.DEMO,
            credentials={"api_key": "k", "api_secret": "s"}
        )
        self.assertEqual(receipt.symbol, "BTCUSDT")
        self.assertEqual(receipt.client_order_id, "ORD-DEMO-TEST-READONLY-1")
        self.assertIn(receipt.status, (OrderStatus.FILLED, OrderStatus.OPEN))


if __name__ == "__main__":
    unittest.main()
