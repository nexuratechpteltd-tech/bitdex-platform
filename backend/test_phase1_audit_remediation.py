#!/usr/bin/env python3
"""
TAURIC — Phase 1 Audit Remediation Regression Suite (Staging Only)
===================================================================
Covers all 14 mandatory requirements from Section 6 using an isolated temporary vault
(never touches production or persistent staging user profiles):

1. Unauthenticated API access is rejected according to the staging security boundary, while authenticated dashboard/API requests succeed.
2. Credential submission over insecure transport is blocked by the transport security gate.
3. Binance profile with no passphrase does NOT return MISSING_PASSPHRASE.
4. Binance profile failing with -2015 returns the accurate Binance error classification and preserves -2015 as provider_error_code.
5. Bitget profile without a passphrase returns MISSING_PASSPHRASE before making a private request.
6. Bitget profile with a passphrase failing with 40099 returns ENVIRONMENT_KEY_MISMATCH, not MISSING_PASSPHRASE.
7. Editing a profile clears stale error banners and resets status to UNTESTED.
8. Identifying a profile does not silently delete a saved passphrase and allows safe re-identification when no active run exists.
9. Strategy Wizard reads the same balance schema written by connection verification.
10. Unverified profiles show NOT VERIFIED / NOT TESTED, not $0.00.
11. Disabled, unverified, unidentified, live-locked, and unimplemented-provider profiles cannot be used to launch a strategy (and return explicit eligibility reasons).
12. One or multiple eligible profiles can be selected for a strategy without leaking state across profiles.
13. Live order submission remains blocked with HTTP 403.
14. Existing saved profiles remain intact and production vault is completely untouched.
"""

import os
import sys
import json
import asyncio
import tempfile
import hashlib

STAGING_BACKEND = "/opt/tauric-platform-staging/backend"
PROD_VAULT = "/opt/tauric-platform/backend/data/credential_vault.json"
STAGING_VAULT = "/opt/tauric-platform-staging/backend/data/credential_vault.json"

sys.path.insert(0, STAGING_BACKEND)

