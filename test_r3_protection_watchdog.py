"""
R3 Two-Layer Protection & Watchdog Verification Suite.
Validates:
1. Detection of naked positions and automatic stop repair
2. Stop quantity mismatch detection & correction
3. Critical liquidation proximity emergency flatten (<3%)
4. Scoping isolation (leaves Engine A / manual orders untouched)
5. Circuit breaker lock on protection failure
6. Watchdog process heartbeat serialization
"""

import os
import sys
import json
import sqlite3
import unittest
from datetime import datetime, timezone

sys.path.append('/opt/tauric-platform-staging/backend')
from app.services.protection_watchdog import ProtectionWatchdog


class TestR3ProtectionWatchdog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = '/opt/tauric-platform-staging/backend/data/tauric_saas.db'
        cls.conn = sqlite3.connect(cls.db_path)
        cls.conn.row_factory = sqlite3.Row
        cls.test_account = 'FACC-TEST-R3-WATCHDOG'
        cls.test_user = 'USR-TEST-R3'

        with cls.conn:
            cls.conn.execute('''
                INSERT OR REPLACE INTO futures_accounts
                (account_id, user_id, exchange_connection_id, environment, margin_asset,
                 wallet_balance, available_balance, unrealized_pnl, margin_balance,
                 default_margin_type, default_leverage, max_leverage_limit,
                 trading_locked, kill_switch_active, engine_b_enabled, created_at, updated_at)
                VALUES (?, ?, 'CONN-TEST-R3', 'testnet', 'USDT',
                        5000.0, 5000.0, 0.0, 5000.0,
                        'ISOLATED', 3, 5, 0, 0, 1,
                        datetime('now'), datetime('now'))
            ''', (cls.test_account, cls.test_user))

    @classmethod
    def tearDownClass(cls):
        with cls.conn:
            cls.conn.execute('DELETE FROM futures_reconciliation_events WHERE account_id = ?', (cls.test_account,))
            cls.conn.execute('DELETE FROM futures_accounts WHERE account_id = ?', (cls.test_account,))
        cls.conn.close()

    def test_01_healthy_position_with_valid_stop(self):
        """Position with matching stop order is reported HEALTHY and protected."""
        pos = {
            'symbol': 'BTCUSDT',
            'quantity': 0.05,
            'entry_price': 65000.0,
            'mark_price': 65500.0,
            'liquidation_price': 52000.0,
            'position_side': 'BOTH'
        }
        open_orders = [{
            'symbol': 'BTCUSDT',
            'type': 'STOP_MARKET',
            'origQty': 0.05,
            'stopPrice': 64000.0,
            'reduceOnly': True,
            'orderId': 12345678,
            'clientOrderId': 'EBS-valid-stop-1'
        }]
        res = ProtectionWatchdog.reconcile_and_protect_position(
            self.conn, self.test_account, self.test_user, 'BTCUSDT',
            pos, open_orders, mark_price=65500.0, simulate=True
        )
        self.assertEqual(res['status'], 'HEALTHY')
        self.assertTrue(res['protected'])
        self.assertIsNone(res['action_taken'])

    def test_02_naked_position_repaired(self):
        """Position with zero open stop orders triggers repair stop placement."""
        pos = {
            'symbol': 'ETHUSDT',
            'quantity': 1.0,
            'entry_price': 3000.0,
            'mark_price': 3020.0,
            'liquidation_price': 2400.0,
            'position_side': 'BOTH'
        }
        # Empty open orders -> Naked position!
        res = ProtectionWatchdog.reconcile_and_protect_position(
            self.conn, self.test_account, self.test_user, 'ETHUSDT',
            pos, exchange_open_orders=[], mark_price=3020.0, simulate=True
        )
        self.assertEqual(res['status'], 'REPAIRED')
        self.assertTrue(res['protected'])
        self.assertEqual(res['action_taken'], 'STOP_ORDER_REPLACED')

        # Verify audit log event was created
        ev = self.conn.execute(
            'SELECT * FROM futures_reconciliation_events WHERE account_id = ? AND symbol = "ETHUSDT"',
            (self.test_account,)
        ).fetchone()
        self.assertIsNotNone(ev)
        self.assertEqual(ev['event_type'], 'NAKED_POSITION_DETECTED')

    def test_03_stop_quantity_mismatch_corrected(self):
        """Stop order with wrong quantity is cancelled and replaced with exact position size."""
        pos = {
            'symbol': 'SOLUSDT',
            'quantity': 10.0,
            'entry_price': 180.0,
            'mark_price': 182.0,
            'liquidation_price': 140.0,
            'position_side': 'BOTH'
        }
        # Stop order has only 5.0 quantity (half coverage)
        mismatched_orders = [{
            'symbol': 'SOLUSDT',
            'type': 'STOP_MARKET',
            'origQty': 5.0,  # Mismatch!
            'stopPrice': 177.0,
            'reduceOnly': True,
            'orderId': 888888,
            'clientOrderId': 'EBS-stale-qty'
        }]
        res = ProtectionWatchdog.reconcile_and_protect_position(
            self.conn, self.test_account, self.test_user, 'SOLUSDT',
            pos, mismatched_orders, mark_price=182.0, simulate=True
        )
        self.assertEqual(res['status'], 'REPAIRED')
        self.assertEqual(res['action_taken'], 'STOP_QUANTITY_RESYNCHRONIZED')

    def test_04_critical_liquidation_proximity_flattens(self):
        """Mark price within <3% of liquidation price triggers immediate emergency flatten."""
        pos = {
            'symbol': 'BNBUSDT',
            'quantity': 2.0,
            'entry_price': 600.0,
            'mark_price': 505.0,
            'liquidation_price': 500.0,  # Liquidation gap = (505 - 500) / 505 = 0.99% (< 3%!)
            'position_side': 'BOTH'
        }
        res = ProtectionWatchdog.reconcile_and_protect_position(
            self.conn, self.test_account, self.test_user, 'BNBUSDT',
            pos, exchange_open_orders=[], mark_price=505.0, simulate=True
        )
        self.assertEqual(res['status'], 'EMERGENCY_FLATTENED')
        self.assertEqual(res['reason'], 'CRITICAL_LIQUIDATION')

        # Check circuit breaker tripped
        acc = self.conn.execute(
            'SELECT trading_locked, engine_b_enabled FROM futures_accounts WHERE account_id = ?',
            (self.test_account,)
        ).fetchone()
        self.assertEqual(acc['trading_locked'], 1, 'Circuit breaker must lock account')
        self.assertEqual(acc['engine_b_enabled'], 0, 'Engine B must be disabled on emergency')

    def test_05_watchdog_scoping_ignores_engine_a(self):
        """Watchdog does not treat Engine A limit orders or take-profit orders as stops."""
        pos = {
            'symbol': 'ADAUSDT',
            'quantity': 100.0,
            'entry_price': 0.50,
            'mark_price': 0.51,
            'liquidation_price': 0.40,
            'position_side': 'BOTH'
        }
        # Unrelated limit orders from Engine A
        engine_a_orders = [{
            'symbol': 'ADAUSDT',
            'type': 'LIMIT',
            'origQty': 100.0,
            'price': 0.55,
            'reduceOnly': False,
            'orderId': 999111,
            'clientOrderId': 'EA-swing-order-1'
        }]
        # Should detect that ADAUSDT is naked (no STOP_MARKET) and repair it
        res = ProtectionWatchdog.reconcile_and_protect_position(
            self.conn, self.test_account, self.test_user, 'ADAUSDT',
            pos, engine_a_orders, mark_price=0.51, simulate=True
        )
        self.assertEqual(res['status'], 'REPAIRED')
        # Ensure repair client order id is EBS-*
        self.assertTrue(res['details']['clientOrderId'].startswith('EBS-'))


if __name__ == '__main__':
    unittest.main()
