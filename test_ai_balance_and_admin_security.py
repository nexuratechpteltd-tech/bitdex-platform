#!/usr/bin/env python3
"""
Bitdex Platform — AI Balance Bug Fix & Admin Security Regression Suite
Verifies:
1. New customer zero-balance initialization ($0.00).
2. Customer with $0 balance rejected with HTTP 402 on billable AI analysis.
3. Customer with $10 balance charged exactly $1.00, post-balance $9.00.
4. Idempotent duplicate request does not double-charge.
5. Failed analysis automatically refunded, net charge $0.00.
6. Multi-tenant customer balance and ledger isolation (Account A vs Account B).
7. Public registration cannot escalate role to ADMIN.
8. Secure provisioning and verification of hello@nexura.ltd as ADMIN with 2FA, preserving go@bitdex.ltd.
"""

import sys
import os
import sqlite3
import jwt
import json
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

DB_PATH = "/opt/tauric-platform-staging/backend/data/tauric_saas.db"
API_BASE = "http://127.0.0.1:8002/api/v1"
JWT_SECRET_KEY = os.getenv("TAURIC_JWT_SECRET", "tauric_super_secret_staging_jwt_key_2026_xyz")
JWT_ALGORITHM = "HS256"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def make_session(user_id, email, role="CUSTOMER"):
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=7)
    session_id = f"SES-{secrets.token_hex(8).upper()}"
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "session_id": session_id,
        "exp": int(exp.timestamp())
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                (session_id, user_id, token_hash, exp.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            )
    finally:
        conn.close()
    return token

def api_call(path, method="GET", data=None, token=None):
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"raw": err_body}

