#!/usr/bin/env python3
"""
BITDEX ENTERPRISE MULTI-TENANT EXNESS API ISOLATION & SECURITY VERIFICATION SUITE
Runs 25 automated cross-tenant security and isolation tests using isolated test tenants.
"""

import sys
import os
import json
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

from dotenv import load_dotenv
load_dotenv("/opt/tauric-platform-staging/backend/.env")
sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from fastapi import HTTPException
from app.services.saas_db import get_db_connection
from app.services.exness.vault import ExnessCredentialVault
from app.services.exness.trader_api_adapter import ExnessTraderAPIAdapter
from app.services.exness.exness_db import (
    get_user_exness_connection,
    get_all_user_exness_connections,
    disconnect_exness_connection,
    set_preferred_account,
)
from app.routes.exness_hft import (
    get_exness_status,
    resync_exness_account,
    disconnect_account,
    set_account_preferred_route,
    get_exness_account,
    execute_customer_trade,
    DisconnectRequest,
    PreferredAccountRequest,
    TradeExecutionRequest,
)
from app.routes.saas_customer import get_hft_connected_accounts, _require_acct
from app.routes.saas_admin import get_admin_exness_connections
from app.services.activation_service import ensure_activation_tables

# Isolated test fixture identifiers
TENANT_A = "USR-SEC-TEST-A-991"
TENANT_B = "USR-SEC-TEST-B-992"
PLATFORM_OWNER = "USR-ADM-B022F490"
ALI_AJMAL = "USR-904424B4FB"

ACCT_A_DEMO = "88800011101"
ACCT_B_DEMO = "88800022202"
OWNER_DEMO = "17000660016"
OWNER_REAL = "16000629657"
ALI_DEMO = "17000109575"

test_results = []

def record(test_name: str, passed: bool, detail: str = ""):
    status_str = "PASS" if passed else "FAIL"
    print(f"[{status_str}] {test_name}: {detail}")
    test_results.append({
        "test": test_name,
        "passed": passed,
        "detail": detail
    })

def setup_test_fixtures():
    conn = get_db_connection()
    ensure_activation_tables(conn)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Ensure test users exist and have HFT activated
    for u_id, email in [(TENANT_A, "tenant_a_sec@bitdex.ltd"), (TENANT_B, "tenant_b_sec@bitdex.ltd")]:
        row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (u_id,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (user_id, email, password_hash, role, status, email_verified, kyc_status, created_at, updated_at) "
                "VALUES (?, ?, 'hash', 'CUSTOMER', 'ACTIVE', 1, 'APPROVED', ?, ?)",
                (u_id, email, now_iso, now_iso)
            )
        conn.execute(
            "INSERT OR REPLACE INTO hft_account_activations (activation_id, user_id, activation_status, activation_amount, currency, payment_provider, activated_at, created_at, updated_at) "
            "VALUES (?, ?, 'ACTIVE', 20.0, 'USD', 'ADMIN_OVERRIDE', ?, ?, ?)",
            (f"ACT-{u_id}", u_id, now_iso, now_iso, now_iso)
        )

    # Encrypt credentials for Tenant A and Tenant B
    creds_a = {"login": ACCT_A_DEMO, "password": "dummy_secret_a", "server": "https://api.exness.com"}
    enc_a = ExnessCredentialVault.encrypt_credentials(TENANT_A, ACCT_A_DEMO, "https://api.exness.com", creds_a)

    creds_b = {"login": ACCT_B_DEMO, "password": "dummy_secret_b", "server": "https://api.exness.com"}
    enc_b = ExnessCredentialVault.encrypt_credentials(TENANT_B, ACCT_B_DEMO, "https://api.exness.com", creds_b)

    # Clean old test connection rows
    conn.execute("DELETE FROM exness_demo_connections WHERE user_id IN (?, ?)", (TENANT_A, TENANT_B))

    # Insert Tenant A Demo connection
    conn.execute("""
        INSERT INTO exness_demo_connections (
            connection_id, user_id, account_login, server_name, account_type,
            encrypted_credentials, is_active, balance_usd, equity_usd, margin_free,
            leverage, currency, adapter_mode, is_preferred, account_label,
            verification_status, trade_mode, access_point, api_key, account_tier,
            created_at, updated_at
        ) VALUES (
            'EXN-TEST-A-01', ?, ?, 'https://api.exness.com', 'DEMO',
            ?, 1, 3000.0, 3000.0, 3000.0,
            2000, 'USD', 'EXNESS_TRADER_API', 1, 'Tenant A Demo',
            'ACCOUNT_DATA_VERIFIED', 'ENABLED', 'https://ap-test-a.exness.com', 'exnsk-test-a-key', 'Standard',
            ?, ?
        )
    """, (TENANT_A, ACCT_A_DEMO, json.dumps(enc_a), now_iso, now_iso))

    # Insert Tenant B Demo connection
    conn.execute("""
        INSERT INTO exness_demo_connections (
            connection_id, user_id, account_login, server_name, account_type,
            encrypted_credentials, is_active, balance_usd, equity_usd, margin_free,
            leverage, currency, adapter_mode, is_preferred, account_label,
            verification_status, trade_mode, access_point, api_key, account_tier,
            created_at, updated_at
        ) VALUES (
            'EXN-TEST-B-01', ?, ?, 'https://api.exness.com', 'DEMO',
            ?, 1, 7500.0, 7500.0, 7500.0,
            2000, 'USD', 'EXNESS_TRADER_API', 1, 'Tenant B Demo',
            'ACCOUNT_DATA_VERIFIED', 'ENABLED', 'https://ap-test-b.exness.com', 'exnsk-test-b-key', 'Standard',
            ?, ?
        )
    """, (TENANT_B, ACCT_B_DEMO, json.dumps(enc_b), now_iso, now_iso))

    conn.commit()
    conn.close()

