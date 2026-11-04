"""
BITDEX Phase 2.3.1 Security Remediation Automated Verification Suite
Tests all 10 security remediation targets from the specification:
1. Missing, incorrect, and correct authentication tokens.
2. Missing / weak secret configuration (fail-closed).
3. Secure transport, CORS wildcard elimination, and IP restriction.
4. Strict DEMO-only validation (rejection of REAL, LIVE, CONTEST, and UNKNOWN).
5. Login and server identity mismatch detection.
6. MT5 failure handling (explicit 503, never empty 200).
7. Missing tick data handling in margin calculation.
8. Invalid order type and invalid volume rejection.
9. Empty and unavailable market data error propagation.
10. Absence of order placement or execution endpoints.
"""

import os
import sys
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Ensure project roots are in path
sys.path.insert(0, "/opt/tauric-platform-staging")
sys.path.insert(0, "/opt/tauric-platform-staging/backend")

# Set test environment token
TEST_TOKEN = "a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef"
os.environ["EXNESS_GATEWAY_AUTH_TOKEN"] = TEST_TOKEN
os.environ["STRICT_STARTUP_CHECK"] = "false"
os.environ["ENFORCE_CLIENT_IP"] = "false"

import httpx
from gateway.windows.mt5_gateway_server import app, validate_gateway_token, ConnectRequest, MarginCheckRequest
import gateway.windows.mt5_gateway_server as gw_server
from app.services.exness.mt5_gateway_adapter import ExnessMT5GatewayAdapter


