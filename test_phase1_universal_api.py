#!/usr/bin/env python3
"""
TAURIC Platform — Phase 1 Universal API Acceptance & Regression Suite
Tests:
1. Market/Provider Separation
2. Product/Account Validation & Provider Schemas
3. Product/Environment Incompatibility Detection (Bitget Spot Demo rejected)
4. Bitget Futures Demo Acceptance
5. Live vs Demo Configuration Persistence
6. Initial Test vs Saved-Profile Retest Parity
7. Backward Compatibility (Legacy Profile Migration)
8. Provider-Specific Error Normalization (Bitget 40099, 40037, 40012, Rate Limit, Outages)
9. Secret Privacy Invariant (Zero secret leakage)
10. Connection Rate Limiter Verification (10 req/min)
11. Platform Execution Lock Invariant (HTTP 403 Forbidden)
"""

import sys
import os
import json
import asyncio
import sys
if "/opt/tauric-platform-staging/backend" not in sys.path:
    sys.path.insert(0, "/opt/tauric-platform-staging/backend")
import unittest
import httpx

BASE_URL = "http://127.0.0.1:8002"
API_URL = f"{BASE_URL}/api/v1"

class TauricPhase1AcceptanceTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(base_url=API_URL, headers={"X-Tauric-Test-Token": "tauric_staging_test_token_8f39b1a47c20"}, timeout=15.0)
        self.created_profiles = []

    async def asyncTearDown(self):
        # Cleanup any profiles created during tests
        for pid in self.created_profiles:
            try:
                await self.client.delete(f"/connections/profiles/{pid}")
            except Exception:
                pass
        await self.client.aclose()

    async def test_01_provider_schema_registry(self):
        """Verify GET /connections/providers/{id}/schema returns typed products and credentials."""
        resp = await self.client.get("/connections/providers/BITGET/schema")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "SUCCESS")
        schema = data["schema"]
        self.assertEqual(schema["provider"], "BITGET")
        self.assertEqual(schema["market_type"], "CRYPTO")
        prod_ids = [p["id"] for p in schema["supported_products"]]
        self.assertIn("FUTURES_USDT", prod_ids)
        self.assertIn("SPOT", prod_ids)
        self.assertEqual(schema["default_product"], "FUTURES_USDT")

        # Test non-existent provider
        bad_resp = await self.client.get("/connections/providers/UNKNOWN_EXCH/schema")
        self.assertEqual(bad_resp.status_code, 404)

    async def test_02_crypto_forex_separation(self):
        """Assert Forex provider rejected on Crypto market and vice versa."""
        # MT5 submitted with CRYPTO market
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "MT5",
            "market_type": "CRYPTO",
            "environment": "DEMO",
            "label": "Invalid MT5 Crypto",
            "api_key": "12345",
            "api_secret": "pass"
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not a valid cryptocurrency exchange", resp.json()["detail"])

        # BINANCE submitted with FOREX market
        resp2 = await self.client.post("/connections/profiles", json={
            "exchange": "BINANCE",
            "market_type": "FOREX",
            "environment": "DEMO",
            "label": "Invalid Binance Forex",
            "api_key": "12345",
            "api_secret": "pass"
        })
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("not a valid forex broker", resp2.json()["detail"])

    async def test_03_product_validation_and_compatibility(self):
        """Assert invalid product rejected and unsupported environment/product rejected."""
        # Unsupported product for Coinbase (Coinbase only supports SPOT)
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "COINBASE",
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "environment": "DEMO",
            "label": "Invalid Coinbase Product",
            "api_key": "key",
            "api_secret": "sec"
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not supported by COINBASE", resp.json()["detail"])

        # Bitget Spot in DEMO mode must be rejected (Bitget has no Spot paper trading)
        resp2 = await self.client.post("/connections/profiles", json={
            "exchange": "BITGET",
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "environment": "DEMO",
            "label": "Invalid Bitget Spot Demo",
            "api_key": "key",
            "api_secret": "sec",
            "passphrase": "pass"
        })
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("does not support DEMO for product SPOT", resp2.json()["detail"])

    async def test_04_bitget_futures_demo_persistence(self):
        """Verify Bitget Futures Demo is accepted, persists product_type, and masks secrets."""
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "BITGET",
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "environment": "DEMO",
            "label": "Bitget Demo Test",
            "api_key": "bg_test_key_12345678",
            "api_secret": "secret_abc_xyz_999",
            "passphrase": "my_passphrase_123"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "SUCCESS")
        profile = data["profile"]
        pid = profile["profile_id"]
        self.created_profiles.append(pid)

        self.assertEqual(profile["product_type"], "FUTURES_USDT")
        self.assertEqual(profile["environment"], "DEMO")
        self.assertEqual(profile["api_key_masked"], "bg_t••••••••5678")
        self.assertNotIn("secret_abc_xyz_999", json.dumps(data))
        self.assertNotIn("my_passphrase_123", json.dumps(data))

        # Query profile by list
        list_resp = await self.client.get("/connections/profiles")
        self.assertEqual(list_resp.status_code, 200)
        found = [p for p in list_resp.json()["profiles"] if p["profile_id"] == pid]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["product_type"], "FUTURES_USDT")

    async def test_05_retest_consistency_and_parity(self):
        """Assert retest loads saved environment and product_type from vault without loss."""
        # Create a valid profile
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "BYBIT",
            "market_type": "CRYPTO",
            "product_type": "UNIFIED",
            "environment": "DEMO",
            "label": "Bybit Retest Parity Test",
            "api_key": "bybit_test_key",
            "api_secret": "bybit_test_secret"
        })
        self.assertEqual(resp.status_code, 200)
        pid = resp.json()["profile"]["profile_id"]
        self.created_profiles.append(pid)

        # Trigger retest via dedicated /retest route
        retest_resp = await self.client.post(f"/connections/profiles/{pid}/retest")
        self.assertEqual(retest_resp.status_code, 200)
        ret_data = retest_resp.json()
        self.assertEqual(ret_data.get("exchange"), "BYBIT")
        self.assertEqual(ret_data.get("environment"), "DEMO")
        self.assertEqual(ret_data.get("product_type"), "UNIFIED")

        # Verify vault record still has product_type and environment intact
        list_resp = await self.client.get("/connections/profiles")
        saved_p = [p for p in list_resp.json()["profiles"] if p["profile_id"] == pid][0]
        self.assertEqual(saved_p["product_type"], "UNIFIED")
        self.assertEqual(saved_p["environment"], "DEMO")

    async def test_06_error_normalization_bitget_40099(self):
        """Verify Bitget 40099 is normalized to ENVIRONMENT_MISMATCH with clear guidance."""
        from app.services.exchange_framework import classify_exchange_error, ErrorClassification
        cls, code, msg, guide = classify_exchange_error(
            exchange="BITGET",
            status_code=400,
            response_text=json.dumps({"code": "40099", "msg": "exchange environment is incorrect", "requestTime": 1792685921718})
        )
        self.assertEqual(cls, ErrorClassification.ENVIRONMENT_MISMATCH)
        self.assertEqual(code, "40099")
        self.assertEqual(msg, "exchange environment is incorrect")
        self.assertIn("Environment mismatch", guide)
        self.assertIn("USDT-M Futures", guide)

    async def test_07_error_normalization_auth_and_permissions(self):
        """Verify error taxonomy across authentication, permission denied, rate limits, and outages."""
        from app.services.exchange_framework import classify_exchange_error, ErrorClassification
        
        # Bitget 40037
        cls, code, _, _ = classify_exchange_error("BITGET", 400, json.dumps({"code": "40037", "msg": "Apikey does not exist"}))
        self.assertEqual(cls, ErrorClassification.AUTHENTICATION_FAILED)
        self.assertEqual(code, "40037")

        # Bitget 40012
        cls, code, _, _ = classify_exchange_error("BITGET", 400, json.dumps({"code": "40012", "msg": "apikey/password is incorrect"}))
        self.assertEqual(cls, ErrorClassification.AUTHENTICATION_FAILED)
        self.assertEqual(code, "40012")

        # Binance -2015 (Permission / IP whitelist)
        cls, code, _, _ = classify_exchange_error("BINANCE", 400, json.dumps({"code": -2015, "msg": "Invalid API-key, IP, or permissions"}))
        self.assertEqual(cls, ErrorClassification.PERMISSION_DENIED)

        # Rate Limit 429
        cls, code, _, _ = classify_exchange_error("BYBIT", 429, json.dumps({"code": "10006", "msg": "Too many visits"}))
        self.assertEqual(cls, ErrorClassification.RATE_LIMITED)

        # Server Outage 503
        cls, code, _, _ = classify_exchange_error("COINBASE", 503, "Service Unavailable")
        self.assertEqual(cls, ErrorClassification.TEMPORARILY_UNAVAILABLE)

    async def test_08_backward_compatibility_legacy_migration(self):
        """Verify legacy profiles lacking product_type are safely backfilled without secret corruption."""
        from app.services.exchange_framework import credential_vault, ProductType
        
        # Insert a simulated legacy profile without product_type
        legacy_id = "prof_legacy_test_01020304"
        credential_vault._profiles[legacy_id] = {
            "profile_id": legacy_id,
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "environment": "DEMO",
            "label": "Legacy Binance Profile",
            "api_key_masked": "bi_t••••••••1234",
            "_credentials_enc": "dummy_enc",
            "is_read_only": True
            # product_type is intentionally missing
        }
        self.created_profiles.append(legacy_id)

        # Trigger migration
        credential_vault._migrate_legacy_profiles()

        # Check that product_type was safely backfilled with default SPOT
        p = credential_vault._profiles[legacy_id]
        self.assertEqual(p.get("product_type"), ProductType.SPOT.value)

    async def test_09_platform_execution_lock(self):
        """Verify live trading submission unconditionally returns HTTP 403 Forbidden."""
        resp = await self.client.post("/orders/live/submit", json={
            "exchange": "BINANCE",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "amount": 0.001,
            "price": 50000.0
        })
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Live trading is hard-locked", resp.json()["detail"])

    async def test_10_rate_limiting_enforcement(self):
        """Verify connection test rate limiting (10 req/60s)."""
        import secrets
        test_ip = f"198.51.100.{secrets.randbelow(200)+20}"
        headers = {"X-Forwarded-For": test_ip}
        
        # Create a temporary profile to test retest rate limiting cleanly
        p_res = await self.client.post("/connections/profiles", json={
            "exchange": "BYBIT",
            "market_type": "CRYPTO",
            "product_type": "UNIFIED",
            "environment": "DEMO",
            "label": "Rate Limit Test Profile",
            "api_key": "k",
            "api_secret": "s"
        })
        self.assertEqual(p_res.status_code, 200)
        pid = p_res.json()["profile"]["profile_id"]
        self.created_profiles.append(pid)

        # Fire retests until throttled
        throttled = False
        allowed = 0
        for _ in range(12):
            r = await self.client.post(f"/connections/profiles/{pid}/retest", headers=headers)
            if r.status_code == 429:
                throttled = True
                self.assertIn("rate limit exceeded", r.text.lower())
                self.assertIsNotNone(r.headers.get("Retry-After"))
                break
            else:
                allowed += 1

        self.assertEqual(allowed, 10)
        self.assertTrue(throttled)


if __name__ == "__main__":
    unittest.main()
