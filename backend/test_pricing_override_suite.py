#!/usr/bin/env python3
"""
Comprehensive Automated Test Suite: Customer Pricing Override
Environment: STAGING ONLY (port 8002 / Tauric SaaS API)
Covers all 8 mandatory validation scenarios:
  1. Valid positive price override ($0.15 on STRATEGY_EXECUTION, confirm=True)
  2. Zero price override ($0.00 on STRATEGY_EXECUTION, confirm=True)
  3. Missing / short reason (reason="" or "ab" -> HTTP 400 / 422)
  4. Invalid negative price (price_usd=-5.0 -> HTTP 400)
  5. Invalid service (service_id="INVALID_SERVICE" -> HTTP 400)
  6. Unauthorized admin (customer token -> HTTP 403, unauthenticated -> HTTP 401)
  7. Successful persistence (customer_pricing_overrides, pricing_change_log, audit_logs)
  8. Customer-facing updated price (GET /api/v1/saas/customer/me and FeeEngine)
"""

import sys
import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import httpx
import jwt

# Add backend directory to sys.path
backend_dir = "/opt/tauric-platform-staging/backend"
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.config import settings
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
from app.services.fee_engine import FeeEngine
from app.services.pricing_service import resolve, resolve_all

DB_PATH = "/opt/tauric-platform-staging/backend/data/tauric_saas.db"
BASE_URL = "http://127.0.0.1:8002"

ADMIN_USER_ID = "USR-66BCFD7350"  # admin@tauric.com
CUSTOMER_USER_ID = "USR-328E147ACA"  # customera@example.com

