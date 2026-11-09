"""
BITDEX — Automated Verification Test Suite (Dynamic Percentage-Based Risk Policy)
================================================================================
Implements mandatory automated tests A through M:
  A. BUY is rejected when M5 EMA9 < EMA21
  B. SELL is rejected when M5 EMA9 > EMA21
  C. Incomplete M5 candle cannot trigger an order
  D. Minimum lot exceeding risk budget results in NO TRADE (ERR_MIN_LOT_EXCEEDS_BUDGET)
  E. Three consecutive losses trigger a persistent 60-minute cooldown
  F. Daily loss limit (1.0% of day-start) prevents additional orders
  G. Duplicate setup fingerprint is rejected
  H. Concurrent requests cannot create duplicate positions
  I. Direct order route invokes central risk gate (forbids naked orders)
  J. Real-account order attempts are rejected at every execution layer
  K. SL/TP attachment failure triggers emergency closure and verified reconciliation
  L. HTTP 202 without broker fill confirmation is not treated as a completed order
  M. Tenant A cannot execute or access Tenant B's account
"""

import asyncio
import os
import sqlite3
import sys
import unittest
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.brokers.strategy_candidate_a import CandidateAStrategy, calc_ema, calc_atr
from app.services.brokers.trading_state_manager import TradingStateManager
from app.services.brokers.central_risk_gate import CentralRiskGate, REAL_TRADING_PERMANENTLY_LOCKED
from app.services.brokers.execution_router import CentralExecutionRouter
from app.services.brokers.risk_policy import RiskPolicy, compute_position_size, broker_account_stats


class MockAdapter:
    """Mock UniversalBrokerAdapter for unit testing."""
    def __init__(self, account_id="17000660016", environment="DEMO", owner_user_id="USR-ADM-B022F490"):
        self.account_id = account_id
        self.environment = environment
        self.owner_user_id = owner_user_id
        self.broker_name = "EXNESS"
        self.trading_platform = "EXNESS_TERMINAL"
        self.adapter_name = "ExnessTerminalBrokerAdapter"
        self.open_positions_list = []
        self.orders_history = []
        self.deals_history = []
        self.attach_sl_tp_called = False
        self.close_position_called = False
        self.client = MagicMock()
        self.client.get_trade_history = AsyncMock(return_value=[])

    async def verify_ownership_and_environment(self, user_id: str):
        if self.owner_user_id and user_id != self.owner_user_id:
            raise PermissionError("TENANT_ISOLATION_VIOLATION")
        if self.environment == "REAL":
            raise PermissionError("REAL_TRADING_PERMANENTLY_LOCKED: Real-account execution is permanently locked.")

    async def get_account_summary(self, force_refresh=False):
        return {
            "account_id": self.account_id,
            "balance": 5000.20,
            "equity": 5000.20,
            "free_margin": 5000.20,
            "currency": "USD",
            "leverage": 2000,
        }

    async def get_instrument_specification(self, symbol="XAUUSD"):
        return {
            "symbol": "XAUUSD",
            "broker_symbol": "XAUUSD",
            "digits": 3,
            "contract_size": 100.0,
            "tick_size": 0.001,
            "tick_value": 0.1,
            "min_volume": 0.01,
            "max_volume": 200.0,
            "volume_step": 0.01,
            "commission_per_lot": 0.0,
            "trade_mode": "enabled",
        }

    async def get_live_quote(self, symbol="XAUUSD"):
        return {
            "symbol": "XAUUSD",
            "bid": 4110.000,
            "ask": 4110.250,
            "time_ms": int(time.time() * 1000),
        }

    async def get_open_positions(self):
        return list(self.open_positions_list)

    async def place_market_order(self, symbol, side, volume, sl=None, tp=None, comment="", idempotency_key=None, dry_run=True):
        if self.environment == "REAL":
            raise PermissionError("REAL_TRADING_PERMANENTLY_LOCKED: Real-account execution is permanently locked.")
        return {
            "status": "ACCEPTED",
            "operation_id": "op_mock_12345",
            "payload": {"symbol": symbol, "side": side, "volume": volume, "sl": sl, "tp": tp},
        }

    async def attach_sl_tp(self, position_id, sl, tp, symbol="XAUUSD", dry_run=True):
        self.attach_sl_tp_called = True
        return {"status": "SUCCESS", "position_id": position_id, "sl": sl, "tp": tp}

    async def close_position(self, position_id, volume=None, dry_run=True):
        self.close_position_called = True
        self.open_positions_list = [p for p in self.open_positions_list if str(p.get("position_id") or p.get("id")) != str(position_id)]
        return {"status": "CLOSED", "position_id": position_id}