async def run_auth_tests(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("SECTION 1: GATEWAY AUTHENTICATION & HEADER VALIDATION TESTS")
    print("=" * 70)

    # 1.1 Missing token
    print("[TEST 1.1] Missing X-Gateway-Auth-Token")
    r = await client.get("/health")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    assert "Missing X-Gateway-Auth-Token" in r.text
    print(f"✓ PASSED: Missing token returned HTTP 401 ({r.json()['detail']})")

    # 1.2 Incorrect token
    print("\n[TEST 1.2] Incorrect X-Gateway-Auth-Token")
    r = await client.get("/health", headers={"X-Gateway-Auth-Token": "wrong_invalid_token_value_32chars!"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    assert "Invalid X-Gateway-Auth-Token" in r.text
    print(f"✓ PASSED: Incorrect token returned HTTP 401 ({r.json()['detail']})")

    # 1.3 Correct token
    print("\n[TEST 1.3] Correct X-Gateway-Auth-Token")
    r = await client.get("/health", headers={"X-Gateway-Auth-Token": TEST_TOKEN})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert r.json()["status"] == "HEALTHY"
    print(f"✓ PASSED: Correct token authenticated cleanly (status={r.json()['status']})")


def run_secret_configuration_tests():
    print("\n" + "=" * 70)
    print("SECTION 2: FAIL-CLOSED SECRET CONFIGURATION TESTS")
    print("=" * 70)

    # 2.1 None token
    print("[TEST 2.1] Missing secret configuration")
    try:
        validate_gateway_token(None)
        assert False, "Failed to reject None token"
    except RuntimeError as e:
        print(f"✓ PASSED: Correctly failed closed on None token: {e}")

    # 2.2 Short token (< 32 chars)
    print("\n[TEST 2.2] Short secret (< 32 characters)")
    try:
        validate_gateway_token("short_secret_123")
        assert False, "Failed to reject short token"
    except RuntimeError as e:
        print(f"✓ PASSED: Correctly failed closed on short token: {e}")

    # 2.3 Known weak / default secret
    print("\n[TEST 2.3] Known default secret rejection")
    try:
        validate_gateway_token("bitdex_mt5_gateway_secure_ipc_token_2026")
        assert False, "Failed to reject known default token"
    except RuntimeError as e:
        print(f"✓ PASSED: Correctly failed closed on known default token: {e}")

    # 2.4 Strong secret passes
    valid = validate_gateway_token(TEST_TOKEN)
    assert valid == TEST_TOKEN
    print("✓ PASSED: Strong 64-char token validated successfully.")


async def run_transport_and_cors_tests(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("SECTION 3: SECURE TRANSPORT & CORS RESTRICTION TESTS")
    print("=" * 70)

    # 3.1 Wildcard CORS Elimination
    print("[TEST 3.1] Verifying wildcard CORS is removed")
    from gateway.windows.mt5_gateway_server import ALLOWED_ORIGINS
    assert "*" not in ALLOWED_ORIGINS, "Wildcard CORS origin found!"
    print(f"✓ PASSED: Wildcard CORS eliminated. Configured origins: {ALLOWED_ORIGINS}")

    # 3.2 IP Allowlist Enforcement
    print("\n[TEST 3.2] Unauthorized client IP rejection")
    os.environ["ENFORCE_CLIENT_IP"] = "true"
    try:
        # Simulate unauthorized IP (e.g. 203.0.113.50)
        unauth_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("203.0.113.50", 12345)),
            base_url="http://test",
            headers={"X-Gateway-Auth-Token": TEST_TOKEN},
        )
        r = await unauth_client.get("/health")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        assert "Access forbidden" in r.text
        print(f"✓ PASSED: Unauthorized client IP blocked with HTTP 403 ({r.json()['detail']})")
    finally:
        os.environ["ENFORCE_CLIENT_IP"] = "false"


async def run_demo_account_validation_tests(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("SECTION 4: STRICT DEMO-ONLY ACCOUNT VALIDATION & IDENTITY TESTS")
    print("=" * 70)

    headers = {"X-Gateway-Auth-Token": TEST_TOKEN}

    # 4.1 Rejection of expected_account_type != "DEMO"
    print("[TEST 4.1] Request with expected_account_type='REAL'")
    r = await client.post(
        "/connect",
        headers=headers,
        json={"login": "149827361", "password": "SecretPassword123!", "server": "Exness-MT5Trial", "expected_account_type": "REAL"},
    )
    assert r.status_code == 422, f"Expected 422 for non-DEMO expected_account_type, got {r.status_code}"
    print("✓ PASSED: Request rejected: Only DEMO expected_account_type accepted.")

    # Mock MT5 functions for testing broker account states
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True

    with patch.object(gw_server, "MT5_AVAILABLE", True), patch.object(gw_server, "mt5", mock_mt5):
        # 4.2 trade_mode = 2 (REAL)
        print("\n[TEST 4.2] Broker returns trade_mode=2 (REAL account)")
        mock_acct = MagicMock()
        mock_acct.login = 149827361
        mock_acct.server = "Exness-MT5Trial"
        mock_acct.trade_mode = 2  # ACCOUNT_TRADE_MODE_REAL
        mock_mt5.account_info.return_value = mock_acct

        r = await client.post(
            "/connect",
            headers=headers,
            json={"login": "149827361", "password": "SecretPassword123!", "server": "Exness-MT5Trial", "expected_account_type": "DEMO"},
        )
        assert r.status_code == 403, f"Expected 403 for REAL account, got {r.status_code}"
        assert "CRITICAL REJECTION: Account type 'REAL' is strictly prohibited" in r.text
        print(f"✓ PASSED: Real account rejected with HTTP 403: {r.json()['detail']}")

        # 4.3 trade_mode = 1 (CONTEST)
        print("\n[TEST 4.3] Broker returns trade_mode=1 (CONTEST account)")
        mock_acct.trade_mode = 1  # ACCOUNT_TRADE_MODE_CONTEST
        r = await client.post(
            "/connect",
            headers=headers,
            json={"login": "149827361", "password": "SecretPassword123!", "server": "Exness-MT5Trial", "expected_account_type": "DEMO"},
        )
        assert r.status_code == 403, f"Expected 403 for CONTEST account, got {r.status_code}"
        assert "CRITICAL REJECTION: Account type 'CONTEST' is strictly prohibited" in r.text
        print(f"✓ PASSED: Contest account rejected with HTTP 403: {r.json()['detail']}")

        # 4.4 trade_mode = 3 (UNKNOWN)
        print("\n[TEST 4.4] Broker returns trade_mode=3 (UNKNOWN account)")
        mock_acct.trade_mode = 3
        r = await client.post(
            "/connect",
            headers=headers,
            json={"login": "149827361", "password": "SecretPassword123!", "server": "Exness-MT5Trial", "expected_account_type": "DEMO"},
        )
        assert r.status_code == 403
        print(f"✓ PASSED: Unknown mode rejected with HTTP 403: {r.json()['detail']}")

        # 4.5 Login mismatch detection
        print("\n[TEST 4.5] Account login mismatch post-auth")
        mock_acct.trade_mode = 0  # DEMO
        mock_acct.login = 999999999  # Broker has 999999999, requested 149827361
        r = await client.post(
            "/connect",
            headers=headers,
            json={"login": "149827361", "password": "SecretPassword123!", "server": "Exness-MT5Trial", "expected_account_type": "DEMO"},
        )
        assert r.status_code == 401
        assert "Account login mismatch" in r.text
        print(f"✓ PASSED: Login mismatch rejected with HTTP 401: {r.json()['detail']}")

        # 4.6 Server mismatch detection
        print("\n[TEST 4.6] Server name mismatch post-auth")
        mock_acct.login = 149827361
        mock_acct.server = "Exness-WrongServer"
        r = await client.post(
            "/connect",
            headers=headers,
            json={"login": "149827361", "password": "SecretPassword123!", "server": "Exness-MT5Trial", "expected_account_type": "DEMO"},
        )
        assert r.status_code == 401
        assert "Server name mismatch" in r.text
        print(f"✓ PASSED: Server mismatch rejected with HTTP 401: {r.json()['detail']}")

        # 4.7 Clean DEMO connection (trade_mode = 0)
        print("\n[TEST 4.7] Verified DEMO account connection (trade_mode=0)")
        mock_acct.server = "Exness-MT5Trial"
        mock_acct.currency = "USD"
        mock_acct.balance = 5000.0
        mock_acct.equity = 5000.0
        mock_acct.leverage = 2000

        r = await client.post(
            "/connect",
            headers=headers,
            json={"login": "149827361", "password": "SecretPassword123!", "server": "Exness-MT5Trial", "expected_account_type": "DEMO"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "CONNECTED"
        assert data["is_demo"] is True
        assert data["account_type"] == "DEMO"
        print("✓ PASSED: Clean DEMO account connection established.")


async def run_mt5_failure_and_empty_data_tests(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("SECTION 5: MT5 FAILURE & EMPTY DATA PROPAGATION TESTS")
    print("=" * 70)

    headers = {"X-Gateway-Auth-Token": TEST_TOKEN}

    # When MT5 is unavailable, all data queries must fail with 503, NEVER empty 200
    with patch.object(gw_server, "MT5_AVAILABLE", False):
        endpoints = [
            ("GET", "/account"),
            ("GET", "/symbols"),
            ("GET", "/symbol/XAUUSDm"),
            ("GET", "/tick/XAUUSDm"),
            ("GET", "/candles/XAUUSDm"),
            ("GET", "/positions"),
            ("GET", "/orders/history"),
            ("GET", "/trades/history"),
            ("POST", "/margin/calculate", {"symbol": "XAUUSDm", "order_type": "BUY", "volume": 0.01}),
            ("POST", "/reconcile", {"account_id": "149827361", "local_positions": []}),
        ]

        for method, path, *body in endpoints:
            if method == "GET":
                r = await client.get(path, headers=headers)
            else:
                r = await client.post(path, headers=headers, json=body[0] if body else {})
            assert r.status_code == 503, f"{method} {path} expected 503 when MT5 unavailable, got {r.status_code}"
            print(f"✓ PASSED: {method} {path} returned HTTP 503 (no fabricated empty response)")


async def run_margin_validation_tests(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("SECTION 6: MARGIN CALCULATION VALIDATION & MISSING TICK TESTS")
    print("=" * 70)

    headers = {"X-Gateway-Auth-Token": TEST_TOKEN}

    # 6.1 Invalid order type (e.g. LIMIT or FOO)
    print("[TEST 6.1] Invalid order_type rejection")
    r = await client.post(
        "/margin/calculate",
        headers=headers,
        json={"symbol": "XAUUSDm", "order_type": "LIMIT", "volume": 0.01},
    )
    assert r.status_code == 422, f"Expected 422 for LIMIT order_type, got {r.status_code}"
    print(f"✓ PASSED: Invalid order_type rejected with HTTP 422 ({r.json()['detail'][0]['msg']})")

    # 6.2 Invalid volume (zero or negative)
    print("\n[TEST 6.2] Non-positive volume rejection")
    r = await client.post(
        "/margin/calculate",
        headers=headers,
        json={"symbol": "XAUUSDm", "order_type": "BUY", "volume": 0.0},
    )
    assert r.status_code == 422, f"Expected 422 for volume=0.0, got {r.status_code}"
    print(f"✓ PASSED: Zero volume rejected with HTTP 422 ({r.json()['detail'][0]['msg']})")

    # 6.3 Missing tick data handling (never calculate with 0.0)
    mock_mt5 = MagicMock()
    mock_mt5.terminal_info.return_value = MagicMock(connected=True, build=4450)

    # Symbol info mock
    mock_sym = MagicMock()
    mock_sym.name = "XAUUSDm"
    mock_sym.visible = True
    mock_sym.trade_mode = 4  # FULL
    mock_sym.volume_min = 0.01
    mock_sym.volume_max = 20.0
    mock_mt5.symbol_info.return_value = mock_sym

    # Tick is None or non-positive
    mock_mt5.symbol_info_tick.return_value = None

    with patch.object(gw_server, "MT5_AVAILABLE", True), patch.object(gw_server, "mt5", mock_mt5):
        print("\n[TEST 6.3] Missing tick quote rejection")
        r = await client.post(
            "/margin/calculate",
            headers=headers,
            json={"symbol": "XAUUSDm", "order_type": "BUY", "volume": 0.01},
        )
        assert r.status_code == 503, f"Expected 503 for missing tick, got {r.status_code}"
        assert "Live tick quote unavailable" in r.text
        print(f"✓ PASSED: Missing tick rejected with HTTP 503: {r.json()['detail']}")

        # Tick with non-positive price (e.g. ask <= 0)
        print("\n[TEST 6.4] Non-positive price rejection")
        mock_tick = MagicMock()
        mock_tick.ask = 0.0
        mock_tick.bid = 0.0
        mock_mt5.symbol_info_tick.return_value = mock_tick
        r = await client.post(
            "/margin/calculate",
            headers=headers,
            json={"symbol": "XAUUSDm", "order_type": "BUY", "volume": 0.01},
        )
        assert r.status_code == 503
        assert "Non-positive quote price" in r.text
        print(f"✓ PASSED: Non-positive price rejected with HTTP 503: {r.json()['detail']}")


async def run_execution_endpoints_invariant_tests(client: httpx.AsyncClient):
    print("\n" + "=" * 70)
    print("SECTION 7: ZERO ORDER EXECUTION ENDPOINTS INVARIANT")
    print("=" * 70)

    headers = {"X-Gateway-Auth-Token": TEST_TOKEN}

    # Verify no execution endpoints exist on gateway
    forbidden_endpoints = [
        ("POST", "/orders"),
        ("POST", "/order"),
        ("POST", "/trade"),
        ("PUT", "/orders"),
        ("DELETE", "/positions"),
        ("POST", "/positions/close"),
    ]

    for method, path in forbidden_endpoints:
        if method == "POST":
            r = await client.post(path, headers=headers, json={})
        elif method == "PUT":
            r = await client.put(path, headers=headers, json={})
        elif method == "DELETE":
            r = await client.delete(path, headers=headers)
        assert r.status_code in (404, 405), f"Found unauthorized endpoint {method} {path} with status {r.status_code}"
        print(f"✓ PASSED: {method} {path} correctly does not exist (HTTP {r.status_code})")


async def run_adapter_token_strength_tests():
    print("\n" + "=" * 70)
    print("SECTION 8: EXNESS ADAPTER TOKEN ENFORCEMENT & CONTEST REJECTION")
    print("=" * 70)

    # 8.1 Weak token on adapter connect
    adapter_weak = ExnessMT5GatewayAdapter(
        account_id="149827361",
        server="Exness-MT5Trial",
        auth_token="short_weak_token",
    )
    try:
        await adapter_weak.connect("Pass123!")
        assert False, "Failed to fail on weak token"
    except RuntimeError as e:
        print(f"✓ PASSED: Adapter failed closed on weak token: {e}")

    # 8.2 Adapter strictly rejects CONTEST account type
    orig_client = httpx.AsyncClient

    class MockContestResponse:
        status_code = 200
        def json(self):
            return {
                "status": "CONNECTED",
                "account_id": "149827361",
                "server": "Exness-MT5Trial",
                "account_type": "CONTEST",  # CONTEST MUST BE REJECTED!
                "broker_authenticated": True,
                "terminal_connected": True,
            }

    class MockContestClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return MockContestResponse()

    httpx.AsyncClient = MockContestClient
    adapter_contest = ExnessMT5GatewayAdapter(
        account_id="149827361",
        server="Exness-MT5Trial",
        auth_token=TEST_TOKEN,
    )
    try:
        await adapter_contest.connect("Pass123!")
        assert False, "Failed to reject CONTEST account in adapter!"
    except PermissionError as e:
        print(f"✓ PASSED: Adapter strictly rejected CONTEST account type: {e}")
    finally:
        httpx.AsyncClient = orig_client


async def main():
    print("=" * 70)
    print("STARTING BITDEX PHASE 2.3.1 SECURITY REMEDIATION VERIFICATION")
    print("=" * 70)

    # Use ASGITransport to test app directly in-memory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
        base_url="http://test",
    ) as client:
        await run_auth_tests(client)
        run_secret_configuration_tests()
        await run_transport_and_cors_tests(client)
        await run_demo_account_validation_tests(client)
        await run_mt5_failure_and_empty_data_tests(client)
        await run_margin_validation_tests(client)
        await run_execution_endpoints_invariant_tests(client)
        await run_adapter_token_strength_tests()

    print("\n" + "=" * 70)
    print("ALL PHASE 2.3.1 SECURITY REMEDIATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