def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=2)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def run_tests():
    admin_token = make_token(ADMIN_USER_ID)
    customer_token = make_token(CUSTOMER_USER_ID)

    admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    customer_headers = {"Authorization": f"Bearer {customer_token}", "Content-Type": "application/json"}

    client = httpx.Client(base_url=BASE_URL, timeout=15.0)

    results = {}
    print("=" * 70)
    print("STARTING BITDEX PRICING OVERRIDE AUTOMATED TEST SUITE")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Target: {BASE_URL} | DB: {DB_PATH}")
    print("=" * 70)

    # -------------------------------------------------------------
    # Scenario 1: Valid positive price override ($0.15 on STRATEGY_EXECUTION)
    # -------------------------------------------------------------
    print("\n[Scenario 1] Valid positive price override ($0.15 on STRATEGY_EXECUTION, confirm=True)...")
    payload1 = {
        "service_id": "STRATEGY_EXECUTION",
        "price_usd": 0.15,
        "reason": "VIP Institutional partnership negotiated execution fee",
        "confirm": True
    }
    r1 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_USER_ID}/pricing/override",
                     headers=admin_headers, json=payload1)
    print(f"  Response Status: {r1.status_code}")
    print(f"  Response Body: {r1.json()}")
    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.text}"
    body1 = r1.json()
    assert body1.get("status") == "SUCCESS", "Status must be SUCCESS"
    assert body1.get("effective_pricing", {}).get("price_usd") == 0.15, "Effective price must be 0.15"
    results["scenario_1_valid_positive"] = "PASSED (HTTP 200, price_usd=0.15)"

    # -------------------------------------------------------------
    # Scenario 2: Zero price override ($0.00 on STRATEGY_EXECUTION)
    # -------------------------------------------------------------
    print("\n[Scenario 2] Zero price override ($0.00 on STRATEGY_EXECUTION, confirm=True)...")
    payload2 = {
        "service_id": "STRATEGY_EXECUTION",
        "price_usd": 0.0,
        "reason": "Trial tier zero execution fees promotion",
        "confirm": True
    }
    r2 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_USER_ID}/pricing/override",
                     headers=admin_headers, json=payload2)
    print(f"  Response Status: {r2.status_code}")
    print(f"  Response Body: {r2.json()}")
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
    body2 = r2.json()
    assert body2.get("status") == "SUCCESS", "Status must be SUCCESS"
    assert body2.get("effective_pricing", {}).get("price_usd") == 0.0, "Effective price must be 0.0"
    results["scenario_2_zero_price"] = "PASSED (HTTP 200, price_usd=0.0)"

    # -------------------------------------------------------------
    # Scenario 3: Missing or short reason (reason="" or "ab" -> 400 or 422)
    # -------------------------------------------------------------
    print("\n[Scenario 3] Missing or short reason (reason='ab' < 3 chars)...")
    payload3 = {
        "service_id": "STRATEGY_EXECUTION",
        "price_usd": 0.20,
        "reason": "ab",
        "confirm": True
    }
    r3 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_USER_ID}/pricing/override",
                     headers=admin_headers, json=payload3)
    print(f"  Response Status: {r3.status_code}")
    print(f"  Response Body: {r3.text}")
    assert r3.status_code in (400, 422), f"Expected 400/422 for short reason, got {r3.status_code}"
    results["scenario_3_short_reason"] = f"PASSED (HTTP {r3.status_code} validation error properly rejected)"

    # -------------------------------------------------------------
    # Scenario 4: Invalid negative price (price_usd=-5.0 -> HTTP 400)
    # -------------------------------------------------------------
    print("\n[Scenario 4] Invalid negative price (price_usd=-5.0)...")
    payload4 = {
        "service_id": "STRATEGY_EXECUTION",
        "price_usd": -5.0,
        "reason": "Testing negative price rejection",
        "confirm": True
    }
    r4 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_USER_ID}/pricing/override",
                     headers=admin_headers, json=payload4)
    print(f"  Response Status: {r4.status_code}")
    print(f"  Response Body: {r4.text}")
    assert r4.status_code == 400, f"Expected 400 for negative price, got {r4.status_code}"
    results["scenario_4_negative_price"] = "PASSED (HTTP 400 price cannot be negative properly rejected)"

    # -------------------------------------------------------------
    # Scenario 5: Invalid service (service_id="INVALID_SERVICE" -> HTTP 400)
    # -------------------------------------------------------------
    print("\n[Scenario 5] Invalid service identifier (service_id='INVALID_SERVICE')...")
    payload5 = {
        "service_id": "INVALID_SERVICE",
        "price_usd": 5.0,
        "reason": "Testing unknown service rejection",
        "confirm": True
    }
    r5 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_USER_ID}/pricing/override",
                     headers=admin_headers, json=payload5)
    print(f"  Response Status: {r5.status_code}")
    print(f"  Response Body: {r5.text}")
    assert r5.status_code == 400, f"Expected 400 for invalid service, got {r5.status_code}"
    results["scenario_5_invalid_service"] = "PASSED (HTTP 400 unknown service rejected)"

    # -------------------------------------------------------------
    # Scenario 6: Unauthorized access (customer token -> HTTP 403, unauthenticated -> HTTP 401)
    # -------------------------------------------------------------
    print("\n[Scenario 6] Unauthorized access checks...")
    # 6a. Customer token
    r6a = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_USER_ID}/pricing/override",
                      headers=customer_headers, json=payload1)
    print(f"  Customer token access response: {r6a.status_code}")
    assert r6a.status_code == 403, f"Expected 403 for non-admin customer, got {r6a.status_code}"
    
    # 6b. No token
    r6b = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_USER_ID}/pricing/override",
                      json=payload1)
    print(f"  No token access response: {r6b.status_code}")
    assert r6b.status_code in (401, 403), f"Expected 401/403 for unauthenticated, got {r6b.status_code}"
    results["scenario_6_unauthorized"] = f"PASSED (Customer: HTTP {r6a.status_code}, Anonymous: HTTP {r6b.status_code})"

    # -------------------------------------------------------------
    # Scenario 7: Successful persistence (database check)
    # -------------------------------------------------------------
    print("\n[Scenario 7] Checking persistence in SQLite database tables...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 7a. customer_pricing_overrides
    row_ovr = conn.execute(
        "SELECT * FROM customer_pricing_overrides WHERE user_id = ? AND service_id = 'STRATEGY_EXECUTION'",
        (CUSTOMER_USER_ID,)
    ).fetchone()
    print(f"  customer_pricing_overrides row: {dict(row_ovr) if row_ovr else None}")
    assert row_ovr is not None, "Override row not found in customer_pricing_overrides"
    assert row_ovr["price_usd"] == 0.0, f"Expected 0.0, got {row_ovr['price_usd']}"
    assert row_ovr["status"] == "ACTIVE", "Override status must be ACTIVE"

    # 7b. pricing_change_log
    row_log = conn.execute(
        "SELECT * FROM pricing_change_log WHERE user_id = ? AND service_id = 'STRATEGY_EXECUTION' ORDER BY created_at DESC LIMIT 1",
        (CUSTOMER_USER_ID,)
    ).fetchone()
    print(f"  pricing_change_log latest: {dict(row_log) if row_log else None}")
    assert row_log is not None, "Log entry not found in pricing_change_log"
    assert row_log["new_price_usd"] == 0.0, f"Expected new_price_usd 0.0, got {row_log['new_price_usd']}"

    # 7c. audit_logs
    row_audit = conn.execute(
        "SELECT * FROM audit_logs WHERE target_user_id = ? AND action = 'CUSTOMER_PRICE_OVERRIDE_SET' ORDER BY created_at DESC LIMIT 1",
        (CUSTOMER_USER_ID,)
    ).fetchone()
    print(f"  audit_logs latest: {dict(row_audit) if row_audit else None}")
    assert row_audit is not None, "Audit log not found for CUSTOMER_PRICE_OVERRIDE_SET"
    
    # 7d. fee_policies sync
    row_fp = conn.execute(
        "SELECT * FROM fee_policies WHERE user_id = ?",
        (CUSTOMER_USER_ID,)
    ).fetchone()
    print(f"  fee_policies row: {dict(row_fp) if row_fp else None}")
    assert row_fp is not None, "fee_policies row missing"
    assert row_fp["execution_fee_usd"] == 0.0, f"Expected fee_policies execution_fee_usd 0.0, got {row_fp['execution_fee_usd']}"

    conn.close()
    results["scenario_7_persistence"] = "PASSED (Verified customer_pricing_overrides, pricing_change_log, audit_logs, fee_policies)"

    # -------------------------------------------------------------
    # Scenario 8: Customer-facing updated price (Customer Portal & FeeEngine)
    # -------------------------------------------------------------
    print("\n[Scenario 8] Verifying customer-facing rate in Customer Portal & FeeEngine...")
    
    # 8a. Customer profile endpoint GET /api/v1/saas/customer/me
    r8_cust = client.get("/api/v1/saas/customer/me", headers=customer_headers)
    print(f"  Customer /me Status: {r8_cust.status_code}")
    body8 = r8_cust.json()
    fp_cust = body8.get("fee_policy", {})
    print(f"  Customer fee_policy: {fp_cust}")
    assert r8_cust.status_code == 200, f"Expected 200 from /me, got {r8_cust.status_code}"
    assert fp_cust.get("execution_fee_usd") == 0.0, f"Expected 0.0 execution fee in customer portal, got {fp_cust.get('execution_fee_usd')}"

    # 8b. FeeEngine.get_user_fee_policy
    engine_fp = FeeEngine.get_user_fee_policy(CUSTOMER_USER_ID)
    print(f"  FeeEngine.get_user_fee_policy: {engine_fp}")
    assert engine_fp["execution_fee_usd"] == 0.0, f"Expected 0.0 in FeeEngine, got {engine_fp['execution_fee_usd']}"

    # 8c. FeeEngine execution fee deduction check with $0.00
    # FeeEngine.assess_execution_fee with rate = 0.0 should produce ZERO_FEE_RATE without error or charge
    charge_result = FeeEngine.assess_execution_fee(
        user_id=CUSTOMER_USER_ID,
        exchange="BINANCE",
        order_id="TEST-ORD-OVERRIDE-001",
        environment="LIVE",
        execution_status="FILLED"
    )
    print(f"  FeeEngine assess_execution_fee result: {charge_result}")
    assert charge_result["status"] == "ZERO_FEE_RATE", f"Unexpected fee status: {charge_result}"
    assert charge_result.get("fee_charged_usd", 0.0) == 0.0, "Zero fee was expected to charge $0.00"

    results["scenario_8_customer_facing"] = "PASSED (Customer /me returned 0.0, FeeEngine returned 0.0 and ZERO_FEE_RATE charged $0.00)"

    print("\n" + "=" * 70)
    print("ALL 8 SCENARIOS PASSED SUCCESSFULLY:")
    for k, v in results.items():
        print(f"  [x] {k}: {v}")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