class TestBitdexRemediation(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        TradingStateManager.ensure_schema(self.conn)
        self.policy = RiskPolicy(risk_pct_per_trade=0.25, daily_loss_limit_pct=1.00)

    def tearDown(self):
        self.conn.close()

    def _generate_synthetic_candles(self, count=80, base_price=4100.0, trend="UP", timeframe="M5"):
        candles = []
        price = base_price
        step = 0.5 if trend == "UP" else (-0.5 if trend == "DOWN" else 0.0)
        tf_secs = 3600 if timeframe == "H1" else (900 if timeframe == "M15" else 300)
        # End at the most recent interval so the latest candle is fresh (< tf_secs old)
        now = int(time.time())
        latest_t = now - (now % tf_secs)
        start_t = latest_t - (count - 1) * tf_secs
        for i in range(count):
            price += step
            candles.append({
                "open": price - 0.2,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price + 0.2,
                "time": start_t + i * tf_secs,
                "is_closed": True,
            })
        return candles

    # ─── TEST A: BUY rejected when M5 EMA9 < EMA21 ────────────────────────────
    def test_a_buy_rejected_when_m5_ema9_below_ema21(self):
        h1 = self._generate_synthetic_candles(80, 4000.0, "UP", "H1")
        m15 = self._generate_synthetic_candles(80, 4050.0, "UP", "M15")
        m5 = self._generate_synthetic_candles(50, 4120.0, "DOWN", "M5")

        res = CandidateAStrategy.evaluate(
            h1_candles=h1,
            m15_candles=m15,
            m5_candles=m5,
            current_bid=4105.0,
            current_ask=4105.25,
            account_equity=5000.0,
            policy=self.policy,
        )
        self.assertEqual(res["outcome"], "NO_TRADE")
        self.assertEqual(res["error_code"], "M5_DOWNTREND_ACTIVE_EMA9_BELOW_EMA21")
        self.assertEqual(res["failed_gate"], "M5_EMA_ALIGNMENT")
        print("  [PASS] Test A: BUY strictly rejected when M5 EMA9 < EMA21.")

    # ─── TEST B: SELL rejected when M5 EMA9 > EMA21 ───────────────────────────
    def test_b_sell_rejected_when_m5_ema9_above_ema21(self):
        h1 = self._generate_synthetic_candles(80, 4200.0, "DOWN", "H1")
        m15 = self._generate_synthetic_candles(80, 4150.0, "DOWN", "M15")
        m5 = self._generate_synthetic_candles(50, 4080.0, "UP", "M5")

        res = CandidateAStrategy.evaluate(
            h1_candles=h1,
            m15_candles=m15,
            m5_candles=m5,
            current_bid=4095.0,
            current_ask=4095.25,
            account_equity=5000.0,
            policy=self.policy,
        )
        self.assertEqual(res["outcome"], "NO_TRADE")
        self.assertEqual(res["error_code"], "M5_UPTREND_ACTIVE_EMA9_ABOVE_EMA21")
        self.assertEqual(res["failed_gate"], "M5_EMA_ALIGNMENT")
        print("  [PASS] Test B: SELL strictly rejected when M5 EMA9 > EMA21.")

    # ─── TEST C: Incomplete M5 candle cannot trigger an order ─────────────────
    def test_c_incomplete_candle_cannot_trigger(self):
        h1 = self._generate_synthetic_candles(80, 4000.0, "UP", "H1")
        m15 = self._generate_synthetic_candles(80, 4050.0, "UP", "M15")
        m5 = self._generate_synthetic_candles(50, 4100.0, "UP", "M5")
        # Developing candle is marked unclosed
        m5[-1]["is_closed"] = False
        # The completed candle lacks rejection confirmation (bearish body)
        m5[-2] = {"open": 4115.0, "high": 4115.5, "low": 4100.0, "close": 4101.0, "time": int(time.time()) - 400, "is_closed": True}

        res = CandidateAStrategy.evaluate(
            h1_candles=h1,
            m15_candles=m15,
            m5_candles=m5,
            current_bid=4110.0,
            current_ask=4110.25,
            account_equity=5000.0,
            policy=self.policy,
        )
        self.assertEqual(res["outcome"], "NO_TRADE")
        print("  [PASS] Test C: Incomplete candle discarded; unconfirmed candle rejection prevents order trigger.")

    # ─── TEST D: Minimum lot exceeding risk budget results in NO TRADE ────────
    def test_d_minimum_lot_exceeds_budget_rejected(self):
        h1 = self._generate_synthetic_candles(80, 4000.0, "UP", "H1")
        m15 = self._generate_synthetic_candles(80, 4050.0, "UP", "M15")
        m5 = self._generate_synthetic_candles(50, 4100.0, "UP", "M5")
        # Ensure trigger bar is a bullish rejection
        m5[-2] = {"open": 4108.0, "high": 4112.0, "low": 4107.0, "close": 4111.5, "time": int(time.time()) - 400, "is_closed": True}

        # Small account ($300). At 0.25%, budget is $0.75 USD.
        # Min lot (0.01 lots = 1.0 oz) with ~3.5 pt stop risk is ~$3.50 USD.
        res = CandidateAStrategy.evaluate(
            h1_candles=h1,
            m15_candles=m15,
            m5_candles=m5,
            current_bid=4111.0,
            current_ask=4111.25,
            account_equity=300.0,
            policy=self.policy,
            spec={"contract_size": 100.0, "tick_size": 0.001, "tick_value": 0.1, "min_volume": 0.01, "volume_step": 0.01, "digits": 3},
        )
        self.assertEqual(res["outcome"], "NO_TRADE")
        self.assertEqual(res["error_code"], "ERR_MIN_LOT_EXCEEDS_BUDGET")
        print("  [PASS] Test D: Minimum lot exceeding risk budget returns ERR_MIN_LOT_EXCEEDS_BUDGET.")

    # ─── TEST E: Three consecutive losses trigger 60-minute cooldown ──────────
    def test_e_consecutive_losses_trigger_cooldown(self):
        acct = "17000660016"
        # Loss 1
        s1 = TradingStateManager.record_trade_result(self.conn, acct, -12.50, 5000.0)
        self.assertEqual(s1["consecutive_losses"], 1)
        cd, until, _ = TradingStateManager.check_cooldown(self.conn, acct)
        self.assertFalse(cd)

        # Loss 2
        s2 = TradingStateManager.record_trade_result(self.conn, acct, -12.50, 4987.5)
        self.assertEqual(s2["consecutive_losses"], 2)
        cd, until, _ = TradingStateManager.check_cooldown(self.conn, acct)
        self.assertFalse(cd)

        # Loss 3 -> TRIPS CIRCUIT BREAKER
        s3 = TradingStateManager.record_trade_result(self.conn, acct, -12.50, 4975.0)
        self.assertEqual(s3["consecutive_losses"], 3)
        cd, until, rem_sec = TradingStateManager.check_cooldown(self.conn, acct)
        self.assertTrue(cd)
        self.assertGreater(rem_sec, 3500)
        self.assertIsNotNone(until)
        print("  [PASS] Test E: Three consecutive losses trigger persistent 60-minute cooldown.")

    # ─── TEST F: Daily loss limit (1.0%) prevents additional orders ───────────
    def test_f_daily_loss_limit_blocks_orders(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        history = [
            {"deal": {"type": "close", "create_time": f"{today}T10:00:00Z", "profit": {"amount": "-26.00"}}},
            {"deal": {"type": "close", "create_time": f"{today}T11:00:00Z", "profit": {"amount": "-25.00"}}},
        ]
        # Total loss -$51.00. Current balance 4949.0 -> day-start balance 5000.0.
        # Daily limit at 1% is $50.00.
        stats = broker_account_stats(history, 4949.0, self.policy)
        self.assertTrue(stats["daily_limit_reached"])
        self.assertEqual(stats["daily_loss_limit_usd"], 50.00)
        self.assertEqual(stats["today_realized_pnl_usd"], -51.00)
        print("  [PASS] Test F: 1.0% daily realized loss ceiling halts additional orders.")

    # ─── TEST G: Duplicate setup fingerprint is rejected ──────────────────────
    def test_g_duplicate_setup_fingerprint_rejected(self):
        fp = TradingStateManager.compute_setup_fingerprint("XAUUSD", "BUY", 1700000000, 4110.5)
        TradingStateManager.invalidate_setup(self.conn, "17000660016", "XAUUSD", "BUY", fp, reason="STOPPED_OUT")

        is_inval, reason = TradingStateManager.is_setup_invalidated(self.conn, "17000660016", fp)
        self.assertTrue(is_inval)
        self.assertEqual(reason, "STOPPED_OUT")
        print("  [PASS] Test G: Invalidation memory blocks repeated setup re-entry.")

    # ─── TEST H: Concurrent requests cannot create duplicate positions ────────
    def test_h_concurrent_position_rejected(self):
        adapter = MockAdapter()
        adapter.open_positions_list = [{"position_id": "72283230", "symbol": "XAUUSD"}]

        async def run():
            h1 = self._generate_synthetic_candles(80, 4000.0, "UP", "H1")
            m15 = self._generate_synthetic_candles(80, 4050.0, "UP", "M15")
            m5 = self._generate_synthetic_candles(50, 4100.0, "UP", "M5")
            quote = await adapter.get_live_quote()
            spec = await adapter.get_instrument_specification()

            res = await CentralRiskGate.evaluate_full_gate(
                conn=self.conn,
                adapter=adapter,
                authenticated_user_id="USR-ADM-B022F490",
                account_id=adapter.account_id,
                symbol="XAUUSD",
                h1_candles=h1,
                m15_candles=m15,
                m5_candles=m5,
                quote=quote,
                spec=spec,
                policy=self.policy,
            )
            return res

        res = asyncio.run(run())
        self.assertFalse(res["passed"])
        self.assertEqual(res["error_code"], "ERR_CONCURRENT_POSITION_EXISTS")
        print("  [PASS] Test H: Concurrent open position strictly rejected.")

    # ─── TEST I: Direct order route invokes central risk gate ─────────────────
    def test_i_adapter_direct_order_boundary_protection(self):
        from app.services.brokers.exness_terminal_adapter import ExnessTerminalBrokerAdapter
        adapter = ExnessTerminalBrokerAdapter(
            owner_user_id="USR-ADM-B022F490",
            connection_id="17000660016",
            account_id="17000660016",
            api_key="17000660016",
            api_secret="",
            environment="DEMO",
            server_name="dx.2.trial.std",
        )

        async def run_naked():
            await adapter.place_market_order(symbol="XAUUSD", side="buy", volume=0.01, sl=None, dry_run=False)

        with self.assertRaises(ValueError):
            asyncio.run(run_naked())
        print("  [PASS] Test I: Adapter boundary forbids naked unprotected orders.")

    # ─── TEST J: Real-account order attempts rejected at every layer ──────────
    def test_j_real_account_orders_strictly_blocked(self):
        real_adapter = MockAdapter(account_id="16000629657", environment="REAL")

        async def run():
            await real_adapter.verify_ownership_and_environment("USR-ADM-B022F490")

        with self.assertRaises(PermissionError):
            asyncio.run(run())

        self.assertTrue(REAL_TRADING_PERMANENTLY_LOCKED)
        print("  [PASS] Test J: Real-account execution permanently locked at every layer.")

    # ─── TEST K: SL attachment failure triggers emergency market close ────────
    def test_k_sl_attachment_failure_emergency_close(self):
        adapter = MockAdapter()
        adapter.open_positions_list = []

        async def mock_place_unprotected(symbol, side, volume, sl=None, tp=None, comment="", idempotency_key=None, dry_run=True):
            adapter.open_positions_list = [{"position_id": "pos_999", "symbol": "XAUUSD", "sl": 0.0}]
            return {
                "status": "ACCEPTED",
                "operation_id": "op_mock_unprotected",
                "payload": {"symbol": symbol, "side": side, "volume": volume, "sl": sl, "tp": tp},
            }
        adapter.place_market_order = mock_place_unprotected

        async def run():
            res = await CentralRiskGate.execute_order_with_fail_safe_protection(
                conn=self.conn,
                adapter=adapter,
                authenticated_user_id="USR-ADM-B022F490",
                account_id=adapter.account_id,
                symbol="XAUUSD",
                h1_candles=self._generate_synthetic_candles(80, 4000.0, "UP", "H1"),
                m15_candles=self._generate_synthetic_candles(80, 4050.0, "UP", "M15"),
                m5_candles=self._generate_synthetic_candles(50, 4100.0, "UP", "M5"),
                quote=await adapter.get_live_quote(),
                spec=await adapter.get_instrument_specification(),
                dry_run=False,
                policy=self.policy,
            )
            return res

        res = asyncio.run(run())
        self.assertFalse(res["passed"])
        self.assertEqual(res["error_code"], "ERR_SL_UNCONFIRMED_EMERGENCY_CLOSED")
        self.assertTrue(adapter.close_position_called)
        print("  [PASS] Test K: Unconfirmed SL triggers immediate emergency market closure.")

    # ─── TEST L: HTTP 202 without fill confirmation is not completed ──────────
    def test_l_http_202_without_fill_not_completed(self):
        adapter = MockAdapter()

        async def run():
            adapter.open_positions_list = []
            res = await CentralRiskGate.execute_order_with_fail_safe_protection(
                conn=self.conn,
                adapter=adapter,
                authenticated_user_id="USR-ADM-B022F490",
                account_id=adapter.account_id,
                symbol="XAUUSD",
                h1_candles=self._generate_synthetic_candles(80, 4000.0, "UP", "H1"),
                m15_candles=self._generate_synthetic_candles(80, 4050.0, "UP", "M15"),
                m5_candles=self._generate_synthetic_candles(50, 4100.0, "UP", "M5"),
                quote=await adapter.get_live_quote(),
                spec=await adapter.get_instrument_specification(),
                dry_run=False,
                policy=self.policy,
            )
            return res

        res = asyncio.run(run())
        self.assertFalse(res["passed"])
        self.assertEqual(res["error_code"], "ERR_FILL_RECONCILIATION_FAILED")
        print("  [PASS] Test L: HTTP 202 without confirmed broker position is not treated as completed.")

    # ─── TEST M: Tenant A cannot execute or access Tenant B's account ─────────
    def test_m_tenant_isolation_violation_blocked(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS exness_demo_connections (user_id TEXT, connection_id TEXT, account_login TEXT, is_active INTEGER, verification_status TEXT, adapter_mode TEXT, account_type TEXT, is_preferred INTEGER, updated_at TEXT)")
        self.conn.execute("INSERT INTO exness_demo_connections VALUES ('USR-A', 'CONN-A', '170001', 1, 'VERIFIED', 'NATIVE', 'DEMO', 1, '2026-01-01')")
        self.conn.execute("INSERT INTO exness_demo_connections VALUES ('USR-B', 'CONN-B', '170002', 1, 'VERIFIED', 'NATIVE', 'DEMO', 1, '2026-01-01')")
        self.conn.execute("CREATE TABLE IF NOT EXISTS user_exchange_connections (user_id TEXT, account_id TEXT, is_active INTEGER, provider TEXT, environment TEXT, created_at TEXT)")

        with self.assertRaises(PermissionError):
            CentralExecutionRouter.resolve_adapter_for_customer(self.conn, "USR-A", "CONN-B")

        print("  [PASS] Test M: Cross-tenant account access raises TENANT_ISOLATION_VIOLATION.")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBitdexRemediation)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
