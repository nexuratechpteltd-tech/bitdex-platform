#!/usr/bin/env python3
"""
Phase 4 Security, Tenant Isolation, Failure Handling & Database Consistency Suite
Environment: STAGING ONLY (port 8002 / https://bitdex.ltd)
"""

import sys
import os
import sqlite3
import httpx
import jwt
from datetime import datetime, timezone, timedelta

backend_dir = "/opt/tauric-platform-staging/backend"
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
from app.services.fee_engine import FeeEngine

DB_PATH = "/opt/tauric-platform-staging/backend/data/tauric_saas.db"
BASE_URL = "http://127.0.0.1:8002"

ADMIN_ID = "USR-66BCFD7350"
CUSTOMER_A_ID = "USR-328E147ACA"
CUSTOMER_B_ID = "USR-TEST-B-PHASE1A"
HELD_CUST_ID = "USR-TEST-HELD-PHASE1A"
BLOCKED_CUST_ID = "USR-TEST-BLOCKED-PHASE1A"
ALI_AJMAL_ID = "USR-904424B4FB"

def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=2)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def run_suite():
    admin_token = make_token(ADMIN_ID)
    customer_a_token = make_token(CUSTOMER_A_ID)
    customer_b_token = make_token(CUSTOMER_B_ID)
    held_token = make_token(HELD_CUST_ID)
    blocked_token = make_token(BLOCKED_CUST_ID)

    admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    customer_a_headers = {"Authorization": f"Bearer {customer_a_token}", "Content-Type": "application/json"}
    customer_b_headers = {"Authorization": f"Bearer {customer_b_token}", "Content-Type": "application/json"}
    held_headers = {"Authorization": f"Bearer {held_token}", "Content-Type": "application/json"}
    blocked_headers = {"Authorization": f"Bearer {blocked_token}", "Content-Type": "application/json"}

    client = httpx.Client(base_url=BASE_URL, timeout=15.0)
    results = {}

    print("=" * 70)
    print("STARTING BITDEX PHASE 4 SECURITY & DATABASE INTEGRITY SUITE")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # ══════════════════════════════════════════════════════════════════════
    # JOURNEY C: SECURITY & TENANT ISOLATION
    # ══════════════════════════════════════════════════════════════════════
    print("\n>>> [JOURNEY C] SECURITY & TENANT ISOLATION CHECKS...")

    # C1: Unauthenticated request to admin route
    r_c1 = client.get("/api/v1/saas/admin/customers")
    print(f"  [C1] Unauthenticated admin request -> Status: {r_c1.status_code}")
    assert r_c1.status_code in (401, 403), f"Expected 401/403, got {r_c1.status_code}"

    # C2: Non-admin customer accessing admin route
    r_c2 = client.get("/api/v1/saas/admin/customers", headers=customer_a_headers)
    print(f"  [C2] Customer accessing admin route -> Status: {r_c2.status_code}")
    assert r_c2.status_code == 403, f"Expected 403, got {r_c2.status_code}"

    # C3: Blocked customer accessing customer portal /me
    r_c3 = client.get("/api/v1/saas/customer/me", headers=blocked_headers)
    print(f"  [C3] Blocked customer accessing /me -> Status: {r_c3.status_code}")
    assert r_c3.status_code == 403, f"Expected 403 for blocked customer, got {r_c3.status_code}"

    # C4: Temporary Hold customer accessing customer portal /me (can view profile/balance, cannot trade)
    r_c4 = client.get("/api/v1/saas/customer/me", headers=held_headers)
    print(f"  [C4] Held customer accessing /me -> Status: {r_c4.status_code}")
    assert r_c4.status_code == 200, f"Expected 200 for held customer to view account, got {r_c4.status_code}"
    assert r_c4.json().get("user", {}).get("status") == "TEMPORARY_HOLD"

    # C5: Mainnet Trading Lock verification on root endpoint
    r_c5 = client.get("/")
    print(f"  [C5] Root status response: {r_c5.json()}")
    assert r_c5.status_code == 200
    assert r_c5.json().get("live_trading_locked") is True, "live_trading_locked MUST be True!"
    assert r_c5.json().get("trading_mode") == "READ_ONLY_RESEARCH"

    results["JOURNEY_C_SECURITY"] = "PASSED (Auth enforcement, RBAC, Blocked rejection, Mainnet locked)"

    # ══════════════════════════════════════════════════════════════════════
    # JOURNEY E: FAILURE HANDLING & INPUT VALIDATION
    # ══════════════════════════════════════════════════════════════════════
    print("\n>>> [JOURNEY E] FAILURE HANDLING & INPUT VALIDATION...")

    # E1: Short reason on override
    r_e1 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_A_ID}/pricing/override",
                       headers=admin_headers,
                       json={"service_id": "STRATEGY_EXECUTION", "price_usd": 0.20, "reason": "ab", "confirm": True})
    print(f"  [E1] Short reason (<3 chars) -> Status: {r_e1.status_code}")
    assert r_e1.status_code in (400, 422), f"Expected 400/422, got {r_e1.status_code}"

    # E2: Negative price on override
    r_e2 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_A_ID}/pricing/override",
                       headers=admin_headers,
                       json={"service_id": "STRATEGY_EXECUTION", "price_usd": -10.0, "reason": "Testing negative price", "confirm": True})
    print(f"  [E2] Negative price -> Status: {r_e2.status_code}")
    assert r_e2.status_code == 400, f"Expected 400, got {r_e2.status_code}"

    # E3: Unknown service ID
    r_e3 = client.post(f"/api/v1/saas/admin/customers/{CUSTOMER_A_ID}/pricing/override",
                       headers=admin_headers,
                       json={"service_id": "UNKNOWN_SERVICE_XYZ", "price_usd": 5.0, "reason": "Testing unknown service", "confirm": True})
    print(f"  [E3] Unknown service ID -> Status: {r_e3.status_code}")
    assert r_e3.status_code == 400, f"Expected 400, got {r_e3.status_code}"

    # E4: Non-existent customer ID
    r_e4 = client.get("/api/v1/saas/admin/customers/USR-DOESNOTEXIST999/360", headers=admin_headers)
    print(f"  [E4] Non-existent customer 360 -> Status: {r_e4.status_code}")
    assert r_e4.status_code == 404, f"Expected 404, got {r_e4.status_code}"

    results["JOURNEY_E_FAILURE_HANDLING"] = "PASSED (Short reason, negative price, invalid service, missing user properly rejected)"

    # ══════════════════════════════════════════════════════════════════════
    # DATABASE INTEGRITY & CRITICAL PRESERVATION CHECK
    # ══════════════════════════════════════════════════════════════════════
    print("\n>>> DATABASE INTEGRITY & CRITICAL PRESERVATION...")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. SQLite PRAGMA integrity_check
    integ = conn.execute("PRAGMA integrity_check;").fetchall()
    print(f"  SQLite integrity_check: {[dict(r) for r in integ]}")
    assert integ[0][0] == "ok", f"Integrity check failed: {integ}"

    # 2. SQLite PRAGMA foreign_key_check
    fk = conn.execute("PRAGMA foreign_key_check;").fetchall()
    print(f"  SQLite foreign_key_check violations count: {len(fk)}")
    assert len(fk) == 0, f"Foreign key check violations found: {fk}"

    # 3. CRITICAL: Ali Ajmal (USR-904424B4FB) pricing overrides preservation
    ali_overrides = conn.execute(
        "SELECT service_id, price_usd, status FROM customer_pricing_overrides WHERE user_id = ? AND status = 'ACTIVE'",
        (ALI_AJMAL_ID,)
    ).fetchall()
    ali_dict = {r["service_id"]: r["price_usd"] for r in ali_overrides}
    print(f"  Ali Ajmal (USR-904424B4FB) active overrides: {ali_dict}")
    assert "STRATEGY_EXECUTION" in ali_dict and ali_dict["STRATEGY_EXECUTION"] == 0.0, "Ali Ajmal STRATEGY_EXECUTION must remain $0.00"
    assert "AI_ANALYSIS" in ali_dict and ali_dict["AI_ANALYSIS"] == 0.0, "Ali Ajmal AI_ANALYSIS must remain $0.00"
    assert "PLATFORM_ACTIVATION" in ali_dict and ali_dict["PLATFORM_ACTIVATION"] == 0.0, "Ali Ajmal PLATFORM_ACTIVATION must remain $0.00"
    print("  CRITICAL CHECK PASSED: Ali Ajmal $0.00 overrides are 100% preserved!")

    # 4. Check negative balances
    neg_balances = conn.execute("SELECT * FROM billing_accounts WHERE prepaid_credits_usd < 0").fetchall()
    print(f"  Negative balances count: {len(neg_balances)}")
    assert len(neg_balances) == 0, f"Negative balances found: {neg_balances}"

    conn.close()
    results["DATABASE_INTEGRITY"] = "PASSED (Integrity OK, FK OK, Ali Ajmal preserved at $0.00, no negative balances)"

    print("\n" + "=" * 70)
    print("PHASE 4 BACKEND QA RESULTS:")
    for k, v in results.items():
        print(f"  [x] {k}: {v}")
    print("=" * 70)

if __name__ == "__main__":
    run_suite()
