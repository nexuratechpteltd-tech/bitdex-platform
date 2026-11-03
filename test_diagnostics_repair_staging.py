#!/usr/bin/env python3
"""
TAURIC Staging Acceptance & Verification Suite
Tests the 6 repair areas:
1. Macroeconomic Event Calendar UX & API freshness
2. Bitget Authentication Diagnostics & Error Mapping
3. 7 Evidence-Based Capability & Permission States (No Unknown/Not tested)
4. Strategy Compatibility Meter with Granular Rationale & Decoupled Balance Logic
5. Decoupled Open Orders & Status Without Balances
6. Disconnect API (Full deletion) & ON/OFF Toggle
7. Failsafe Locks (live_trading_locked=True, HTTP 403 on live order submit)
"""

import asyncio
import json
import httpx
import sys
import os

sys.path.insert(0, "/opt/tauric-platform-staging/backend")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_URL = "http://127.0.0.1:8002/api/v1"

async def run_tests():
    results = {}
    print("=" * 70)
    print("STARTING TAURIC STAGING VERIFICATION SUITE")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # ─────────────────────────────────────────────────────────────────
        # TEST 1: Health & Safety Lock Invariants
        # ─────────────────────────────────────────────────────────────────
        print("\n[TEST 1] Verifying System Health & Safety Locks...")
        r_health = await client.get(f"{BASE_URL}/health")
        assert r_health.status_code == 200, f"Health check failed: {r_health.status_code}"
        health_data = r_health.json()
        print(f"  Health: {health_data.get('status')}")

        # Check live trading lock endpoint
        r_live = await client.post(f"{BASE_URL}/orders/live/submit", json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.01})
        print(f"  Live Submit Status: HTTP {r_live.status_code}")
        assert r_live.status_code == 403, f"CRITICAL: Live order submit did not return 403! Got {r_live.status_code}"
        results["safety_locks"] = "PASS: live submission blocked with HTTP 403"

        # ─────────────────────────────────────────────────────────────────
        # TEST 2: Macroeconomic Calendar API
        # ─────────────────────────────────────────────────────────────────
        print("\n[TEST 2] Verifying Macroeconomic Calendar API & Freshness...")
        r_cal = await client.get(f"{BASE_URL}/signals/calendar")
        print(f"  Calendar Status: HTTP {r_cal.status_code}")
        assert r_cal.status_code == 200, f"Calendar endpoint returned {r_cal.status_code}"
        cal_data = r_cal.json()
        cal_summary = cal_data.get("calendar", {})
        events = cal_summary.get("events", [])
        status_flag = cal_summary.get("status")
        is_stale = cal_summary.get("is_stale")
        time_window = cal_summary.get("time_window_covered")
        print(f"  Status: {status_flag}, Stale: {is_stale}, Events Count: {len(events)}, Horizon: {time_window}")
        assert len(events) > 0, "No macroeconomic events returned!"
        assert "currency" in events[0] or "country" in events[0], "Malformed event object"
        results["calendar_api"] = f"PASS: {len(events)} events returned, status={status_flag}, horizon={time_window}"

        # ─────────────────────────────────────────────────────────────────
        # TEST 3: Bitget Error Classification & Custom Config Sanitization
        # ─────────────────────────────────────────────────────────────────
        print("\n[TEST 3] Verifying Bitget Error Classification & Sanitization...")
        from app.services.exchange_framework import (
            exchange_framework,
            credential_vault,
            classify_exchange_error,
            CapabilityState,
            get_capability_state_label,
            evaluate_strategy_compatibility,
            STRATEGY_CAPABILITY_REQUIREMENTS,
        )

        # Test error code classifications
        cls_40099, c_val, msg_val, expl_40099 = classify_exchange_error("BITGET", 400, json.dumps({"code": "40099", "msg": "exchange environment is incorrect"}))
        print(f"  40099 Error Classification: {expl_40099}")
        assert "Environment / product mismatch" in expl_40099
        assert "Bitget Demo keys require USDT-M Futures endpoints" in expl_40099

        cls_40037, _, _, expl_40037 = classify_exchange_error("BITGET", 400, json.dumps({"code": "40037", "msg": "apikey does not exist"}))
        print(f"  40037 Error Classification: {expl_40037}")
        assert "API Key not recognized by Bitget" in expl_40037

        cls_pass, _, _, expl_pass = classify_exchange_error("BITGET", 400, json.dumps({"code": "40012", "msg": "password is incorrect"}))
        print(f"  40012 Error Classification: {expl_pass}")
        assert "API Passphrase or signature incorrect" in expl_pass

        cls_clock, _, _, expl_clock = classify_exchange_error("BITGET", 400, json.dumps({"code": "40005", "msg": "request timestamp expired"}))
        print(f"  40005 Error Classification: {expl_clock}")
        assert "Server clock skew" in expl_clock

        cls_ip, _, _, expl_ip = classify_exchange_error("BITGET", 400, json.dumps({"code": "40017", "msg": "ip is not in the whitelist"}))
        print(f"  40017 Error Classification: {expl_ip}")
        assert "IP restriction" in expl_ip

        # Test custom_config sanitization in get_adapter
        contaminated_cfg = {
            "product_type": "FUTURES_USDT",
            "balance_path": "/api/v2/spot/account/assets",
            "account_info_path": "/api/v2/spot/account/info"
        }
        sanitized_adapter = exchange_framework.get_adapter("BITGET", custom_config=contaminated_cfg)
        print(f"  Sanitized Bitget Futures Balance Path: {sanitized_adapter.config.get('balance_path')}")
        assert "/mix/" in sanitized_adapter.config.get("balance_path"), "Spot path was not sanitized away from Futures!"
        results["bitget_diagnostics"] = "PASS: error mapping accurate and futures paths protected from spot contamination"

        # ─────────────────────────────────────────────────────────────────
        # TEST 4: Capability & Permission Matrix (Evidence-Based 7 States)
        # ─────────────────────────────────────────────────────────────────
        print("\n[TEST 4] Verifying 7 Evidence-Based Capability States...")
        profiles = credential_vault.list_profiles()
        print(f"  Total Profiles in Vault: {len(profiles)}")
        assert len(profiles) > 0, "No profiles found in vault"

        # Test live connection verification endpoint for permission_matrix output
        test_prof = profiles[0]
        pid = test_prof.get("profile_id")
        r_conn_test = await client.post(f"{BASE_URL}/connections/test", json={"profile_id": pid})
        assert r_conn_test.status_code == 200, f"Connection test failed: {r_conn_test.status_code}"
        test_res = r_conn_test.json()
        matrix = test_res.get("permission_matrix") or []
        print(f"  Profile {pid} ({test_res.get('exchange')}): {len(matrix)} capability rows verified")
        assert len(matrix) >= 14, f"Expected at least 14 capability rows, got {len(matrix)}"

        valid_7_states = [
            "Supported and verified",
            "Supported but not yet tested",
            "Permission missing or denied",
            "Authentication failed",
            "Unsupported by provider/product",
            "Temporarily unavailable",
            "Requires additional configuration",
        ]

        for row in matrix:
            state_label = row.get("result") or get_capability_state_label(row.get("state"))
            assert state_label in valid_7_states, f"Invalid state found in matrix: '{state_label}'"
            assert "Unknown" not in state_label, f"Forbidden 'Unknown' in state: {state_label}"
            assert "Not tested" != state_label, f"Forbidden 'Not tested' in state: {state_label}"
            assert "capability" in row, "Missing capability name"
            assert "detail" in row, "Missing detail"

        results["capability_matrix"] = f"PASS: all {len(matrix)} capabilities mapped to 7 evidence-based states; zero unknown/untested"

        # ─────────────────────────────────────────────────────────────────
        # TEST 5: Strategy Compatibility Meter (Decoupled Balance Logic)
        # ─────────────────────────────────────────────────────────────────
        print("\n[TEST 5] Verifying Strategy Compatibility Auditing...")
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Compatible Spot Profile
        mock_profile = {
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": now_iso,
            "capability_matrix": [
                {"capability_id": "MARKET_TICKER", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_SYMBOLS", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_CANDLES", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "ACCOUNT_AUTH", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "WALLET_BALANCES", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "OPEN_ORDERS_READ", "state": "VERIFIED_SUPPORTED"},
            ]
        }
        compat = evaluate_strategy_compatibility(mock_profile, "SPOT_GRID")
        spot_eval = compat.get("strategies", {}).get("SPOT_GRID", {})
        print(f"  SPOT_GRID compatibility status: {spot_eval.get('status')}")
        assert spot_eval.get("status") == "COMPATIBLE", f"Expected COMPATIBLE, got {spot_eval.get('status')}"
        assert len(spot_eval.get("missing_prerequisites", [])) == 0
        assert len(spot_eval.get("required_capabilities", [])) == 6

        # Incompatible product test: Futures grid on Spot profile
        futures_eval = evaluate_strategy_compatibility(mock_profile, "FUTURES_GRID").get("strategies", {}).get("FUTURES_GRID", {})
        print(f"  FUTURES_GRID status on Spot profile: {futures_eval.get('status')} - Reasons: {futures_eval.get('reasons')}")
        assert futures_eval.get("status") == "INCOMPATIBLE"
        assert "Product category mismatch" in futures_eval.get("reasons", [""])[0]

        # Missing capability test: Wallet balance missing on SPOT_GRID
        unauth_profile = {
            "market_type": "CRYPTO",
            "product_type": "SPOT",
            "last_tested_utc": now_iso,
            "capability_matrix": [
                {"capability_id": "MARKET_TICKER", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_SYMBOLS", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "MARKET_CANDLES", "state": "VERIFIED_SUPPORTED"},
                {"capability_id": "WALLET_BALANCES", "state": "PERMISSION_DENIED", "evidence": "API Key read balance denied"},
            ]
        }
        unauth_eval = evaluate_strategy_compatibility(unauth_profile, "SPOT_GRID").get("strategies", {}).get("SPOT_GRID", {})
        print(f"  Unauthenticated status: {unauth_eval.get('status')} - Reasons: {unauth_eval.get('reasons')}")
        assert unauth_eval.get("status") == "INCOMPATIBLE"
        assert "WALLET_BALANCES is PERMISSION_DENIED" in unauth_eval.get("reasons", [""])[0]
        results["strategy_compatibility"] = "PASS: strategy compatibility evaluates products, mandatory/denied capabilities, and granular reasons"

        # ─────────────────────────────────────────────────────────────────
        # TEST 6: Decoupled Open Orders Route (/orders/open)
        # ─────────────────────────────────────────────────────────────────
        print("\n[TEST 6] Verifying Decoupled Open Orders Endpoint...")
        r_orders = await client.get(f"{BASE_URL}/orders/open?environment=ALL")
        print(f"  Open Orders Status: HTTP {r_orders.status_code}")
        assert r_orders.status_code == 200, f"Open orders returned {r_orders.status_code}"
        orders_data = r_orders.json()
        print(f"  Balance Status: {orders_data.get('balance_status')}")
        print(f"  Orders Count: {orders_data.get('count')}")
        assert "orders" in orders_data
        assert "balance_status" in orders_data
        results["decoupled_orders"] = f"PASS: orders retrieved decoupled from balance; balance_status={orders_data.get('balance_status')}"

        # ─────────────────────────────────────────────────────────────────
        # TEST 7: Disconnect API & ON/OFF Toggle
        # ─────────────────────────────────────────────────────────────────
        print("\n[TEST 7] Verifying Disconnect API & ON/OFF Toggle...")
        # Create a disposable test profile
        saved_prof = credential_vault.save_profile(
            exchange="BINANCE",
            label="Disposable Test Key",
            api_key="mock_test_key_abc123",
            api_secret="mock_test_secret_xyz789",
            environment="DEMO",
            custom_config={"product_type": "SPOT"}
        )
        test_prof_id = saved_prof["profile_id"] if isinstance(saved_prof, dict) else saved_prof
        print(f"  Created test profile: {test_prof_id}")
        assert credential_vault.get_profile_public(test_prof_id) is not None

        # Toggle Active OFF
        r_toggle_off = await client.post(f"{BASE_URL}/connections/profiles/{test_prof_id}/toggle-active", json={"is_active": False})
        assert r_toggle_off.status_code == 200
        p_off = credential_vault.get_profile_public(test_prof_id)
        assert p_off.get("is_active") is False, "Profile was not toggled off!"
        print(f"  Profile toggled off: is_active={p_off.get('is_active')}")

        # Toggle Active ON
        r_toggle_on = await client.post(f"{BASE_URL}/connections/profiles/{test_prof_id}/toggle-active", json={"is_active": True})
        assert r_toggle_on.status_code == 200
        p_on = credential_vault.get_profile_public(test_prof_id)
        assert p_on.get("is_active") is True, "Profile was not toggled on!"
        print(f"  Profile toggled on: is_active={p_on.get('is_active')}")

        # Disconnect (Full deletion)
        r_del = await client.delete(f"{BASE_URL}/connections/profiles/{test_prof_id}")
        assert r_del.status_code == 200
        assert credential_vault.get_profile_public(test_prof_id) is None, "Profile was not deleted upon disconnect!"
        print(f"  Profile {test_prof_id} permanently disconnected and deleted from vault.")
        results["disconnect_and_toggle"] = "PASS: toggle active on/off functional and disconnect deletes profile from vault"

    print("\n" + "=" * 70)
    print("ALL 7 VERIFICATION DOMAINS PASSED SUCCESSFULLY")
    print("=" * 70)
    for k, v in results.items():
        print(f"  - {k}: {v}")

    return results

if __name__ == "__main__":
    asyncio.run(run_tests())
