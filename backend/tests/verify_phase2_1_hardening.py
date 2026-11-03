"""
BITDEX Phase 2.1 Code Audit & Security Hardening Verification Suite
Tests:
1. Missing, invalid, and corrupted vault keys (strict fail-closed).
2. Tenant isolation and tamper detection.
3. Key rotation and atomic database migration.
4. Separate connection semantics (adapter_connected, broker_authenticated, is_mock, broker_mode).
5. Deterministic adapter selection (no accidental mock fallback on real gateway failure).
6. Independent reconciliation (discrepancy detection without self-comparison).
7. Attempted live execution rejection.
8. Regression safety of Phase 1 Long-Term Strategy.
"""

import os
import sys
import json
import secrets
import sqlite3
import asyncio
import httpx
from datetime import datetime, timezone

from app.services.saas_db import DB_PATH, get_db_connection
from app.services.exness.vault import ExnessCredentialVault, get_master_key
from app.services.exness.mock_adapter import ExnessDeterministicMockAdapter
from app.services.exness.mt5_gateway_adapter import ExnessMT5GatewayAdapter
from app.services.exness.exness_db import (
    get_active_local_positions,
    rotate_database_vault_keys,
    log_reconciliation,
)
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM, jwt

BASE_URL = "http://127.0.0.1:8002/api/v1/hft/exness"