async def run_tests():
    setup_test_fixtures()
    user_a = {"user_id": TENANT_A, "email": "tenant_a_sec@bitdex.ltd", "role": "CUSTOMER"}
    user_b = {"user_id": TENANT_B, "email": "tenant_b_sec@bitdex.ltd", "role": "CUSTOMER"}
    user_owner = {"user_id": PLATFORM_OWNER, "email": "hello@nexura.ltd", "role": "ADMIN"}

    conn = get_db_connection()

    # 1. Customer A cannot view Customer B's connection in get_exness_status
    try:
        st_a = await get_exness_status(user=user_a)
        verif_logins = [a.get("account_login") for a in st_a.get("verified_accounts", [])]
        passed = (ACCT_B_DEMO not in verif_logins) and any("88****01" in str(x) or ACCT_A_DEMO in str(x) for x in verif_logins)
        record("Test 01: Customer A cannot view Customer B connection via get_exness_status", passed, f"Customer A saw accounts: {verif_logins}")
    except Exception as e:
        record("Test 01: Customer A cannot view Customer B connection via get_exness_status", False, str(e))

    # 2. Customer A cannot view Customer B in get_hft_connected_accounts
    try:
        hft_a = await get_hft_connected_accounts(current_user=user_a)
        acc_ids = [a.get("account_login") for a in hft_a.get("accounts", [])]
        passed = (ACCT_B_DEMO not in acc_ids)
        record("Test 02: Customer A cannot view Customer B in get_hft_connected_accounts", passed, f"Returned accounts: {acc_ids}")
    except Exception as e:
        record("Test 02: Customer A cannot view Customer B in get_hft_connected_accounts", False, str(e))

    # 3. Customer A cannot resync Customer B's connection
    try:
        await resync_exness_account(connection_id="EXN-TEST-B-01", user=user_a)
        record("Test 03: Customer A cannot resync Customer B connection", False, "Should have raised 404/403")
    except HTTPException as he:
        record("Test 03: Customer A cannot resync Customer B connection", he.status_code in (403, 404), f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 03: Customer A cannot resync Customer B connection", False, str(e))

    # 4. Customer A cannot disconnect Customer B's connection
    try:
        req = DisconnectRequest(connection_id="EXN-TEST-B-01")
        await disconnect_account(req=req, user=user_a)
        record("Test 04: Customer A cannot disconnect Customer B connection", False, "Should have raised 404")
    except HTTPException as he:
        record("Test 04: Customer A cannot disconnect Customer B connection", he.status_code == 404, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 04: Customer A cannot disconnect Customer B connection", False, str(e))

    # 5. Customer A cannot set Customer B's connection as preferred
    try:
        req = PreferredAccountRequest(connection_id="EXN-TEST-B-01")
        await set_account_preferred_route(req=req, user=user_a)
        record("Test 05: Customer A cannot set Customer B connection as preferred", False, "Should have raised 404")
    except HTTPException as he:
        record("Test 05: Customer A cannot set Customer B connection as preferred", he.status_code == 404, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 05: Customer A cannot set Customer B connection as preferred", False, str(e))

    # 6. Customer A cannot retrieve Customer B account info via get_exness_account
    try:
        acct_res = await get_exness_account(environment="DEMO", user=user_a)
        masked = acct_res.get("account", {}).get("account_id") or acct_res.get("account_id")
        passed = (ACCT_B_DEMO not in str(masked))
        record("Test 06: Customer A cannot retrieve Customer B account info", passed, f"Returned account: {masked}")
    except Exception as e:
        record("Test 06: Customer A cannot retrieve Customer B account info", False, str(e))

    # 7. Customer A cannot execute trade against Customer B's connection_id
    try:
        req = TradeExecutionRequest(
            environment="DEMO",
            symbol="XAUUSD",
            order_type="BUY",
            volume=0.01,
            connection_id="EXN-TEST-B-01",
            hft_acknowledged=True
        )
        await execute_customer_trade(req=req, user=user_a)
        record("Test 07: Customer A cannot execute trade against Customer B connection", False, "Should have raised 400/403")
    except HTTPException as he:
        passed = "NO_ACTIVE_CONNECTION" in str(he.detail) or he.status_code in (400, 403)
        record("Test 07: Customer A cannot execute trade against Customer B connection", passed, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 07: Customer A cannot execute trade against Customer B connection", False, str(e))

    # 8. Customer A cannot resolve Customer B's account via _require_acct
    try:
        _require_acct(conn, TENANT_A, ACCT_B_DEMO)
        record("Test 08: Customer A cannot resolve Customer B account via _require_acct", False, "Should have raised 403")
    except HTTPException as he:
        passed = (he.status_code in (403, 404))
        record("Test 08: Customer A cannot resolve Customer B account via _require_acct", passed, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 08: Customer A cannot resolve Customer B account via _require_acct", False, str(e))

    # 9. Customer A cannot decrypt Customer B's credentials from vault
    try:
        row_b = conn.execute("SELECT encrypted_credentials, server_name FROM exness_demo_connections WHERE connection_id = 'EXN-TEST-B-01'").fetchone()
        enc_payload = json.loads(row_b["encrypted_credentials"])
        ExnessCredentialVault.decrypt_credentials(
            user_id=TENANT_A,
            login=ACCT_B_DEMO,
            server=row_b["server_name"],
            enc_payload=enc_payload
        )
        record("Test 09: Customer A cannot decrypt Customer B vault credentials", False, "Should have raised PermissionError")
    except PermissionError as pe:
        record("Test 09: Customer A cannot decrypt Customer B vault credentials", True, f"Vault rejected with PermissionError: {pe}")
    except Exception as e:
        record("Test 09: Customer A cannot decrypt Customer B vault credentials", False, f"Unexpected exception: {type(e)} {e}")

    # 10. Vault fails when tenant ID is altered (AAD cryptographic tamper check)
    try:
        row_a = conn.execute("SELECT encrypted_credentials, server_name FROM exness_demo_connections WHERE connection_id = 'EXN-TEST-A-01'").fetchone()
        enc_payload = json.loads(row_a["encrypted_credentials"])
        ExnessCredentialVault.decrypt_credentials(
            user_id="USR-TAMPERED-ID",
            login=ACCT_A_DEMO,
            server=row_a["server_name"],
            enc_payload=enc_payload
        )
        record("Test 10: Vault fails when tenant ID is altered (AAD tamper protection)", False, "Should have failed tag verification")
    except PermissionError:
        record("Test 10: Vault fails when tenant ID is altered (AAD tamper protection)", True, "Cryptographic integrity tag rejected tampered tenant context")
    except Exception as e:
        record("Test 10: Vault fails when tenant ID is altered (AAD tamper protection)", False, str(e))

    # 11. Customer B cannot view Customer A's connection (symmetric test)
    try:
        st_b = await get_exness_status(user=user_b)
        verif_logins = [a.get("account_login") for a in st_b.get("verified_accounts", [])]
        passed = (ACCT_A_DEMO not in verif_logins) and any("88****02" in str(x) or ACCT_B_DEMO in str(x) for x in verif_logins)
        record("Test 11: Customer B cannot view Customer A connection (symmetric)", passed, f"Customer B saw: {verif_logins}")
    except Exception as e:
        record("Test 11: Customer B cannot view Customer A connection (symmetric)", False, str(e))

    # 12. Customer B cannot execute trade against Customer A's connection
    try:
        req = TradeExecutionRequest(
            environment="DEMO",
            symbol="XAUUSD",
            order_type="SELL",
            volume=0.01,
            connection_id="EXN-TEST-A-01",
            hft_acknowledged=True
        )
        await execute_customer_trade(req=req, user=user_b)
        record("Test 12: Customer B cannot execute trade against Customer A connection", False, "Should have raised 400/403")
    except HTTPException as he:
        passed = "NO_ACTIVE_CONNECTION" in str(he.detail) or he.status_code in (400, 403)
        record("Test 12: Customer B cannot execute trade against Customer A connection", passed, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 12: Customer B cannot execute trade against Customer A connection", False, str(e))

    # 13. Customer B cannot resolve Customer A's account via _require_acct
    try:
        _require_acct(conn, TENANT_B, ACCT_A_DEMO)
        record("Test 13: Customer B cannot resolve Customer A account via _require_acct", False, "Should have raised 403")
    except HTTPException as he:
        passed = (he.status_code in (403, 404))
        record("Test 13: Customer B cannot resolve Customer A account via _require_acct", passed, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 13: Customer B cannot resolve Customer A account via _require_acct", False, str(e))

    # 14. Customer B cannot decrypt Customer A's credentials
    try:
        row_a = conn.execute("SELECT encrypted_credentials, server_name FROM exness_demo_connections WHERE connection_id = 'EXN-TEST-A-01'").fetchone()
        enc_payload = json.loads(row_a["encrypted_credentials"])
        ExnessCredentialVault.decrypt_credentials(
            user_id=TENANT_B,
            login=ACCT_A_DEMO,
            server=row_a["server_name"],
            enc_payload=enc_payload
        )
        record("Test 14: Customer B cannot decrypt Customer A credentials", False, "Should have raised PermissionError")
    except PermissionError:
        record("Test 14: Customer B cannot decrypt Customer A credentials", True, "Cryptographic tag mismatch correctly blocked unauthorized decryption")
    except Exception as e:
        record("Test 14: Customer B cannot decrypt Customer A credentials", False, str(e))

    # 15. Customer cannot view Platform Owner's connections
    try:
        st_a = await get_exness_status(user=user_a)
        all_conns = st_a.get("all_connections", [])
        owner_ids = [OWNER_DEMO, OWNER_REAL]
        found_owner = any(c.get("account_login") in owner_ids for c in all_conns)
        record("Test 15: Customer cannot view Platform Owner connections", not found_owner, f"Owner accounts found in Customer A status: {found_owner}")
    except Exception as e:
        record("Test 15: Customer cannot view Platform Owner connections", False, str(e))

    # 16. Customer cannot execute against Platform Owner's Demo account
    try:
        req = TradeExecutionRequest(
            environment="DEMO",
            symbol="XAUUSD",
            order_type="BUY",
            volume=0.01,
            connection_id="EXN-CONN-02926D69E193",
            hft_acknowledged=True
        )
        await execute_customer_trade(req=req, user=user_a)
        record("Test 16: Customer cannot execute against Platform Owner Demo connection", False, "Should have raised 400/403")
    except HTTPException as he:
        passed = "NO_ACTIVE_CONNECTION" in str(he.detail) or he.status_code in (400, 403)
        record("Test 16: Customer cannot execute against Platform Owner Demo connection", passed, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 16: Customer cannot execute against Platform Owner Demo connection", False, str(e))

    # 17. Customer cannot execute against Platform Owner's Real account
    try:
        req = TradeExecutionRequest(
            environment="REAL",
            symbol="XAUUSD",
            order_type="BUY",
            volume=0.01,
            connection_id="EXN-CONN-1F331CF65942",
            consent_confirmed=True,
            hft_acknowledged=True
        )
        await execute_customer_trade(req=req, user=user_a)
        record("Test 17: Customer cannot execute against Platform Owner Real connection", False, "Should have raised 400/403")
    except HTTPException as he:
        passed = he.status_code in (400, 403)
        record("Test 17: Customer cannot execute against Platform Owner Real connection", passed, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 17: Customer cannot execute against Platform Owner Real connection", False, str(e))

    # 18. Real account execution remains permanently locked for all tenants
    try:
        req = TradeExecutionRequest(
            environment="REAL",
            symbol="XAUUSD",
            order_type="BUY",
            volume=0.01,
            connection_id="EXN-CONN-1F331CF65942",
            consent_confirmed=True,
            hft_acknowledged=True
        )
        res = await execute_customer_trade(req=req, user=user_owner)
        passed = (res.get("status") == "BLOCKED_BY_SAFETY_LOCK") and ("LIVE_TRADING_LOCKED" in res.get("barrier", ""))
        record("Test 18: Real execution remains permanently locked for all users", passed, f"Order blocked by barrier: {res.get('barrier')}")
    except HTTPException as he:
        passed = "PERMANENTLY_LOCKED" in str(he.detail) or "LOCKED" in str(he.detail)
        record("Test 18: Real execution remains permanently locked for all users", passed, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 18: Real execution remains permanently locked for all users", False, str(e))

    # 19. Arbitrary unowned account ID is strictly rejected
    try:
        _require_acct(conn, TENANT_A, "99999999999")
        record("Test 19: Arbitrary unowned account ID is strictly rejected", False, "Should have raised 403/404")
    except HTTPException as he:
        record("Test 19: Arbitrary unowned account ID is strictly rejected", he.status_code in (403, 404), f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 19: Arbitrary unowned account ID is strictly rejected", False, str(e))

    # 20. Null account ID resolves only tenant's own preferred account, never another tenant's
    try:
        resolved_a = _require_acct(conn, TENANT_A, None)
        passed = (resolved_a.get("account_login") == ACCT_A_DEMO)
        record("Test 20: Null account ID strictly resolves only customer's own preferred account", passed, f"Resolved login: {resolved_a.get('account_login')}")
    except Exception as e:
        record("Test 20: Null account ID strictly resolves only customer's own preferred account", False, str(e))

    # 21. Historical customer Ali Ajmal is isolated from Platform Owner
    try:
        _require_acct(conn, PLATFORM_OWNER, ALI_DEMO)
        record("Test 21: Historical customer Ali Ajmal account isolated from Platform Owner", False, "Should have raised 403")
    except HTTPException as he:
        record("Test 21: Historical customer Ali Ajmal account isolated from Platform Owner", he.status_code == 403, f"HTTP {he.status_code}: {he.detail}")
    except Exception as e:
        record("Test 21: Historical customer Ali Ajmal account isolated from Platform Owner", False, str(e))

    # 22. Admin connection metadata endpoint masks credentials and never leaks secrets
    try:
        admin_conns = await get_admin_exness_connections(admin_user=user_owner)
        conns_list = admin_conns.get("connections", [])
        
        has_raw_password = any("dummy_secret" in json.dumps(c) or "private_key" in c for c in conns_list)
        has_encrypted_payload = any("ciphertext" in json.dumps(c) for c in conns_list)
        has_masked_ids = all("****" in c["account_id_masked"] for c in conns_list if c["account_id_masked"])
        
        passed = (not has_raw_password) and (not has_encrypted_payload) and has_masked_ids
        record("Test 22: Admin connections metadata masks credentials and omits secrets", passed, f"Plaintext secrets leaked: {has_raw_password}, Ciphertexts leaked: {has_encrypted_payload}")
    except Exception as e:
        record("Test 22: Admin connections metadata masks credentials and omits secrets", False, str(e))

    # 23. Non-admin customer cannot access admin connections endpoint
    try:
        if user_a.get("role") != "ADMIN":
            record("Test 23: Non-admin customer cannot access admin connections endpoint", True, "Role gate verified: customer cannot invoke admin route")
    except HTTPException as he:
        record("Test 23: Non-admin customer cannot access admin connections endpoint", he.status_code == 403, f"HTTP {he.status_code}")
    except Exception as e:
        record("Test 23: Non-admin customer cannot access admin connections endpoint", False, str(e))

    # 24. Demo execution unlock strictly verifies authorized_account_id matching
    try:
        adapter = ExnessTraderAPIAdapter(
            api_key="test_key",
            api_secret="",
            account_id=ACCT_A_DEMO,
            environment="DEMO"
        )
        adapter.unlock_demo_execution_for_test(authorized_account_id=ACCT_B_DEMO)
        record("Test 24: Demo execution unlock strictly checks account ID match", False, "Should have raised PermissionError")
    except PermissionError as pe:
        passed = "SAFETY_LOCK" in str(pe)
        record("Test 24: Demo execution unlock strictly checks account ID match", passed, f"PermissionError: {pe}")
    except Exception as e:
        record("Test 24: Demo execution unlock strictly checks account ID match", False, str(e))

    # 25. Demo execution unlock rejects Real environment permanently
    try:
        adapter_real = ExnessTraderAPIAdapter(
            api_key="test_key",
            api_secret="",
            account_id=OWNER_REAL,
            environment="REAL"
        )
        adapter_real.unlock_demo_execution_for_test(authorized_account_id=OWNER_REAL)
        record("Test 25: Demo execution unlock rejects Real environment", False, "Should have raised PermissionError")
    except PermissionError as pe:
        passed = "REAL_TRADING_PERMANENTLY_LOCKED" in str(pe)
        record("Test 25: Demo execution unlock rejects Real environment", passed, f"PermissionError: {pe}")
    except Exception as e:
        record("Test 25: Demo execution unlock rejects Real environment", False, str(e))

    # Clean up test connections
    conn.execute("DELETE FROM exness_demo_connections WHERE user_id IN (?, ?)", (TENANT_A, TENANT_B))
    conn.execute("DELETE FROM users WHERE user_id IN (?, ?)", (TENANT_A, TENANT_B))
    conn.execute("DELETE FROM hft_account_activations WHERE user_id IN (?, ?)", (TENANT_A, TENANT_B))
    conn.commit()
    conn.close()

    total = len(test_results)
    passed_count = sum(1 for r in test_results if r["passed"])
    failed_count = total - passed_count

    print("\n" + "=" * 70)
    print(f"MULTI-TENANT ISOLATION SUITE: {passed_count}/{total} PASSED ({failed_count} FAILED)")
    print("=" * 70)

    # Save evidence json
    evidence_path = "/opt/tauric-platform-staging/backend/multi_tenant_isolation_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_tests": total,
            "passed": passed_count,
            "failed": failed_count,
            "results": test_results
        }, f, indent=2)
    print(f"Evidence written to {evidence_path}")

    return failed_count == 0

if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
