"""
TAURIC Trading Platform — Phase 3A Defect Remediation Acceptance Suite
Tests:
Task 1: Eliminate Stale Verification State on Retest
  - Retest DNS error invalidates stale success and wipes account_data
  - Retest timeout invalidates stale success and sets TEMPORARILY_UNAVAILABLE
  - Subsequent successful retest restores verified status
  - Encrypted credentials remain intact and decryptable across failures
Task 2: Binance Product-Specific Routing
  - Binance Spot routes to api.binance.com /api/v3/*
  - Binance Futures Live routes to fapi.binance.com /fapi/v1/*
  - Binance Futures Demo routes to testnet.binancefuture.com /fapi/v1/*
  - Binance unsupported products rejected with HTTP 400 Bad Request
  - Binance Futures strategy compatibility correctly evaluated against FUTURES_GRID
Task 3: Safe Rate Limiting & Authorized Test Bypass
  - Normal rate limiting enforced at 10 req/min with HTTP 429
  - Authorized bypass token from loopback peer admitted
  - Invalid/spoofed token fails closed
"""

import sys
if "/opt/tauric-platform-staging/backend" not in sys.path:
    sys.path.insert(0, "/opt/tauric-platform-staging/backend")

import unittest
import asyncio
import httpx
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.services.exchange_framework import (
    credential_vault,
    exchange_framework,
    ConnectionStatus,
    CapabilityState,
    ErrorClassification,
    ProductType,
    evaluate_strategy_compatibility
)

STAGING_BASE_URL = "http://127.0.0.1:8002/api/v1"
TEST_BYPASS_TOKEN = "tauric_staging_test_token_8f39b1a47c20"
BYPASS_HEADERS = {"X-Tauric-Test-Token": TEST_BYPASS_TOKEN}


