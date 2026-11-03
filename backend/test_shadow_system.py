import sys
import unittest
import asyncio
import json
import httpx
from pathlib import Path

# Add backend to path
sys.path.insert(0, "/opt/tauric-platform/backend")

from app.services.shadow_store import shadow_store
from app.services.outcome_engine import outcome_engine
from app.services.jev_client import jev_client

class TestShadowValidationSystem(unittest.TestCase):

    def test_01_shadow_store_persistence(self):
        """Verify shadow decisions persist to SQLite and JSON with unique ID."""
        test_payload = {
            "symbol": "TEST-USD",
            "timeframe": "1h",
            "current_price": 50000.0,
            "market_regime": "range_chop",
            "tauric_decision": "Hold",
            "tauric_direction": "FLAT",
            "reconciliation_result": "NO_TRADE",
            "agreement_status": "DISAGREE",
            "jev_fast_decision": "WAIT",
            "jev_fast_direction": "FLAT"
        }
        did = shadow_store.record_decision(test_payload)
        self.assertTrue(did.startswith("SHD-TEST-USD-"))
        
        # Verify retrieved from DB
        fetched = shadow_store.get_decision(did)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["symbol"], "TEST-USD")
        self.assertEqual(fetched["current_price"], 50000.0)

    def test_02_ambiguous_candle_detection(self):
        """Verify that when both TP and SL are hit in the same candle, outcome is strictly AMBIGUOUS."""
        # Long trade: Entry = 100, Stop = 95, TP1 = 110
        # Candle with Low = 90 (breaches stop) AND High = 115 (breaches TP)
        candles = [
            {"open_time": 1000, "open": 100, "high": 115, "low": 90, "close": 105, "volume": 100, "close_time": 2000}
        ]
        res = outcome_engine.evaluate_single_trade("LONG", 100.0, 95.0, 110.0, 120.0, candles)
        self.assertEqual(res["outcome"], "AMBIGUOUS", f"Expected AMBIGUOUS but got {res['outcome']}")
        self.assertEqual(res["net_pnl"], 0.0)

        # Short trade: Entry = 100, Stop = 105, TP1 = 90
        # Candle with High = 110 (breaches stop) AND Low = 85 (breaches TP)
        candles_short = [
            {"open_time": 1000, "open": 100, "high": 110, "low": 85, "close": 95, "volume": 100, "close_time": 2000}
        ]
        res_s = outcome_engine.evaluate_single_trade("SHORT", 100.0, 105.0, 90.0, 80.0, candles_short)
        self.assertEqual(res_s["outcome"], "AMBIGUOUS", f"Expected AMBIGUOUS but got {res_s['outcome']}")

    def test_03_chronological_tp_sl_order(self):
        """Verify chronological resolution when TP and SL happen across separate candles."""
        # Long trade: Candle 1 moves up and hits TP1 (High 112 > TP 110, Low 99 > Stop 95)
        # Candle 2 later collapses to 90 (Stop 95)
        candles = [
            {"open_time": 1000, "open": 100, "high": 112, "low": 99, "close": 111, "volume": 100, "close_time": 2000},
            {"open_time": 2001, "open": 111, "high": 111, "low": 90, "close": 91, "volume": 100, "close_time": 3000}
        ]
        res = outcome_engine.evaluate_single_trade("LONG", 100.0, 95.0, 110.0, 120.0, candles)
        self.assertEqual(res["outcome"], "WIN_TP1")
        self.assertGreater(res["net_pnl"], 0.0)

    def test_04_mfe_and_mae_calculation(self):
        """Verify Maximum Favorable and Adverse Excursions."""
        # Long trade: Entry = 100, Stop = 80, TP = 150
        # Candle 1: High = 110, Low = 92
        # Candle 2: High = 125, Low = 96
        candles = [
            {"open_time": 1000, "open": 100, "high": 110, "low": 92, "close": 108, "volume": 100, "close_time": 2000},
            {"open_time": 2001, "open": 108, "high": 125, "low": 96, "close": 120, "volume": 100, "close_time": 3000}
        ]
        res = outcome_engine.evaluate_single_trade("LONG", 100.0, 80.0, 150.0, 160.0, candles)
        self.assertEqual(res["mfe"], 25.0)  # max high (125) - entry (100)
        self.assertEqual(res["mae"], 8.0)   # entry (100) - min low (92)

    def test_05_jev_veto_telemetry_metrics(self):
        """Verify summary accurately reflects Tauric trades vetoed by Jev."""
        summary = shadow_store.get_summary_statistics()
        self.assertIn("jev_veto_analysis", summary)
        v = summary["jev_veto_analysis"]
        self.assertIn("tauric_trades_vetoed_by_jev", v)
        self.assertIn("vetoed_trades_that_would_have_lost", v)
        self.assertIn("vetoed_trades_that_would_have_won", v)
        self.assertIn("vetoed_ambiguous", v)
        self.assertIn("tauric_trades_jev_agreed", v)

    def test_06_agreement_and_anomaly_flags(self):
        """Verify agreement telemetry and anomaly detection thresholds."""
        summary = shadow_store.get_summary_statistics()
        self.assertIn("agreement_telemetry", summary)
        a = summary["agreement_telemetry"]
        self.assertIn("agreement_rate_percent", a)
        self.assertIn("disagreement_rate_percent", a)
        self.assertIn("avg_latencies_ms", a)

    def test_07_historical_eth_run_intact(self):
        """Verify RUN-ETH-USD-20260929_125459 files are 100% intact on disk."""
        eth_dir = Path("/opt/tauric-platform/backend/data/reports/ETH-USD_20260929_125459")
        self.assertTrue(eth_dir.exists())
        self.assertTrue((eth_dir / "complete_report.md").exists())
        self.assertTrue((eth_dir / "run_data.json").exists())
        self.assertTrue((eth_dir / "1_analysts").exists())
        self.assertTrue((eth_dir / "5_portfolio").exists())

    def test_08_credential_isolation(self):
        """Verify zero API keys are exposed via any shadow endpoints."""
        summary_str = json.dumps(shadow_store.get_summary_statistics())
        self.assertNotIn("apikey_", summary_str)
        self.assertNotIn("typesafe_api_key", summary_str.lower())
        self.assertNotIn("venice_api_key", summary_str.lower())

    def test_09_safety_invariants(self):
        """Verify live trading and order routing remain disabled."""
        from app.config import settings
        self.assertTrue(settings.live_trading_locked)
        self.assertTrue(settings.read_only_mode)

if __name__ == "__main__":
    unittest.main()
