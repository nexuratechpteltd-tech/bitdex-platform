import unittest
import asyncio
import hashlib
import json
import time

from app.services.snapshot_engine import snapshot_engine, compute_snapshot_hash
from app.services.dual_ai_engine import dual_ai_engine
from app.services.shadow_store import shadow_store
from app.services.telemetry_manager import telemetry_manager
from app.config import validate_model_preflight, resolve_model_tier

class TestPhase321AdversarialAudit(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        dual_ai_engine.active_job_id = None
        dual_ai_engine.active_job_started_at = None

    def tearDown(self):
        dual_ai_engine.active_job_id = None
        dual_ai_engine.active_job_started_at = None
        self.loop.close()

    def test_a1_unchecked_news_clearance_never_claims_clear(self):
        snap = self.loop.run_until_complete(snapshot_engine.create_snapshot('ETHUSDT', require_event_risk_clear=False))
        self.assertEqual(snap['calendar']['event_risk_status'], 'UNKNOWN')
        self.assertIn('CALENDAR_PROVIDER_DISABLED_EVENT_RISK_UNKNOWN', snap['uncertainty_flags'])

    def test_a2_required_news_clearance_fails_closed_on_unknown(self):
        snap = self.loop.run_until_complete(snapshot_engine.create_snapshot('ETHUSDT', require_event_risk_clear=True))
        self.assertFalse(snap['eligible_for_ai'])
        self.assertIn('EVENT_RISK_NOT_CLEAR_UNKNOWN', snap['safety_gate_reasons'])

    def test_a3_model_cannot_override_event_risk_gate(self):
        snap = {
            'calendar': {'provider_status': 'DISABLED', 'event_risk_status': 'UNKNOWN', 'is_blackout': False},
            'technical_trade_setup': {'qualified': True, 'direction': 'BUY', 'stop_loss': 90.0, 'take_profit_1': 120.0},
            'market_data': {'price': 100.0, 'freshness_status': 'FRESH'},
            'liquidity': {'liquidity_status': 'QUALIFIED'}
        }
        t_res = {'model_id': 'deepseek-v4-flash', 'status': 'COMPLETED', 'directional_view': 'BULLISH', 'event_risk_interpretation': 'News is clear'}
        j_res = {'model_id': 'jev-latest', 'status': 'COMPLETED', 'directional_view': 'BULLISH', 'event_risk_interpretation': 'No risk'}
        rec = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res, require_event_risk_clear=True)
        self.assertEqual(rec['reconciliation_outcome'], 'WAIT')
        self.assertEqual(rec['agreement_status'], 'GATE_VETO')

    def test_b1_hash_changes_on_any_material_field(self):
        base_snap = {
            'snapshot_id': 'SNAP-1',
            'created_at_utc': '2026-10-21T10:00:00Z',
            'exchange': 'BINANCE',
            'symbol': 'BTCUSDT',
            'market_data': {'price': 65000.0, 'volume_24h': 1000000.0},
            'indicators': {'rsi': 55.0},
            'regime': {'market_regime': 'RISK_ON'},
            'liquidity': {'liquidity_status': 'QUALIFIED'}
        }
        base_hash = compute_snapshot_hash(base_snap)
        mutations = [
            ('price', {'market_data': {'price': 65000.5, 'volume_24h': 1000000.0}}),
            ('volume', {'market_data': {'price': 65000.0, 'volume_24h': 1000001.0}}),
            ('rsi', {'indicators': {'rsi': 55.1}}),
            ('regime', {'regime': {'market_regime': 'NEUTRAL'}}),
            ('exchange', {'exchange': 'BYBIT'})
        ]
        for field, mut in mutations:
            modified = json.loads(json.dumps(base_snap))
            modified.update(mut)
            mut_hash = compute_snapshot_hash(modified)
            self.assertNotEqual(base_hash, mut_hash, f'Hash failed to change on mutating {field}')

    def test_c1_concurrency_lock_enforces_single_active_job(self):
        self.assertTrue(dual_ai_engine.acquire_job_slot('JOB-A'))
        self.assertFalse(dual_ai_engine.acquire_job_slot('JOB-B'))
        dual_ai_engine.release_job_slot('JOB-A')
        self.assertTrue(dual_ai_engine.acquire_job_slot('JOB-B'))
        dual_ai_engine.release_job_slot('JOB-B')

    def test_d1_audit_failed_liquidity_gate(self):
        snap = {
            'market_data': {'price': 100.0, 'freshness_status': 'FRESH'},
            'calendar': {'event_risk_status': 'CLEAR', 'is_blackout': False},
            'liquidity': {'liquidity_status': 'ILLIQUID', 'depth_quote': 500.0},
            'technical_trade_setup': {'qualified': True, 'direction': 'BUY', 'stop_loss': 90.0, 'take_profit_1': 120.0, 'entry_validity_sec': 3600}
        }
        t_res = {'model_id': 'deepseek-v4-flash', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        j_res = {'model_id': 'jev-latest', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        rec = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res)
        self.assertEqual(rec['reconciliation_outcome'], 'WAIT')
        self.assertEqual(rec['agreement_status'], 'GATE_VETO')
        self.assertEqual(rec['model_agreement_status'], 'AGREED')
        self.assertTrue(any('Liquidity qualification failed' in r for r in rec['veto_reasons']))

    def test_d2_audit_stale_prices_in_reconciliation(self):
        snap = {
            'market_data': {'price': 100.0, 'freshness_status': 'STALE'},
            'calendar': {'event_risk_status': 'CLEAR', 'is_blackout': False},
            'liquidity': {'liquidity_status': 'QUALIFIED'},
            'technical_trade_setup': {'qualified': True, 'direction': 'BUY', 'stop_loss': 90.0, 'take_profit_1': 120.0, 'entry_validity_sec': 3600}
        }
        t_res = {'model_id': 'deepseek-v4-flash', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        j_res = {'model_id': 'jev-latest', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        rec = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res)
        self.assertEqual(rec['reconciliation_outcome'], 'WAIT')
        self.assertEqual(rec['agreement_status'], 'GATE_VETO')
        self.assertEqual(rec['model_agreement_status'], 'AGREED')
        self.assertTrue(any('Market data freshness gate failed' in r for r in rec['veto_reasons']))

    def test_d3_audit_expired_entry_validity(self):
        snap = {
            'market_data': {'price': 100.0, 'freshness_status': 'FRESH'},
            'calendar': {'event_risk_status': 'CLEAR', 'is_blackout': False},
            'liquidity': {'liquidity_status': 'QUALIFIED'},
            'technical_trade_setup': {'qualified': True, 'direction': 'BUY', 'stop_loss': 90.0, 'take_profit_1': 120.0, 'entry_validity_sec': 0}
        }
        t_res = {'model_id': 'deepseek-v4-flash', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        j_res = {'model_id': 'jev-latest', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        rec = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res)
        self.assertEqual(rec['reconciliation_outcome'], 'WAIT')
        self.assertEqual(rec['agreement_status'], 'GATE_VETO')
        self.assertEqual(rec['model_agreement_status'], 'AGREED')
        self.assertTrue(any('Entry validity window has expired' in r for r in rec['veto_reasons']))

    def test_d4_audit_unqualified_setup(self):
        snap = {
            'market_data': {'price': 100.0, 'freshness_status': 'FRESH'},
            'calendar': {'event_risk_status': 'CLEAR', 'is_blackout': False},
            'liquidity': {'liquidity_status': 'QUALIFIED'},
            'technical_trade_setup': {'qualified': False, 'direction': 'BUY', 'stop_loss': 90.0, 'take_profit_1': 120.0, 'entry_validity_sec': 3600}
        }
        t_res = {'model_id': 'deepseek-v4-flash', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        j_res = {'model_id': 'jev-latest', 'status': 'COMPLETED', 'directional_view': 'BULLISH'}
        rec = dual_ai_engine.reconcile_evaluations(snap, t_res, j_res)
        self.assertEqual(rec['reconciliation_outcome'], 'WAIT')
        self.assertEqual(rec['agreement_status'], 'GATE_VETO')
        self.assertEqual(rec['model_agreement_status'], 'AGREED')
        self.assertTrue(any('Technical trade setup is not qualified' in r for r in rec['veto_reasons']))

if __name__ == '__main__':
    unittest.main()
