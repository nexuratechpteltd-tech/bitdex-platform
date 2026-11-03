import asyncio
import httpx
import json
import time
import jwt
import sqlite3
from typing import Dict, Any

from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
from app.services.saas_db import get_db_connection
from app.services.exchange_framework import exchange_framework
from app.services.ledger_db import upsert_exchange_order

BASE_URL = "http://127.0.0.1:8002/api/v1"

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + 7200
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def setup_fixtures():
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db_connection() as conn:
        def upsert_user(uid, email, role, st, fn, ln):
            existing = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)).fetchone()
            if existing:
                conn.execute("UPDATE users SET status = ?, role = ?, email = ?, updated_at = ? WHERE user_id = ?", (st, role, email, now, uid))
            else:
                conn.execute("""
                    INSERT INTO users (user_id, email, password_hash, role, status, email_verified, kyc_status, first_name, last_name, country, two_factor_enabled, created_at, updated_at)
                    VALUES (?, ?, 'dummy_hash', ?, ?, 1, 'VERIFIED', ?, ?, 'SG', 0, ?, ?)
                """, (uid, email, role, st, fn, ln, now, now))

        upsert_user('USR-328E147ACA', 'customera@example.com', 'CUSTOMER', 'ACTIVE', 'Customer', 'A')
        upsert_user('USR-TEST-B-PHASE1A', 'customerb@example.com', 'CUSTOMER', 'ACTIVE', 'Customer', 'B')
        upsert_user('USR-TEST-HELD-PHASE1A', 'held@example.com', 'CUSTOMER', 'TEMPORARY_HOLD', 'Held', 'User')
        upsert_user('USR-TEST-BLOCKED-PHASE1A', 'blocked@example.com', 'CUSTOMER', 'BLOCKED', 'Blocked', 'User')

        def upsert_conn(acc_id, uid, label):
            c_existing = conn.execute("SELECT account_id FROM user_exchange_connections WHERE account_id = ?", (acc_id,)).fetchone()
            if c_existing:
                conn.execute("UPDATE user_exchange_connections SET user_id = ?, is_active = 1 WHERE account_id = ?", (uid, acc_id))
            else:
                conn.execute("""
                    INSERT INTO user_exchange_connections (account_id, user_id, provider, environment, is_active, label, encrypted_credentials, created_at)
                    VALUES (?, ?, 'BINANCE', 'DEMO', 1, ?, 'mock_creds', ?)
                """, (acc_id, uid, label, now))

        upsert_conn('CONN-CUST-A-DEMO', 'USR-328E147ACA', 'Customer A Binance Demo')
        upsert_conn('CONN-CUST-A-NOBAL', 'USR-328E147ACA', 'Customer A Zero Balance Demo')
        upsert_conn('CONN-CUST-B-DEMO', 'USR-TEST-B-PHASE1A', 'Customer B Binance Demo')

    from app.services.fee_engine import FeeEngine
    for uid in ['USR-328E147ACA', 'USR-TEST-B-PHASE1A', 'USR-TEST-HELD-PHASE1A']:
        FeeEngine.get_billing_account(uid)
        FeeEngine.get_user_fee_policy(uid)
        with get_db_connection() as conn:
            conn.execute("UPDATE billing_accounts SET prepaid_credits_usd = 500.0 WHERE user_id = ?", (uid,))
            conn.execute("UPDATE fee_policies SET activation_fee_charged = 1, fee_waived = 0 WHERE user_id = ?", (uid,))

    # Create Customer B's order in ledger
    order_b_client_id = "ORD-TEST-B-ORDER-001"
    upsert_exchange_order({
        "internal_order_id": f"INT-{order_b_client_id}",
        "client_order_id": order_b_client_id,
        "exchange_order_id": "9998887771",
        "user_id": "USR-TEST-B-PHASE1A",
        "account_id": "CONN-CUST-B-DEMO",
        "provider": "BINANCE",
        "environment": "DEMO",
        "symbol": "BTCUSDT",
        "display_pair": "BTC/USDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "requested_price": 65000.0,
        "avg_fill_price": 65000.0,
        "orig_qty": 0.05,
        "executed_qty": 0.05,
        "cummulative_quote_qty": 3250.0,
        "status": "FILLED",
        "commission_total": 3.25,
        "commission_asset": "USDT",
        "verification_status": "EXCHANGE_VERIFIED",
        "raw_json": {
            "client_order_id": order_b_client_id,
            "user_id": "USR-TEST-B-PHASE1A",
            "account_id": "CONN-CUST-B-DEMO",
            "status": "FILLED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "executed_qty": 0.05,
            "avg_fill_price": 65000.0
        }
    })

    # Create Customer B's position in memory store
    pos_b_id = "POS-CUST-B-ACTIVE-01"
    exchange_framework._positions[pos_b_id] = {
        "position_id": pos_b_id,
        "symbol": "BTCUSDT",
        "exchange": "BINANCE",
        "environment": "DEMO",
        "side": "LONG",
        "size": 0.05,
        "entry_price": 65000.0,
        "mark_price": 65500.0,
        "unrealized_pnl": 25.0,
        "unrealized_pnl_pct": 0.77,
        "realized_pnl": 0.0,
        "fees_paid": 3.25,
        "opened_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "closed_at_utc": None,
        "status": "OPEN",
        "origin": "EXCHANGE_CONFIRMED_DEMO",
        "origin_label": "Exchange-Confirmed Demo",
        "is_exchange_confirmed": True,
        "user_id": "USR-TEST-B-PHASE1A",
        "account_id": "CONN-CUST-B-DEMO"
    }
    exchange_framework._save_stores()

    # Also register in _orders map
    exchange_framework._orders[order_b_client_id] = {
        "client_order_id": order_b_client_id,
        "user_id": "USR-TEST-B-PHASE1A",
        "account_id": "CONN-CUST-B-DEMO",
        "status": "FILLED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "executed_qty": 0.05,
        "avg_fill_price": 65000.0
    }

