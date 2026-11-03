"""
R1 Dual-Engine Acceptance & Verification Suite.
Validates:
1. Symbol mutual exclusivity lease acquisition & collision prevention
2. Lease expiration and atomic reclamation
3. Aggregate portfolio exposure gate (50% max)
4. Engine B default OFF state
5. Order prefix ownership isolation (EA-* vs EB-*)
6. Regression integrity of existing Engine A records
"""

import os
import sys
import time
import sqlite3
import unittest
from datetime import datetime, timezone, timedelta

sys.path.append('/opt/tauric-platform-staging/backend')
from app.services.engine_coordinator import EngineCoordinator


class TestR1DualEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = '/opt/tauric-platform-staging/backend/data/tauric_saas.db'
        cls.conn = sqlite3.connect(cls.db_path)
        cls.conn.row_factory = sqlite3.Row
        cls.test_account = 'FACC-TEST-R1-COORDINATOR'

        # Ensure test account exists
        with cls.conn:
            cls.conn.execute('''
                INSERT OR REPLACE INTO futures_accounts
                (account_id, user_id, exchange_connection_id, environment, margin_asset,
                 wallet_balance, available_balance, unrealized_pnl, margin_balance,
                 default_margin_type, default_leverage, max_leverage_limit,
                 trading_locked, kill_switch_active, engine_b_enabled, created_at, updated_at)
                VALUES (?, 'USR-TEST-R1', 'CONN-TEST-R1', 'testnet', 'USDT',
                        1000.0, 1000.0, 0.0, 1000.0,
                        'ISOLATED', 3, 10, 0, 0, 0,
                        datetime('now'), datetime('now'))
            ''', (cls.test_account,))

    @classmethod
    def tearDownClass(cls):
        with cls.conn:
            cls.conn.execute('DELETE FROM futures_symbol_leases WHERE account_id = ?', (cls.test_account,))
            cls.conn.execute('DELETE FROM futures_accounts WHERE account_id = ?', (cls.test_account,))
        cls.conn.close()

    def setUp(self):
        with self.conn:
            self.conn.execute('DELETE FROM futures_symbol_leases WHERE account_id = ?', (self.test_account,))

    def test_01_engine_b_default_off(self):
        """Engine B must strictly default to OFF for any new account."""
        is_enabled = EngineCoordinator.is_engine_b_enabled(self.conn, self.test_account)
        self.assertFalse(is_enabled, 'Engine B must default to OFF')

        # Test explicit enablement and disablement
        EngineCoordinator.set_engine_b_status(self.conn, self.test_account, True)
        self.assertTrue(EngineCoordinator.is_engine_b_enabled(self.conn, self.test_account))

        EngineCoordinator.set_engine_b_status(self.conn, self.test_account, False)
        self.assertFalse(EngineCoordinator.is_engine_b_enabled(self.conn, self.test_account))

    def test_02_symbol_mutual_exclusivity(self):
        """Engine A acquiring BTCUSDT must prevent Engine B from acquiring BTCUSDT."""
        # Engine A acquires lease on BTCUSDT
        ok, token_a, err = EngineCoordinator.acquire_lease(
            self.conn, self.test_account, 'BTCUSDT', 'ENGINE_A', duration_seconds=60
        )
        self.assertTrue(ok, f'Engine A failed to acquire lease: {err}')
        self.assertIsNotNone(token_a)

        # Engine B attempts to acquire lease on same symbol -> MUST BE REJECTED
        ok_b, token_b, reason_b = EngineCoordinator.acquire_lease(
            self.conn, self.test_account, 'BTCUSDT', 'ENGINE_B', duration_seconds=60
        )
        self.assertFalse(ok_b, 'Engine B should be rejected due to collision')
        self.assertIsNone(token_b)
        self.assertIn('currently locked by ENGINE_A', reason_b)

        # Verify active lease query returns Engine A
        lease = EngineCoordinator.get_active_lease(self.conn, self.test_account, 'BTCUSDT')
        self.assertIsNotNone(lease)
        self.assertEqual(lease['engine_id'], 'ENGINE_A')

    def test_03_same_engine_lease_renewal(self):
        """Same engine acquiring same symbol should renew/extend, not reject."""
        ok, token_1, _ = EngineCoordinator.acquire_lease(
            self.conn, self.test_account, 'ETHUSDT', 'ENGINE_A', duration_seconds=60
        )
        self.assertTrue(ok)

        # Re-acquire same symbol by same engine
        ok2, token_2, _ = EngineCoordinator.acquire_lease(
            self.conn, self.test_account, 'ETHUSDT', 'ENGINE_A', duration_seconds=120
        )
        self.assertTrue(ok2)
        self.assertEqual(token_1, token_2, 'Same engine should retain lease token upon renewal')

    def test_04_lease_release_and_handoff(self):
        """Releasing lease allows competing engine to acquire it."""
        ok, token_a, _ = EngineCoordinator.acquire_lease(
            self.conn, self.test_account, 'SOLUSDT', 'ENGINE_A', duration_seconds=60
        )
        self.assertTrue(ok)

        # Engine A releases lease
        released = EngineCoordinator.release_lease(self.conn, self.test_account, 'SOLUSDT', 'ENGINE_A', token_a)
        self.assertTrue(released)

        # Engine B can now acquire SOLUSDT
        ok_b, token_b, _ = EngineCoordinator.acquire_lease(
            self.conn, self.test_account, 'SOLUSDT', 'ENGINE_B', duration_seconds=60
        )
        self.assertTrue(ok_b, 'Engine B should be able to acquire released symbol')
        self.assertIsNotNone(token_b)

    def test_05_lease_expiration_reclamation(self):
        """Expired lease can be claimed by another engine."""
        # Artificially insert expired lease for Engine A
        past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
        with self.conn:
            self.conn.execute('''
                INSERT OR REPLACE INTO futures_symbol_leases
                (account_id, symbol, engine_id, lease_token, acquired_at, expires_at, status)
                VALUES (?, 'AVAXUSDT', 'ENGINE_A', 'LSE-EXPIRED', ?, ?, 'ACTIVE')
            ''', (self.test_account, past_time, past_time))

        # Engine B attempts to acquire expired lease
        ok_b, token_b, _ = EngineCoordinator.acquire_lease(
            self.conn, self.test_account, 'AVAXUSDT', 'ENGINE_B', duration_seconds=60
        )
        self.assertTrue(ok_b, 'Expired lease must be reclaimable')
        self.assertNotEqual(token_b, 'LSE-EXPIRED')

    def test_06_aggregate_exposure_gate(self):
        """Aggregate margin exposure across all positions must not exceed 50% equity."""
        # Account equity = ,000. Max allowed margin =  (50%).
        # 1. Proposed margin =  -> Approved (30% <= 50%)
        ok, curr, proposed, reason = EngineCoordinator.check_aggregate_exposure(
            self.conn, self.test_account, new_margin_usd=300.0, max_exposure_ratio=0.50
        )
        self.assertTrue(ok, f'Should approve 300 margin: {reason}')
        self.assertEqual(proposed, 300.0)

        # 2. Proposed margin =  -> Rejected (60% > 50%)
        ok_fail, curr_f, proposed_f, reason_f = EngineCoordinator.check_aggregate_exposure(
            self.conn, self.test_account, new_margin_usd=600.0, max_exposure_ratio=0.50
        )
        self.assertFalse(ok_fail, 'Should reject 600 margin on 1000 balance')
        self.assertIn('PORTFOLIO_EXPOSURE_SATURATED', reason_f)

    def test_07_order_prefix_ownership(self):
        """Engines can only modify/cancel orders matching their ownership prefix."""
        self.assertTrue(EngineCoordinator.validate_order_ownership('EA-1234-abcd', 'ENGINE_A'))
        self.assertTrue(EngineCoordinator.validate_order_ownership('FO-legacy-order', 'ENGINE_A'))
        self.assertFalse(EngineCoordinator.validate_order_ownership('EB-1234-abcd', 'ENGINE_A'), 'Engine A cannot touch EB orders')

        self.assertTrue(EngineCoordinator.validate_order_ownership('EB-1234-abcd', 'ENGINE_B'))
        self.assertTrue(EngineCoordinator.validate_order_ownership('EBS-stop-1234', 'ENGINE_B'))
        self.assertFalse(EngineCoordinator.validate_order_ownership('EA-1234-abcd', 'ENGINE_B'), 'Engine B cannot touch EA orders')

    def test_08_engine_a_regression_preservation(self):
        """Confirm historical Engine A tables, trades, and Ali Ajmal records remain intact."""
        c = self.conn.cursor()
        scalp_trades = c.execute('SELECT COUNT(*) FROM futures_scalp_trades').fetchone()[0]
        self.assertGreater(scalp_trades, 0, 'Historical trades must be preserved')

        ali_overrides = c.execute('SELECT COUNT(*) FROM customer_pricing_overrides WHERE user_id = "USR-904424B4FB"').fetchone()[0]
        self.assertEqual(ali_overrides, 3, 'Ali Ajmal overrides must remain intact')


if __name__ == '__main__':
    unittest.main()
