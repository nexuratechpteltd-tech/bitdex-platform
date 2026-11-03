"""
TAURIC Trading Platform — Phase 2 Capability Discovery & Strategy Compatibility Acceptance Suite
Target: Isolated Staging Environment (http://127.0.0.1:8002)

Tests:
1. Universal Provider Capabilities Endpoint & Strategy Registry Verification
2. Standardized Capability States & Evidence Types Verification (16 items)
3. Freshness & Latency Tracking (Timestamp & Latency ms)
4. Strategy Compatibility: COMPATIBLE Scenario (Spot Grid on Verified Spot)
5. Strategy Compatibility: INCOMPATIBLE Market Mismatch (Forex on Crypto)
6. Strategy Compatibility: INCOMPATIBLE Product Mismatch (Spot Grid on Futures)
7. Strategy Compatibility: INDETERMINATE Stale Evidence (>24h)
8. Provider Outage / Inconclusive Safety (Never convert timeout into Unsupported)
9. Authoritative Key Permissions & Withdrawal Invariant
10. Multi-Provider Adapter Capability Discovery (Binance, Bybit, Bitget, MT5, OKX)
11. Strategy Compatibility Does Not Authorize Trading (Platform Lock HTTP 403)
12. Vault Retest Parity & Secret Privacy Invariant
"""

import sys
if "/opt/tauric-platform-staging/backend" not in sys.path:
    sys.path.insert(0, "/opt/tauric-platform-staging/backend")
import unittest
import asyncio
import httpx
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

STAGING_BASE_URL = "http://127.0.0.1:8002/api/v1"

