import sys
import os
import hashlib
import hmac
import sqlite3
import datetime
import httpx
from fastapi import HTTPException

# Add backend directory to sys.path
sys.path.insert(0, "/opt/tauric-platform-staging/backend")
os.environ.setdefault("DATABASE_PATH", "/opt/tauric-platform-staging/backend/data/tauric_saas.db")

from app.services.email_service import EmailService
from app.services.auth_manager import AuthManager, get_db_connection, _compute_otp_hash

def run_tests():
    print("=" * 60)
    print("STARTING BITDEX STAGING EMAIL OTP VERIFICATION SUITE")
    print("=" * 60)

    # 1. Direct EmailService dispatch test to test_customer@bitdex.io
    print("\n[TEST 1] Testing direct EmailService.send_login_otp to test_customer@bitdex.io...")
    test_otp = "123890"
    disp = EmailService.send_login_otp("test_customer@bitdex.io", test_otp)
    print(f"  Result: status={disp.get('status')}, blocked={disp.get('delivery_blocked')}, id={disp.get('dispatch_id')}")
    assert disp.get("status") in ("ACCEPTED", "SENT"), f"Expected ACCEPTED/SENT, got {disp.get('status')}"
    assert disp.get("delivery_blocked") is False, "Expected delivery_blocked=False"
    
    # Check email_dispatches table
    conn = get_db_connection()
    row = conn.execute("SELECT dispatch_id, recipient_email, status, details_json FROM email_dispatches WHERE dispatch_id = ?", (disp.get("dispatch_id"),)).fetchone()
    conn.close()
    assert row is not None, "Dispatch record not found in DB"
    print(f"  DB record confirmed: recipient={row['recipient_email']}, status={row['status']}")
    print(f"  Dispatch details: {row['details_json']}")
    print("  -> TEST 1 PASSED!")

    # 2. AuthManager.initiate_login test
    print("\n[TEST 2] Testing AuthManager.initiate_login for test.customer@sheltr.agency...")
    login_res = AuthManager.initiate_login("test.customer@sheltr.agency", "TestCustomer2026!")
    print(f"  Login response: status={login_res.get('status')}, delivery_status={login_res.get('delivery_status')}, message={login_res.get('message')}")
    assert login_res.get("status") == "EMAIL_OTP_REQUIRED", "Expected status EMAIL_OTP_REQUIRED"
    assert login_res.get("delivery_status") in ("ACCEPTED", "SENT"), f"Expected ACCEPTED/SENT, got {login_res.get('delivery_status')}"
    assert login_res.get("delivery_blocked") is False, "Expected delivery_blocked=False"
    assert login_res.get("message") == "Email provider accepted the message", f"Unexpected message: {login_res.get('message')}"
    challenge_id = login_res["challenge_id"]
    print(f"  Challenge created: {challenge_id}")
    print("  -> TEST 2 PASSED!")

    # 3. Rate limiting and Resend OTP test
    print("\n[TEST 3] Testing Resend OTP rate-limiting cooldown and dispatch...")
    try:
        AuthManager.resend_login_otp(challenge_id)
        raise AssertionError("Expected 429 Rate Limit exception on immediate resend!")
    except HTTPException as e:
        print(f"  Immediate resend correctly rejected: {e.status_code} - {e.detail}")
        assert e.status_code == 429, f"Expected 429, got {e.status_code}"

    # Simulate cooldown elapse by setting resend_after to past
    conn = get_db_connection()
    past_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute("UPDATE login_challenges SET resend_after = ? WHERE challenge_id = ?", (past_iso, challenge_id))
    conn.commit()
    conn.close()

    resend_res = AuthManager.resend_login_otp(challenge_id)
    print(f"  Cooldown elapsed resend response: status={resend_res.get('status')}, delivery_status={resend_res.get('delivery_status')}")
    assert resend_res.get("status") == "RESENT", "Expected status RESENT"
    assert resend_res.get("delivery_status") in ("ACCEPTED", "SENT"), f"Expected ACCEPTED/SENT, got {resend_res.get('delivery_status')}"
    assert resend_res.get("message") == "Email provider accepted the message"
    print("  -> TEST 3 PASSED!")

    # 4. OTP verification, attempt decrementing, and session creation
    print("\n[TEST 4] Testing OTP verification, attempt decrementing, and session creation...")
    # Attempt with invalid OTP
    try:
        AuthManager.verify_login_otp(challenge_id, "000000")
        raise AssertionError("Expected 401 exception for invalid OTP!")
    except HTTPException as e:
        print(f"  Invalid OTP rejected: {e.status_code} - {e.detail}")
        assert e.status_code == 401
        assert "Attempts remaining: 2" in e.detail

    # Find plain OTP for the test challenge
    conn = get_db_connection()
    chal = conn.execute("SELECT otp_hash, otp_salt FROM login_challenges WHERE challenge_id = ?", (challenge_id,)).fetchone()
    conn.close()
    
    plain_otp = None
    for cand in range(100000, 1000000):
        c_str = str(cand)
        if _compute_otp_hash(c_str, chal["otp_salt"]) == chal["otp_hash"]:
            plain_otp = c_str
            break
    assert plain_otp is not None, "Failed to resolve plain OTP for test"

    # Verify with correct OTP
    verify_res = AuthManager.verify_login_otp(challenge_id, plain_otp)
    print(f"  Valid OTP verification response: status={verify_res.get('status')}, token_type={verify_res.get('token_type')}")
    assert verify_res.get("status") == "SUCCESS", "Expected status SUCCESS"
    assert "token" in verify_res, "Expected session token in verify_res"
    assert verify_res["user"]["email"] == "test.customer@sheltr.agency"

    # Ensure replay of same OTP fails
    try:
        AuthManager.verify_login_otp(challenge_id, plain_otp)
        raise AssertionError("Expected 401 exception for reused OTP session!")
    except HTTPException as e:
        print(f"  Replay attempt rejected: {e.status_code} - {e.detail}")
        assert e.status_code == 401
    print("  -> TEST 4 PASSED!")

    # 5. Full HTTP endpoint roundtrip via FastAPI port 8002 and Next.js proxy port 33900
    print("\n[TEST 5] Testing HTTP endpoint roundtrip via Next.js proxy (port 33900)...")
    client = httpx.Client(base_url="http://127.0.0.1:33900", timeout=30.0)
    resp = client.post("/api/backend/saas/auth/login", json={
        "email": "test.customer@sheltr.agency",
        "password": "TestCustomer2026!"
    })
    print(f"  HTTP Login response status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    print(f"  Body: status={body.get('status')}, delivery_status={body.get('delivery_status')}, message={body.get('message')}")
    assert body.get("status") == "EMAIL_OTP_REQUIRED"
    assert body.get("delivery_status") in ("ACCEPTED", "SENT")
    assert body.get("message") == "Email provider accepted the message"
    assert body.get("delivery_blocked") is False

    # Test HTTP resend rate limit
    chal_http = body["challenge_id"]
    resend_resp = client.post("/api/backend/saas/auth/resend-otp", json={"challenge_id": chal_http})
    print(f"  HTTP Resend cooldown rejection: {resend_resp.status_code} - {resend_resp.json().get('detail')}")
    assert resend_resp.status_code == 429

    print("  -> TEST 5 PASSED!")

    print("\n" + "=" * 60)
    print("ALL 5 VERIFICATION SUITE TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
