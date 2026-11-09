import sys
import json
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
import jwt
import httpx

sys.path.insert(0, '/opt/tauric-platform-staging/backend')
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
from app.services.saas_db import get_db_connection

# 1. Create valid Admin token
conn = get_db_connection()
user = conn.execute("SELECT * FROM users WHERE email = 'test_customer@bitdex.io'").fetchone()
if not user:
    print('Admin user not found')
    sys.exit(1)
user = dict(user)

now = datetime.now(timezone.utc)
exp = now + timedelta(days=7)
session_id = f"SES-{secrets.token_hex(16).upper()}"
payload = {
    "sub": user["user_id"],
    "email": user["email"],
    "role": user["role"],
    "session_id": session_id,
    "exp": int(exp.timestamp())
}
admin_token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
token_hash = hashlib.sha256(admin_token.encode("utf-8")).hexdigest()

with conn:
    conn.execute("""
        INSERT INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (session_id, user["user_id"], token_hash, exp.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")))
conn.close()

print(f"Admin token created successfully for {user['email']} ({user['user_id']})")

# 2. Test session validation
print('\n--- 1. Testing /api/backend/saas/customer/me via HTTPS ---')
with httpx.Client(base_url='https://bitdex.ltd', timeout=10.0, verify=False) as client:
    r = client.get('/api/backend/saas/customer/me', headers={'Authorization': f'Bearer {admin_token}'})
    print(f"Status: {r.status_code}")
    me = r.json()
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert me['user']['role'] == 'ADMIN'
    print(f"OK: Session validated. User role: {me['user']['role']}, email: {me['user']['email']}")

# 3. Test Admin Panel APIs
print('\n--- 2. Testing Admin Panel APIs via HTTPS ---')
with httpx.Client(base_url='https://bitdex.ltd', timeout=10.0, verify=False) as client:
    headers = {'Authorization': f'Bearer {admin_token}'}
    
    r = client.get('/api/backend/saas/admin/customers', headers=headers)
    print(f"Customers API: {r.status_code}, count: {len(r.json().get('customers', []))}")
    assert r.status_code == 200

    r = client.get('/api/backend/saas/admin/support/tickets', headers=headers)
    print(f"Support Tickets API: {r.status_code}, count: {len(r.json().get('tickets', []))}")
    assert r.status_code == 200

    r = client.get('/api/backend/saas/admin/pricing/global', headers=headers)
    print(f"Global Pricing API: {r.status_code}, pricing: {r.json().get('global', {})}")
    assert r.status_code == 200

    r = client.get('/api/backend/saas/admin/audit-logs?limit=5', headers=headers)
    print(f"Audit Logs API: {r.status_code}, logs returned: {len(r.json().get('audit_logs', []))}")
    assert r.status_code == 200

    r = client.get('/api/backend/saas/admin/provider-operations', headers=headers)
    print(f"Provider Operations API: {r.status_code}")
    assert r.status_code == 200

    r = client.get(f"/api/backend/saas/admin/customers/{user['user_id']}/360", headers=headers)
    print(f"Customer 360 composite API: {r.status_code}, balance: ${r.json().get('balance_usd')}")
    assert r.status_code == 200

# 4. Test Role Protection (Non-admin access denied)
print('\n--- 3. Testing RBAC Role Enforcement on Admin Panel ---')
conn = get_db_connection()
cust_user = conn.execute("SELECT * FROM users WHERE role = 'CUSTOMER' LIMIT 1").fetchone()
conn.close()
if cust_user:
    cust_dict = dict(cust_user)
    cust_payload = {
        "sub": cust_dict["user_id"],
        "email": cust_dict["email"],
        "role": "CUSTOMER",
        "session_id": f"SES-{secrets.token_hex(16).upper()}",
        "exp": int(exp.timestamp())
    }
    cust_token = jwt.encode(cust_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    cust_token_hash = hashlib.sha256(cust_token.encode("utf-8")).hexdigest()
    conn = get_db_connection()
    with conn:
        conn.execute("""
            INSERT INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (cust_payload["session_id"], cust_dict["user_id"], cust_token_hash, exp.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")))
    conn.close()
    with httpx.Client(base_url='https://bitdex.ltd', timeout=10.0, verify=False) as client:
        r_forbidden = client.get('/api/backend/saas/admin/customers', headers={'Authorization': f'Bearer {cust_token}'})
        print(f"Customer access to /api/backend/saas/admin/customers: HTTP {r_forbidden.status_code}")
        assert r_forbidden.status_code == 403, f"Expected 403 Forbidden, got {r_forbidden.status_code}"
        print('OK: Non-admin users are strictly rejected with HTTP 403 Forbidden.')

# 5. Test Exness Test Connection
print('\n--- 4. Testing Exness Connection via HTTPS (Proving 404 is resolved) ---')
with httpx.Client(base_url='https://bitdex.ltd', timeout=10.0, verify=False) as client:
    headers = {'Authorization': f'Bearer {admin_token}', 'Content-Type': 'application/json'}
    test_payload = {
        'connection_method': 'TRADER_API',
        'account_login': '16000629657',
        'api_key': 'exnsk-test-sample-key-12345678',
        'api_secret': 'b' * 128,
        'server_name': 'https://gateway.exness.com',
        'account_tier': 'STANDARD',
        'account_label': 'Verification Test'
    }
    r_exn = client.post('/api/v1/hft/exness/real/connect', headers=headers, json=test_payload)
    print(f"Exness Connect Endpoint: HTTP {r_exn.status_code}")
    print(f"Response Body: {r_exn.text}")
    assert r_exn.status_code != 404, 'Endpoint returned 404!'
    assert r_exn.status_code == 400, f"Expected 400 (auth failed), got {r_exn.status_code}"
    exn_data = r_exn.json()
    assert exn_data['detail']['status'] == 'FAILED'
    print(f"OK: Endpoint is found and functioning. Diagnostic error: {exn_data['detail']['reason']}")

# 6. Test Connected Accounts
print('\n--- 5. Testing Connected Accounts Endpoint ---')
with httpx.Client(base_url='https://bitdex.ltd', timeout=10.0, verify=False) as client:
    headers = {'Authorization': f'Bearer {admin_token}'}
    r = client.get('/api/v1/saas/customer/trading/hft/connected-accounts', headers=headers)
    print(f"Connected Accounts: HTTP {r.status_code}")
    assert r.status_code == 200
    data = r.json()
    assert data['live_trading_locked'] is True
    assert data['read_only_mode'] is True
    print(f"Safety locks verified: live_trading_locked={data['live_trading_locked']}, read_only_mode={data['read_only_mode']}")
    for acct in data.get('accounts', []):
        print(f"Account: {acct['display_label']} | Status={acct['connection_status']} | Connected={acct['connected']}")
        # Ensure status is one of the strictly permitted values
        assert acct['connection_status'] in ('VERIFIED', 'NOT TESTED', 'DISCONNECTED', 'ERROR'), f"Invalid status: {acct['connection_status']}"

# 7. Test Dashboard Landing and Header HTML
print('\n--- 6. Testing Dashboard Rendered HTML for Header Badges ---')
with httpx.Client(base_url='https://bitdex.ltd', timeout=10.0, verify=False) as client:
    r = client.get('/')
    print(f"Landing page: HTTP {r.status_code}")
    assert r.status_code == 200
    html = r.text
    assert '<span>Locked</span>' not in html, 'Found <span>Locked</span> in rendered HTML!'
    assert 'SIMULATED / DEMO ENVIRONMENT (STAGING)' not in html
    print('OK: Header badges cleaned up. No Locked or SIMULATED/DEMO badges present.')

print('\n=============================================')
print('ALL ACCEPTANCE TESTS COMPLETED SUCCESSFULLY!')
print('=============================================')