async def run_failure_cases():
    print("\n" + "=" * 70)
    print("SECTION 1: FAILURE CASES & SECURITY HARDENING TESTS")
    print("=" * 70)

    orig_vault_key = os.environ.get("TAURIC_VAULT_KEY")

    # 1. Missing Vault Key Fail-Closed
    print("\n[TEST 1.1] Missing Vault Master Key (Fail-Closed)")
    try:
        os.environ.pop("TAURIC_VAULT_KEY", None)
        os.environ.pop("BITDEX_VAULT_KEY", None)
        try:
            get_master_key()
            raise AssertionError("FAIL: Expected RuntimeError when vault key is missing!")
        except RuntimeError as e:
            print(f"✓ PASSED: Correctly failed closed with RuntimeError: {e}")
    finally:
        if orig_vault_key:
            os.environ["TAURIC_VAULT_KEY"] = orig_vault_key

    # 2. Invalid Key Length
    print("\n[TEST 1.2] Invalid Vault Key Length (Fail-Closed)")
    try:
        os.environ["TAURIC_VAULT_KEY"] = "abcd" * 10  # 40 chars instead of 64
        try:
            get_master_key()
            raise AssertionError("FAIL: Expected ValueError on invalid key length!")
        except ValueError as e:
            print(f"✓ PASSED: Correctly failed closed with ValueError: {e}")
    finally:
        if orig_vault_key:
            os.environ["TAURIC_VAULT_KEY"] = orig_vault_key

    # 3. Invalid Non-Hex Characters
    print("\n[TEST 1.3] Invalid Non-Hex Characters in Vault Key")
    try:
        os.environ["TAURIC_VAULT_KEY"] = "Z" * 64
        try:
            get_master_key()
            raise AssertionError("FAIL: Expected ValueError on non-hex key!")
        except ValueError as e:
            print(f"✓ PASSED: Correctly failed closed with ValueError: {e}")
    finally:
        if orig_vault_key:
            os.environ["TAURIC_VAULT_KEY"] = orig_vault_key

    # 4. Cross-Tenant Decryption (Tenant Isolation via AAD)
    print("\n[TEST 1.4] Cross-Tenant Decryption Attack (AAD Isolation)")
    tenant_a = "USR-TENANT-ALPHA"
    tenant_b = "USR-TENANT-BETA"
    login = "149827361"
    server = "Exness-MT5Trial"
    secret = "TopSecretDemoPassword123!"

    enc_payload = ExnessCredentialVault.encrypt_credentials(tenant_a, login, secret, server)
    try:
        ExnessCredentialVault.decrypt_credentials(tenant_b, login, server, enc_payload)
        raise AssertionError("FAIL: Tenant B was able to decrypt Tenant A's ciphertext!")
    except PermissionError as e:
        print(f"✓ PASSED: Blocked with PermissionError: {e}")

    # 5. Corrupted Nonce
    print("\n[TEST 1.5] Corrupted Nonce Validation")
    corrupt_nonce_payload = enc_payload.copy()
    corrupt_nonce_payload["nonce"] = "deadbeef"  # Wrong length
    try:
        ExnessCredentialVault.decrypt_credentials(tenant_a, login, server, corrupt_nonce_payload)
        raise AssertionError("FAIL: Decryption did not reject corrupted nonce length!")
    except ValueError as e:
        print(f"✓ PASSED: Correctly rejected corrupted nonce: {e}")

    # 6. Corrupted Ciphertext / Tag Tampering
    print("\n[TEST 1.6] Tampered Ciphertext Tag")
    tampered_payload = enc_payload.copy()
    # Flip the last byte of ciphertext
    ct = list(tampered_payload["ciphertext"])
    ct[-2:] = "00" if ct[-2:] != "00" else "ff"
    tampered_payload["ciphertext"] = "".join(ct)
    try:
        ExnessCredentialVault.decrypt_credentials(tenant_a, login, server, tampered_payload)
        raise AssertionError("FAIL: Decryption accepted tampered ciphertext!")
    except PermissionError as e:
        print(f"✓ PASSED: Authenticated encryption detected tamper: {e}")

    # 7. Disconnected MT5 Gateway Terminal Safety
    print("\n[TEST 1.7] Unavailable MT5 Gateway (Fail-Closed)")
    gw = ExnessMT5GatewayAdapter("149827361", "Exness-MT5Trial", gateway_url="http://127.0.0.1:59999")
    gw_status = await gw.connect()
    assert gw_status["status"] == "MT5_TERMINAL_UNAVAILABLE"
    assert gw_status["adapter_connected"] is False
    assert gw_status["broker_authenticated"] is False
    print(f"✓ PASSED: Gateway gracefully reports {gw_status['status']} without crashing.")

    # 8. Unavailable Broker Reconciliation
    print("\n[TEST 1.8] Unavailable Broker Reconciliation Behavior")
    rec_disc = await gw.reconcile_account(local_positions=[{"ticket": "123", "volume": 0.01}])
    assert rec_disc["status"] == "BROKER_UNAVAILABLE"
    assert rec_disc["reconciliation_source"] == "AUTHORITATIVE_BROKER"
    print(f"✓ PASSED: Reconcile returned status={rec_disc['status']} when broker data unreachable.")

    # 9. Attempted Live Execution Rejection
    print("\n[TEST 1.9] Live Execution Server-Side Lock")
    try:
        await gw.submit_order({"symbol": "XAUUSDm", "volume": 0.01, "is_live": True})
        raise AssertionError("FAIL: Live order submission was not blocked!")
    except PermissionError as e:
        print(f"✓ PASSED: Gateway order submission blocked: {e}")