async def run_tests():
    setup_fixtures()

    admin_token = create_token("USR-66BCFD7350")
    cust_a_token = create_token("USR-328E147ACA")
    cust_b_token = create_token("USR-TEST-B-PHASE1A")
    held_token = create_token("USR-TEST-HELD-PHASE1A")
    blocked_token = create_token("USR-TEST-BLOCKED-PHASE1A")

    results = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # TEST 1: Unauthenticated GET /ledger/orders/open -> Expect 401
        r1 = await client.get(f"{BASE_URL}/ledger/orders/open")
        results.append({
            "test_id": 1,
            "name": "Unauthenticated GET /ledger/orders/open",
            "method": "GET",
            "path": "/ledger/orders/open",
            "expected_status": 401,
            "actual_status": r1.status_code,
            "passed": r1.status_code == 401,
            "response_body": r1.json() if r1.headers.get("content-type", "").startswith("application/json") else r1.text[:200]
        })

        # TEST 2: Invalid token GET /ledger/orders/history -> Expect 401
        r2 = await client.get(
            f"{BASE_URL}/ledger/orders/history",
            headers={"Authorization": "Bearer INVALID_EXPIRED_MOCK_TOKEN_XYZ"}
        )
        results.append({
            "test_id": 2,
            "name": "Invalid token GET /ledger/orders/history",
            "method": "GET",
            "path": "/ledger/orders/history",
            "expected_status": 401,
            "actual_status": r2.status_code,
            "passed": r2.status_code == 401,
            "response_body": r2.json() if r2.headers.get("content-type", "").startswith("application/json") else r2.text[:200]
        })

        # TEST 3: Customer A calling GET /orders/positions -> Expect positions scoped to A only (no B positions)
        r3 = await client.get(
            f"{BASE_URL}/orders/positions",
            headers={"Authorization": f"Bearer {cust_a_token}"}
        )
        r3_body = r3.json() if r3.status_code == 200 else {}
        positions_returned = r3_body.get("open_positions", []) + r3_body.get("closed_positions", [])
        has_b_position = any(p.get("position_id") == "POS-CUST-B-ACTIVE-01" or p.get("user_id") == "USR-TEST-B-PHASE1A" for p in positions_returned)
        t3_passed = (r3.status_code == 200) and (not has_b_position)
        results.append({
            "test_id": 3,
            "name": "Customer A calling GET /orders/positions (scoped to A, no B positions)",
            "method": "GET",
            "path": "/orders/positions",
            "expected_status": 200,
            "actual_status": r3.status_code,
            "passed": t3_passed,
            "has_b_position_leaked": has_b_position,
            "positions_count": len(positions_returned),
            "response_body": {"positions_count": len(positions_returned), "has_b_position": has_b_position}
        })

        # TEST 4: Customer A calling POST /orders/positions/{pos_B_id}/close -> Expect 403
        r4 = await client.post(
            f"{BASE_URL}/orders/positions/POS-CUST-B-ACTIVE-01/close",
            headers={"Authorization": f"Bearer {cust_a_token}"},
            json={"exit_price": 66000.0}
        )
        results.append({
            "test_id": 4,
            "name": "Customer A calling POST /orders/positions/{pos_B_id}/close",
            "method": "POST",
            "path": "/orders/positions/POS-CUST-B-ACTIVE-01/close",
            "expected_status": 403,
            "actual_status": r4.status_code,
            "passed": r4.status_code == 403,
            "response_body": r4.json() if r4.headers.get("content-type", "").startswith("application/json") else r4.text[:200]
        })

        # TEST 5: Customer A calling POST /orders/cancel with Customer B's order ID -> Expect 403
        r5 = await client.post(
            f"{BASE_URL}/orders/cancel",
            headers={"Authorization": f"Bearer {cust_a_token}"},
            json={
                "symbol": "BTCUSDT",
                "client_order_id": "ORD-TEST-B-ORDER-001",
                "exchange": "BINANCE",
                "environment": "DEMO"
            }
        )
        results.append({
            "test_id": 5,
            "name": "Customer A calling POST /orders/cancel with Customer B's order ID",
            "method": "POST",
            "path": "/orders/cancel",
            "expected_status": 403,
            "actual_status": r5.status_code,
            "passed": r5.status_code == 403,
            "response_body": r5.json() if r5.headers.get("content-type", "").startswith("application/json") else r5.text[:200]
        })

        # TEST 6: Customer A calling GET /orders/receipt/{order_B_client_id} -> Expect 403
        r6 = await client.get(
            f"{BASE_URL}/orders/receipt/ORD-TEST-B-ORDER-001",
            headers={"Authorization": f"Bearer {cust_a_token}"}
        )
        results.append({
            "test_id": 6,
            "name": "Customer A calling GET /orders/receipt/{order_B_client_id}",
            "method": "GET",
            "path": "/orders/receipt/ORD-TEST-B-ORDER-001",
            "expected_status": 403,
            "actual_status": r6.status_code,
            "passed": r6.status_code == 403,
            "response_body": r6.json() if r6.headers.get("content-type", "").startswith("application/json") else r6.text[:200]
        })

        # TEST 7: Unauthenticated POST /orders/demo/submit -> Expect 401
        r7 = await client.post(
            f"{BASE_URL}/orders/demo/submit",
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 65000.0,
                "idempotency_key": "IDEMP-UNAUTH-TEST-001"
            }
        )
        results.append({
            "test_id": 7,
            "name": "Unauthenticated POST /orders/demo/submit",
            "method": "POST",
            "path": "/orders/demo/submit",
            "expected_status": 401,
            "actual_status": r7.status_code,
            "passed": r7.status_code == 401,
            "response_body": r7.json() if r7.headers.get("content-type", "").startswith("application/json") else r7.text[:200]
        })

        # TEST 8: Missing exchange balance order submission -> Expect HTTP 400 (no fabricated balance)
        r8 = await client.post(
            f"{BASE_URL}/orders/demo/submit",
            headers={"Authorization": f"Bearer {cust_a_token}"},
            json={
                "profile_id": "CONN-CUST-A-NOBAL",
                "exchange": "BINANCE",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 65000.0,
                "quote_balance": 0.0,
                "idempotency_key": f"IDEMP-NOBAL-{int(time.time())}"
            }
        )
        results.append({
            "test_id": 8,
            "name": "Missing exchange balance order submission (rejection without fake $10k)",
            "method": "POST",
            "path": "/orders/demo/submit",
            "expected_status": 400,
            "actual_status": r8.status_code,
            "passed": r8.status_code == 400,
            "response_body": r8.json() if r8.headers.get("content-type", "").startswith("application/json") else r8.text[:200]
        })

        # TEST 9: Held customer submitting order -> Expect 403 with status explanation
        r9 = await client.post(
            f"{BASE_URL}/orders/demo/submit",
            headers={"Authorization": f"Bearer {held_token}"},
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 65000.0,
                "quote_balance": 1000.0,
                "idempotency_key": f"IDEMP-HELD-{int(time.time())}"
            }
        )
        results.append({
            "test_id": 9,
            "name": "Held customer submitting order (TEMPORARY_HOLD)",
            "method": "POST",
            "path": "/orders/demo/submit",
            "expected_status": 403,
            "actual_status": r9.status_code,
            "passed": r9.status_code == 403,
            "response_body": r9.json() if r9.headers.get("content-type", "").startswith("application/json") else r9.text[:200]
        })

        # TEST 10: Blocked customer submitting order -> Expect 403
        r10 = await client.post(
            f"{BASE_URL}/orders/demo/submit",
            headers={"Authorization": f"Bearer {blocked_token}"},
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 65000.0,
                "quote_balance": 1000.0,
                "idempotency_key": f"IDEMP-BLOCKED-{int(time.time())}"
            }
        )
        results.append({
            "test_id": 10,
            "name": "Blocked customer submitting order (BLOCKED)",
            "method": "POST",
            "path": "/orders/demo/submit",
            "expected_status": 403,
            "actual_status": r10.status_code,
            "passed": r10.status_code == 403,
            "response_body": r10.json() if r10.headers.get("content-type", "").startswith("application/json") else r10.text[:200]
        })

        # TEST 11: Legitimate Admin access continues to function -> Expect 200
        r11 = await client.get(
            f"{BASE_URL}/ledger/orders/open",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        results.append({
            "test_id": 11,
            "name": "Legitimate Admin access GET /ledger/orders/open",
            "method": "GET",
            "path": "/ledger/orders/open",
            "expected_status": 200,
            "actual_status": r11.status_code,
            "passed": r11.status_code == 200,
            "response_body": {"count": r11.json().get("count")} if r11.status_code == 200 else r11.text[:200]
        })

        # TEST 12: Legitimate Customer access continues to function -> Expect 200
        r12 = await client.get(
            f"{BASE_URL}/ledger/orders/open",
            headers={"Authorization": f"Bearer {cust_a_token}"}
        )
        results.append({
            "test_id": 12,
            "name": "Legitimate Customer access GET /ledger/orders/open",
            "method": "GET",
            "path": "/ledger/orders/open",
            "expected_status": 200,
            "actual_status": r12.status_code,
            "passed": r12.status_code == 200,
            "response_body": {"count": r12.json().get("count")} if r12.status_code == 200 else r12.text[:200]
        })

    print(json.dumps(results, indent=2))
    all_passed = all(r["passed"] for r in results)
    print(f"\nOVERALL RESULT: {'ALL 12 TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

if __name__ == "__main__":
    asyncio.run(run_tests())
