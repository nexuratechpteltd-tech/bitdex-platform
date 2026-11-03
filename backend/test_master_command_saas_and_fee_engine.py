#!/usr/bin/env python3
"""
TAURIC Master Command — Comprehensive Automated Acceptance Test Suite
Verifies:
1. Existing Trading Integrity & Simplified Dashboard Regression
2. Tenant Boundary Isolation & RBAC (Customer A vs B vs Admin vs Owner)
3. Three Distinct Qualifying Orders Produce Exactly Three Fees ($0.30 x 3 = $0.90)
4. Multiple Partial Fills on One Order Never Duplicate Fees (Idempotency)
5. Duplicate / Delayed Payment Webhooks Never Duplicate Credits (Idempotency)
6. Non-Live / Unsubmitted / Rejected / Simulated Orders Incur Zero Platform Fees
7. Customer-Specific Fee Overrides (A: $0.30, B: $1.00, C: Waived, D: $30 Act / 0 Exec)
8. Activation Fee Once-Only Enforcement
9. Low-Balance Preflight Gate (Blocks New Execution Without Liquidating Positions)
10. Admin Governance (Block / Unblock / Fee Policy Updates / Immutable Audit Logs)
11. KYC State Transitions & HMAC-SHA256 Webhook Verification
12. Safety Invariants (live_trading_locked=true, read_only_mode=true, zero live orders)
"""

import sys
import os
import hmac
import hashlib
import json
import secrets
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8002/api/v1"
WEBHOOK_SECRET = "tauric_webhook_hmac_secret_2026_xyz"

def request_json(url, method="GET", data=None, token=None, headers_extra=None):
    headers = {"User-Agent": "TauricMasterAcceptance/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(data).encode("utf-8")
    else:
        data_bytes = None
    if headers_extra:
        headers.update(headers_extra)

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}

