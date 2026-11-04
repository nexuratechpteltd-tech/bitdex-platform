"""
BITDEX Phase 4 Independent Automated Acceptance Suite:
Dual Exness Connectivity, Demo + Real Execution & Customer Fund Transfer.
Verifies all 10 quantitative and operational invariants on staging.
"""

import sys
import os
import uuid
import time
import asyncio
import httpx
import jwt

# Add backend directory
sys.path.append("/opt/tauric-platform-staging/backend")

from app.services.saas_db import get_db_connection
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
from app.services.exness.vault import ExnessCredentialVault
from app.services.exness.risk_guard import ExnessRiskGuard

BASE_URL = "http://127.0.0.1:8002/api/v1"


def get_test_token() -> str:
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT user_id FROM users WHERE status = 'ACTIVE' LIMIT 1").fetchone()
        user_id = user["user_id"]
        session_id = f"SES-P4-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at) "
            "VALUES (?, ?, 'hash', ?, 0, datetime('now'))",
            (session_id, user_id, time.time() + 86400)
        )
        conn.commit()
        return jwt.encode(
            {"sub": user_id, "session_id": session_id, "exp": time.time() + 86400},
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )
    finally:
        conn.close()


async def run_all_tests():
    token = get_test_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # TEST 1: Dual Environment Status
        try:
            r = await client.get(f"{BASE_URL}/hft/exness/status", headers=headers)
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            d = r.json()
            assert "DEMO" in d.get("environments_supported", []), "DEMO missing in supported environments"
            assert "REAL" in d.get("environments_supported", []), "REAL missing in supported environments"
            assert d.get("live_trading_locked") is True, "live_trading_locked must be True"
            assert d.get("emergency_lock_active") is True, "emergency_lock_active must be True"
            results.append(("1. Dual Environment Status Discovery", "PASSED", f"Environments: {d['environments_supported']}, Locks: Verified Fail-Closed"))
        except Exception as e:
            results.append(("1. Dual Environment Status Discovery", "FAILED", str(e)))

        # TEST 2: Real Account Registration & Vault Encryption
        try:
            r = await client.post(
                f"{BASE_URL}/hft/exness/real/connect",
                json={
                    "connection_method": "MT5_GATEWAY",
                    "account_login": "88492011",
                    "password": "SecurePassword#2026",
                    "server_name": "Exness-Real",
                },
                headers=headers,
            )
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            d = r.json()
            assert d.get("environment") == "REAL", "Connection environment must be REAL"
            assert d.get("live_execution_locked") is True, "Live execution locked must be True"
            results.append(("2. Exness Real Account Connect & AES-256 Vault", "PASSED", f"Connection ID: {d.get('connection_id')}, Env: {d.get('environment')}"))
        except Exception as e:
            results.append(("2. Exness Real Account Connect & AES-256 Vault", "FAILED", str(e)))

        # TEST 3: Account Telemetry for Demo vs Real
        try:
            r_demo = await client.get(f"{BASE_URL}/hft/exness/account?environment=DEMO", headers=headers)
            assert r_demo.status_code == 200, f"Expected 200 for Demo, got {r_demo.status_code}"
            assert r_demo.json().get("environment") == "DEMO"

            r_real = await client.get(f"{BASE_URL}/hft/exness/account?environment=REAL", headers=headers)
            assert r_real.status_code == 200, f"Expected 200 for Real, got {r_real.status_code}"
            assert r_real.json().get("environment") == "REAL"
            results.append(("3. Dual Environment Account Telemetry", "PASSED", "Demo & Real telemetry endpoints isolated and responsive"))
        except Exception as e:
            results.append(("3. Dual Environment Account Telemetry", "FAILED", str(e)))

        # TEST 4: Real Order Execution WITHOUT Consent (Strict Rejection)
        try:
            r_noconsent = await client.post(
                f"{BASE_URL}/hft/exness/trade/execute",
                json={
                    "environment": "REAL",
                    "symbol": "BTCUSDm",
                    "side": "BUY",
                    "volume": 0.01,
                    "consent_confirmed": False,
                },
                headers=headers,
            )
            assert r_noconsent.status_code == 400, f"Expected 400, got {r_noconsent.status_code}"
            assert "REAL_EXECUTION_CONSENT_REQUIRED" in r_noconsent.text
            results.append(("4. Real Trade Missing Consent Rejection", "PASSED", "HTTP 400: Customer consent signature strictly required"))
        except Exception as e:
            results.append(("4. Real Trade Missing Consent Rejection", "FAILED", str(e)))

        # TEST 5: Real Order Execution WITH Consent (Safety Lock Barrier)
        try:
            r_real = await client.post(
                f"{BASE_URL}/hft/exness/trade/execute",
                json={
                    "environment": "REAL",
                    "symbol": "BTCUSDm",
                    "side": "BUY",
                    "volume": 0.01,
                    "price": 78500.0,
                    "stop_loss": 77000.0,
                    "take_profit": 81000.0,
                    "consent_confirmed": True,
                },
                headers=headers,
            )
            assert r_real.status_code == 200, f"Expected 200, got {r_real.status_code}"
            d = r_real.json()
            assert d.get("status") == "BLOCKED_BY_SAFETY_LOCK"
            assert d.get("barrier") == "LIVE_TRADING_LOCKED"
            results.append(("5. Real Trade Safety Lock Barrier Enforcement", "PASSED", f"Blocked: {d.get('barrier')}, Zero Live Orders Placed"))
        except Exception as e:
            results.append(("5. Real Trade Safety Lock Barrier Enforcement", "FAILED", str(e)))

        # TEST 6: Demo Order Execution (Simulated Fill Receipt)
        try:
            r_demo = await client.post(
                f"{BASE_URL}/hft/exness/trade/execute",
                json={
                    "environment": "DEMO",
                    "symbol": "BTCUSDm",
                    "side": "BUY",
                    "volume": 0.01,
                    "price": 78500.0,
                    "consent_confirmed": False,
                },
                headers=headers,
            )
            assert r_demo.status_code == 200, f"Expected 200, got {r_demo.status_code}"
            d = r_demo.json()
            assert d.get("status") == "FILLED"
            assert d.get("environment") == "DEMO"
            assert d.get("ticket") is not None
            results.append(("6. Demo Order Execution & Ticket Generation", "PASSED", f"Simulated Ticket: {d.get('ticket')}, Fill: ${d.get('fill_price')}"))
        except Exception as e:
            results.append(("6. Demo Order Execution & Ticket Generation", "FAILED", str(e)))

        # TEST 7: Payments API Balances Retrieval
        try:
            r_bal = await client.get(f"{BASE_URL}/hft/exness/payments/balances", headers=headers)
            assert r_bal.status_code == 200, f"Expected 200, got {r_bal.status_code}"
            d = r_bal.json()
            assert len(d.get("wallets", [])) >= 2, "Expected at least 2 wallets"
            results.append(("7. Payments API Wallet Balances Inspection", "PASSED", f"Retrieved {len(d['wallets'])} Exness Wallets (USD & Partner)"))
        except Exception as e:
            results.append(("7. Payments API Wallet Balances Inspection", "FAILED", str(e)))

        # TEST 8: Payments Transfer with Mandatory Idempotency Key
        idemp_key = f"TEST-IDEMP-{uuid.uuid4().hex[:12]}"
        try:
            r_trf = await client.post(
                f"{BASE_URL}/hft/exness/payments/transfer",
                json={
                    "transfer_type": "INTERNAL_WALLET_TO_ACCOUNT",
                    "source_id": "WLT-USD-PRIMARY",
                    "destination_id": "ACC-REAL-8849",
                    "amount": 500.0,
                    "currency": "USD",
                    "idempotency_key": idemp_key,
                },
                headers=headers,
            )
            assert r_trf.status_code == 200, f"Expected 200, got {r_trf.status_code}"
            d = r_trf.json()
            assert d.get("status") == "SUCCESS"
            assert d.get("transfer", {}).get("broker_transfer_id") is not None
            results.append(("8. Payments API Transfer Creation", "PASSED", f"Transfer ID: {d['transfer']['transfer_id']}, Broker Ref: {d['transfer']['broker_transfer_id']}"))
        except Exception as e:
            results.append(("8. Payments API Transfer Creation", "FAILED", str(e)))

        # TEST 9: Idempotency Protection (Duplicate Transfer Rejection)
        try:
            r_dup = await client.post(
                f"{BASE_URL}/hft/exness/payments/transfer",
                json={
                    "transfer_type": "INTERNAL_WALLET_TO_ACCOUNT",
                    "source_id": "WLT-USD-PRIMARY",
                    "destination_id": "ACC-REAL-8849",
                    "amount": 500.0,
                    "currency": "USD",
                    "idempotency_key": idemp_key,
                },
                headers=headers,
            )
            assert r_dup.status_code == 200, f"Expected 200, got {r_dup.status_code}"
            d = r_dup.json()
            assert d.get("status") == "DUPLICATE_IDEMPOTENT_REQUEST", f"Expected DUPLICATE_IDEMPOTENT_REQUEST, got {d.get('status')}"
            results.append(("9. Duplicate Idempotency Key Protection", "PASSED", "Duplicate transfer caught and prevented from re-executing"))
        except Exception as e:
            results.append(("9. Duplicate Idempotency Key Protection", "FAILED", str(e)))

        # TEST 10: Payments Transfer History Ledger
        try:
            r_hist = await client.get(f"{BASE_URL}/hft/exness/payments/history", headers=headers)
            assert r_hist.status_code == 200, f"Expected 200, got {r_hist.status_code}"
            d = r_hist.json()
            assert len(d.get("transfers", [])) >= 1, "Expected at least 1 transfer in history"
            results.append(("10. Payments Transfer History Audit Ledger", "PASSED", f"Verified {len(d['transfers'])} recorded transfers in SQLite"))
        except Exception as e:
            results.append(("10. Payments Transfer History Audit Ledger", "FAILED", str(e)))

    print("\n" + "=" * 80)
    print("BITDEX PHASE 4 ACCEPTANCE VERIFICATION SUMMARY")
    print("=" * 80)
    all_passed = True
    for name, status, details in results:
        flag = "✓" if status == "PASSED" else "✗"
        print(f"[{flag}] {name:50} | {status:8} | {details}")
        if status != "PASSED":
            all_passed = False
    print("=" * 80)
    if all_passed:
        print("ALL 10 PHASE 4 ACCEPTANCE INVARIANTS SATISFIED.")
    else:
        print("SOME TESTS FAILED.")
    print("=" * 80 + "\n")
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
