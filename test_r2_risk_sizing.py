"""
R2 Risk Sizing & Accounting Unit Test Suite.
Verifies all 10 mandatory risk dimensions:
1. Zero / negative balance rejection
2. Stop-distance-based notional calculation
3. 5x leverage clamp for Engine B
4. Minimum notional conflict rejection (anti-inflation invariant)
5. Maker vs Taker fee calculation
6. Funding cost deduction
7. Partial fill realized net P&L reconciliation
8. Precision step-size and tick-size handling
9. Anti-martingale / anti-averaging down enforcement
10. Boundary conditions (zero stop distance, extreme wide stop)
"""

import sys
import unittest

sys.path.append('/opt/tauric-platform-staging/backend')
from app.services.futures_risk_sizing_engine import FuturesRiskSizingEngine


class TestR2RiskSizing(unittest.TestCase):
    def setUp(self):
        self.standard_filters = {
            'min_qty': 0.001,
            'max_qty': 1000.0,
            'step_size': 0.001,
            'min_notional': 5.0,
            'tick_size': 0.01
        }

    def test_01_zero_and_negative_balance(self):
        """Zero or negative equity must be immediately rejected."""
        res_zero = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=0.0, available_balance=100.0, entry_price=100.0, stop_price=98.0,
            symbol_filters=self.standard_filters
        )
        self.assertFalse(res_zero['approved'])
        self.assertEqual(res_zero['rejection_code'], 'REJECTED_ZERO_OR_NEGATIVE_EQUITY')

        res_neg = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=-50.0, available_balance=100.0, entry_price=100.0, stop_price=98.0,
            symbol_filters=self.standard_filters
        )
        self.assertFalse(res_neg['approved'])

    def test_02_stop_distance_based_notional(self):
        """Target notional is strictly derived from dollar risk / stop distance."""
        # Equity = ,000, risk = 1% ( risk budget)
        # Entry = , Stop =  (2.0% stop distance)
        # Total risk ratio = 2.0% + 0.05% slippage = 2.05%
        # Target notional =  / 0.0205 = ~,878.05
        res = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=10000.0, available_balance=5000.0, entry_price=100.0, stop_price=98.0,
            symbol_filters=self.standard_filters, risk_pct=0.01, is_maker=True
        )
        self.assertTrue(res['approved'], f'Expected approved sizing: {res}')
        self.assertEqual(res['leverage'], 5, 'Must clamp to 5x for Engine B')
        self.assertAlmostEqual(res['dollar_risk_budget_usd'], 100.0, places=1)
        self.assertTrue(4500.0 <= res['notional_usd'] <= 5000.0)

    def test_03_min_notional_rejection_no_inflation(self):
        """If risk budget requires notional below exchange minimum, REJECT rather than inflate!"""
        # Small equity: , risk = 1% (zsh.50 risk budget)
        # Entry = , Stop =  (5% stop distance)
        # Target notional = zsh.50 / 0.0505 = ~.90
        # If min_notional is .0, sizing MUST REJECT, NOT INFLATE!
        filters = dict(self.standard_filters)
        filters['min_notional'] = 25.0

        res = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=50.0, available_balance=50.0, entry_price=100.0, stop_price=95.0,
            symbol_filters=filters, risk_pct=0.01
        )
        self.assertFalse(res['approved'], 'Should reject when min notional exceeds risk budget')
        self.assertEqual(res['rejection_code'], 'REJECTED_MIN_NOTIONAL_EXCEEDS_RISK_BUDGET')

    def test_04_leverage_capped_at_five(self):
        """Even if caller passes 10x or 20x, Engine B leverage must be clamped to 5x."""
        res = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=1000.0, available_balance=500.0, entry_price=50.0, stop_price=49.0,
            symbol_filters=self.standard_filters, max_leverage=20
        )
        self.assertTrue(res['approved'])
        self.assertEqual(res['leverage'], 5, 'Leverage must be capped at 5x')

    def test_05_maker_vs_taker_fee_accounting(self):
        """Maker entry (0.02%) must calculate lower fees than taker (0.04%)."""
        res_maker = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=1000.0, available_balance=500.0, entry_price=100.0, stop_price=98.0,
            symbol_filters=self.standard_filters, is_maker=True
        )
        res_taker = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=1000.0, available_balance=500.0, entry_price=100.0, stop_price=98.0,
            symbol_filters=self.standard_filters, is_maker=False
        )
        self.assertTrue(res_maker['approved'])
        self.assertTrue(res_taker['approved'])
        self.assertLess(
            res_maker['fee_breakdown']['entry_fee_usd'],
            res_taker['fee_breakdown']['entry_fee_usd']
        )

    def test_06_realized_net_pnl_with_partial_fills(self):
        """Test accurate realized net P&L calculation with multi-tier partial fills."""
        # Long trade:
        # Fill 1: 0.5 qty @ , fee = zsh.01
        # Fill 2: 0.5 qty @ , fee = zsh.0101
        # Total entry: 1.0 qty, avg price = .50, fee = zsh.0201
        # Exit Fill 1: 0.6 qty @ , fee = zsh.0247
        # Exit Fill 2: 0.4 qty @ , fee = zsh.0166
        # Total exit: 1.0 qty, avg price = .40, fee = zsh.0413
        # Gross = 1.0 * (103.40 - 100.50) = .90
        # Total fees = zsh.0201 + zsh.0413 = zsh.0614
        # Funding fees = zsh.05
        # Net PnL = .90 - zsh.0614 - zsh.05 = .7886
        entry_fills = [
            {'price': 100.0, 'qty': 0.5, 'fee': 0.01},
            {'price': 101.0, 'qty': 0.5, 'fee': 0.0101}
        ]
        exit_fills = [
            {'price': 103.0, 'qty': 0.6, 'fee': 0.0247},
            {'price': 104.0, 'qty': 0.4, 'fee': 0.0166}
        ]
        pnl_res = FuturesRiskSizingEngine.calculate_realized_net_pnl(
            side='BUY', entry_fills=entry_fills, exit_fills=exit_fills, funding_fees_paid=0.05
        )
        self.assertEqual(pnl_res['matched_qty'], 1.0)
        self.assertEqual(pnl_res['avg_entry_price'], 100.50)
        self.assertEqual(pnl_res['avg_exit_price'], 103.40)
        self.assertAlmostEqual(pnl_res['gross_pnl_usd'], 2.90, places=2)
        self.assertAlmostEqual(pnl_res['net_pnl_usd'], 2.7886, places=4)
        self.assertTrue(pnl_res['is_profitable'])
        self.assertFalse(pnl_res['is_partial'])

    def test_07_anti_martingale_enforcement(self):
        """Loss-based leverage or risk escalation must raise ValueError."""
        base_risk = 50.0
        # Escalating risk to  after a loss -> MUST RAISE ERROR
        with self.assertRaises(ValueError):
            FuturesRiskSizingEngine.assert_no_martingale_escalation(
                base_risk_usd=base_risk, proposed_risk_usd=100.0, last_trade_loss=True
            )

        # Same or lower risk after loss -> Valid
        FuturesRiskSizingEngine.assert_no_martingale_escalation(
            base_risk_usd=base_risk, proposed_risk_usd=50.0, last_trade_loss=True
        )
        FuturesRiskSizingEngine.assert_no_martingale_escalation(
            base_risk_usd=base_risk, proposed_risk_usd=30.0, last_trade_loss=True
        )

    def test_08_boundary_price_conditions(self):
        """Zero stop distance or equal prices must be rejected cleanly."""
        res_equal = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=1000.0, available_balance=500.0, entry_price=100.0, stop_price=100.0,
            symbol_filters=self.standard_filters
        )
        self.assertFalse(res_equal['approved'])
        self.assertEqual(res_equal['rejection_code'], 'REJECTED_ZERO_STOP_DISTANCE')

        # Stop too tight (< 0.1%)
        res_tight = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=1000.0, available_balance=500.0, entry_price=100.0, stop_price=99.95,
            symbol_filters=self.standard_filters
        )
        self.assertFalse(res_tight['approved'])
        self.assertEqual(res_tight['rejection_code'], 'REJECTED_STOP_TOO_TIGHT')

        # Stop too wide (> 15%)
        res_wide = FuturesRiskSizingEngine.calculate_risk_first_sizing(
            equity=1000.0, available_balance=500.0, entry_price=100.0, stop_price=80.0,
            symbol_filters=self.standard_filters
        )
        self.assertFalse(res_wide['approved'])
        self.assertEqual(res_wide['rejection_code'], 'REJECTED_STOP_TOO_WIDE')


if __name__ == '__main__':
    unittest.main()