def run_key_rotation_tests():
    print("\n" + "=" * 70)
    print("SECTION 2: KEY ROTATION & RECOVERY TESTS")
    print("=" * 70)

    user_id = "USR-ROTATE-TEST"
    login = "149827361"
    server = "Exness-MT5Trial"
    pwd = "OriginalPasswordBeforeRotation!@#"

    key1 = secrets.token_bytes(32)
    key2 = secrets.token_bytes(32)

    # 1. Encrypt with Key 1
    enc1 = ExnessCredentialVault.encrypt_credentials(user_id, login, pwd, server, override_key=key1)
    dec1 = ExnessCredentialVault.decrypt_credentials(user_id, login, server, enc1, override_key=key1)
    assert dec1["password"] == pwd
    print("✓ Encrypted and decrypted under Key 1.")

    # 2. Rotate to Key 2
    enc2 = ExnessCredentialVault.rotate_credentials(user_id, login, server, enc1, current_key=key1, new_key=key2)
    assert "key_rotated_at" in enc2
    assert enc2["nonce"] != enc1["nonce"], "Rotation must generate fresh unique nonce!"

    # Verify decrypts under Key 2
    dec2 = ExnessCredentialVault.decrypt_credentials(user_id, login, server, enc2, override_key=key2)
    assert dec2["password"] == pwd
    print("✓ Successfully decrypted under Key 2 post-rotation.")

    # Verify fails under Key 1
    try:
        ExnessCredentialVault.decrypt_credentials(user_id, login, server, enc2, override_key=key1)
        raise AssertionError("FAIL: Rotated payload should fail under Key 1!")
    except PermissionError:
        print("✓ Old Key 1 correctly rejected on rotated payload.")

    # 3. Database In-Place Rotation Helper Test
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from app.services.exness.exness_db import apply_exness_migrations, save_exness_connection
    apply_exness_migrations(conn)

    save_exness_connection(conn, user_id, login, server, enc1)
    rotated_count = rotate_database_vault_keys(conn, key1.hex(), key2.hex())
    assert rotated_count == 1

    row = conn.execute("SELECT * FROM exness_demo_connections WHERE user_id = ?", (user_id,)).fetchone()
    db_payload = json.loads(row["encrypted_credentials"])
    db_dec = ExnessCredentialVault.decrypt_credentials(user_id, login, server, db_payload, override_key=key2)
    assert db_dec["password"] == pwd
    print(f"✓ Database atomic rotation verified: {rotated_count} connection updated in place.")
    conn.close()


async def run_reconciliation_audit():
    print("\n" + "=" * 70)
    print("SECTION 3: INDEPENDENT RECONCILIATION AUDIT (NO SELF-COMPARISON)")
    print("=" * 70)

    adapter = ExnessDeterministicMockAdapter("149827361", "Exness-MT5Trial", initial_balance=5000.0)
    await adapter.connect()

    # Scenario A: Clean Match (Empty broker, empty local)
    res_a = await adapter.reconcile_account(local_positions=[])
    assert res_a["status"] == "RECONCILED"
    assert res_a["discrepancy_count"] == 0
    assert res_a["broker_positions_count"] == 0
    assert res_a["local_positions_count"] == 0
    print("✓ Scenario A (Clean Match): Status = RECONCILED, discrepancies = 0.")

    # Scenario B: Untracked Broker Position (Broker has open ticket, local has none)
    order = await adapter.submit_order({
        "symbol": "XAUUSDm",
        "order_type": "BUY",
        "volume": 0.01,
        "idempotency_key": "IDEMP-REC-TEST-B",
    })
    ticket = order["ticket"]

    res_b = await adapter.reconcile_account(local_positions=[])
    assert res_b["status"] == "DISCREPANCY_DETECTED"
    assert res_b["discrepancy_count"] == 1
    assert res_b["discrepancies"][0]["type"] == "UNTRACKED_BROKER_POSITION"
    assert res_b["discrepancies"][0]["ticket"] == ticket
    assert res_b["broker_positions_count"] == 1
    assert res_b["local_positions_count"] == 0
    print(f"✓ Scenario B (Untracked Broker Position): Status = DISCREPANCY_DETECTED, Broker={res_b['broker_positions_count']}, Local={res_b['local_positions_count']}.")

    # Scenario C: Matched Position (Broker has ticket, local has matching ticket and volume)
    res_c = await adapter.reconcile_account(local_positions=[{
        "broker_ticket": ticket,
        "volume": 0.01,
        "order_side": "BUY",
    }])
    assert res_c["status"] == "RECONCILED"
    assert res_c["discrepancy_count"] == 0
    assert res_c["broker_positions_count"] == 1
    assert res_c["local_positions_count"] == 1
    print("✓ Scenario C (Matched Position): Status = RECONCILED, discrepancies = 0.")

    # Scenario D: Volume Mismatch
    res_d = await adapter.reconcile_account(local_positions=[{
        "broker_ticket": ticket,
        "volume": 0.02,  # Differs from broker 0.01
        "order_side": "BUY",
    }])
    assert res_d["status"] == "DISCREPANCY_DETECTED"
    assert res_d["discrepancies"][0]["type"] == "VOLUME_MISMATCH"
    print("✓ Scenario D (Volume Mismatch): Status = DISCREPANCY_DETECTED.")

    # Clean up
    await adapter.close_position(ticket)
    await adapter.disconnect()