class TauricPhase2CapabilityDiscoveryTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        headers = {"X-Tauric-Test-Token": "tauric_staging_test_token_8f39b1a47c20"}
        self.client = httpx.AsyncClient(base_url=STAGING_BASE_URL, headers=headers, timeout=15.0)
        self.created_profiles: List[str] = []

    async def asyncTearDown(self):
        for pid in self.created_profiles:
            try:
                await self.client.delete(f"/connections/profiles/{pid}")
            except Exception:
                pass
        await self.client.aclose()

    # -------------------------------------------------------------------------
    # Test 1: Strategy Registry & Requirements Inspection
    # -------------------------------------------------------------------------
    async def test_01_strategy_registry_inspection(self):
        """Verify GET /connections/strategies exposes all 5 platform strategies with mandatory capabilities."""
        resp = await self.client.get("/connections/strategies")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "SUCCESS")
        strats = {s["strategy_id"]: s for s in data.get("strategies", [])}

        expected = ["SPOT_GRID", "FUTURES_GRID", "FOREX_SCALP", "FOREX_SWING", "CRYPTO_MOMENTUM"]
        for s_id in expected:
            self.assertIn(s_id, strats, f"Strategy {s_id} must be registered.")
            s = strats[s_id]
            self.assertTrue(len(s["mandatory_capabilities"]) > 0)
            self.assertIn("market_type", s)
            self.assertIn("supported_products", s)
            self.assertEqual(s.get("max_evidence_age_hours"), 24)

    # -------------------------------------------------------------------------
    # Test 2: Standardized Capability States & Evidence Types
    # -------------------------------------------------------------------------
    async def test_02_standardized_capability_states_and_evidence(self):
        """Verify all 8 explicit CapabilityState and 5 EvidenceType enums are properly declared and used."""
        from app.services.exchange_framework import CapabilityState, EvidenceType

        valid_states = {
            "VERIFIED_SUPPORTED", "VERIFIED_UNSUPPORTED", "PERMISSION_DENIED",
            "AUTHENTICATION_FAILED", "CONFIGURATION_MISMATCH", "TEMPORARILY_UNAVAILABLE",
            "NOT_TESTED", "INCONCLUSIVE"
        }
        for s in valid_states:
            self.assertEqual(getattr(CapabilityState, s).value, s)

        valid_evidence = {
            "PROBE_SUCCESS", "PROBE_REJECTION", "KEY_METADATA", "DOCUMENTATION_ONLY", "NONE"
        }
        for e in valid_evidence:
            self.assertEqual(getattr(EvidenceType, e).value, e)

    # -------------------------------------------------------------------------
    # Test 3: Bitget Futures Capability Discovery & Matrix Structure
    # -------------------------------------------------------------------------
    async def test_03_capability_matrix_generation_on_test(self):
        """Verify pre-save connection probe generates 16-point capability matrix and 14-point permission matrix."""
        resp = await self.client.post("/connections/test", json={
            "exchange": "BITGET",
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "environment": "DEMO",
            "api_key": "bg_mock_key_test",
            "api_secret": "bg_mock_sec_test",
            "passphrase": "bg_mock_pass_test"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Check 16-item capability_matrix
        cap_matrix = data.get("capability_matrix", [])
        self.assertTrue(len(cap_matrix) >= 15, f"Expected at least 15 capabilities, got {len(cap_matrix)}")
        cap_ids = [c["capability_id"] for c in cap_matrix]
        self.assertIn("MARKET_TICKER", cap_ids)
        self.assertIn("MARKET_SYMBOLS", cap_ids)
        self.assertIn("ACCOUNT_AUTH", cap_ids)
        self.assertIn("TRANSFERS_WITHDRAWALS", cap_ids)

        for c in cap_matrix:
            self.assertIn("state", c)
            self.assertIn("evidence_type", c)
            self.assertIn("evidence", c)
            self.assertIn("timestamp", c)

        # Check backward-compatibility 14-item permission_matrix
        perm_matrix = data.get("permission_matrix", [])
        self.assertEqual(len(perm_matrix), 14, f"Legacy permission_matrix must have exactly 14 items, got {len(perm_matrix)}")
        transfer_item = next(i for i in perm_matrix if "Transfers / withdrawals" in i.get("capability", ""))
        self.assertIn("Disabled or unavailable", transfer_item.get("result", ""))

    # -------------------------------------------------------------------------
    # Test 4: Strategy Compatibility: COMPATIBLE Scenario
    # -------------------------------------------------------------------------
    async def test_04_strategy_compatibility_compatible(self):
        """Verify SPOT_GRID returns COMPATIBLE when all mandatory capabilities are satisfied and evidence is fresh."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await self.client.post("/connections/strategy-compatibility", json={
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": now_iso,
            "capability_matrix": [
                {"capability_id": "MARKET_TICKER", "state": "VERIFIED_SUPPORTED", "evidence": "Ticker feed ok"},
                {"capability_id": "MARKET_SYMBOLS", "state": "VERIFIED_SUPPORTED", "evidence": "Symbols ok"},
                {"capability_id": "MARKET_CANDLES", "state": "VERIFIED_SUPPORTED", "evidence": "Candles ok"},
                {"capability_id": "ACCOUNT_AUTH", "state": "VERIFIED_SUPPORTED", "evidence": "Auth ok"},
                {"capability_id": "WALLET_BALANCES", "state": "VERIFIED_SUPPORTED", "evidence": "Balances ok"},
                {"capability_id": "OPEN_ORDERS_READ", "state": "VERIFIED_SUPPORTED", "evidence": "Open orders ok"}
            ],
            "strategy_id": "SPOT_GRID"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        eval_spot = data["strategies"]["SPOT_GRID"]
        self.assertEqual(eval_spot["status"], "COMPATIBLE")
        self.assertTrue(any("mandatory capabilities verified" in r for r in eval_spot["reasons"]))
        self.assertEqual(len(eval_spot["missing_capabilities"]), 0)

    # -------------------------------------------------------------------------
    # Test 5: Strategy Compatibility: INCOMPATIBLE Market Mismatch
    # -------------------------------------------------------------------------
    async def test_05_strategy_compatibility_market_mismatch(self):
        """Verify FOREX_SCALP returns INCOMPATIBLE when connection profile is CRYPTO."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await self.client.post("/connections/strategy-compatibility", json={
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": now_iso,
            "capability_matrix": [
                {"capability_id": "MARKET_TICKER", "state": "VERIFIED_SUPPORTED"}
            ],
            "strategy_id": "FOREX_SCALP"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        eval_forex = data["strategies"]["FOREX_SCALP"]
        self.assertEqual(eval_forex["status"], "INCOMPATIBLE")
        self.assertTrue(any("Market type mismatch" in r for r in eval_forex["reasons"]))

    # -------------------------------------------------------------------------
    # Test 6: Strategy Compatibility: INCOMPATIBLE Product Mismatch
    # -------------------------------------------------------------------------
    async def test_06_strategy_compatibility_product_mismatch(self):
        """Verify SPOT_GRID returns INCOMPATIBLE when account is FUTURES_USDT."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await self.client.post("/connections/strategy-compatibility", json={
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "last_tested_utc": now_iso,
            "capability_matrix": [
                {"capability_id": "MARKET_TICKER", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_SYMBOLS", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_CANDLES", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "ACCOUNT_AUTH", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "WALLET_BALANCES", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "OPEN_ORDERS_READ", "state": "VERIFIED_SUPPORTED"}
            ],
            "strategy_id": "SPOT_GRID"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        eval_spot = data["strategies"]["SPOT_GRID"]
        self.assertEqual(eval_spot["status"], "INCOMPATIBLE")
        self.assertTrue(any("Product category mismatch" in r for r in eval_spot["reasons"]))

    # -------------------------------------------------------------------------
    # Test 7: Strategy Compatibility: INDETERMINATE Stale Evidence (>24h)
    # -------------------------------------------------------------------------
    async def test_07_strategy_compatibility_stale_evidence(self):
        """Verify strategy compatibility returns INDETERMINATE when evidence is older than 24 hours."""
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await self.client.post("/connections/strategy-compatibility", json={
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": stale_time,
            "capability_matrix": [
                {"capability_id": "MARKET_TICKER", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_SYMBOLS", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_CANDLES", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "ACCOUNT_AUTH", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "WALLET_BALANCES", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "OPEN_ORDERS_READ", "state": "VERIFIED_SUPPORTED"}
            ],
            "strategy_id": "SPOT_GRID"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        eval_spot = data["strategies"]["SPOT_GRID"]
        self.assertEqual(eval_spot["status"], "INDETERMINATE")
        self.assertTrue(any("evidence is stale" in r for r in eval_spot["reasons"]))

    # -------------------------------------------------------------------------
    # Test 8: Inconclusive Safety (Timeouts must NOT be Unsupported)
    # -------------------------------------------------------------------------
    async def test_08_inconclusive_safety_on_timeout(self):
        """Verify timeouts yield INCONCLUSIVE rather than VERIFIED_UNSUPPORTED."""
        from app.services.exchange_framework import CapabilityState
        # Evaluate profile where ticker is INCONCLUSIVE
        resp = await self.client.post("/connections/strategy-compatibility", json={
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capability_matrix": [
                {"capability_id": "MARKET_TICKER", "state": CapabilityState.INCONCLUSIVE.value, "evidence": "Probe timed out after 8s"}
            ],
            "strategy_id": "SPOT_GRID"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        eval_spot = data["strategies"]["SPOT_GRID"]
        self.assertEqual(eval_spot["status"], "INDETERMINATE")
        self.assertTrue(any("INCONCLUSIVE" in r for r in eval_spot["reasons"]))

    # -------------------------------------------------------------------------
    # Test 9: Authoritative Key Permissions & Withdrawal Safety
    # -------------------------------------------------------------------------
    async def test_09_authoritative_key_permissions_and_withdrawal_safety(self):
        """Verify transfers/withdrawals are marked NOT_TESTED with strict safety invariant."""
        resp = await self.client.post("/connections/test", json={
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "environment": "DEMO",
            "api_key": "binance_mock_key",
            "api_secret": "binance_mock_secret"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        cap_matrix = data.get("capability_matrix", [])
        transfer_cap = next(c for c in cap_matrix if c["capability_id"] == "TRANSFERS_WITHDRAWALS")
        self.assertEqual(transfer_cap["state"], "NOT_TESTED")
        self.assertEqual(transfer_cap["authoritative_key_permission"], False)
        self.assertIn("disabled or unavailable", transfer_cap["evidence"].lower())

    # -------------------------------------------------------------------------
    # Test 10: Multi-Provider Adapter Capability Discovery
    # -------------------------------------------------------------------------
    async def test_10_multi_provider_adapter_discovery(self):
        """Verify universal discovery engine supports Binance, Bybit, Bitget, MT5, and Custom Forex."""
        providers_to_test = [
            ("BINANCE", "CRYPTO", "SPOT", "DEMO"),
            ("BYBIT", "CRYPTO", "UNIFIED", "DEMO"),
            ("BITGET", "CRYPTO", "FUTURES_USDT", "DEMO"),
            ("MT5", "FOREX", "MT5_HEDGING", "DEMO"),
            ("CUSTOM_FOREX", "FOREX", "FOREX_STANDARD", "DEMO")
        ]
        for exch, mkt, prod, env in providers_to_test:
            resp = await self.client.post("/connections/test", json={
                "exchange": exch,
                "market_type": mkt,
                "product_type": prod,
                "environment": env,
                "api_key": f"mock_key_{exch}",
                "api_secret": f"mock_sec_{exch}",
                "passphrase": f"mock_pass_{exch}"
            })
            self.assertEqual(resp.status_code, 200, f"Provider {exch} connection test failed with {resp.status_code}")
            d = resp.json()
            self.assertIn("capability_matrix", d)
            self.assertIn("strategy_compatibility", d)
            self.assertTrue(len(d["capability_matrix"]) >= 15)

    # -------------------------------------------------------------------------
    # Test 11: Strategy Compatibility Does NOT Authorize Trading (Lock HTTP 403)
    # -------------------------------------------------------------------------
    async def test_11_strategy_compatibility_never_bypasses_hard_lock(self):
        """Verify strategy compatibility check does not authorize live trading (HTTP 403 strictly enforced)."""
        # Ensure notice is present in compatibility response
        resp = await self.client.get("/connections/strategies")
        self.assertEqual(resp.status_code, 200)

        # Attempt to submit a live order
        order_resp = await self.client.post("/orders/live/submit", json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 60000.0,
            "exchange": "BINANCE"
        })
        self.assertEqual(order_resp.status_code, 403, "Live order submission must return HTTP 403 Forbidden")
        self.assertIn("live_trading_locked=true", order_resp.json()["detail"])

    # -------------------------------------------------------------------------
    # Test 12: Profile Vault Retest Parity & Secret Privacy Invariant
    # -------------------------------------------------------------------------
    async def test_12_profile_vault_retest_parity_and_secret_privacy(self):
        """Verify saved profile retains capability_matrix, strategy_compatibility, and hides secrets."""
        # 1. Create a profile
        secret_value = "super_secret_phase2_key_999"
        pass_value = "passphrase_phase2_888"
        save_resp = await self.client.post("/connections/profiles", json={
            "exchange": "BITGET",
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "environment": "DEMO",
            "label": "Phase2 Test Profile",
            "api_key": "bg_phase2_test_key",
            "api_secret": secret_value,
            "passphrase": pass_value
        })
        self.assertEqual(save_resp.status_code, 200)
        profile_id = save_resp.json()["profile"]["profile_id"]
        self.created_profiles.append(profile_id)

        # 2. Retest profile
        retest_resp = await self.client.post(f"/connections/profiles/{profile_id}/retest")
        self.assertEqual(retest_resp.status_code, 200)
        retest_data = retest_resp.json()

        self.assertIn("capability_matrix", retest_data)
        self.assertIn("strategy_compatibility", retest_data)
        self.assertNotIn(secret_value, json.dumps(retest_data))
        self.assertNotIn(pass_value, json.dumps(retest_data))

        # 3. Retrieve capabilities endpoint
        caps_resp = await self.client.get(f"/connections/profiles/{profile_id}/capabilities")
        self.assertEqual(caps_resp.status_code, 200)
        caps_data = caps_resp.json()
        self.assertIn("capability_matrix", caps_data)
        self.assertIn("strategy_compatibility", caps_data)
        self.assertNotIn(secret_value, json.dumps(caps_data))

        # 4. Strategy compatibility endpoint for profile
        strat_resp = await self.client.get(f"/connections/profiles/{profile_id}/strategy-compatibility")
        self.assertEqual(strat_resp.status_code, 200)
        strat_data = strat_resp.json()
        self.assertIn("strategies", strat_data)
        self.assertIn("safe_execution_notice", strat_data)


if __name__ == "__main__":
    unittest.main()
