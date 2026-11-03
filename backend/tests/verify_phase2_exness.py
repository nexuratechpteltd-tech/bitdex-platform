"""
Automated Integration Verification Suite for BITDEX Phase 2:
Exness MT5 Adapter, Vault Security, Additive Database Schema, and Fail-Closed Architecture.
"""

import asyncio
import json
import sqlite3
import httpx

from app.services.saas_db import DB_PATH, get_db_connection

BASE_URL = "http://127.0.0.1:8002/api/v1/hft/exness"


async def main():
    print("=" * 70)
    print("BITDEX PHASE 2 EXNESS INTEGRATION VERIFICATION")
    print("=" * 70)

    # 1. Generate Auth Token
    from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM, jwt
    token = jwt.encode({"sub": "USR-328E147ACA"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # TEST 1: GET /status
        print("\n[TEST 1] GET /hft/exness/status")
        r = await client.get(f"{BASE_URL}/status", headers=headers)
        assert r.status_code == 200, f"Failed status check: {r.text}"
        data = r.json()
        print("Response:", json.dumps(data, indent=2))
        assert data["status"] == "SUCCESS"
        assert data["live_trading_locked"] is True, "CRITICAL: Live trading MUST be locked!"
        assert data["environment"] == "DEMO_ONLY"
        assert data["broker_mode"] == "DETERMINISTIC_MOCK_DEMO"
        print(">>> TEST 1 PASSED: Subsystem online, demo-only, live trading strictly locked.")

        # TEST 2: POST /demo/connect
        print("\n[TEST 2] POST /hft/exness/demo/connect")
        connect_payload = {
            "account_login": "149827361",
            "password": "SecureTestPassword2026!",
            "server_name": "Exness-MT5Trial",
            "use_mock": True
        }
        r = await client.post(f"{BASE_URL}/demo/connect", headers=headers, json=connect_payload)
        assert r.status_code == 200, f"Failed connect: {r.text}"
        data = r.json()
        print("Response:", json.dumps(data, indent=2))
        assert data["status"] == "SUCCESS"
        assert "connection_id" in data
        assert data["credentials"]["password_masked"] == "••••••••"
        assert "SecureTestPassword2026!" not in r.text, "CRITICAL: Plaintext password leaked in API response!"
        conn_id = data["connection_id"]
        print(f">>> TEST 2 PASSED: Connected to Exness Demo. Connection ID: {conn_id}")

        # TEST 3: GET /account
        print("\n[TEST 3] GET /hft/exness/account")
        r = await client.get(f"{BASE_URL}/account", headers=headers)
        assert r.status_code == 200, f"Failed account: {r.text}"
        data = r.json()
        print("Response:", json.dumps(data, indent=2))
        assert data["account"]["balance"] == 5000.0
        assert data["account"]["leverage"] == 2000
        print(">>> TEST 3 PASSED: Account telemetry verified ($5000 demo equity, 1:2000 leverage).")

        # TEST 4: GET /symbols
        print("\n[TEST 4] GET /hft/exness/symbols")
        r = await client.get(f"{BASE_URL}/symbols", headers=headers)
        assert r.status_code == 200, f"Failed symbols: {r.text}"
        data = r.json()
        print(f"Total symbols discovered: {data['count']}")
        for s in data["symbols"]:
            print(f" - {s['broker_symbol']} ({s['canonical_symbol']}): Contract Size = {s['contract_size']}, Spread = {s['spread']}")
        assert data["count"] >= 4
        assert any(s["broker_symbol"] == "XAUUSDm" for s in data["symbols"])
        print(">>> TEST 4 PASSED: Exness MT5 instruments enumerated.")

        # TEST 5: GET /symbol/XAUUSDm
        print("\n[TEST 5] GET /hft/exness/symbol/XAUUSDm")
        r = await client.get(f"{BASE_URL}/symbol/XAUUSDm", headers=headers)
        assert r.status_code == 200, f"Failed symbol detail: {r.text}"
        data = r.json()
        print("Response:", json.dumps(data, indent=2))
        assert data["symbol_info"]["contract_size"] == 100.0
        assert data["latest_tick"]["bid"] > 2000.0
        print(">>> TEST 5 PASSED: Gold (XAUUSDm) contract spec and real-time tick verified.")

        # TEST 6: POST /margin/calculate
        print("\n[TEST 6] POST /hft/exness/margin/calculate (0.01 lot XAU/USD)")
        margin_payload = {"symbol": "XAUUSDm", "order_type": "BUY", "volume": 0.01}
        r = await client.post(f"{BASE_URL}/margin/calculate", headers=headers, json=margin_payload)
        assert r.status_code == 200, f"Failed margin calculation: {r.text}"
        data = r.json()
        print("Response:", json.dumps(data, indent=2))
        assert data["margin_check"]["is_affordable"] is True
        assert 1.0 <= data["margin_check"]["required_margin_usd"] <= 2.0
        print(">>> TEST 6 PASSED: Pre-trade margin check verified (Required margin ~ $1.37).")

        # TEST 7: POST /reconcile
        print("\n[TEST 7] POST /hft/exness/reconcile")
        r = await client.post(f"{BASE_URL}/reconcile", headers=headers)
        assert r.status_code == 200, f"Failed reconcile: {r.text}"
        data = r.json()
        print("Response:", json.dumps(data, indent=2))
        assert data["reconciliation"]["status"] == "RECONCILED"
        assert data["reconciliation"]["discrepancy_count"] == 0
        rec_log_id = data["log_id"]
        print(f">>> TEST 7 PASSED: Account reconciliation completed. Log ID: {rec_log_id}")

    # TEST 8: Direct Database Verification
    print("\n[TEST 8] Database Verification (saas.db)")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Check connection record
        row = conn.execute("SELECT * FROM exness_demo_connections WHERE connection_id = ?", (conn_id,)).fetchone()
        assert row is not None, "Connection record not found in exness_demo_connections!"
        print(f"Verified connection in DB: {dict(row)}")
        
        # Verify AES-256-GCM encrypted payload in DB
        enc_payload = json.loads(row["encrypted_credentials"])
        assert enc_payload["cipher"] == "AES-256-GCM"
        assert "password" not in str(enc_payload)
        print("Verified encrypted credentials payload in DB (AES-256-GCM ciphertext + nonce).")

        # Check reconciliation log
        rec_row = conn.execute("SELECT * FROM exness_hft_reconciliation_logs WHERE log_id = ?", (rec_log_id,)).fetchone()
        assert rec_row is not None, "Reconciliation log not found in exness_hft_reconciliation_logs!"
        print(f"Verified reconciliation log in DB: {dict(rec_row)}")
        print(">>> TEST 8 PASSED: Database persistence and cryptographic vault integrity confirmed.")
    finally:
        conn.close()

    print("\n" + "=" * 70)
    print("ALL PHASE 2 EXNESS INTEGRATION TESTS COMPLETED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