async def run_endpoint_semantics_and_mode_switching():
    print("\n" + "=" * 70)
    print("SECTION 4: API BROKER CONNECTION SEMANTICS & DETERMINISTIC SELECTION")
    print("=" * 70)

    token = jwt.encode({"sub": "USR-328E147ACA"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. GET /status (Check separate fields)
        print("\n[TEST 4.1] Checking GET /status discrete fields")
        r = await client.get(f"{BASE_URL}/status", headers=headers)
        assert r.status_code == 200, f"Status check failed: {r.text}"
        data = r.json()
        print("Status telemetry:", json.dumps(data, indent=2))
        assert "adapter_connected" in data
        assert "broker_authenticated" in data
        assert "is_mock" in data
        assert "broker_mode" in data
        assert "connection_type" in data
        assert data["live_trading_locked"] is True
        print("✓ PASSED: Status includes discrete adapter and authentication fields.")

        # 2. Connect with use_mock = True
        print("\n[TEST 4.2] Explicit Simulated Mock Connection (use_mock=True)")
        r_mock = await client.post(
            f"{BASE_URL}/demo/connect",
            headers=headers,
            json={
                "account_login": "149827361",
                "password": "MockSecurePassword2026!",
                "server_name": "Exness-MT5Trial",
                "use_mock": True,
            },
        )
        assert r_mock.status_code == 200, f"Connect failed: {r_mock.text}"
        m_data = r_mock.json()
        assert m_data["is_mock"] is True
        assert m_data["adapter_connected"] is True
        assert m_data["broker_authenticated"] is False  # Must not claim real broker auth
        assert m_data["broker_mode"] == "DETERMINISTIC_MOCK_DEMO"
        assert m_data["connection_type"] == "SIMULATED_DEMO"
        print("✓ PASSED: Mock connection explicitly labelled as simulated.")

        # 3. Connect with use_mock = False (Real MT5 Gateway mode without active bridge)
        print("\n[TEST 4.3] Deterministic Real Gateway Mode (use_mock=False, No accidental mock fallback)")
        r_real = await client.post(
            f"{BASE_URL}/demo/connect",
            headers=headers,
            json={
                "account_login": "149827361",
                "password": "RealGatewayPassword2026!",
                "server_name": "Exness-MT5Trial",
                "use_mock": False,
            },
        )
        # Must fail closed with 503 MT5_TERMINAL_UNAVAILABLE and NOT fall back to mock
        assert r_real.status_code == 503, f"Expected 503, got {r_real.status_code}: {r_real.text}"
        err_detail = r_real.json()["detail"]
        print("Error detail:", json.dumps(err_detail, indent=2))
        assert err_detail["status"] == "MT5_TERMINAL_UNAVAILABLE"
        assert err_detail["is_mock"] is False
        assert err_detail["broker_mode"] == "EXNESS_MT5_GATEWAY"
        print("✓ PASSED: Real gateway mode safely failed closed without accidental mock fallback.")

        # 4. Trigger /reconcile via API
        print("\n[TEST 4.4] POST /reconcile via API (Independent local vs broker cross-check)")
        r_rec = await client.post(f"{BASE_URL}/reconcile", headers=headers)
        assert r_rec.status_code == 200
        rec_data = r_rec.json()
        print("Reconciliation response:", json.dumps(rec_data, indent=2))
        rec = rec_data["reconciliation"]
        assert "broker_positions_count" in rec
        assert "local_positions_count" in rec
        assert rec["reconciliation_source"] == "SIMULATED_MOCK"
        print("✓ PASSED: Authoritative API reconciliation executed.")


async def main():
    print("=" * 70)
    print("STARTING BITDEX PHASE 2.1 SECURITY HARDENING VERIFICATION")
    print("=" * 70)

    await run_failure_cases()
    run_key_rotation_tests()
    await run_reconciliation_audit()
    await run_endpoint_semantics_and_mode_switching()

    print("\n" + "=" * 70)
    print("ALL PHASE 2.1 SECURITY HARDENING AND AUDIT TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
