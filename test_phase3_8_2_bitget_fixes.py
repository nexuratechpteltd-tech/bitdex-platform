"""
Tauric Platform — Phase 3.8.2 Bitget Authentication Automated Tests
Exclusively tests /opt/tauric-platform-staging/ backend and proxy APIs:
1. Bitget Demo environment routing (paptrading: 1)
2. Bitget Live environment routing (paptrading omitted)
3. Content-Type: application/json header inclusion
4. Whitespace sanitization on API key, secret, and passphrase
5. Path normalization (leading slash) and canonical query parameter sorting
6. Missing/empty passphrase handling
7. End-to-end API route environment forwarding (DEMO vs LIVE)
8. Mocked exchange responses (40037, 40012, 200 OK balances)
9. Safety hard-locks: live_trading_locked=true, read_only_mode=true, 403 on live order submission
"""

import sys
import os
import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import unittest
from unittest.mock import patch, MagicMock
import httpx

# Ensure staging backend is on sys.path
sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from app.services.exchange_framework import (
    CustomExchangeAdapter,
    Environment,
    ExchangeId,
    SigningMethod,
    ConnectionStatus,
    exchange_framework
)
from app.config import settings

STAGING_BASE_URL = "https://127.0.0.1:33900/trading/api/backend"

class TestBitgetAuthenticationStaging(unittest.TestCase):

    def setUp(self):
        self.bitget_config = {
            "exchange_name": "BITGET",
            "base_url": "https://api.bitget.com",
            "auth_method": "HMAC_SHA256_BASE64",
            "key_header": "ACCESS-KEY",
            "sign_header": "ACCESS-SIGN",
            "time_header": "ACCESS-TIMESTAMP",
            "passphrase_header": "ACCESS-PASSPHRASE",
            "sign_placement": "HEADER",
            "ping_path": "/api/v2/public/time",
            "symbols_path": "/api/v2/spot/public/symbols",
            "ticker_path": "/api/v2/spot/market/tickers?symbol=BTCUSDT",
            "account_path": "/api/v2/spot/account/assets",
            "balances_path": "/api/v2/spot/account/assets",
            "test_symbol": "BTCUSDT"
        }
        self.adapter = CustomExchangeAdapter(custom_config=self.bitget_config, exchange_name="BITGET")

    # -------------------------------------------------------------------------
    # 1. Bitget Demo Environment Routing: paptrading: 1 Header
    # -------------------------------------------------------------------------
    def test_bitget_demo_routing_headers(self):
        creds = {
            "api_key": "bg_demo_key_123",
            "api_secret": "bg_demo_secret_456",
            "passphrase": "bg_demo_passphrase_789"
        }
        headers, params = self.adapter._build_auth_headers_and_params(
            method="GET",
            path="/api/v2/spot/account/assets",
            query_params={},
            credentials=creds,
            environment=Environment.DEMO
        )
        self.assertEqual(headers.get("paptrading"), "1", "Mandatory 'paptrading: 1' header missing for Bitget DEMO!")
        self.assertEqual(headers.get("Content-Type"), "application/json", "Mandatory 'Content-Type: application/json' header missing!")
        self.assertEqual(headers.get("Accept"), "application/json")
        self.assertEqual(headers.get("ACCESS-KEY"), "bg_demo_key_123")
        self.assertEqual(headers.get("ACCESS-PASSPHRASE"), "bg_demo_passphrase_789")
        self.assertTrue(headers.get("ACCESS-TIMESTAMP").isdigit(), "ACCESS-TIMESTAMP must be integer milliseconds")
        self.assertTrue(len(headers.get("ACCESS-SIGN")) == 44, "Base64 HMAC-SHA256 signature must be 44 chars")
        print("✓ Test 1 Passed: Bitget DEMO requests receive 'paptrading: 1' and 'Content-Type: application/json'")

    # -------------------------------------------------------------------------
    # 2. Bitget Live Environment Routing: paptrading Header Omitted
    # -------------------------------------------------------------------------
    def test_bitget_live_routing_headers(self):
        creds = {
            "api_key": "bg_live_key_123",
            "api_secret": "bg_live_secret_456",
            "passphrase": "bg_live_passphrase_789"
        }
        headers, params = self.adapter._build_auth_headers_and_params(
            method="GET",
            path="/api/v2/spot/account/assets",
            query_params={},
            credentials=creds,
            environment=Environment.LIVE
        )
        self.assertNotIn("paptrading", headers, "'paptrading' header must NOT be sent for Bitget LIVE requests!")
        self.assertEqual(headers.get("Content-Type"), "application/json")
        self.assertEqual(headers.get("ACCESS-KEY"), "bg_live_key_123")
        print("✓ Test 2 Passed: Bitget LIVE requests strictly omit 'paptrading' header")

    # -------------------------------------------------------------------------
    # 3. Credential Whitespace Handling (Sanitization & Signature Accuracy)
    # -------------------------------------------------------------------------
    def test_whitespace_sanitization(self):
        dirty_creds = {
            "api_key": "  bg_key_with_spaces \n ",
            "api_secret": "  bg_secret_with_spaces \t ",
            "passphrase": "  bg_pass_with_spaces \r\n "
        }
        clean_key = "bg_key_with_spaces"
        clean_secret = "bg_secret_with_spaces"
        clean_pass = "bg_pass_with_spaces"

        headers, params = self.adapter._build_auth_headers_and_params(
            method="GET",
            path="/api/v2/spot/account/assets",
            query_params={},
            credentials=dirty_creds,
            environment=Environment.LIVE
        )
        self.assertEqual(headers.get("ACCESS-KEY"), clean_key, "API Key was not stripped of whitespace!")
        self.assertEqual(headers.get("ACCESS-PASSPHRASE"), clean_pass, "Passphrase was not stripped of whitespace!")

        # Verify signature was calculated using the stripped secret
        ts = headers.get("ACCESS-TIMESTAMP")
        expected_payload = f"{ts}GET/api/v2/spot/account/assets"
        expected_digest = hmac.new(clean_secret.encode('utf-8'), expected_payload.encode('utf-8'), hashlib.sha256).digest()
        expected_sig = base64.b64encode(expected_digest).decode('utf-8')
        self.assertEqual(headers.get("ACCESS-SIGN"), expected_sig, "Signature was not computed with stripped secret!")
        print("✓ Test 3 Passed: Whitespace stripped safely; signature verified against stripped secret")

    # -------------------------------------------------------------------------
    # 4. Path & Query String Normalization
    # -------------------------------------------------------------------------
    def test_path_and_query_normalization(self):
        creds = {"api_key": "k", "api_secret": "s", "passphrase": "p"}

        # A. Path without leading slash
        headers_no_slash, _ = self.adapter._build_auth_headers_and_params(
            method="GET",
            path="api/v2/spot/account/assets",  # Missing leading slash
            query_params={},
            credentials=creds
        )
        ts1 = headers_no_slash["ACCESS-TIMESTAMP"]
        expected_payload1 = f"{ts1}GET/api/v2/spot/account/assets"
        expected_sig1 = base64.b64encode(hmac.new(b"s", expected_payload1.encode(), hashlib.sha256).digest()).decode()
        self.assertEqual(headers_no_slash["ACCESS-SIGN"], expected_sig1, "Path without leading slash was not normalized!")

        # B. Canonical query parameter sorting
        params_order1 = {"symbol": "BTCUSDT", "coin": "USDT"}
        params_order2 = {"coin": "USDT", "symbol": "BTCUSDT"}

        with patch("time.time", return_value=1700000000.0):
            h1, _ = self.adapter._build_auth_headers_and_params("GET", "/api/v2/test", params_order1, creds)
            h2, _ = self.adapter._build_auth_headers_and_params("GET", "/api/v2/test", params_order2, creds)

        self.assertEqual(h1["ACCESS-SIGN"], h2["ACCESS-SIGN"], "Query parameter ordering produced different signatures!")
        expected_payload = "1700000000000GET/api/v2/test?coin=USDT&symbol=BTCUSDT"
        expected_sig = base64.b64encode(hmac.new(b"s", expected_payload.encode(), hashlib.sha256).digest()).decode()
        self.assertEqual(h1["ACCESS-SIGN"], expected_sig)
        print("✓ Test 4 Passed: Path normalized to leading slash; query parameters sorted canonically")

    # -------------------------------------------------------------------------
    # 5. Missing / Empty Passphrase Handling
    # -------------------------------------------------------------------------
    def test_missing_passphrase_handling(self):
        creds_no_pass = {"api_key": "k", "api_secret": "s"}
        headers, _ = self.adapter._build_auth_headers_and_params("GET", "/api/v2/test", {}, creds_no_pass)
        self.assertNotIn("ACCESS-PASSPHRASE", headers, "Passphrase header should not be set when missing")

        creds_empty_pass = {"api_key": "k", "api_secret": "s", "passphrase": "   "}
        headers2, _ = self.adapter._build_auth_headers_and_params("GET", "/api/v2/test", {}, creds_empty_pass)
        self.assertNotIn("ACCESS-PASSPHRASE", headers2, "Passphrase header should not be set when empty string")
        print("✓ Test 5 Passed: Missing or empty passphrases handled safely without crashing")

    # -------------------------------------------------------------------------
    # 6. End-to-End API Route Environment Forwarding (Staging Proxy)
    # -------------------------------------------------------------------------
    def test_staging_api_route_environment_forwarding(self):
        client = httpx.Client(verify=False, timeout=10)

        # Test DEMO payload
        demo_payload = {
            "exchange": "BITGET",
            "environment": "DEMO",
            "api_key": "mock_demo_key",
            "api_secret": "mock_demo_secret",
            "passphrase": "mock_demo_pass"
        }
        r_demo = client.post(f"{STAGING_BASE_URL}/connections/test/", json=demo_payload)
        self.assertEqual(r_demo.status_code, 200)
        resp_demo = r_demo.json()
        self.assertEqual(resp_demo.get("environment"), "DEMO", "DEMO environment was not preserved in response!")
        self.assertEqual(resp_demo.get("connection_status"), "AUTHENTICATION_FAILED", "Mock credentials must fail authentication")

        # Test LIVE payload
        live_payload = {
            "exchange": "BITGET",
            "environment": "LIVE",
            "api_key": "mock_live_key",
            "api_secret": "mock_live_secret",
            "passphrase": "mock_live_pass"
        }
        r_live = client.post(f"{STAGING_BASE_URL}/connections/test/", json=live_payload)
        self.assertEqual(r_live.status_code, 200)
        resp_live = r_live.json()
        self.assertEqual(resp_live.get("environment"), "LIVE", "LIVE environment was not preserved in response!")
        print("✓ Test 6 Passed: Staging API route accurately forwards DEMO and LIVE environments")

    # -------------------------------------------------------------------------
    # 7. Mocked Exchange Error Code Handling (40037, 40012, 200 OK)
    # -------------------------------------------------------------------------
    def test_mocked_exchange_error_handling(self):
        import asyncio

        # A. Mock 40037 Apikey does not exist
        mock_resp_40037 = httpx.Response(
            status_code=400,
            json={"code": "40037", "msg": "Apikey does not exist", "requestTime": 1700000000000, "data": None}
        )

        # B. Mock 40012 apikey/password is incorrect
        mock_resp_40012 = httpx.Response(
            status_code=400,
            json={"code": "40012", "msg": "apikey/password is incorrect", "requestTime": 1700000000000, "data": None}
        )

        # C. Mock 200 OK balances list
        mock_resp_200 = httpx.Response(
            status_code=200,
            json={"code": "00000", "msg": "success", "data": [{"coin": "USDT", "available": "150.00"}]}
        )

        def make_side_effect(target_resp):
            async def side_effect(url, **kwargs):
                if "public/time" in url:
                    return httpx.Response(200, json={"code": "00000", "data": {"serverTime": 1700000000000}})
                elif "public/symbols" in url:
                    return httpx.Response(200, json={"code": "00000", "data": [{"symbol": "BTCUSDT"}]})
                elif "market/tickers" in url:
                    return httpx.Response(200, json={"code": "00000", "data": [{"symbol": "BTCUSDT", "lastPr": "65000"}]})
                elif "account/assets" in url:
                    return target_resp
                return httpx.Response(404)
            return side_effect

        async def run_mock_tests():
            creds = {"api_key": "k", "api_secret": "s", "passphrase": "p"}
            with patch("httpx.AsyncClient.get") as mock_get:
                # 40037 check
                mock_get.side_effect = make_side_effect(mock_resp_40037)
                res1 = await self.adapter.run_capability_verification(Environment.DEMO, creds)
                self.assertEqual(res1["status"], "FAIL")
                self.assertEqual(res1["connection_status"], ConnectionStatus.AUTHENTICATION_FAILED.value)
                auth_ep = next(e for e in res1["endpoints"] if e["category"] == "AUTHENTICATION")
                self.assertEqual(auth_ep["status"], "FAIL")
                self.assertIn("Authentication rejected", auth_ep["error"])

                # 40012 check
                mock_get.side_effect = make_side_effect(mock_resp_40012)
                res2 = await self.adapter.run_capability_verification(Environment.LIVE, creds)
                self.assertEqual(res2["status"], "FAIL")
                self.assertEqual(res2["connection_status"], ConnectionStatus.AUTHENTICATION_FAILED.value)

                # 200 OK check
                mock_get.side_effect = make_side_effect(mock_resp_200)
                res3 = await self.adapter.run_capability_verification(Environment.LIVE, creds)
                self.assertEqual(res3["status"], "PASS")
                self.assertEqual(res3["connection_status"], ConnectionStatus.VERIFIED_READ_ONLY.value)
                self.assertIn("BALANCE_QUERY", res3["capabilities"])

        asyncio.run(run_mock_tests())
        print("✓ Test 7 Passed: Mocked Bitget error codes 40037 & 40012 mapped to AUTHENTICATION_FAILED; 200 OK mapped to VERIFIED_READ_ONLY")

    # -------------------------------------------------------------------------
    # 8. Strict Trading Boundaries & Order Submission Blocked (HTTP 403)
    # -------------------------------------------------------------------------
    def test_strict_trading_boundaries_and_order_block(self):
        # 1. Assert configuration flags
        self.assertTrue(settings.live_trading_locked, "live_trading_locked must remain True!")
        self.assertTrue(settings.read_only_mode, "read_only_mode must remain True!")

        # 2. Assert live order submission endpoint returns HTTP 403 Forbidden
        with httpx.Client(timeout=5) as client:
            r = client.post(
                "http://127.0.0.1:8002/api/v1/orders/live/submit",
                json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001}
            )
            self.assertEqual(r.status_code, 403, f"Expected HTTP 403, got {r.status_code}")
        print("✓ Test 8 Passed: Safety hard-locks verified; live order submission rejected with HTTP 403 Forbidden")


if __name__ == "__main__":
    unittest.main()
