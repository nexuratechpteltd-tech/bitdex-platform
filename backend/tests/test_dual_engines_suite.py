import unittest
import asyncio
from app.services.brokers.micro_scalping_engine import MicroScalpingEngine, MicroScalpConfig
from app.services.brokers.precision_strategy_engine import PrecisionStrategyEngine, PrecisionEngineConfig
from app.services.brokers.shared_risk_manager import SharedCentralRiskManager
from app.services.saas_db import get_db_connection

class MockAdapter:
    async def get_account_summary(self):
        return {'balance': 5000.0, 'equity': 5000.0, 'free_margin': 5000.0}
    async def get_positions(self):
        return []

class TestDualStrategyArchitecture(unittest.TestCase):
    def setUp(self):
        self.micro = MicroScalpingEngine()
        self.prec = PrecisionStrategyEngine()

    def test_micro_sub_dollar_rejection(self):
        candles_m1 = [{'close': 2000.0 + i, 'high': 2005.0 + i, 'low': 1995.0 + i} for i in range(30)]
        candles_m5 = [{'close': 2000.0 + i*2, 'high': 2010.0 + i*2, 'low': 1990.0 + i*2} for i in range(30)]
        contract_spec = {
            'digits': 2,
            'tick_size': 0.01,
            'tick_value': 1.0,
            'contract_size': 100.0,
            'min_lot': 0.05,
            'lot_step': 0.01
        }
        res = self.micro.evaluate_setup('XAUUSD', candles_m1, candles_m5, 2030.0, 2030.5, contract_spec, 5000.0)
        self.assertEqual(res['decision'], 'NO_TRADE')
        self.assertIn('SUB_DOLLAR_BUDGET_EXCEEDED', res['reason'])

    def test_precision_daily_limit(self):
        res = self.prec.evaluate_precision_setup('BTCUSD', [], [], [], 75000.0, 75010.0, 5000.0, {}, daily_executed_count=3)
        self.assertEqual(res['decision'], 'NO_TRADE')
        self.assertIn('DAILY_EXECUTION_LIMIT_REACHED', res['reason'])

    def test_permanent_real_lock_in_shared_risk_manager(self):
        async def run_async():
            conn = get_db_connection()
            try:
                passed, reason, metrics = await SharedCentralRiskManager.preflight_check(
                    conn=conn,
                    account_id='16000629657', # Real account
                    adapter=MockAdapter(),
                    symbol='BTCUSD',
                    side='BUY',
                    volume=0.01,
                    entry_price=75000.0,
                    sl_price=74000.0,
                    engine_type='SCALP',
                    real_trading_permanently_locked=True
                )
                self.assertFalse(passed)
                self.assertIn('REAL_TRADING_PERMANENTLY_LOCKED', reason)
            finally:
                conn.close()
        asyncio.run(run_async())

if __name__ == '__main__':
    unittest.main()