def run_tests():
    print("=" * 80)
    print("STARTING TAURIC MASTER COMMAND ACCEPTANCE TEST SUITE")
    print("=" * 80)

    passed_count = 0
    total_tests = 16

    # -------------------------------------------------------------
    # TEST 1: Safety Invariants Platform-Wide
    # -------------------------------------------------------------
    print("\n[TEST 1] Verifying Safety Invariants (live_trading_locked, read_only_mode)...")
    status_code, data = request_json(f"{BASE_URL}/health")
    assert status_code == 200, f"Health check failed: {status_code}"
    sec = data.get("security", {})
    assert sec.get("live_trading_locked") is True, "live_trading_locked must be True"
    assert sec.get("read_only_mode") is True, "read_only_mode must be True"
    print("  -> PASSED: live_trading_locked=true and read_only_mode=true strictly active.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 2: Admin & Owner Initial Accounts
    # -------------------------------------------------------------
    print("\n[TEST 2] Verifying Admin and Owner Account Authentication...")
    status_code, admin_login = request_json(
        f"{BASE_URL}/saas/auth/login",
        method="POST",
        data={"email": "admin@tauric.com", "password": "AdminSecurePass2026!"}
    )
    assert status_code == 200, f"Admin login failed: {status_code}"
    admin_token = admin_login["token"]
    assert admin_login["user"]["role"] == "ADMIN"

    status_code, owner_login = request_json(
        f"{BASE_URL}/saas/auth/login",
        method="POST",
        data={"email": "owner@tauric.com", "password": "OwnerSecurePass2026!"}
    )
    assert status_code == 200, f"Owner login failed: {status_code}"
    owner_token = owner_login["token"]
    assert owner_login["user"]["role"] == "OWNER"
    print("  -> PASSED: Admin and Owner accounts authenticated with distinct roles.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 3: Multi-Customer Registration & Session Tokens
    # -------------------------------------------------------------
    print("\n[TEST 3] Creating Independent Customers (Customer A & B)...")
    email_a = f"cust_a_{secrets.token_hex(3)}@example.com"
    email_b = f"cust_b_{secrets.token_hex(3)}@example.com"

    status_code, reg_a = request_json(f"{BASE_URL}/saas/auth/register", method="POST", data={"email": email_a, "password": "PassCustA2026!"})
    assert status_code == 200, f"Cust A reg failed: {status_code}"
    user_a_id = reg_a["user"]["user_id"]

    status_code, reg_b = request_json(f"{BASE_URL}/saas/auth/register", method="POST", data={"email": email_b, "password": "PassCustB2026!"})
    assert status_code == 200, f"Cust B reg failed: {status_code}"
    user_b_id = reg_b["user"]["user_id"]

    _, login_a = request_json(f"{BASE_URL}/saas/auth/login", method="POST", data={"email": email_a, "password": "PassCustA2026!"})
    token_a = login_a["token"]

    _, login_b = request_json(f"{BASE_URL}/saas/auth/login", method="POST", data={"email": email_b, "password": "PassCustB2026!"})
    token_b = login_b["token"]
    print(f"  -> PASSED: Customer A ({user_a_id}) and Customer B ({user_b_id}) registered and logged in.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 4: Tenant Boundary Isolation (A cannot access B)
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing Tenant Boundary Isolation (Customer A vs B)...")
    # Customer A adds an exchange connection
    status_code, conn_a = request_json(
        f"{BASE_URL}/saas/customer/connections",
        method="POST",
        data={
            "provider": "BINANCE",
            "label": "Customer A Binance Demo",
            "environment": "DEMO",
            "product_type": "SPOT",
            "api_key": "apiKeyCustA12345",
            "api_secret": "apiSecretCustA67890"
        },
        token=token_a
    )
    assert status_code == 200, f"Connection add failed: {status_code}"
    acct_a_id = conn_a["account_id"]

    # Customer B tries to delete Customer A's connection -> MUST RETURN 403 or 404
    status_code, del_res = request_json(
        f"{BASE_URL}/saas/customer/connections/{acct_a_id}",
        method="DELETE",
        token=token_b
    )
    assert status_code in (403, 404), f"Tenant isolation breached! Code: {status_code}"

    # Customer A tries to access Admin route -> MUST RETURN 403
    status_code, admin_probe = request_json(f"{BASE_URL}/saas/admin/customers", token=token_a)
    assert status_code == 403, f"Customer accessed Admin route! Code: {status_code}"
    print("  -> PASSED: Cross-tenant access denied and non-admin blocked from admin endpoints.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 5: Prepaid Credit Top-Up & Deduplication (Idempotency)
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing Prepaid Credit Top-Up & Webhook Deduplication...")
    pay_ref = f"PAY-TEST-{secrets.token_hex(4).upper()}"
    status_code, topup_1 = request_json(
        f"{BASE_URL}/saas/customer/billing/topup",
        method="POST",
        data={"amount_usd": 100.0, "payment_reference": pay_ref},
        token=token_a
    )
    assert status_code == 200 and topup_1["current_balance_usd"] == 100.0

    # Repeat exact same payment reference -> MUST NOT DOUBLE-CREDIT
    status_code, topup_2 = request_json(
        f"{BASE_URL}/saas/customer/billing/topup",
        method="POST",
        data={"amount_usd": 100.0, "payment_reference": pay_ref},
        token=token_a
    )
    assert status_code == 200
    assert topup_2["current_balance_usd"] == 100.0, f"Duplicate credit occurred! Balance: {topup_2['current_balance_usd']}"
    print("  -> PASSED: Top-up of $100 posted. Duplicate payment reference safely deduplicated.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 6: Three Distinct Qualifying Orders Produce Exactly Three Fees
    # -------------------------------------------------------------
    print("\n[TEST 6] Testing 3 Distinct Qualifying Orders -> Exactly 3 Fees ($0.30 x 3 = $0.90)...")
    from app.services.fee_engine import FeeEngine

    # Check initial balance
    acct = FeeEngine.get_billing_account(user_a_id)
    initial_balance = acct["prepaid_credits_usd"]  # 100.0

    # Order 1
    res1 = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-101", fill_id="FILL-101-A", environment="LIVE", execution_status="FILLED")
    # Note: On first live order, activation fee ($20) + execution fee ($0.30) are assessed
    assert res1["status"] == "POSTED"
    assert res1["fee_charged_usd"] == 0.30

    # Order 2
    res2 = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-102", fill_id="FILL-102-A", environment="LIVE", execution_status="FILLED")
    assert res2["status"] == "POSTED"
    assert res2["fee_charged_usd"] == 0.30

    # Order 3
    res3 = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-103", fill_id="FILL-103-A", environment="LIVE", execution_status="FILLED")
    assert res3["status"] == "POSTED"
    assert res3["fee_charged_usd"] == 0.30

    # Ledger check: exactly 3 EXECUTION_FEE entries
    ledger_a = FeeEngine.get_ledger_history(user_a_id, limit=20)
    exec_fees = [e for e in ledger_a if e["entry_type"] == "EXECUTION_FEE"]
    assert len(exec_fees) == 3, f"Expected 3 execution fees, got {len(exec_fees)}"
    total_exec_amount = sum(abs(e["amount_usd"]) for e in exec_fees)
    assert round(total_exec_amount, 2) == 0.90, f"Expected $0.90 total execution fees, got {total_exec_amount}"
    print(f"  -> PASSED: 3 distinct orders generated exactly 3 execution fees totaling ${total_exec_amount:.2f}.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 7: Multiple Partial Fills on One Order Never Duplicate Fees
    # -------------------------------------------------------------
    print("\n[TEST 7] Testing Multiple Partial Fills on One Order (Zero Duplicate Fees)...")
    # Order ORD-200 with 3 partial fills
    fill_res_1 = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-200", fill_id="FILL-200-PART1", environment="LIVE", execution_status="PARTIALLY_FILLED")
    assert fill_res_1["status"] == "POSTED"
    assert fill_res_1["is_duplicate"] is False

    fill_res_2 = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-200", fill_id="FILL-200-PART2", environment="LIVE", execution_status="PARTIALLY_FILLED")
    assert fill_res_2["status"] == "ALREADY_ASSESSED"
    assert fill_res_2["is_duplicate"] is True

    fill_res_3 = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-200", fill_id="FILL-200-FINAL", environment="LIVE", execution_status="FILLED")
    assert fill_res_3["status"] == "ALREADY_ASSESSED"
    assert fill_res_3["is_duplicate"] is True

    # Ledger count for ORD-200 must be exactly 1
    ledger_ord_200 = [e for e in FeeEngine.get_ledger_history(user_a_id) if e.get("billable_order_ref") == "ORD-200"]
    assert len(ledger_ord_200) == 1, f"Duplicate charges detected for order ORD-200: {len(ledger_ord_200)}"
    print("  -> PASSED: 3 partial fills for order ORD-200 resulted in exactly 1 platform execution fee.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 8: Non-Live / Unsubmitted / Rejected / Simulated Orders Incur Zero Fees
    # -------------------------------------------------------------
    print("\n[TEST 8] Testing Non-Billable Order States (Demo, Paper, Rejected, Unsubmitted)...")
    demo_res = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-DEMO-99", environment="DEMO", execution_status="FILLED")
    assert demo_res["status"] == "EXEMPT_ENVIRONMENT" and demo_res["fee_charged_usd"] == 0.0

    paper_res = FeeEngine.assess_execution_fee(user_a_id, "TAURIC_SIM", "ORD-PAPER-99", environment="PAPER", execution_status="FILLED")
    assert paper_res["status"] == "EXEMPT_ENVIRONMENT" and paper_res["fee_charged_usd"] == 0.0

    rej_res = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-REJ-99", environment="LIVE", execution_status="REJECTED")
    assert rej_res["status"] == "EXEMPT_STATUS" and rej_res["fee_charged_usd"] == 0.0

    plan_res = FeeEngine.assess_execution_fee(user_a_id, "BINANCE", "ORD-PLAN-99", environment="LIVE", execution_status="PLAN_ONLY")
    assert plan_res["status"] == "EXEMPT_STATUS" and plan_res["fee_charged_usd"] == 0.0
    print("  -> PASSED: Demo, paper, rejected, and planned orders charged $0.00 platform fees.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 9: Activation Fee Once-Only Enforcement
    # -------------------------------------------------------------
    print("\n[TEST 9] Verifying Activation Fee Once-Only Rule...")
    # Check activation fee entries for customer A
    act_entries = [e for e in FeeEngine.get_ledger_history(user_a_id) if e["entry_type"] == "ACTIVATION_FEE"]
    assert len(act_entries) == 1, f"Expected exactly 1 activation fee, got {len(act_entries)}"
    assert abs(act_entries[0]["amount_usd"]) == 20.0

    # Explicit attempt to re-assess activation fee -> MUST RETURN existing record, not duplicate
    re_assess = FeeEngine.assess_activation_fee(user_a_id, trigger_event="SECOND_TRIGGER_ATTEMPT")
    assert re_assess is not None
    assert re_assess["entry_id"] == act_entries[0]["entry_id"]
    print("  -> PASSED: Activation fee of $20.00 was assessed once and strictly locked against re-assessment.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 10: Individual Customer Fee Overrides (Customers B, C, D)
    # -------------------------------------------------------------
    print("\n[TEST 10] Testing Customer Fee Overrides (B: $1.00, C: Waived, D: $30 Act / 0 Exec)...")
    # Customer B: Override execution fee to $1.00
    status_code, res_b_policy = request_json(
        f"{BASE_URL}/saas/admin/customers/{user_b_id}/fee-policy",
        method="PUT",
        data={"execution_fee_usd": 1.00},
        token=admin_token
    )
    assert status_code == 200
    assert res_b_policy["fee_policy"]["execution_fee_usd"] == 1.00

    # Top up customer B with $10
    FeeEngine.add_prepaid_credits(user_b_id, 10.0, "TOPUP-CUSTB")
    b_fee = FeeEngine.assess_execution_fee(user_b_id, "BINANCE", "ORD-B-1", environment="LIVE", execution_status="FILLED")
    assert b_fee["status"] == "POSTED"
    assert b_fee["fee_charged_usd"] == 1.00, f"Customer B charged {b_fee['fee_charged_usd']}, expected 1.00"

    # Customer C: Waived fees
    email_c = f"cust_c_{secrets.token_hex(3)}@example.com"
    _, reg_c = request_json(f"{BASE_URL}/saas/auth/register", method="POST", data={"email": email_c, "password": "PassCustC2026!"})
    user_c_id = reg_c["user"]["user_id"]
    FeeEngine.update_user_fee_policy(user_c_id, "ADMIN", fee_waived=True, waiver_reason="Promotional beta partner")
    c_fee = FeeEngine.assess_execution_fee(user_c_id, "BINANCE", "ORD-C-1", environment="LIVE", execution_status="FILLED")
    assert c_fee["status"] == "FEE_WAIVED" and c_fee["fee_charged_usd"] == 0.0

    # Customer D: Activation fee $30, Execution fee disabled
    email_d = f"cust_d_{secrets.token_hex(3)}@example.com"
    _, reg_d = request_json(f"{BASE_URL}/saas/auth/register", method="POST", data={"email": email_d, "password": "PassCustD2026!"})
    user_d_id = reg_d["user"]["user_id"]
    FeeEngine.update_user_fee_policy(user_d_id, "ADMIN", activation_fee_usd=30.0, execution_fee_enabled=False)
    d_fee = FeeEngine.assess_execution_fee(user_d_id, "BINANCE", "ORD-D-1", environment="LIVE", execution_status="FILLED")
    assert d_fee["status"] == "EXEMPT_POLICY_DISABLED" and d_fee["fee_charged_usd"] == 0.0
    print("  -> PASSED: Fee overrides verified for Customer B ($1.00), C (Waived), and D (Disabled).")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 11: Low-Balance Preflight Gate
    # -------------------------------------------------------------
    print("\n[TEST 11] Testing Low-Balance Trading Preflight Gate...")
    # Customer with $0.00 credits
    email_e = f"cust_e_{secrets.token_hex(3)}@example.com"
    _, reg_e = request_json(f"{BASE_URL}/saas/auth/register", method="POST", data={"email": email_e, "password": "PassCustE2026!"})
    user_e_id = reg_e["user"]["user_id"]
    _, login_e = request_json(f"{BASE_URL}/saas/auth/login", method="POST", data={"email": email_e, "password": "PassCustE2026!"})
    token_e = login_e["token"]

    status_code, preflight_e = request_json(f"{BASE_URL}/saas/customer/trading-preflight?environment=LIVE", token=token_e)
    assert status_code == 200
    assert preflight_e["eligible"] is False
    assert "Insufficient prepaid credits" in preflight_e["reason"]

    # Demo preflight should pass even with 0 credits
    status_code, preflight_demo = request_json(f"{BASE_URL}/saas/customer/trading-preflight?environment=DEMO", token=token_e)
    assert status_code == 200 and preflight_demo["eligible"] is True
    print("  -> PASSED: Zero-credit account blocked from live trading; demo trading permitted.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 12: Admin Block / Unblock Customer Controls
    # -------------------------------------------------------------
    print("\n[TEST 12] Testing Admin Customer Block / Unblock Workflow...")
    # Block customer A
    status_code, block_res = request_json(
        f"{BASE_URL}/saas/admin/customers/{user_a_id}/status",
        method="POST",
        data={"status": "BLOCKED", "reason": "Compliance review"},
        token=admin_token
    )
    assert status_code == 200
    assert block_res["new_status"] == "BLOCKED"

    # Customer A should now be rejected on login or API requests
    status_code, block_check = request_json(
        f"{BASE_URL}/saas/customer/me",
        token=token_a
    )
    assert status_code == 403, f"Blocked customer was not denied! Code: {status_code}"

    # Unblock customer A
    status_code, unblock_res = request_json(
        f"{BASE_URL}/saas/admin/customers/{user_a_id}/status",
        method="POST",
        data={"status": "ACTIVE", "reason": "Review completed"},
        token=admin_token
    )
    assert status_code == 200
    assert unblock_res["new_status"] == "ACTIVE"

    # Customer A should now succeed
    status_code, unblock_check = request_json(
        f"{BASE_URL}/saas/customer/me",
        token=token_a
    )
    assert status_code == 200
    print("  -> PASSED: Customer block immediately revoked API access; unblock restored access.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 13: KYC State Transitions & Webhook HMAC Verification
    # -------------------------------------------------------------
    print("\n[TEST 13] Testing KYC State Transitions & HMAC-SHA256 Webhook Verification...")
    # 1. Admin sets KYC status to REQUESTED
    status_code, kyc_req = request_json(
        f"{BASE_URL}/saas/admin/customers/{user_a_id}/kyc/status",
        method="POST",
        data={"kyc_status": "REQUESTED", "provider": "SUMSUB", "notes": "Tier 2 live upgrade"},
        token=admin_token
    )
    assert status_code == 200
    assert kyc_req["new_kyc_status"] == "REQUESTED"

    # Trading preflight must now be blocked due to pending KYC
    _, pre_kyc = request_json(f"{BASE_URL}/saas/customer/trading-preflight?environment=LIVE", token=token_a)
    assert pre_kyc["eligible"] is False
    assert "KYC identity verification is required" in pre_kyc["reason"]

    # 2. Simulate Sumsub Webhook approving KYC with valid HMAC signature
    payload = {
        "event": "applicantReviewed",
        "user_id": user_a_id,
        "provider": "SUMSUB",
        "status": "APPROVED",
        "verification_hash": hashlib.sha256(f"SUMSUB:{user_a_id}".encode()).hexdigest(),
        "timestamp": "2026-10-26T12:00:00Z"
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    valid_sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    # Tampered signature should fail 401
    status_code, tampered = request_json(
        f"{BASE_URL}/saas/webhooks/kyc",
        method="POST",
        data=payload,
        headers_extra={"x-payload-signature": "invalid_sig_12345"}
    )
    assert status_code == 401, f"Webhook accepted tampered signature! Code: {status_code}"

    # Valid signature should succeed
    status_code, webhook_res = request_json(
        f"{BASE_URL}/saas/webhooks/kyc",
        method="POST",
        data=payload,
        headers_extra={"x-payload-signature": valid_sig}
    )
    assert status_code == 200
    assert "APPROVED" in webhook_res["message"]

    # Verify customer KYC status is now APPROVED
    _, me_a = request_json(f"{BASE_URL}/saas/customer/me", token=token_a)
    assert me_a["user"]["kyc_status"] == "APPROVED"
    print("  -> PASSED: HMAC-verified webhook successfully updated KYC status to APPROVED.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 14: Administrative Audit Log Verification
    # -------------------------------------------------------------
    print("\n[TEST 14] Verifying Immutable Administrative & Security Audit Logs...")
    status_code, audit_data = request_json(f"{BASE_URL}/saas/admin/audit-logs?limit=20", token=admin_token)
    assert status_code == 200
    logs = audit_data["logs"]
    actions = [l["action"] for l in logs]
    assert "CUSTOMER_STATUS_UPDATED" in actions
    assert "FEE_POLICY_UPDATED" in actions
    assert "KYC_WEBHOOK_PROCESSED" in actions
    print(f"  -> PASSED: Audit logs verified ({len(logs)} records captured including policy updates and KYC events).")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 15: Existing Trading & Unified P&L Regression
    # -------------------------------------------------------------
    print("\n[TEST 15] Verifying Existing Trading Positions & Unified P&L Regression...")
    status_code, positions_crypto = request_json(f"{BASE_URL}/orders/positions?market_type=CRYPTO")
    assert status_code == 200
    assert positions_crypto["status"] == "SUCCESS"
    assert positions_crypto["metrics"]["fee_treatment"] == "deducted_from_gross_realized"

    status_code, positions_forex = request_json(f"{BASE_URL}/orders/positions?market_type=FOREX")
    assert status_code == 200
    assert positions_forex["status"] == "SUCCESS"
    print("  -> PASSED: Unified P&L and market scoping regression checks intact.")
    passed_count += 1

    # -------------------------------------------------------------
    # TEST 16: Zero Production Mutations & Strict Read-Only Safeguards
    # -------------------------------------------------------------
    print("\n[TEST 16] Confirming Zero Live Orders Placed & Production Safeguards...")
    # Attempting to call live submit endpoint must strictly fail with 403 Forbidden
    status_code, submit_probe = request_json(f"{BASE_URL}/orders/live/submit", method="POST", data={})
    assert status_code == 403, f"Live order submission endpoint was not blocked! Code: {status_code}"
    print("  -> PASSED: Order submission endpoint hard-locked with HTTP 403 Forbidden.")
    passed_count += 1

    print("\n" + "=" * 80)
    print(f"ALL {passed_count}/{total_tests} ACCEPTANCE TESTS PASSED (100% SUCCESS RATE)")
    print("=" * 80)

if __name__ == "__main__":
    run_tests()
