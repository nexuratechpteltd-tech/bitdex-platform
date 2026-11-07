"""
BITDEX — PHASE 7D: CONTROLLED DEMO EXECUTION READINESS FULL ACCEPTANCE SUITE
============================================================================
Exhaustive test suite verifying all 10 Stage 2-4 isolation and risk barrier gates.
"""

import sys
import json
import sqlite3
import unittest
from datetime import datetime, timezone
from fastapi import HTTPException

sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.saas_db import get_db_connection
from app.services.demo_execution_service import (
    DemoExecutionService,
    ensure_demo_tables,
    ALLOWED_EXNESS_SYMBOLS,
    MAX_SIMULTANEOUS_POSITIONS,
    MAX_ENTRIES_PER_INSTRUMENT,
    MAX_TOTAL_EXPOSURE_PCT,
    MAX_DAILY_LOSS_USD,
    MIN_RISK_REWARD_RATIO
)


class TestPhase7DDemoExecutionFull(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = get_db_connection()
        ensure_demo_tables(cls.conn)
        cls.primary_user = "USR-ADM-B022F490"
        cls.target_demo_account = "EXN-CONN-A4E7BE39D276"  # Exness MT5 Demo #474861031
        cls.target_real_account = "CONN-BIN-LIVE-MIGRATED"   # Real account
        cls.conflicting_account = "EXN-CONN-3D40DE9B8CE8"   # Tenant conflict

    @classmethod
    def tearDownClass(cls):
        # Clean up any test positions or records
        cls.conn.execute("DELETE FROM futures_positions WHERE user_id = ? AND position_id LIKE 'TEST-POS-%'", (cls.primary_user,))
        cls.conn.execute("DELETE FROM futures_realized_pnl WHERE user_id = ? AND pnl_id LIKE 'TEST-PNL-%'", (cls.primary_user,))
        cls.conn.commit()
        cls.conn.close()

    def test_01_demo_authorization_success(self):
        """1. Explicit verified Demo account receives an isolated Demo authorization token."""
        res = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD",
            confirm_demo_only=True
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["authorization"]["is_authorized"])
        self.assertTrue(res["authorization"]["auth_token"].startswith("DEMO-AUTH-"))
        self.assertEqual(res["authorization"]["environment"], "DEMO")
        self.assertEqual(res["authorization"]["broker_login"], "474861031")
        self.assertEqual(res["authorization"]["server_name"], "Exness-MT5Trial15")
        self.assertEqual(res["authorization"]["worker_instance_id"], "INST-474861031")
        self.assertEqual(res["authorization"]["adapter_name"], "EXNESS_MT5_GATEWAY")

        # Global safety locks
        self.assertTrue(res["global_safety_locks"]["live_trading_locked"])
        self.assertTrue(res["global_safety_locks"]["real_trading_locked"])
        self.assertTrue(res["global_safety_locks"]["read_only_mode"])
        self.assertEqual(res["global_safety_locks"]["orders_dispatched_to_broker"], 0)

    def test_02_hard_reject_real_account(self):
        """2. Any Real account authorization attempt is hard-rejected with HTTP 403."""
        with self.assertRaises(HTTPException) as ctx:
            DemoExecutionService.authorize_demo_execution(
                conn=self.conn,
                user_id=self.primary_user,
                account_id=self.target_real_account,
                symbol="BTCUSD"
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("REAL_TRADING_PERMANENTLY_LOCKED", ctx.exception.detail)

    def test_03_reject_duplicate_tenant_conflict_account(self):
        """3. Duplicate tenant conflict account is strictly rejected with HTTP 403."""
        with self.assertRaises(HTTPException) as ctx:
            DemoExecutionService.authorize_demo_execution(
                conn=self.conn,
                user_id="USR-66BCFD7350",
                account_id=self.conflicting_account,
                symbol="BTCUSD"
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("DUPLICATE_TENANT_CONFLICT", ctx.exception.detail)

    def test_04_reject_cross_tenant_unauthorized_account(self):
        """4. Unauthorized cross-tenant account request is blocked."""
        with self.assertRaises(HTTPException) as ctx:
            DemoExecutionService.authorize_demo_execution(
                conn=self.conn,
                user_id="USR-00FC311000",
                account_id=self.target_demo_account,
                symbol="BTCUSD"
            )
        self.assertIn(ctx.exception.status_code, (403, 404))

    def test_05_mandatory_sl_and_tp_enforcement(self):
        """5. Rejection of orders missing Stop Loss, Take Profit, or with invalid distances."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth["authorization"]["auth_token"]

        # Missing SL
        with self.assertRaises(HTTPException) as ctx_sl:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={"symbol": "BTCUSD", "direction": "BUY", "entry_price": 75800.0, "volume": 0.01, "stop_loss_price": 0.0, "take_profit_price": 76000.0}
            )
        self.assertEqual(ctx_sl.exception.status_code, 400)
        self.assertIn("MANDATORY_STOP_LOSS_MISSING", ctx_sl.exception.detail)

        # Missing TP
        with self.assertRaises(HTTPException) as ctx_tp:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={"symbol": "BTCUSD", "direction": "BUY", "entry_price": 75800.0, "volume": 0.01, "stop_loss_price": 75700.0, "take_profit_price": 0.0}
            )
        self.assertEqual(ctx_tp.exception.status_code, 400)
        self.assertIn("MANDATORY_TAKE_PROFIT_MISSING", ctx_tp.exception.detail)

        # Stop loss too close (< $0.50 points)
        with self.assertRaises(HTTPException) as ctx_dist:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={"symbol": "BTCUSD", "direction": "BUY", "entry_price": 75800.0, "volume": 0.01, "stop_loss_price": 75799.70, "take_profit_price": 76000.0}
            )
        self.assertEqual(ctx_dist.exception.status_code, 400)
        self.assertIn("STOP_LOSS_TOO_CLOSE", ctx_dist.exception.detail)

        # R:R < 1.50
        with self.assertRaises(HTTPException) as ctx_rr:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={"symbol": "BTCUSD", "direction": "BUY", "entry_price": 75800.0, "volume": 0.01, "stop_loss_price": 75700.0, "take_profit_price": 75850.0}
            )
        self.assertEqual(ctx_rr.exception.status_code, 400)
        self.assertIn("INSUFFICIENT_RISK_REWARD", ctx_rr.exception.detail)

    def test_06_risk_barrier_max_positions_limit(self):
        """6. Risk Barrier Gate: Reject order when 3 simultaneous positions are open."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth["authorization"]["auth_token"]

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Insert 3 test open positions
        for i in range(3):
            self.conn.execute(
                """
                INSERT OR REPLACE INTO futures_positions
                (position_id, user_id, account_id, symbol, position_side, margin_type, leverage, quantity,
                 entry_price, mark_price, liquidation_price, isolated_margin, unrealized_pnl, realized_pnl,
                 status, active_stop_loss_order_id, opened_at, updated_at, entry_fee_usd, stop_exchange_order_id)
                VALUES (?, ?, ?, 'ETHUSD', 'LONG', 'ISOLATED', 3, 0.1, 2500.0, 2500.0, 1800.0, 83.33, 0.0, 0.0, 'OPEN', 'SL-TEST', ?, ?, 0.25, 'ST-TEST')
                """,
                (f"TEST-POS-{i}", self.primary_user, self.target_demo_account, now_str, now_str)
            )
        self.conn.commit()

        # Attempt 4th position -> Must be rejected with 429
        with self.assertRaises(HTTPException) as ctx:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={"symbol": "BTCUSD", "direction": "BUY", "entry_price": 75800.0, "volume": 0.01, "stop_loss_price": 75700.0, "take_profit_price": 76000.0}
            )
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("POSITION_LIMIT_REACHED", ctx.exception.detail)

        # Clean up test positions
        self.conn.execute("DELETE FROM futures_positions WHERE user_id = ? AND position_id LIKE 'TEST-POS-%'", (self.primary_user,))
        self.conn.commit()

    def test_07_risk_barrier_exposure_cap(self):
        """7. Risk Barrier Gate: Reject order exceeding 30% account equity exposure cap."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth["authorization"]["auth_token"]

        # On equity $5076.03, 30% cap is $1522.80.
        # Margin for 0.1 BTC at 75800 with 3x leverage = (75800 * 0.1)/3 = 2526.67 > 1522.80
        with self.assertRaises(HTTPException) as ctx:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={
                    "symbol": "BTCUSD",
                    "direction": "BUY",
                    "entry_price": 75800.0,
                    "volume": 0.1,  # Large volume
                    "stop_loss_price": 75700.0,
                    "take_profit_price": 76000.0,
                    "account_equity": 5076.03
                }
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("EXPOSURE_CAP_EXCEEDED", ctx.exception.detail)

    def test_08_risk_barrier_daily_loss_limit(self):
        """8. Risk Barrier Gate: Reject order when daily loss limit ($50.00 USD) is reached."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth["authorization"]["auth_token"]

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Insert a realized loss of -$55.00 for today
        self.conn.execute(
            """
            INSERT INTO futures_realized_pnl
            (pnl_id, user_id, account_id, symbol, position_id, closing_order_id, entry_price, exit_price,
             closed_qty, gross_pnl_usd, total_fees_usd, net_pnl_usd, funding_fee_total_usd, source, created_at)
            VALUES ('TEST-PNL-1', ?, ?, 'BTCUSD', 'POS-TEST', 'ORD-TEST', 76000.0, 75450.0, 0.1, -55.0, 0.5, -55.0, 0.0, 'EXNESS', ?)
            """,
            (self.primary_user, self.target_demo_account, now_str)
        )
        self.conn.commit()

        # Attempt order -> Must be rejected with 429
        with self.assertRaises(HTTPException) as ctx:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={"symbol": "BTCUSD", "direction": "BUY", "entry_price": 75800.0, "volume": 0.01, "stop_loss_price": 75700.0, "take_profit_price": 76000.0}
            )
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("DAILY_LOSS_LIMIT_REACHED", ctx.exception.detail)

        # Clean up test pnl
        self.conn.execute("DELETE FROM futures_realized_pnl WHERE user_id = ? AND pnl_id = 'TEST-PNL-1'", (self.primary_user,))
        self.conn.commit()

    def test_09_emergency_stop_disarm(self):
        """9. Emergency Stop disarms Demo authorization instantly and revokes execution."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth["authorization"]["auth_token"]

        disarm = DemoExecutionService.emergency_disarm(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            reason="Acceptance test emergency disarm"
        )
        self.assertEqual(disarm["status"], "SUCCESS")
        self.assertTrue(disarm["emergency_disarmed"])

        # Check status returns is_authorized = False
        stat = DemoExecutionService.get_demo_status(conn=self.conn, user_id=self.primary_user, account_id=self.target_demo_account)
        self.assertFalse(stat["is_authorized"])

        # Subsequent order attempt fails
        with self.assertRaises(HTTPException) as ctx:
            DemoExecutionService.validate_and_simulate_order(
                conn=self.conn,
                user_id=self.primary_user,
                auth_token=token,
                order_spec={"symbol": "BTCUSD", "direction": "BUY", "entry_price": 75800.0, "volume": 0.01, "stop_loss_price": 75700.0, "take_profit_price": 76000.0}
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_10_simulated_order_pre_execution_zero_live_orders(self):
        """10. Simulated order pre-execution passes all gates, confirming ZERO live orders to MT5."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth["authorization"]["auth_token"]

        res = DemoExecutionService.validate_and_simulate_order(
            conn=self.conn,
            user_id=self.primary_user,
            auth_token=token,
            order_spec={
                "symbol": "BTCUSD",
                "direction": "SELL",
                "entry_price": 75800.0,
                "volume": 0.01,
                "stop_loss_price": 75900.0,   # $100 stop distance
                "take_profit_price": 75600.0,  # $200 TP distance -> R:R 2.0:1
                "account_equity": 5076.03
            }
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["validation_status"], "PASSED_ALL_RISK_BARRIERS")
        self.assertTrue(res["risk_checks"]["mandatory_stop_loss_verified"])
        self.assertTrue(res["risk_checks"]["mandatory_take_profit_verified"])
        self.assertTrue(res["risk_checks"]["broker_stops_level_conforming"])
        self.assertTrue(res["risk_checks"]["risk_reward_acceptable"])
        self.assertFalse(res["broker_dispatch"]["dispatched_to_broker"])
        self.assertEqual(res["broker_dispatch"]["mode"], "CONTROLLED_DEMO_REPLAY_SIMULATION")

    def test_11_preflight_demo_order_readiness(self):
        """11. Non-mutating preflight test confirms account identity, broker symbol BTCUSDr and monetary risk."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth["authorization"]["auth_token"]

        res = DemoExecutionService.preflight_demo_order(
            conn=self.conn,
            user_id=self.primary_user,
            auth_token=token,
            order_spec={
                "symbol": "BTCUSD",
                "direction": "BUY",
                "entry_price": 75800.0,
                "volume": 0.01,
                "stop_loss_price": 75700.0,
                "take_profit_price": 76000.0,
                "account_equity": 5076.03
            }
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["preflight_status"], "READY_FOR_EXECUTION_HELD")
        self.assertEqual(res["account_verification"]["broker_login"], "474861031")
        self.assertEqual(res["account_verification"]["environment"], "DEMO")
        self.assertEqual(res["proposed_order"]["broker_symbol"], "BTCUSDr")
        self.assertEqual(res["proposed_order"]["max_monetary_risk_usd"], 1.0)
        self.assertEqual(res["proposed_order"]["risk_reward_ratio"], 2.0)
        self.assertFalse(res["safety_governance"]["broker_order_submitted"])


    def test_12_demo_gateway_dispatch_preflight(self):
        """12. Full end-to-end Demo execution pathway verified via Windows Gateway in non-mutating preflight mode."""
        auth = DemoExecutionService.authorize_demo_execution(
            conn=self.conn,
            user_id=self.primary_user,
            account_id=self.target_demo_account,
            symbol="BTCUSD"
        )
        token = auth['authorization']['auth_token']

        res = DemoExecutionService.dispatch_demo_order(
            conn=self.conn,
            user_id=self.primary_user,
            auth_token=token,
            order_spec={
                "symbol": "BTCUSD",
                "direction": "BUY",
                "entry_price": 75687.04,
                "volume": 0.01,
                "stop_loss_price": 75587.04,
                "take_profit_price": 75887.04,
                "account_equity": 5075.76
            },
            dry_run=True
        )
        self.assertEqual(res['status'], "SUCCESS")
        self.assertEqual(res['execution_mode'], "NON_MUTATING_PREFLIGHT")
        self.assertEqual(res['preflight_status'], "READY_FOR_EXECUTION_HELD")
        self.assertFalse(res['safety_governance']['dispatched_to_broker'])
        self.assertTrue(res['safety_governance']['live_trading_locked'])
        self.assertTrue(res['safety_governance']['real_trading_locked'])
        self.assertEqual(res['order_details']['broker_symbol'], "BTCUSDr")
        self.assertEqual(res['order_details']['max_monetary_risk_usd'], 1.0)
        self.assertIn("interactive_worker", res['gateway_verification'])
        self.assertEqual(res['gateway_verification']['interactive_worker']['session_id'], 2)
        self.assertEqual(res['gateway_verification']['interactive_worker']['verified_login'], 474861031)


if __name__ == "__main__":
    unittest.main(verbosity=2)