def run_tests():
    print("=" * 70)
    print("STARTING BITDEX AI BALANCE & ADMIN PROVISIONING REGRESSION SUITE")
    print("=" * 70)

    # ─── Test 1: Safety Invariants ─────────────────────────────────────
    status, health = api_call("/health")
    assert status == 200, f"Health check failed: {health}"
    sec = health.get("security", {})
    assert sec.get("live_trading_locked") is True, "live_trading_locked must be True"
    assert sec.get("read_only_mode") is True, "read_only_mode must be True"
    print("✓ [PASS] Safety Locks: live_trading_locked=True, read_only_mode=True verified")

    # ─── Test 2: New Customer Zero-Balance Guarantee ───────────────────
    new_email = f"new_cust_{secrets.token_hex(4)}@bitdex.ltd"
    status, reg = api_call("/saas/auth/register", "POST", {
        "email": new_email,
        "password": "Password123!Secure",
        "first_name": "New",
        "last_name": "Customer",
        "country": "SG"
    })
    assert status == 200, f"Registration failed: {reg}"
    new_uid = reg["user"]["user_id"]
    new_token = make_session(new_uid, new_email, "CUSTOMER")

    # Verify Database Balance is strictly 0.0
    conn = get_db()
    try:
        acct = conn.execute("SELECT * FROM billing_accounts WHERE user_id = ?", (new_uid,)).fetchone()
        assert acct is not None, "Billing account must exist"
        assert float(acct["prepaid_credits_usd"]) == 0.0, f"Expected 0.0 balance, got {acct['prepaid_credits_usd']}"
    finally:
        conn.close()

    # Verify Pricing Endpoint
    status, pricing = api_call("/saas/customer/ai-analysis/pricing", token=new_token)
    assert status == 200, f"Pricing call failed: {pricing}"
    p = pricing["pricing"]
    assert p["prepaid_balance_usd"] == 0.0, f"Expected 0.0, got {p['prepaid_balance_usd']}"
    assert p["price_usd"] == 1.0, f"Expected $1.00 price, got {p['price_usd']}"
    assert p["eligible"] is False, "Customer with $0 must not be eligible"
    assert p["shortfall_usd"] == 1.0, f"Expected shortfall 1.0, got {p['shortfall_usd']}"

    # Attempt AI analysis with $0 balance
    idem_new = f"TEST-IDEMP-{secrets.token_hex(6)}"
    status, run_res = api_call("/saas/customer/ai-analysis/run", "POST", {
        "symbol": "BTCUSDT",
        "market": "CRYPTO",
        "timeframe": "1h",
        "idempotency_key": idem_new
    }, token=new_token)
    assert status == 402, f"Expected HTTP 402 for $0 balance, got {status}: {run_res}"
    print(f"✓ [PASS] New Customer Zero Balance: Initial $0.00 verified, AI analysis rejected with HTTP 402 ({new_email})")

    # ─── Test 3: Customer with $10 Balance ─────────────────────────────
    funded_email = f"funded_cust_{secrets.token_hex(4)}@bitdex.ltd"
    status, reg = api_call("/saas/auth/register", "POST", {
        "email": funded_email,
        "password": "Password123!Secure",
        "first_name": "Funded",
        "last_name": "Customer",
        "country": "SG"
    })
    assert status == 200
    funded_uid = reg["user"]["user_id"]
    funded_token = make_session(funded_uid, funded_email, "CUSTOMER")

    # Credit $10.00
    conn = get_db()
    try:
        with conn:
            conn.execute("UPDATE billing_accounts SET prepaid_credits_usd = 10.0 WHERE user_id = ?", (funded_uid,))
    finally:
        conn.close()

    # Verify Pricing shows $10.00
    status, pricing = api_call("/saas/customer/ai-analysis/pricing", token=funded_token)
    assert status == 200
    assert pricing["pricing"]["prepaid_balance_usd"] == 10.0
    assert pricing["pricing"]["eligible"] is True

    # Execute billable analysis
    idem_funded = f"TEST-IDEMP-{secrets.token_hex(6)}"
    status, run_res = api_call("/saas/customer/ai-analysis/run", "POST", {
        "symbol": "ETHUSDT",
        "market": "CRYPTO",
        "timeframe": "1h",
        "idempotency_key": idem_funded
    }, token=funded_token)
    assert status == 200, f"Analysis failed: {run_res}"
    assert run_res["charged_amount_usd"] == 1.0, f"Expected 1.0 charged, got {run_res['charged_amount_usd']}"
    assert run_res["balance_after_usd"] == 9.0, f"Expected 9.0 post balance, got {run_res['balance_after_usd']}"

    # Verify DB Ledger entry
    conn = get_db()
    try:
        acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (funded_uid,)).fetchone()
        assert float(acct["prepaid_credits_usd"]) == 9.0, f"Expected 9.0 in DB, got {acct['prepaid_credits_usd']}"
        ledger = conn.execute("SELECT * FROM billing_ledger WHERE user_id = ?", (funded_uid,)).fetchall()
        assert len(ledger) == 1, f"Expected exactly 1 ledger row, got {len(ledger)}"
        assert ledger[0]["amount_usd"] == -1.0
        assert ledger[0]["balance_after_usd"] == 9.0
    finally:
        conn.close()
    print("✓ [PASS] Funded Customer ($10): Charged exactly $1.00 USD, post-balance $9.00 USD, ledger verified")

    # ─── Test 4: Idempotent Duplicate Request ──────────────────────────
    status, dup_res = api_call("/saas/customer/ai-analysis/run", "POST", {
        "symbol": "ETHUSDT",
        "market": "CRYPTO",
        "timeframe": "1h",
        "idempotency_key": idem_funded
    }, token=funded_token)
    assert status == 200, f"Duplicate request failed: {dup_res}"
    assert dup_res.get("is_duplicate") is True, "Must be flagged as duplicate"
    assert dup_res["balance_after_usd"] == 9.0, f"Balance must remain 9.0, got {dup_res['balance_after_usd']}"

    conn = get_db()
    try:
        acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (funded_uid,)).fetchone()
        assert float(acct["prepaid_credits_usd"]) == 9.0, f"Duplicate request caused charge! Balance: {acct['prepaid_credits_usd']}"
        ledger = conn.execute("SELECT * FROM billing_ledger WHERE user_id = ?", (funded_uid,)).fetchall()
        assert len(ledger) == 1, "Duplicate request must not write second ledger entry"
    finally:
        conn.close()
    print("✓ [PASS] Idempotency: Duplicate request returned cached result with zero additional charge")

    # ─── Test 5: Unsuccessful Analysis Failure Refund ─────────────────
    idem_fail = f"TEST-FAIL-{secrets.token_hex(6)}"
    status, fail_res = api_call("/saas/customer/ai-analysis/run", "POST", {
        "symbol": "SOLUSDT",
        "market": "CRYPTO",
        "timeframe": "1h",
        "idempotency_key": idem_fail,
        "simulate_failure": True
    }, token=funded_token)
    assert status == 502, f"Expected 502 for failure, got {status}: {fail_res}"
    assert "FAILED_REFUNDED" in str(fail_res), f"Expected FAILED_REFUNDED in {fail_res}"

    conn = get_db()
    try:
        acct = conn.execute("SELECT prepaid_credits_usd FROM billing_accounts WHERE user_id = ?", (funded_uid,)).fetchone()
        assert float(acct["prepaid_credits_usd"]) == 9.0, f"Balance must be restored to 9.0, got {acct['prepaid_credits_usd']}"
        ledger = conn.execute("SELECT entry_type, amount_usd, balance_after_usd FROM billing_ledger WHERE user_id = ? ORDER BY created_at ASC", (funded_uid,)).fetchall()
        assert len(ledger) == 3, f"Expected 3 ledger entries (1 fee, 1 fee, 1 refund), got {len(ledger)}"
        assert ledger[-1]["entry_type"] == "AI_RESEARCH_REFUND"
        assert ledger[-1]["amount_usd"] == 1.0
        assert ledger[-1]["balance_after_usd"] == 9.0
    finally:
        conn.close()
    print("✓ [PASS] Failure Refund: Automatic refund triggered on error, balance restored to $9.00 USD")

    # ─── Test 6: Multi-Tenant Account Isolation (Cust A vs Cust B) ────
    cust_a_email = f"cust_a_{secrets.token_hex(4)}@bitdex.ltd"
    status, reg_a = api_call("/saas/auth/register", "POST", {
        "email": cust_a_email, "password": "Password123!Secure", "first_name": "Alice", "last_name": "A", "country": "SG"
    })
    uid_a = reg_a["user"]["user_id"]
    token_a = make_session(uid_a, cust_a_email, "CUSTOMER")

    cust_b_email = f"cust_b_{secrets.token_hex(4)}@bitdex.ltd"
    status, reg_b = api_call("/saas/auth/register", "POST", {
        "email": cust_b_email, "password": "Password123!Secure", "first_name": "Bob", "last_name": "B", "country": "SG"
    })
    uid_b = reg_b["user"]["user_id"]
    token_b = make_session(uid_b, cust_b_email, "CUSTOMER")

    # Seed Cust A with $5.00, Cust B with $15.00
    conn = get_db()
    try:
        with conn:
            conn.execute("UPDATE billing_accounts SET prepaid_credits_usd = 5.0 WHERE user_id = ?", (uid_a,))
            conn.execute("UPDATE billing_accounts SET prepaid_credits_usd = 15.0 WHERE user_id = ?", (uid_b,))
    finally:
        conn.close()

    # Cust A checks pricing -> 5.0
    _, p_a = api_call("/saas/customer/ai-analysis/pricing", token=token_a)
    assert p_a["pricing"]["prepaid_balance_usd"] == 5.0

    # Cust B checks pricing -> 15.0
    _, p_b = api_call("/saas/customer/ai-analysis/pricing", token=token_b)
    assert p_b["pricing"]["prepaid_balance_usd"] == 15.0

    # Cust A executes AI analysis ($1.00)
    status, _ = api_call("/saas/customer/ai-analysis/run", "POST", {
        "symbol": "BTCUSDT", "market": "CRYPTO", "timeframe": "1h", "idempotency_key": f"IDEMP-A-{secrets.token_hex(4)}"
    }, token=token_a)
    assert status == 200

    # Verify Cust A is now 4.0, Cust B remains strictly 15.0
    _, p_a2 = api_call("/saas/customer/ai-analysis/pricing", token=token_a)
    assert p_a2["pricing"]["prepaid_balance_usd"] == 4.0, f"Expected 4.0 for A, got {p_a2['pricing']['prepaid_balance_usd']}"

    _, p_b2 = api_call("/saas/customer/ai-analysis/pricing", token=token_b)
    assert p_b2["pricing"]["prepaid_balance_usd"] == 15.0, f"Cust B balance contaminated! Expected 15.0, got {p_b2['pricing']['prepaid_balance_usd']}"
    print("✓ [PASS] Multi-Tenant Isolation: Cust A ($5.00->$4.00) and Cust B ($15.00) verified completely isolated")

    # ─── Test 7: Public Registration Role Escalation Rejection ────────
    hacker_email = f"hacker_{secrets.token_hex(4)}@example.com"
    status, reg_hack = api_call("/saas/auth/register", "POST", {
        "email": hacker_email,
        "password": "Password123!Secure",
        "first_name": "Hacker",
        "last_name": "Escalation",
        "country": "SG",
        "role": "ADMIN"  # Attempt to inject ADMIN
    })
    assert status == 200
    assert reg_hack["user"]["role"] == "CUSTOMER", f"Privilege escalation vulnerability! Got {reg_hack['user']['role']}"

    hack_token = make_session(reg_hack["user"]["user_id"], hacker_email, "CUSTOMER")
    status, _ = api_call("/saas/admin/customers", token=hack_token)
    assert status == 403, f"Non-admin reached admin console! Status: {status}"
    print("✓ [PASS] Role Escalation Rejection: Attempted ADMIN registration created strictly as CUSTOMER; admin endpoint 403")

    # ─── Test 8: Administrator Verification for hello@nexura.ltd ──────
    conn = get_db()
    try:
        admin_row = conn.execute("SELECT * FROM users WHERE email = 'hello@nexura.ltd'").fetchone()
        assert admin_row is not None, "hello@nexura.ltd must exist"
        assert admin_row["role"] == "ADMIN", f"Expected ADMIN role, got {admin_row['role']}"
        assert admin_row["status"] == "ACTIVE", f"Expected ACTIVE status, got {admin_row['status']}"
        assert admin_row["two_factor_enabled"] == 1, "Mandatory 2FA must be enabled for admin"

        # Verify go@bitdex.ltd remains the official primary admin
        go_row = conn.execute("SELECT * FROM users WHERE email = 'go@bitdex.ltd'").fetchone()
        assert go_row is not None, "go@bitdex.ltd must exist"
        assert go_row["role"] == "ADMIN", "go@bitdex.ltd must remain ADMIN"
        assert go_row["status"] == "ACTIVE", "go@bitdex.ltd must remain ACTIVE"
    finally:
        conn.close()

    admin_token = make_session(admin_row["user_id"], "hello@nexura.ltd", "ADMIN")
    status, admin_data = api_call("/saas/admin/customers", token=admin_token)
    assert status == 200, f"Admin console access failed: {admin_data}"
    assert "customers" in admin_data, "Admin data must contain customers"
    print("✓ [PASS] Admin Provisioning & Verification: hello@nexura.ltd verified as ADMIN with 2FA; Admin Console accessible")

    print("=" * 70)
    print("ALL 8 REGRESSION SUITES PASSED SUCCESSFULLY")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