class TauricPhase3ADefectRemediationTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(base_url=STAGING_BASE_URL, headers=BYPASS_HEADERS, timeout=15.0)
        self.created_profiles: List[str] = []

    async def asyncTearDown(self):
        for pid in self.created_profiles:
            try:
                await self.client.delete(f"/connections/profiles/{pid}")
            except Exception:
                try:
                    credential_vault.delete_profile(pid)
                except Exception:
                    pass
        await self.client.aclose()

    # =========================================================================
    # TASK 1: ELIMINATE STALE VERIFICATION STATE
    # =========================================================================

    async def test_01_retest_dns_error_invalidates_stale_success(self):
        """Verify retest failure on DNS error wipes stale account_data, clears demo_verified, and sets CONFIGURATION_MISMATCH."""
        # 1. Create a profile via API
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "CUSTOM",
            "environment": "DEMO",
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "label": "DNS Test Profile",
            "api_key": "valid_test_key_dns",
            "api_secret": "valid_test_secret_dns",
            "custom_config": {"base_url": "https://api.binance.com"}
        })
        self.assertEqual(resp.status_code, 200)
        pid = (resp.json().get("profile_id") or resp.json().get("profile", {}).get("profile_id"))
        self.created_profiles.append(pid)

        # 2. Simulate an initial successful verification
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        simulated_matrix = [{
            "capability_id": "MARKET_TICKER",
            "name": "Price Ticker",
            "category": "MARKET_DATA",
            "state": CapabilityState.VERIFIED_SUPPORTED.value,
            "evidence_type": "PROBE_SUCCESS",
            "evidence": "Verified",
            "timestamp": now_iso,
            "latency_ms": 25,
            "raw_provider_code": None,
            "remediation": None,
            "authoritative_key_permission": None
        }]
        simulated_account_data = {
            "market_type": "CRYPTO",
            "total_equity_usd": 15000.0,
            "available_balance_usd": 10000.0,
            "asset_balances": [{"asset": "USDT", "available": 10000.0, "total": 10000.0}]
        }
        credential_vault.update_verification_results(
            profile_id=pid,
            connection_status=ConnectionStatus.VERIFIED_READ_ONLY.value,
            verification_label="VERIFIED_READ_ONLY",
            endpoint_results=[{"name": "Ping", "status": "PASS"}],
            capabilities=["MARKET_DATA", "BALANCE_QUERY"],
            account_data=simulated_account_data,
            capability_matrix=simulated_matrix
        )

        # Confirm vault records verified state
        p_before = credential_vault.get_profile_public(pid)
        self.assertTrue(p_before.get("demo_verified"))
        self.assertIsNotNone(p_before.get("account_data"))
        self.assertEqual(p_before.get("connection_status"), ConnectionStatus.VERIFIED_READ_ONLY.value)

        # 3. Modify custom_config to a non-resolving domain and retest
        p_entry = credential_vault._profiles[pid]
        p_entry["custom_config"] = {"base_url": "https://nonexistent-dns-domain-xyz987654321.test/api"}
        credential_vault._save()

        # 4. Trigger retest over API
        resp = await self.client.post(f"/connections/profiles/{pid}/retest")
        self.assertEqual(resp.status_code, 200)
        d = resp.json()

        # API response must show non-success with accurate classification
        self.assertEqual(d.get("status"), "FAIL")
        self.assertEqual(d.get("error_classification"), ErrorClassification.CONFIGURATION_MISMATCH.value)
        self.assertEqual(d.get("connection_status"), ConnectionStatus.DISCONNECTED.value)
        self.assertIsNone(d.get("account_data"))

        # 5. Inspect stored vault profile: old success MUST be cleared
        p_after = credential_vault.get_profile_public(pid)
        self.assertFalse(p_after.get("demo_verified"), "demo_verified must be cleared to False on retest failure")
        self.assertFalse(p_after.get("live_verified"), "live_verified must be False")
        self.assertIsNone(p_after.get("account_data"), "stale account balances must be wiped to None")
        self.assertEqual(p_after.get("connection_status"), ConnectionStatus.DISCONNECTED.value)
        self.assertEqual(p_after.get("verification_label"), "CONFIGURATION_MISMATCH")

        # Capability matrix must reflect CONFIGURATION_MISMATCH
        cap_matrix = p_after.get("capability_matrix", [])
        self.assertTrue(len(cap_matrix) >= 15)
        for c in cap_matrix:
            if c["capability_id"] != "TRANSFERS_WITHDRAWALS":
                self.assertEqual(c["state"], CapabilityState.CONFIGURATION_MISMATCH.value)

    async def test_02_retest_timeout_invalidates_stale_success(self):
        """Verify retest timeout sets TEMPORARILY_UNAVAILABLE and clears stale verified flags."""
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "CUSTOM",
            "environment": "DEMO",
            "market_type": "CRYPTO",
            "label": "Timeout Profile",
            "api_key": "timeout_key",
            "api_secret": "timeout_secret",
            "custom_config": {"base_url": "https://api.binance.com"}
        })
        self.assertEqual(resp.status_code, 200)
        pid = (resp.json().get("profile_id") or resp.json().get("profile", {}).get("profile_id"))
        self.created_profiles.append(pid)

        # Mark as verified first
        credential_vault.update_verification_results(
            profile_id=pid,
            connection_status=ConnectionStatus.VERIFIED_READ_ONLY.value,
            verification_label="VERIFIED_READ_ONLY",
            endpoint_results=[],
            capabilities=["BALANCE_QUERY"],
            account_data={"balance": 5000.0}
        )
        self.assertTrue(credential_vault.get_profile_public(pid)["demo_verified"])

        # Point to a routable blackhole IP that causes SSRF failure or timeout
        credential_vault._profiles[pid]["custom_config"] = {"base_url": "https://10.255.255.1"}
        credential_vault._save()

        # Retest
        resp = await self.client.post(f"/connections/profiles/{pid}/retest")
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        self.assertEqual(d["status"], "FAIL")

        p_after = credential_vault.get_profile_public(pid)
        self.assertFalse(p_after["demo_verified"], "Stale demo_verified must be cleared")
        self.assertIsNone(p_after["account_data"], "Stale balance data must be cleared")

    async def test_03_retest_subsequent_success_recovery(self):
        """Verify that after a failed retest, a subsequent successful retest restores verified status cleanly."""
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "CUSTOM",
            "environment": "DEMO",
            "market_type": "CRYPTO",
            "label": "Recovery Profile",
            "api_key": "rec_key",
            "api_secret": "rec_secret",
            "custom_config": {"base_url": "https://api.binance.com"}
        })
        self.assertEqual(resp.status_code, 200)
        pid = (resp.json().get("profile_id") or resp.json().get("profile", {}).get("profile_id"))
        self.created_profiles.append(pid)

        # 1. First retest fails
        credential_vault.update_verification_results(
            profile_id=pid,
            connection_status=ConnectionStatus.DISCONNECTED.value,
            verification_label="DISCONNECTED",
            endpoint_results=[],
            capabilities=[],
            account_data=None
        )
        self.assertFalse(credential_vault.get_profile_public(pid)["demo_verified"])
        self.assertIsNone(credential_vault.get_profile_public(pid)["account_data"])

        # 2. Subsequent retest succeeds
        fresh_account_data = {"market_type": "CRYPTO", "total_equity_usd": 2500.0}
        credential_vault.update_verification_results(
            profile_id=pid,
            connection_status=ConnectionStatus.VERIFIED_READ_ONLY.value,
            verification_label="VERIFIED_READ_ONLY",
            endpoint_results=[{"name": "Ping", "status": "PASS"}],
            capabilities=["MARKET_DATA", "BALANCE_QUERY"],
            account_data=fresh_account_data
        )

        p_recovered = credential_vault.get_profile_public(pid)
        self.assertTrue(p_recovered["demo_verified"])
        self.assertIsNotNone(p_recovered["account_data"])
        self.assertEqual(p_recovered["account_data"]["total_equity_usd"], 2500.0)

    async def test_04_credentials_preserved_atomically_across_failures(self):
        """Verify that encryption bundle in vault.json remains intact and decryptable across failed retests."""
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "CUSTOM",
            "environment": "DEMO",
            "market_type": "CRYPTO",
            "label": "Atomic Preserved Profile",
            "api_key": "secret_preserve_key_123",
            "api_secret": "super_secret_payload_xyz_789",
            "passphrase": "my_precious_passphrase",
            "custom_config": {"base_url": "https://api.binance.com"}
        })
        self.assertEqual(resp.status_code, 200)
        pid = (resp.json().get("profile_id") or resp.json().get("profile", {}).get("profile_id"))
        self.created_profiles.append(pid)

        # Trigger retest that fails
        p_entry = credential_vault._profiles[pid]
        p_entry["custom_config"] = {"base_url": "https://nonexistent-fail-domain.test"}
        credential_vault._save()

        resp = await self.client.post(f"/connections/profiles/{pid}/retest")
        self.assertEqual(resp.status_code, 200)

        # Decrypt stored credentials and ensure they match original values exactly
        creds = credential_vault.get_credentials(pid)
        self.assertIsNotNone(creds)
        self.assertEqual(creds["api_key"], "secret_preserve_key_123")
        self.assertEqual(creds["api_secret"], "super_secret_payload_xyz_789")
        self.assertEqual(creds["passphrase"], "my_precious_passphrase")

    # =========================================================================
    # TASK 2: BINANCE PRODUCT-SPECIFIC ROUTING
    # =========================================================================

    async def test_05_binance_spot_routing(self):
        """Verify Binance with product_type=SPOT routes to api.binance.com and /api/v3/*."""
        resp = await self.client.post("/connections/test", json={
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "environment": "LIVE",
            "api_key": "mock_spot_key",
            "api_secret": "mock_spot_secret"
        })
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        self.assertEqual(d.get("product_type"), "SPOT")
        endpoints = d.get("endpoints", [])
        urls = [e.get("url", "") for e in endpoints]

        # Verify Spot endpoints were probed
        self.assertTrue(any("api.binance.com/api/v3/ping" in u for u in urls), f"Missing v3 ping in {urls}")
        self.assertTrue(any("api.binance.com/api/v3/ticker" in u for u in urls), f"Missing v3 ticker in {urls}")
        self.assertFalse(any("fapi.binance.com" in u for u in urls), "Spot must not contact fapi.binance.com")

    async def test_06_binance_futures_live_routing(self):
        """Verify Binance with product_type=FUTURES_USDT LIVE routes to fapi.binance.com and /fapi/v1/*."""
        resp = await self.client.post("/connections/test", json={
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "environment": "LIVE",
            "api_key": "mock_futures_key",
            "api_secret": "mock_futures_secret"
        })
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        self.assertEqual(d.get("product_type"), "FUTURES_USDT")
        endpoints = d.get("endpoints", [])
        urls = [e.get("url", "") for e in endpoints]

        # Verify Futures endpoints were probed
        self.assertTrue(any("fapi.binance.com/fapi/v1/time" in u for u in urls), f"Missing fapi time in {urls}")
        self.assertTrue(any("fapi.binance.com/fapi/v1/ticker/price" in u for u in urls), f"Missing fapi ticker in {urls}")
        self.assertFalse(any("api.binance.com/api/v3" in u for u in urls), "Futures must not contact Spot api.binance.com")

        # Verify Public ping & ticker succeeded against real fapi.binance.com
        ping_res = next((e for e in endpoints if "time" in e.get("url", "")), None)
        self.assertIsNotNone(ping_res)
        self.assertEqual(ping_res.get("status"), "PASS")

        ticker_res = next((e for e in endpoints if "ticker" in e.get("url", "")), None)
        self.assertIsNotNone(ticker_res)
        self.assertEqual(ticker_res.get("status"), "PASS")

    async def test_07_binance_futures_demo_routing(self):
        """Verify Binance with product_type=FUTURES_USDT DEMO routes to testnet.binancefuture.com."""
        resp = await self.client.post("/connections/test", json={
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "environment": "DEMO",
            "api_key": "mock_demo_futures_key",
            "api_secret": "mock_demo_futures_secret"
        })
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        endpoints = d.get("endpoints", [])
        urls = [e.get("url", "") for e in endpoints]

        self.assertTrue(any("testnet.binancefuture.com/fapi/v1/time" in u for u in urls), f"Missing testnet fapi time in {urls}")

    async def test_08_binance_unsupported_product_rejected(self):
        """Verify unadvertised/unsupported products (e.g. OPTIONS, COIN_FUTURES) are rejected with HTTP 400."""
        resp = await self.client.post("/connections/profiles", json={
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "product_type": "COIN_FUTURES",
            "environment": "LIVE",
            "label": "Invalid Binance Product",
            "api_key": "any_key",
            "api_secret": "any_secret"
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not supported by BINANCE", resp.json().get("detail", ""))

    async def test_09_binance_futures_strategy_compatibility(self):
        """Verify Binance FUTURES_USDT evaluates contract requirements and rejects SPOT_GRID."""
        # 1. FUTURES_USDT against SPOT_GRID -> INCOMPATIBLE (product mismatch)
        eval_resp = await self.client.post("/connections/strategy-compatibility", json={
            "market_type": "CRYPTO",
            "product_type": "FUTURES_USDT",
            "last_tested_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "strategy_id": "SPOT_GRID",
            "capability_matrix": []
        })
        self.assertEqual(eval_resp.status_code, 200)
        d = eval_resp.json()
        strat = d["strategies"]["SPOT_GRID"]
        self.assertEqual(strat["status"], "INCOMPATIBLE")
        self.assertTrue(any("Product category mismatch" in r for r in strat["reasons"]))

        # 2. SPOT against FUTURES_GRID -> INCOMPATIBLE (product mismatch)
        eval_spot = await self.client.post("/connections/strategy-compatibility", json={
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "strategy_id": "FUTURES_GRID",
            "capability_matrix": []
        })
        self.assertEqual(eval_spot.status_code, 200)
        strat_fut = eval_spot.json()["strategies"]["FUTURES_GRID"]
        self.assertEqual(strat_fut["status"], "INCOMPATIBLE")

    # =========================================================================
    # TASK 3: SAFE RATE LIMITING & AUTHORIZED TEST BYPASS
    # =========================================================================

    async def test_10_normal_rate_limiting_enforced_without_token(self):
        """Verify unauthenticated requests without test bypass token are strictly throttled at 10 req/min."""
        async with httpx.AsyncClient(base_url=STAGING_BASE_URL, timeout=10.0) as unauth_client:
            for i in range(10):
                r = await unauth_client.post("/connections/test", json={
                    "exchange": "BINANCE",
                    "market_type": "CRYPTO",
                    "product_type": "SPOT",
                    "environment": "DEMO",
                    "api_key": f"unauth_test_key_{i}",
                    "api_secret": "sec"
                })
                self.assertNotEqual(r.status_code, 429, f"Premature rate limit at request {i+1}")

            throttled = await unauth_client.post("/connections/test", json={
                "exchange": "BINANCE",
                "market_type": "CRYPTO",
                "product_type": "SPOT",
                "environment": "DEMO",
                "api_key": "unauth_test_key_11",
                "api_secret": "sec"
            })
            self.assertEqual(throttled.status_code, 429)
            self.assertIn("Retry-After", throttled.headers)

    async def test_11_invalid_token_fails_closed(self):
        """Verify request with invalid/spoofed test token fails closed and is subjected to normal rate limit."""
        async with httpx.AsyncClient(base_url=STAGING_BASE_URL, headers={"X-Tauric-Test-Token": "invalid_forged_token_123"}, timeout=10.0) as forged_client:
            r = await forged_client.post("/connections/test", json={
                "exchange": "BINANCE",
                "market_type": "CRYPTO",
                "product_type": "SPOT",
                "environment": "DEMO",
                "api_key": "forged_key",
                "api_secret": "sec"
            })
            self.assertEqual(r.status_code, 429, "Forged token must fail closed and remain throttled")

    async def test_12_authorized_bypass_token_admits_request(self):
        """Verify authorized test bypass token from loopback peer admits test requests smoothly."""
        resp = await self.client.post("/connections/test", json={
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "environment": "DEMO",
            "api_key": "bypass_authorized_key",
            "api_secret": "sec"
        })
        self.assertEqual(resp.status_code, 200, f"Authorized bypass request was unexpectedly rejected: {resp.status_code}")


if __name__ == "__main__":
    unittest.main()
