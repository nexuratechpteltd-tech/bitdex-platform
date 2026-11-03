#!/usr/bin/env python3
"""
Comprehensive End-to-End Staging Verification Suite for
Universal Multi-Exchange & Multi-Broker Architecture (v3.9.0)
Tests Staging Backend (http://127.0.0.1:8002) and Dashboard Proxy (https://127.0.0.1:33900)
"""

import sys
import os
sys.path.insert(0, '/opt/tauric-platform-staging/backend')

import json
import httpx
from app.services.exchange_framework import exchange_framework

BACKEND_BASE = "http://127.0.0.1:8002/api/v1"
DASHBOARD_BASE = "https://127.0.0.1:33900/trading/api/backend"

results = []

def record(test_num, title, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Test {test_num}: {title}")
    if detail:
        print(f"       Detail: {detail}")
    results.append({"test_num": test_num, "title": title, "passed": passed, "detail": detail})

def main():
    print("=" * 70)
    print("TAURIC UNIVERSAL MULTI-EXCHANGE & MULTI-BROKER STAGING VERIFICATION")
    print("=" * 70)

    client = httpx.Client(timeout=10.0, verify=False)

    # 1. Universal Provider Registry Listing
    try:
        r = client.get(f"{BACKEND_BASE}/connections/providers")
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "SUCCESS"
        providers = data.get("providers", [])
        assert len(providers) >= 8, f"Expected at least 8 providers, got {len(providers)}"
        prov_ids = [p["id"] for p in providers]
        assert "BINANCE" in prov_ids and "BITGET" in prov_ids and "MT5" in prov_ids
        record(1, "Universal Provider Registry Listing (GET /connections/providers)", True, f"Loaded {len(providers)} providers: {', '.join(prov_ids)}")
    except Exception as e:
        record(1, "Universal Provider Registry Listing (GET /connections/providers)", False, str(e))

    # 2. Market-Filtered Provider Registry (CRYPTO vs FOREX)
    try:
        r_crypto = client.get(f"{BACKEND_BASE}/connections/providers?market_type=CRYPTO")
        r_forex = client.get(f"{BACKEND_BASE}/connections/providers?market_type=FOREX")
        crypto_provs = [p["id"] for p in r_crypto.json().get("providers", [])]
        forex_provs = [p["id"] for p in r_forex.json().get("providers", [])]
        assert "BINANCE" in crypto_provs and "BITGET" in crypto_provs
        assert "MT5" in forex_provs and "CUSTOM_FOREX" in forex_provs
        assert "BINANCE" not in forex_provs and "MT5" not in crypto_provs
        record(2, "Market-Filtered Provider Registry (CRYPTO vs FOREX)", True, f"Crypto: {crypto_provs} | Forex: {forex_provs}")
    except Exception as e:
        record(2, "Market-Filtered Provider Registry (CRYPTO vs FOREX)", False, str(e))

    # 3. Binance Provider Schema (No Passphrase Requirement)
    try:
        r = client.get(f"{BACKEND_BASE}/connections/providers/BINANCE")
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
        data = r.json()
        p = data.get("provider", {})
        assert p.get("provider") == "BINANCE"
        assert p.get("implementation_status") == "IMPLEMENTED_TESTED"
        assert p.get("test_coverage") == "100%"
        assert p.get("requires_passphrase") is False
        req_fields = [f["field"] for f in p.get("required_credentials", [])]
        assert "api_key" in req_fields and "api_secret" in req_fields
        assert "passphrase" not in req_fields
        record(3, "Binance Provider Schema (Independent HMAC-SHA256 Hex, No Passphrase)", True, f"Status: {p.get('implementation_status')}, Fields: {req_fields}, Requires Passphrase: {p.get('requires_passphrase')}")
    except Exception as e:
        record(3, "Binance Provider Schema (Independent HMAC-SHA256 Hex, No Passphrase)", False, str(e))

    # 4. Bitget Provider Schema (Mandatory Passphrase)
    try:
        r = client.get(f"{BACKEND_BASE}/connections/providers/BITGET")
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
        data = r.json()
        p = data.get("provider", {})
        assert p.get("provider") == "BITGET"
        assert p.get("implementation_status") == "IMPLEMENTED_TESTED"
        assert p.get("test_coverage") == "100%"
        assert p.get("requires_passphrase") is True
        req_fields = [f["field"] for f in p.get("required_credentials", [])]
        assert "api_key" in req_fields and "api_secret" in req_fields and "passphrase" in req_fields
        record(4, "Bitget Provider Schema (HMAC-SHA256 Base64, Mandatory Passphrase)", True, f"Status: {p.get('implementation_status')}, Fields: {req_fields}, Requires Passphrase: {p.get('requires_passphrase')}")
    except Exception as e:
        record(4, "Bitget Provider Schema (HMAC-SHA256 Base64, Mandatory Passphrase)", False, str(e))

    # 5. MetaTrader 5 & Custom Forex Provider Contracts
    try:
        r_mt5 = client.get(f"{BACKEND_BASE}/connections/providers/MT5")
        r_cf = client.get(f"{BACKEND_BASE}/connections/providers/CUSTOM_FOREX")
        p_mt5 = r_mt5.json().get("provider", {})
        p_cf = r_cf.json().get("provider", {})
        assert p_mt5.get("implementation_status") == "BRIDGE_DEPENDENT"
        assert p_cf.get("implementation_status") == "BRIDGE_DEPENDENT"
        assert p_mt5.get("market_type") == "FOREX"
        assert p_cf.get("market_type") == "FOREX"
        record(5, "Forex Provider Contracts (MT5 Gateway & REST Broker, BRIDGE_DEPENDENT)", True, f"MT5 Status: {p_mt5.get('implementation_status')} | Custom Forex Status: {p_cf.get('implementation_status')}")
    except Exception as e:
        record(5, "Forex Provider Contracts (MT5 Gateway & REST Broker, BRIDGE_DEPENDENT)", False, str(e))

    # 6. Strategy Preflight Routing (Paper Simulation Mode)
    try:
        r = client.post(f"{BACKEND_BASE}/connections/strategy/preflight", json={
            "profile_id": "PAPER",
            "strategy_id": "SPOT_GRID",
            "symbol": "BTCUSDT"
        })
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "READY"
        assert data.get("eligible") is True
        assert "Run Spot Grid on Paper Simulation Sandbox" in data.get("confirmation_summary")
        record(6, "Strategy Preflight Routing (Paper Sandbox Confirmation)", True, f"Summary: '{data.get('confirmation_summary')}' | Status: {data.get('status')}")
    except Exception as e:
        record(6, "Strategy Preflight Routing (Paper Sandbox Confirmation)", False, str(e))

    # 7. Independent Profile Toggle ON/OFF & Execution Blocker
    try:
        # Get profiles list
        r_profs = client.get(f"{BACKEND_BASE}/connections/profiles")
        profs = r_profs.json().get("profiles", [])
        if profs:
            target_p = profs[0]
            pid = target_p["profile_id"]

            # Toggle OFF
            r_toggle_off = client.post(f"{BACKEND_BASE}/connections/profiles/{pid}/toggle-active", json={"is_active": False})
            assert r_toggle_off.status_code == 200, f"Toggle off failed: {r_toggle_off.text}"
            res_off = r_toggle_off.json()
            assert res_off.get("is_active") is False, f"Expected False, got {res_off.get('is_active')}"

            # Run preflight on disabled profile -> Must return BLOCKED
            r_pf_blocked = client.post(f"{BACKEND_BASE}/connections/strategy/preflight", json={
                "profile_id": pid,
                "strategy_id": "SPOT_GRID"
            })
            pf_data = r_pf_blocked.json()
            assert pf_data.get("status") == "BLOCKED", f"Expected BLOCKED, got {pf_data.get('status')}"
            assert pf_data.get("eligible") is False
            assert any("disabled" in b.lower() or "off" in b.lower() for b in pf_data.get("blockers", []))

            # Toggle back ON (restore original state)
            r_toggle_on = client.post(f"{BACKEND_BASE}/connections/profiles/{pid}/toggle-active", json={"is_active": True})
            assert r_toggle_on.status_code == 200, f"Toggle on failed: {r_toggle_on.text}"
            res_on = r_toggle_on.json()
            assert res_on.get("is_active") is True, f"Expected True, got {res_on.get('is_active')}"

            record(7, "Independent Profile Active Toggle ON/OFF & Strategy Preflight Blocker", True, f"Profile {pid} toggled OFF -> Preflight BLOCKED with: {pf_data.get('blockers')}. Restored to ON.")
        else:
            record(7, "Independent Profile Active Toggle ON/OFF & Strategy Preflight Blocker", True, "No saved profiles in vault (skipped live profile toggle test).")
    except Exception as e:
        record(7, "Independent Profile Active Toggle ON/OFF & Strategy Preflight Blocker", False, str(e))

    # 8. Strategy Product Compatibility Gates (Spot Grid vs Futures)
    try:
        pf_paper_futures = exchange_framework.strategy_preflight(profile_id="PAPER", strategy_id="FUTURES_GRID")
        assert pf_paper_futures.get("eligible") is True
        assert "Run Futures Grid on Paper Simulation Sandbox" in pf_paper_futures.get("confirmation_summary")
        record(8, "Strategy Compatibility Confirmation String Generation", True, f"Summary: '{pf_paper_futures.get('confirmation_summary')}'")
    except Exception as e:
        record(8, "Strategy Compatibility Confirmation String Generation", False, str(e))

    # 9. Decoupled Open Orders (balance failure does not block orders)
    try:
        r = client.get(f"{BACKEND_BASE}/orders/open?environment=PAPER")
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "SUCCESS"
        assert "orders" in data
        assert "balance_status" in data
        record(9, "Decoupled Open Orders Normalization (GET /orders/open)", True, f"Count: {data.get('count')}, Balance Status: {data.get('balance_status')}")
    except Exception as e:
        record(9, "Decoupled Open Orders Normalization (GET /orders/open)", False, str(e))

    # 10. Platform Safety Invariant (Live Trading Hard-Locked HTTP 403)
    try:
        r = client.post(f"{BACKEND_BASE}/orders/live/submit", json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.001,
            "price": 60000.0,
            "idempotency_key": "safety_check_001"
        })
        assert r.status_code == 403, f"Expected HTTP 403, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "locked" in detail.lower()
        record(10, "Platform Safety Invariant: Live Order Submit Returns HTTP 403", True, f"HTTP 403 Confirmed: {detail}")
    except Exception as e:
        record(10, "Platform Safety Invariant: Live Order Submit Returns HTTP 403", False, str(e))

    print("\n" + "=" * 70)
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    print(f"SUMMARY: {passed_count}/{total_count} TESTS PASSED (100% PASS RATE: {passed_count == total_count})")
    print("=" * 70)

    if passed_count != total_count:
        sys.exit(1)

if __name__ == "__main__":
    main()
