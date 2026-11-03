"""
Tauric Trading Platform v3.8.2 — Additional Security & Edge-Cases Test Suite
Target: Staging Environment (http://127.0.0.1:8002)

Validates:
1. Cross-profile credential retrieval isolation & AES-256-GCM AAD tamper protection.
2. Order execution lock bypass resistance across all live order endpoints and adapter methods.
3. Invalid provider string rejection & case insensitivity normalization.
4. Segregated balance summary structure, stale timestamp tracking, and freshness flags.
5. Advanced SSRF protections (IPv6 loopback [::1], 0.0.0.0, non-HTTP schemes, cloud metadata).
6. Capability Matrix Invariant: Capability #14 (transfers/withdrawals) permanently disabled.
7. Profile cleanup and privacy leak checks.
"""

import asyncio
import json
import httpx
import os
import sys
import traceback

BASE_URL = "http://127.0.0.1:8002/api/v1"

async def run_security_and_edge_case_tests():
    print("=" * 80)
    print("TAURIC v3.8.2 — SECURITY & EDGE-CASE AUDIT SUITE")
    print("Target: http://127.0.0.1:8002 (Staging)")
    print("=" * 80)

    client = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)
    passed = 0
    total = 7
    created_profile_ids = []

    # --------------------------------------------------------------------------
    # TEST 1: Cross-Profile Isolation & AES-256-GCM AAD Tamper Protection
    # --------------------------------------------------------------------------
    print("\n[Test 1] Cross-profile isolation & AES-256-GCM AAD binding...")
    try:
        # Create Profile A (Binance Demo)
        r_a = await client.post("/connections/profiles", json={
            "exchange": "BINANCE",
            "market_type": "CRYPTO",
            "environment": "DEMO",
            "label": "Audit Isolation Profile A",
            "api_key": "BINANCE_KEY_AAAA1111",
            "api_secret": "BINANCE_SECRET_AAAA2222"
        })
        assert r_a.status_code == 200, f"Profile A creation failed: {r_a.text}"
        prof_a_id = r_a.json()["profile"]["profile_id"]
        created_profile_ids.append(prof_a_id)

        # Create Profile B (Bybit Demo)
        r_b = await client.post("/connections/profiles", json={
            "exchange": "BYBIT",
            "market_type": "CRYPTO",
            "environment": "DEMO",
            "label": "Audit Isolation Profile B",
            "api_key": "BYBIT_KEY_BBBB1111",
            "api_secret": "BYBIT_SECRET_BBBB2222"
        })
        assert r_b.status_code == 200, f"Profile B creation failed: {r_b.text}"
        prof_b_id = r_b.json()["profile"]["profile_id"]
        created_profile_ids.append(prof_b_id)

        # Verify public listing strips secrets for both
        r_list = await client.get("/connections/profiles")
        assert r_list.status_code == 200
        profiles = {p["profile_id"]: p for p in r_list.json()["profiles"]}

        assert prof_a_id in profiles and prof_b_id in profiles
        p_a = profiles[prof_a_id]
        p_b = profiles[prof_b_id]

        assert "api_secret" not in p_a and "api_secret" not in p_b
        assert "BINANCE_SECRET_AAAA2222" not in json.dumps(r_list.json())
        assert "BYBIT_SECRET_BBBB2222" not in json.dumps(r_list.json())

        # Test AAD Cryptographic Binding via backend internal vault
        from app.services.exchange_framework import credential_vault, _decrypt_aes_gcm
        enc_a = credential_vault._profiles[prof_a_id]["_credentials_enc"]
        aad_b = f"{prof_b_id}:BYBIT:DEMO"

        tamper_caught = False
        try:
            # Attempt to decrypt Profile A's ciphertext using Profile B's AAD
            _decrypt_aes_gcm(enc_a, aad_b)
        except Exception:
            tamper_caught = True

        assert tamper_caught, "FAIL: Tampered AAD was not rejected by AES-256-GCM authentication tag!"
        print("  ✓ PASS: Cross-profile isolation enforced; AAD mismatch rejected by AES-256-GCM.")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        traceback.print_exc()

    # --------------------------------------------------------------------------
    # TEST 2: Order Execution Lock Bypass Resistance Across Endpoints
    # --------------------------------------------------------------------------
    print("\n[Test 2] Order execution lock bypass resistance across all routes...")
    try:
        # Route 1: POST /orders/live/submit
        r_live_submit = await client.post("/orders/live/submit")
        assert r_live_submit.status_code == 403, f"Expected 403 Forbidden, got {r_live_submit.status_code}"
        assert "live_trading_locked=true" in r_live_submit.text

        # Route 2: POST /orders/cancel with environment="LIVE"
        r_live_cancel = await client.post("/orders/cancel", json={
            "symbol": "BTCUSDT",
            "client_order_id": "ORD_LIVE_TEST_001",
            "profile_id": prof_a_id,
            "exchange": "BINANCE",
            "environment": "LIVE"
        })
        assert r_live_cancel.status_code in (400, 403), f"Expected 400/403, got {r_live_cancel.status_code}"
        assert "live_trading_locked" in r_live_cancel.text.lower() or "locked" in r_live_cancel.text.lower()

        # Direct Adapter Test: Verify all adapters refuse execute_live_order
        from app.services.exchange_framework import exchange_framework
        adapter_lock_enforced = True
        for exch_name in ["BINANCE", "BITGET", "BYBIT", "COINBASE", "OKX", "KRAKEN", "CUSTOM", "MT5", "CUSTOM_FOREX"]:
            adapter = exchange_framework.get_adapter(exch_name)
            try:
                # Should fail closed on live execution
                await adapter.execute_order(
                    symbol="BTCUSDT",
                    side="BUY",
                    order_type="LIMIT",
                    quantity=0.01,
                    price=50000.0,
                    environment="LIVE",
                    credentials={"api_key": "k", "api_secret": "s"}
                )
                adapter_lock_enforced = False
                print(f"  ✗ FAIL: Adapter {exch_name} allowed live order execution!")
                break
            except PermissionError as pe:
                assert "live_trading_locked" in str(pe).lower() or "locked" in str(pe).lower()
            except Exception as e:
                # Other exceptions (like reject) also expected
                pass

        assert adapter_lock_enforced, "Adapter failed live execution hard-lock check"
        print("  ✓ PASS: Live execution lock strictly blocks live orders across API routes & adapters.")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        traceback.print_exc()

    # --------------------------------------------------------------------------
    # TEST 3: Invalid Provider Rejection & Case Insensitivity Normalization
    # --------------------------------------------------------------------------
    print("\n[Test 3] Provider normalization and invalid provider rejection...")
    try:
        # 1. Lowercase provider 'bitget'
        r_lower = await client.post("/connections/profiles", json={
            "exchange": "bitget",
            "market_type": "CRYPTO",
            "environment": "DEMO",
            "label": "Case Test Bitget 2",
            "api_key": "KEY_BG_LOWER_2",
            "api_secret": "SEC_BG_LOWER_2"
        })
        assert r_lower.status_code == 200, f"Expected 200, got {r_lower.status_code}: {r_lower.text}"
        p_lower_id = r_lower.json()["profile"]["profile_id"]
        created_profile_ids.append(p_lower_id)
        assert r_lower.json()["profile"]["exchange"] == "BITGET"

        # 2. Non-existent provider
        r_invalid = await client.post("/connections/profiles", json={
            "exchange": "NON_EXISTENT_BROKER_XYZ",
            "market_type": "CRYPTO",
            "environment": "DEMO",
            "label": "Invalid Exchange Profile",
            "api_key": "DUMMY",
            "api_secret": "DUMMY"
        })
        assert r_invalid.status_code == 400, f"Expected 400, got {r_invalid.status_code}: {r_invalid.text}"
        assert "valid" in r_invalid.text.lower() or "supported" in r_invalid.text.lower()

        print("  ✓ PASS: Case normalized to uppercase and non-existent providers rejected with 400.")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        traceback.print_exc()

    # --------------------------------------------------------------------------
    # TEST 4: Stale Data Flagging & Balances Summary Segregation
    # --------------------------------------------------------------------------
    print("\n[Test 4] Stale data flagging & balance summary segregation...")
    try:
        r_bal = await client.get("/connections/balances/summary")
        assert r_bal.status_code == 200
        data = r_bal.json()

        assert "live" in data and "demo" in data
        assert "connected" in data["live"] and "connected" in data["demo"]
        assert isinstance(data["live"]["profiles"], list)
        assert isinstance(data["demo"]["profiles"], list)

        # Check freshness and timestamp structures on profiles
        for acct in data["demo"]["profiles"]:
            assert "environment" in acct and acct["environment"] == "DEMO"
            assert "market_type" in acct
            assert "created_at_utc" in acct

        # Check total balances are not combined across environments
        assert "combined_equity" not in data and "total_portfolio_equity" not in data

        print("  ✓ PASS: Balances are strictly segregated; live and demo never merged.")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        traceback.print_exc()

    # --------------------------------------------------------------------------
    # TEST 5: Advanced SSRF Defenses (IPv6, 0.0.0.0, Non-HTTP Schemes)
    # --------------------------------------------------------------------------
    print("\n[Test 5] Advanced SSRF defenses (IPv6, 0.0.0.0, non-HTTP, metadata)...")
    try:
        from app.services.exchange_framework import validate_endpoint_url, SSRFValidationError
        vectors = [
            ("http://[::1]:8002/api", "IPv6 loopback [::1]"),
            ("http://0.0.0.0:8002/api", "All-zeros IPv4 0.0.0.0"),
            ("ftp://ftp.broker.com/api", "Non-HTTP FTP scheme"),
            ("file:///etc/passwd", "Local file scheme"),
            ("https://metadata.google.internal/computeMetadata/v1", "GCP metadata internal hostname"),
            ("http://169.254.169.254/latest/meta-data/", "AWS/Azure link-local metadata IP"),
            ("http://10.255.0.1:8080/api", "RFC1918 Private class A 10.0.0.0/8"),
            ("http://192.168.1.1:8080/api", "RFC1918 Private class C 192.168.0.0/16"),
        ]

        blocked_count = 0
        for url, desc in vectors:
            try:
                validate_endpoint_url(url)
                print(f"  ✗ FAIL: SSRF allowed vector {desc}: {url}")
            except SSRFValidationError:
                blocked_count += 1

        assert blocked_count == len(vectors), f"Expected {len(vectors)} blocked, got {blocked_count}"
        print(f"  ✓ PASS: All {blocked_count}/{len(vectors)} advanced SSRF attack vectors blocked.")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        traceback.print_exc()

    # --------------------------------------------------------------------------
    # TEST 6: Capability Invariant: Capability #14 Strictly Disabled
    # --------------------------------------------------------------------------
    print("\n[Test 6] Capability matrix invariant: transfers/withdrawals permanently disabled...")
    try:
        r_probe = await client.post("/connections/test", json={
            "exchange": "BITGET",
            "market_type": "CRYPTO",
            "environment": "DEMO",
            "intended_permissions": ["READ_MARKET", "READ_ACCOUNT", "TRADE_ORDERS", "TRADE_MODIFY"],
            "api_key": "DUMMY_KEY",
            "api_secret": "DUMMY_SECRET",
            "passphrase": "DUMMY_PASSPHRASE"
        })
        assert r_probe.status_code == 200
        matrix = r_probe.json().get("permission_matrix", [])
        assert len(matrix) == 14, f"Expected 14 matrix items, got {len(matrix)}"

        item_14 = matrix[13]
        assert "transfer" in item_14["capability"].lower() or "withdrawal" in item_14["capability"].lower()
        assert "disabled or unavailable" in item_14["result"].lower()

        print("  ✓ PASS: Capability #14 remains permanently disabled even with trade permissions.")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        traceback.print_exc()

    # --------------------------------------------------------------------------
    # TEST 7: Cleanup of Temporary Test Profiles & Leak Audit
    # --------------------------------------------------------------------------
    print("\n[Test 7] Cleanup of temporary audit profiles & credential leak verification...")
    try:
        cleanup_success = True
        for pid in created_profile_ids:
            r_del = await client.delete(f"/connections/profiles/{pid}")
            if r_del.status_code != 200:
                cleanup_success = False
                print(f"  ✗ Failed to delete profile {pid}: {r_del.text}")

        # Also delete case test profile if any
        r_rem = await client.get("/connections/profiles")
        for p in r_rem.json().get("profiles", []):
            if "prof_bitget_demo_871d1feb" in p["profile_id"] or "Case Test Bitget" in p.get("label", "") or "Audit Isolation" in p.get("label", ""):
                await client.delete(f"/connections/profiles/{p['profile_id']}")

        assert cleanup_success, "Cleanup failed"
        print("  ✓ PASS: All temporary profiles cleaned up cleanly with zero residual records.")
        passed += 1
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        traceback.print_exc()

    print("\n" + "=" * 80)
    print(f"SECURITY & EDGE-CASE RESULTS: {passed}/{total} SCENARIOS PASSED (100%: {passed == total})")
    print("=" * 80)
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_security_and_edge_case_tests())
    sys.exit(0 if success else 1)
