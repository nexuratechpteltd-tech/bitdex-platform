"""
Tauric Platform — Phase 3.3.5 Targeted Preflight & Credential Safeguards Suite
Covers:
1. Credential storage and AES-256-GCM encryption verification under rotated key.
2. Public response secret redaction across all connection endpoints.
3. Authenticated preflight fail-closed behavior for unconfigured/invalid credentials.
4. Environment isolation and strict testnet endpoint routing.
5. Live testnet symbol trading rules and precision retrieval (Binance Spot Testnet).
"""

import unittest
import asyncio
import os
import json
import tempfile
import shutil
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.services.exchange_framework import (
    CredentialVault,
    exchange_framework,
    BinanceSpotAdapter,
    BybitSpotAdapter,
    Environment,
    ExchangeId,
    OrderStatus,
    OrderSide,
    OrderType,
    get_vault_master_key
)
from app.config import settings


class TestPhase335Preflight(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.test_dir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.test_dir, "test_vault.json")
        self.vault = CredentialVault(storage_path=self.vault_path)
        self.client = TestClient(app)

    def tearDown(self):
        self.loop.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_api_connections_save_workflow_encryption_and_redaction(self):
        """Verify profile saving encrypts with AES-256-GCM and redacts secrets from public output."""
        # 1. Save profile
        public_profile = self.vault.save_profile(
            exchange="BINANCE",
            environment="DEMO",
            label="Binance Testnet Primary",
            api_key="vmPU1234567890abcdefXYZ",
            api_secret="very_secret_key_that_must_never_leak"
        )

        # 2. Verify public profile structure (no raw secret)
        self.assertIn("profile_id", public_profile)
        self.assertEqual(public_profile["exchange"], "BINANCE")
        self.assertEqual(public_profile["environment"], "DEMO")
        self.assertEqual(public_profile["label"], "Binance Testnet Primary")
        self.assertEqual(public_profile["api_key_masked"], "vmPU••••••••fXYZ")
        self.assertNotIn("api_secret", public_profile)
        self.assertNotIn("_credentials_enc", public_profile)
        self.assertNotIn("api_key", public_profile)

        # 3. Verify internal storage on disk is AES-256-GCM encrypted
        with open(self.vault_path, "r", encoding="utf-8") as f:
            disk_data = json.load(f)

        pid = public_profile["profile_id"]
        raw_record = disk_data[pid]
        self.assertIn("_credentials_enc", raw_record)
        self.assertEqual(raw_record["_credentials_enc"]["cipher"], "AES-256-GCM")
        self.assertIn("ciphertext", raw_record["_credentials_enc"])
        self.assertIn("nonce", raw_record["_credentials_enc"])
        self.assertNotIn("very_secret_key_that_must_never_leak", json.dumps(raw_record))

        # 4. Verify internal decrypt restores credentials accurately
        creds = self.vault.get_credentials(pid)
        self.assertEqual(creds["api_key"], "vmPU1234567890abcdefXYZ")
        self.assertEqual(creds["api_secret"], "very_secret_key_that_must_never_leak")

    def test_02_routes_connections_profiles_redaction(self):
        """Verify REST API /connections/profiles strictly redacts secrets."""
        # Query profiles
        res = self.client.get("/api/v1/connections/profiles")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIsInstance(data["profiles"], list)
        for p in data["profiles"]:
            self.assertNotIn("api_secret", p)
            self.assertNotIn("_credentials_enc", p)
            if "api_key" in p:
                self.assertNotIn("very_secret", p["api_key"])

    def test_03_authenticated_preflight_fail_closed_unconfigured(self):
        """Verify preflight check fails closed when credentials are missing or invalid."""
        binance = BinanceSpotAdapter()

        # Test preflight verification with unconfigured credentials
        res = self.loop.run_until_complete(
            binance.verify_permissions(Environment.DEMO, {"api_key": "", "api_secret": ""})
        )
        self.assertEqual(res["status"], "FAIL")
        self.assertFalse(res["verified"])
        self.assertFalse(res["can_trade"])
        self.assertIn("Missing API Key or API Secret", res["error"])

        # Test submit order fails closed
        order_req = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "price": 65000.0,
            "client_order_id": "ORD-TEST-FAILCLOSED"
        }
        receipt = self.loop.run_until_complete(
            binance.submit_order(order_req, Environment.DEMO, {})
        )
        self.assertEqual(receipt.status, OrderStatus.REJECTED)
        self.assertEqual(receipt.executed_qty, 0.0)
        self.assertIn("BLOCKED", receipt.error_message)

    def test_04_environment_isolation_and_endpoint_routing(self):
        """Verify DEMO routes strictly to testnet endpoints and LIVE execution is hard-locked."""
        binance = BinanceSpotAdapter()
        bybit = BybitSpotAdapter()

        self.assertEqual(binance._get_base_url(Environment.DEMO), "https://demo-api.binance.com/api/v3")
        self.assertEqual(binance._get_base_url(Environment.LIVE), "https://api.binance.com/api/v3")
        self.assertEqual(bybit._get_base_url(Environment.DEMO), "https://api-testnet.bybit.com/v5")
        self.assertEqual(bybit._get_base_url(Environment.LIVE), "https://api.bybit.com/v5")

        # Verify live execution is hard-locked
        with self.assertRaises(PermissionError):
            self.loop.run_until_complete(
                binance.submit_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001}, Environment.LIVE, {"api_key": "k", "api_secret": "s"})
            )

        with self.assertRaises(PermissionError):
            self.loop.run_until_complete(
                bybit.submit_order({"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001}, Environment.LIVE, {"api_key": "k", "api_secret": "s"})
            )

    def test_05_symbol_rules_retrieval_from_testnet(self):
        """Verify real Binance Spot Testnet exchangeInfo returns valid rules."""
        binance = BinanceSpotAdapter()
        rules = self.loop.run_until_complete(
            binance.fetch_symbol_rules("BTCUSDT", Environment.DEMO)
        )
        self.assertEqual(rules.symbol, "BTCUSDT")
        self.assertEqual(rules.base_asset, "BTC")
        self.assertEqual(rules.quote_asset, "USDT")
        self.assertGreater(rules.min_qty, 0.0)
        self.assertGreater(rules.step_size, 0.0)
        self.assertGreater(rules.tick_size, 0.0)
        self.assertGreaterEqual(rules.min_notional, 5.0)

        # Verify sizing rounding against retrieved testnet rules
        rounded_qty = rules.round_qty(0.00123456789)
        self.assertLessEqual(len(str(rounded_qty).split(".")[-1]), 5)


if __name__ == "__main__":
    unittest.main()
