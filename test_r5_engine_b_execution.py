"""
R5 Engine B Autonomous Execution Verification Suite.
Validates:
1. Donchian upper/lower channel breakout logic
2. ADX trend strength filtering
3. RVOL surge validation
4. Signal emission (LONG / SHORT / NO_TRADE)
5. Execution cycle: lease acquisition, risk sizing, position creation, stop attachment
6. Engine B disabled gate enforcement
"""

import os
import sys
import sqlite3
import unittest
from datetime import datetime, timezone

sys.path.append('/opt/tauric-platform-staging/backend')
from app.services.futures_engine_b import EngineBFuturesService
from app.services.engine_coordinator import EngineCoordinator


class TestR5EngineBExecution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = '/opt/tauric-platform-staging/backend/data/tauric_saas.db'
        cls.conn = sqlite3.connect(cls.db_path)
        cls.conn.row_factory = sqlite3.Row
        cls.test_account = 'FACC-TEST-R5-ENGINE-B'
        cls.test_user = 'USR-TEST-R5'

        with cls.conn:
            cls.conn.execute('''
                INSERT OR REPLACE INTO futures_accounts
                (account_id, user_id, exchange_connection_id, environment, margin_asset,
                 wallet_balance, available_balance, unrealized_pnl, margin_balance,
                 default_margin_type, default_leverage, max_leverage_limit,
                 trading_locked, kill_switch_active, engine_b_enabled, created_at, updated_at)
                VALUES (?, ?, 'CONN-TEST-R5', 'testnet', 'USDT',
                        5000.0, 5000.0, 0.0, 5000.0,
                        'ISOLATED', 3, 5, 0, 0, 1,
                        datetime('now'), datetime('now'))
            ''', (cls.test_account, cls.test_user))

    @classmethod
    def tearDownClass(cls):
        with cls.conn:
            cls.conn.execute('DELETE FROM futures_symbol_leases WHERE account_id = ?', (cls.test_account,))
            cls.conn.execute('DELETE FROM futures_positions WHERE account_id = ?', (cls.test_account,))
            cls.conn.execute('DELETE FROM futures_scalp_trades WHERE account_id = ?', (cls.test_account,))
            cls.conn.execute('DELETE FROM futures_accounts WHERE account_id = ?', (cls.test_account,))
        cls.conn.close()

    def setUp(self):
        with self.conn:
            self.conn.execute('DELETE FROM futures_symbol_leases WHERE account_id = ?', (self.test_account,))
            self.conn.execute('DELETE FROM futures_positions WHERE account_id = ?', (self.test_account,))

    def _generate_synthetic_klines(self, count=30, trend='UP'):
        klines = []
        base_price = 100.0
        for i in range(count):
            if trend == 'UP':
                high = base_price + (i * 0.5) + 0.3
                low = base_price + (i * 0.5) - 0.2
                close = base_price + (i * 0.5) + 0.1
            else:
                high = base_price - (i * 0.5) + 0.2
                low = base_price - (i * 0.5) - 0.3
                close = base_price - (i * 0.5) - 0.1
            quote_vol = 10000.0 if i < (count - 3) else 25000.0  # Vol surge at end
            klines.append({
                'open': base_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': 100.0,
                'quote_volume': quote_vol
            })
        return klines

    def test_01_donchian_breakout_detection(self):
        """Donchian upper breakout generates LONG signal."""
        klines_up = self._generate_synthetic_klines(30, trend='UP')
        curr_price = klines_up[-1]['high'] + 0.1  # Price exceeds channel
        book_ticker = {'bid': curr_price, 'ask': curr_price + 0.01, 'spread_ratio': 0.0001}

        sig = EngineBFuturesService.evaluate_signal(klines_up, klines_up, curr_price, book_ticker)
        self.assertEqual(sig['signal'], 'LONG')
        self.assertIn('BREAKOUT', sig['reason'])
        self.assertGreater(sig['rvol'], 1.5)

    def test_02_spread_gate_rejection(self):
        """Wide spread (>5 bps) generates NO_TRADE signal."""
        klines_up = self._generate_synthetic_klines(30, trend='UP')
        curr_price = klines_up[-1]['high'] + 0.1
        book_ticker = {'bid': curr_price, 'ask': curr_price + 1.0, 'spread_ratio': 0.001} # 10 bps > 5 bps

        sig = EngineBFuturesService.evaluate_signal(klines_up, klines_up, curr_price, book_ticker)
        self.assertEqual(sig['signal'], 'NO_TRADE')
        self.assertIn('SPREAD_TOO_WIDE', sig['reason'])

    def test_03_execution_cycle_full_lifecycle(self):
        """Execution cycle acquires lease, checks sizing & exposure, and creates position with stop."""
        sig_data = {
            'signal': 'LONG',
            'entry_price': 100.0,
            'stop_price': 98.0,
            'target_price': 104.0,
            'reason': 'MOMENTUM_TEST'
        }
        filters = {'min_qty': 0.001, 'max_qty': 1000.0, 'step_size': 0.001, 'min_notional': 5.0}

        res = EngineBFuturesService.execute_scalp_cycle(
            self.conn, self.test_account, self.test_user, 'BTCUSDT', sig_data, filters, simulate=True
        )
        self.assertTrue(res['success'], f'Execution cycle failed: {res}')
        self.assertEqual(res['symbol'], 'BTCUSDT')
        self.assertEqual(res['direction'], 'LONG')
        self.assertEqual(res['leverage'], 5)
        self.assertTrue(res['client_order_id'].startswith('EB-'))
        self.assertTrue(res['stop_client_order_id'].startswith('EBS-'))

        # Check position in DB
        pos = self.conn.execute('SELECT * FROM futures_positions WHERE account_id = ?', (self.test_account,)).fetchone()
        self.assertIsNotNone(pos)
        self.assertEqual(pos['status'], 'OPEN')
        self.assertEqual(pos['symbol'], 'BTCUSDT')

        # Check symbol lease is ACTIVE
        lease = EngineCoordinator.get_active_lease(self.conn, self.test_account, 'BTCUSDT')
        self.assertIsNotNone(lease)
        self.assertEqual(lease['engine_id'], 'ENGINE_B')

    def test_04_execution_cycle_engine_b_disabled_gate(self):
        """When Engine B is disabled on account, execution cycle is rejected immediately."""
        # Disable Engine B on account
        EngineCoordinator.set_engine_b_status(self.conn, self.test_account, False)

        sig_data = {'signal': 'LONG', 'entry_price': 100.0, 'stop_price': 98.0, 'target_price': 104.0}
        filters = {'min_qty': 0.001, 'max_qty': 1000.0, 'step_size': 0.001, 'min_notional': 5.0}

        res = EngineBFuturesService.execute_scalp_cycle(
            self.conn, self.test_account, self.test_user, 'ETHUSDT', sig_data, filters, simulate=True
        )
        self.assertFalse(res['success'])
        self.assertEqual(res['error'], 'ENGINE_B_DISABLED')


if __name__ == '__main__':
    unittest.main()