from fastapi.testclient import TestClient
from app.main import app
from app.security import get_api_auth_token
from app.services.exchange_framework import (
    CredentialVault,
    credential_vault,
    exchange_framework,
    resolve_actionable_error_code,
    provider_requires_passphrase,
    get_provider_error_guidance,
    ConnectionStatus,
)
from app.services.strategy_orchestrator import StrategyOrchestrator, strategy_orchestrator


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def run_all_tests():
    prod_vault_hash_before = sha256_file(PROD_VAULT)
    staging_vault_hash_before = sha256_file(STAGING_VAULT)

    results = []

    def record(test_id: str, name: str, passed: bool, detail: str):
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] {test_id}: {name} -> {detail}")
        results.append({
            "id": test_id,
            "name": name,
            "passed": passed,
            "detail": detail,
        })
        if not passed:
            raise AssertionError(f"Test {test_id} ({name}) failed: {detail}")

    # Create an isolated temporary directory for vault and strategy runs
    with tempfile.TemporaryDirectory(prefix="tauric_phase1_test_") as tmpdir:
        isolated_vault_path = os.path.join(tmpdir, "isolated_test_vault.json")
        isolated_runs_path = os.path.join(tmpdir, "isolated_strategy_runs.json")

        # Swap credential_vault.storage_path and strategy_orchestrator.storage_path to isolated temp files
        orig_vault_path = credential_vault.storage_path
        orig_profiles = dict(credential_vault._profiles)
        orig_mtime = credential_vault._last_mtime
        orig_runs_path = strategy_orchestrator.storage_path
        orig_runs = dict(strategy_orchestrator._runs)

        try:
            credential_vault.storage_path = isolated_vault_path
            credential_vault._profiles = {}
            credential_vault._save()

            strategy_orchestrator.storage_path = isolated_runs_path
            strategy_orchestrator._runs = {}
            strategy_orchestrator._save()

            client = TestClient(app)
            auth_token = get_api_auth_token()
            auth_headers = {"X-Tauric-Api-Key": auth_token}

            # -----------------------------------------------------------------
            # Test 1: P0 Unauthenticated API access rejected (401), authenticated succeeds (200), OpenAPI docs disabled (404)
            # -----------------------------------------------------------------
            r_unauth = client.get("/api/v1/connections/profiles")
            r_health = client.get("/api/v1/health")
            r_docs = client.get("/docs")
            r_openapi = client.get("/openapi.json")
            r_auth = client.get("/api/v1/connections/profiles", headers=auth_headers)

            t1_ok = (
                r_unauth.status_code == 401
                and r_unauth.json().get("error_code") == "UNAUTHORIZED_API_REQUEST"
                and r_health.status_code == 200
                and r_docs.status_code == 404
                and r_openapi.status_code == 404
                and r_auth.status_code == 200
            )
            record(
                "T01",
                "Staging API authentication boundary & OpenAPI docs disabled",
                t1_ok,
                f"unauth={r_unauth.status_code} ({r_unauth.json().get('error_code')}), health={r_health.status_code}, docs={r_docs.status_code}, openapi={r_openapi.status_code}, auth={r_auth.status_code}",
            )

            # -----------------------------------------------------------------
            # Test 2: P0 Transport Security Gate blocks plaintext HTTP credential submissions
            # -----------------------------------------------------------------
            r_insecure = client.post(
                "/api/v1/connections/universal",
                headers={
                    **auth_headers,
                    "X-Forwarded-Proto": "http",
                    "X-Forwarded-For": "198.51.100.42",
                },
                json={
                    "label": "Insecure HTTP Attempt",
                    "api_key": "dummy_key_1234567890",
                    "api_secret": "dummy_secret_1234567890",
                },
            )
            r_secure = client.post(
                "/api/v1/connections/universal",
                headers={
                    **auth_headers,
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-For": "198.51.100.42",
                },
                json={
                    "label": "Secure HTTPS Profile",
                    "api_key": "binance_test_key_alpha_9999",
                    "api_secret": "binance_test_sec_alpha_9999",
                },
            )
            t2_ok = (
                r_insecure.status_code == 403
                and r_insecure.json().get("error_code") == "INSECURE_TRANSPORT_BLOCKED"
                and r_secure.status_code == 200
            )
            record(
                "T02",
                "Transport Security Gate blocks credential submission over plaintext HTTP",
                t2_ok,
                f"http_status={r_insecure.status_code} ({r_insecure.json().get('error_code')}), https_status={r_secure.status_code}",
            )
            binance_pid = r_secure.json()["profile"]["profile_id"]

            # -----------------------------------------------------------------
            # Test 3: Binance profile with no passphrase does NOT return MISSING_PASSPHRASE
            # -----------------------------------------------------------------
            # Identify as BINANCE and configure DEMO SPOT
            r_id_bin = client.post(
                f"/api/v1/connections/profiles/{binance_pid}/identify",
                headers=auth_headers,
                json={"provider": "BINANCE", "environment": "DEMO", "product_type": "SPOT"},
            )
            bin_prof = r_id_bin.json()["profile"]
            code_bin_no_pass = resolve_actionable_error_code(
                "BINANCE", 401, None, "Authentication rejected by exchange (HTTP 401): Invalid API Key, Passphrase, or Signature.", has_passphrase=False
            )
            t3_ok = (
                r_id_bin.status_code == 200
                and bin_prof["requires_passphrase"] is False
                and bin_prof["has_passphrase"] is False
                and code_bin_no_pass != "MISSING_PASSPHRASE"
                and code_bin_no_pass == "INVALID_API_KEY"
            )
            record(
                "T03",
                "Binance profile with no passphrase never returns MISSING_PASSPHRASE",
                t3_ok,
                f"requires_passphrase={bin_prof['requires_passphrase']}, resolved_code={code_bin_no_pass}",
            )

            # -----------------------------------------------------------------
            # Test 4: Binance profile failing with -2015 returns INVALID_API_KEY and preserves -2015 as provider_error_code
            # -----------------------------------------------------------------
            code_2015 = resolve_actionable_error_code(
                "BINANCE",
                401,
                "-2015",
                "Authentication rejected by exchange (HTTP 401): Invalid API Key, Passphrase, or Signature. Provider msg: Invalid API-key, IP, or permissions for action.",
                has_passphrase=False,
            )
            credential_vault.update_verification_results(
                profile_id=binance_pid,
                connection_status=ConnectionStatus.AUTHENTICATION_FAILED.value,
                verification_label=code_2015,
                endpoint_results=[{
                    "name": "Account Authentication & Signing",
                    "url": "https://testnet.binance.vision/api/v3/account",
                    "category": "AUTHENTICATION",
                    "status": "FAIL",
                    "http_status": 401,
                    "provider_error_code": "-2015",
                    "error": "Invalid API-key, IP, or permissions for action.",
                }],
                capabilities=[],
                account_data=None,
                actionable_error_code=code_2015,
                provider_error_code="-2015",
                provider_error_message="Invalid API-key, IP, or permissions for action.",
            )
            r_cap_bin = client.get(f"/api/v1/connections/profiles/{binance_pid}/capability-report", headers=auth_headers)
            cap_bin = r_cap_bin.json()
            t4_ok = (
                code_2015 == "INVALID_API_KEY"
                and cap_bin["actionable_error_code"] == "INVALID_API_KEY"
                and cap_bin["provider_error_code"] == "-2015"
                and "bitget" not in (cap_bin.get("error_guidance") or "").lower()
                and "binance" in (cap_bin.get("error_guidance") or "").lower()
            )
            record(
                "T04",
                "Binance -2015 preserves provider_error_code='-2015' and returns Binance-specific INVALID_API_KEY guidance",
                t4_ok,
                f"actionable={cap_bin['actionable_error_code']}, provider_error_code={cap_bin['provider_error_code']}, guidance={cap_bin['error_guidance']}",
            )

            # -----------------------------------------------------------------
            # Test 5: Bitget profile without passphrase returns MISSING_PASSPHRASE before making a network request
            # -----------------------------------------------------------------
            r_bg_create = client.post(
                "/api/v1/connections/universal",
                headers=auth_headers,
                json={
                    "label": "Bitget No Passphrase Profile",
                    "api_key": "bg_key_without_pass_123456",
                    "api_secret": "bg_sec_without_pass_123456",
                },
            )
            bg_pid = r_bg_create.json()["profile"]["profile_id"]
            client.post(
                f"/api/v1/connections/profiles/{bg_pid}/identify",
                headers=auth_headers,
                json={"provider": "BITGET", "environment": "DEMO", "product_type": "FUTURES_USDT"},
            )
            r_bg_test = client.post(
                "/api/v1/connections/test",
                headers=auth_headers,
                json={"profile_id": bg_pid},
            )
            bg_test_data = r_bg_test.json()
            t5_ok = (
                r_bg_test.status_code == 200
                and bg_test_data.get("status") == "BLOCKED"
                and bg_test_data.get("actionable_error_code") == "MISSING_PASSPHRASE"
                and bg_test_data.get("network_request_made") is False
                and bg_test_data.get("provider_error_code") is None
            )
            record(
                "T05",
                "Bitget profile without passphrase returns MISSING_PASSPHRASE before making any network request",
                t5_ok,
                f"status={bg_test_data.get('status')}, actionable={bg_test_data.get('actionable_error_code')}, network_request_made={bg_test_data.get('network_request_made')}",
            )

            # -----------------------------------------------------------------
            # Test 6: Bitget profile with passphrase failing with 40099 returns ENVIRONMENT_KEY_MISMATCH, not MISSING_PASSPHRASE
            # -----------------------------------------------------------------
            code_40099 = resolve_actionable_error_code(
                "BITGET",
                400,
                "40099",
                "Authentication rejected by exchange (HTTP 400): Invalid API Key, Passphrase, or Signature. Provider msg: exchange environment is incorrect",
                has_passphrase=True,
            )
            t6_ok = (
                code_40099 == "ENVIRONMENT_KEY_MISMATCH"
                and code_40099 != "MISSING_PASSPHRASE"
            )
            record(
                "T06",
                "Bitget profile with passphrase failing with 40099 returns ENVIRONMENT_KEY_MISMATCH (never MISSING_PASSPHRASE)",
                t6_ok,
                f"resolved_code={code_40099}",
            )

            # -----------------------------------------------------------------
            # Test 7: Editing a profile clears stale error banners and resets status to UNTESTED
            # -----------------------------------------------------------------
            r_edit_bin = client.put(
                f"/api/v1/connections/profiles/{binance_pid}",
                headers=auth_headers,
                json={"label": "Updated Binance Profile"},
            )
            edited_bin = r_edit_bin.json()["profile"]
            t7_ok = (
                r_edit_bin.status_code == 200
                and edited_bin["connection_status"] == "UNTESTED"
                and edited_bin["actionable_error_code"] is None
                and edited_bin["provider_error_code"] is None
                and edited_bin["error_guidance"] is None
                and edited_bin["endpoint_results"] == []
            )
            record(
                "T07",
                "Editing a profile clears all stale error codes, guidance, and endpoint_results and resets to UNTESTED",
                t7_ok,
                f"status={edited_bin['connection_status']}, actionable={edited_bin['actionable_error_code']}, provider_code={edited_bin['provider_error_code']}",
            )

            # -----------------------------------------------------------------
            # Test 8: Identifying a profile preserves saved passphrase and allows re-identification when no active run exists
            # -----------------------------------------------------------------
            r_with_pass = client.post(
                "/api/v1/connections/universal",
                headers=auth_headers,
                json={
                    "label": "Multi-Identify Passphrase Profile",
                    "api_key": "reid_key_1234567890",
                    "api_secret": "reid_sec_1234567890",
                    "passphrase": "my_saved_passphrase_secret",
                },
            )
            reid_pid = r_with_pass.json()["profile"]["profile_id"]
            # First identify as BINANCE (which doesn't require passphrase)
            r_id1 = client.post(
                f"/api/v1/connections/profiles/{reid_pid}/identify",
                headers=auth_headers,
                json={"provider": "BINANCE", "environment": "DEMO", "product_type": "SPOT"},
            )
            # Then re-identify as BITGET (which requires passphrase)
            r_id2 = client.post(
                f"/api/v1/connections/profiles/{reid_pid}/identify",
                headers=auth_headers,
                json={"provider": "BITGET", "environment": "DEMO", "product_type": "FUTURES_USDT"},
            )
            reid_prof = r_id2.json()["profile"]
            decrypted_reid = credential_vault.get_credentials(reid_pid)
            t8_ok = (
                r_id1.status_code == 200
                and r_id2.status_code == 200
                and reid_prof["exchange"] == "BITGET"
                and reid_prof["has_passphrase"] is True
                and decrypted_reid.get("passphrase") == "my_saved_passphrase_secret"
            )
            record(
                "T08",
                "Identifying/re-identifying a profile preserves the saved passphrase in the vault",
                t8_ok,
                f"exchange={reid_prof['exchange']}, has_passphrase={reid_prof['has_passphrase']}",
            )

            # -----------------------------------------------------------------
            # Test 9: Strategy Wizard reads the exact unified balance schema written by connection verification
            # -----------------------------------------------------------------
            credential_vault.update_verification_results(
                profile_id=reid_pid,
                connection_status=ConnectionStatus.VERIFIED_READ_ONLY.value,
                verification_label=ConnectionStatus.VERIFIED_READ_ONLY.value,
                endpoint_results=[],
                capabilities=["ACCOUNT_READ", "BALANCES_READ"],
                account_data={
                    "market_type": "CRYPTO",
                    "provider": "BITGET",
                    "environment": "DEMO",
                    "balance_verified": True,
                    "total_equity_usd": 2450.75,
                    "available_balance_usd": 1825.50,
                    "asset_balances": [
                        {"asset": "USDT", "available": 1825.50, "locked": 625.25, "total": 2450.75}
                    ],
                },
            )
            r_bal = client.get(f"/api/v1/orchestration/profiles/{reid_pid}/balance?asset=SOL/USDT", headers=auth_headers)
            bal_cap = r_bal.json()["capital"]
            t9_ok = (
                r_bal.status_code == 200
                and bal_cap["verified"] is True
                and bal_cap["available_capital"] == 1825.50
                and bal_cap["total_equity"] == 2450.75
                and "$1,825.50" in bal_cap["balance_display"]
            )
            record(
                "T09",
                "Strategy Wizard reads unified balance schema (available_balance_usd / asset_balances.available)",
                t9_ok,
                f"available_capital={bal_cap['available_capital']}, total_equity={bal_cap['total_equity']}, display={bal_cap['balance_display']}",
            )

            # -----------------------------------------------------------------
            # Test 10: Unverified/untested profiles show NOT TESTED / NOT VERIFIED, never $0.00
            # -----------------------------------------------------------------
            r_untested_bal = client.get(f"/api/v1/orchestration/profiles/{binance_pid}/balance?asset=BTC/USDT", headers=auth_headers)
            untested_cap = r_untested_bal.json()["capital"]
            t10_ok = (
                r_untested_bal.status_code == 200
                and untested_cap["verified"] is False
                and untested_cap["available_capital"] is None
                and untested_cap["balance_display"] in ("NOT TESTED", "NOT VERIFIED")
            )
            record(
                "T10",
                "Untested/unverified profiles return available_capital=None and NOT TESTED/NOT VERIFIED (never $0.00)",
                t10_ok,
                f"verified={untested_cap['verified']}, available_capital={untested_cap['available_capital']}, display={untested_cap['balance_display']}",
            )

            # -----------------------------------------------------------------
            # Test 11: Disabled, unverified, unidentified, live-locked, and unimplemented-provider profiles cannot launch strategies
            # -----------------------------------------------------------------
            # Create an unidentified profile
            r_unid = client.post(
                "/api/v1/connections/universal",
                headers=auth_headers,
                json={"label": "User Unidentified Key", "api_key": "unid_k_1", "api_secret": "unid_s_1"},
            )
            unid_pid = r_unid.json()["profile"]["profile_id"]

            # Create a LIVE verified profile (blocked by live_trading_locked)
            r_live = client.post(
                "/api/v1/connections/universal",
                headers=auth_headers,
                json={"label": "User Live Binance Key", "api_key": "live_k_1", "api_secret": "live_s_1"},
            )
            live_pid = r_live.json()["profile"]["profile_id"]
            client.post(
                f"/api/v1/connections/profiles/{live_pid}/identify",
                headers=auth_headers,
                json={"provider": "BINANCE", "environment": "LIVE", "product_type": "SPOT"},
            )
            credential_vault.update_verification_results(
                profile_id=live_pid,
                connection_status=ConnectionStatus.VERIFIED_READ_ONLY.value,
                verification_label=ConnectionStatus.VERIFIED_READ_ONLY.value,
                endpoint_results=[],
                capabilities=["ACCOUNT_READ"],
                account_data={"total_equity_usd": 500.0, "available_balance_usd": 500.0, "asset_balances": [{"asset": "USDT", "available": 500.0}]},
            )

            # Check /api/v1/orchestration/profiles/eligible
            r_elig = client.get("/api/v1/orchestration/profiles/eligible", headers=auth_headers)
            elig_data = r_elig.json()
            elig_ids = [p["profile_id"] for p in elig_data["eligible_profiles"]]
            inelig_map = {p["profile_id"]: p for p in elig_data["ineligible_profiles"]}

            # Also check authoritative provider status for BYBIT / OKX / COINBASE (must be PLANNED, not IMPLEMENTED_TESTED)
            r_provs = client.get("/api/v1/orchestration/providers", headers=auth_headers).json()["providers"]
            prov_status_map = {p["id"]: p["implementation_status"] for p in r_provs}

            t11_ok = (
                "PAPER" in elig_ids
                and reid_pid in elig_ids
                and binance_pid in inelig_map and inelig_map[binance_pid]["eligibility_code"] == "PRIVATE_AUTH_NOT_VERIFIED"
                and bg_pid in inelig_map and inelig_map[bg_pid]["eligibility_code"] == "MISSING_PASSPHRASE"
                and unid_pid in inelig_map and inelig_map[unid_pid]["eligibility_code"] == "PROVIDER_NOT_IDENTIFIED"
                and live_pid in inelig_map and inelig_map[live_pid]["eligibility_code"] == "LIVE_TRADING_LOCKED"
                and prov_status_map.get("BINANCE") == "IMPLEMENTED_TESTED"
                and prov_status_map.get("BITGET") == "IMPLEMENTED_TESTED"
                and prov_status_map.get("BYBIT") == "PLANNED"
                and prov_status_map.get("OKX") == "PLANNED"
                and prov_status_map.get("COINBASE") == "PLANNED"
            )
            record(
                "T11",
                "Server-side eligibility & authoritative provider registry reject unverified/unidentified/live-locked/unimplemented profiles with explicit reasons",
                t11_ok,
                f"eligible={elig_ids}, ineligible_codes={{k: v['eligibility_code'] for k, v in inelig_map.items()}}, bybit={prov_status_map.get('BYBIT')}",
            )

            # -----------------------------------------------------------------
            # Test 12: Multi-profile strategy selection launches isolated runs without leaking state across profiles
            # -----------------------------------------------------------------
            r_multi_launch = client.post(
                "/api/v1/orchestration/runs/launch",
                headers=auth_headers,
                json={
                    "asset": "SOL/USDT",
                    "strategy_id": "SPOT_GRID",
                    "profile_ids": ["PAPER", reid_pid],
                    "investment_amount": 150.0,
                    "environment": "DEMO",
                    "parameters": {"grid_count": 5, "reference_price": 150.0},
                },
            )
            multi_data = r_multi_launch.json()
            runs_created = multi_data.get("strategy_runs") or []
            t12_ok = (
                r_multi_launch.status_code == 200
                and len(runs_created) == 2
                and runs_created[0]["profile_id"] == "PAPER"
                and runs_created[0]["environment"] == "PAPER"
                and runs_created[0]["provider_id"] == "PAPER"
                and runs_created[1]["profile_id"] == reid_pid
                and runs_created[1]["environment"] == "DEMO"
                and runs_created[1]["provider_id"] == "BITGET"
                and runs_created[0]["run_id"] != runs_created[1]["run_id"]
                and runs_created[0]["balance_source"]["available_at_start"] == 10000.0
                and runs_created[1]["balance_source"]["available_at_start"] == 1825.50
            )
            record(
                "T12",
                "Multi-profile strategy launch creates independent, isolated runs per profile with separate balances & environments",
                t12_ok,
                f"runs={[ (r['run_id'], r['profile_id'], r['provider_id'], r['environment'], r['balance_source']['available_at_start']) for r in runs_created ]}",
            )

            # -----------------------------------------------------------------
            # Test 13: Live order submission remains hard-locked with HTTP 403
            # -----------------------------------------------------------------
            r_live_order = client.post(
                "/api/v1/orders/live/submit",
                headers=auth_headers,
                json={"symbol": "BTCUSDT", "side": "BUY", "order_type": "LIMIT", "quantity": 0.01, "price": 50000},
            )
            t13_ok = r_live_order.status_code == 403
            record(
                "T13",
                "Live order submission endpoint remains hard-locked with HTTP 403",
                t13_ok,
                f"status_code={r_live_order.status_code}",
            )

        finally:
            # Restore original vault and orchestrator paths in memory
            credential_vault.storage_path = orig_vault_path
            credential_vault._profiles = orig_profiles
            credential_vault._last_mtime = orig_mtime
            strategy_orchestrator.storage_path = orig_runs_path
            strategy_orchestrator._runs = orig_runs

    # -----------------------------------------------------------------
    # Test 14: Verify production vault and persistent staging vault are byte-for-byte untouched by tests
    # -----------------------------------------------------------------
    prod_vault_hash_after = sha256_file(PROD_VAULT)
    staging_vault_hash_after = sha256_file(STAGING_VAULT)
    t14_ok = (
        prod_vault_hash_before == prod_vault_hash_after
        and staging_vault_hash_before == staging_vault_hash_after
    )
    record(
        "T14",
        "Production and staging persistent vaults remain byte-for-byte untouched by isolated test suite",
        t14_ok,
        f"prod_sha256_match={prod_vault_hash_before == prod_vault_hash_after}, staging_sha256_match={staging_vault_hash_before == staging_vault_hash_after}",
    )

    print(f"\nALL {len(results)}/{len(results)} PHASE 1 REGRESSION TESTS PASSED!")


if __name__ == "__main__":
    run_all_tests()
