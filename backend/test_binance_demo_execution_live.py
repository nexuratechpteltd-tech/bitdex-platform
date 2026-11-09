import asyncio
import httpx
import json
import secrets
import jwt
import hashlib
from datetime import datetime, timezone, timedelta
from app.services.exchange_framework import exchange_framework, BinanceSpotAdapter, CustomExchangeAdapter, Environment, OrderStatus, credential_vault
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM, get_db_connection

async def run_tests():
    print('=== BITDEX BINANCE DEMO EXECUTION FORENSIC VERIFICATION ===')

    # TEST 1: Adapter Resolution
    adapter = exchange_framework.get_adapter('BINANCE')
    assert isinstance(adapter, BinanceSpotAdapter), f'FAILED: Expected BinanceSpotAdapter, got {type(adapter)}'
    assert not isinstance(adapter, CustomExchangeAdapter), 'FAILED: Returned CustomExchangeAdapter!'
    print('✓ TEST 1 PASSED: get_adapter("BINANCE") resolved strictly to BinanceSpotAdapter.')

    # TEST 2: Credentials Resolution
    creds = credential_vault.get_credentials('CONN-DK-BIN-DEMO-MIGRATED')
    assert creds is not None, 'FAILED: Could not retrieve credentials for CONN-DK-BIN-DEMO-MIGRATED'
    assert creds.get('api_key') and creds.get('api_secret'), 'FAILED: Missing key or secret in credentials'
    print('✓ TEST 2 PASSED: Real Binance Mock Trading credentials decrypted from vault.')

    # TEST 3: Hard Safety Lock on Live Execution
    try:
        await adapter.submit_order({'symbol': 'BTCUSDT', 'side': 'BUY', 'quantity': 0.001}, Environment.LIVE, creds)
        assert False, 'FAILED: Live execution should have raised PermissionError!'
    except PermissionError as e:
        print(f'✓ TEST 3 PASSED: Live execution hard-locked: {e}')

    # Generate valid authenticated session token for test_customer@bitdex.io
    conn = get_db_connection()
    user = conn.execute("SELECT user_id, email, role FROM users WHERE email = 'test_customer@bitdex.io'").fetchone()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=1)
    session_id = f"SES-{secrets.token_hex(8).upper()}"
    payload = {
        "sub": user["user_id"],
        "email": user["email"],
        "role": user["role"],
        "session_id": session_id,
        "remember_me": True,
        "exp": int(expires_at.timestamp())
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with conn:
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at) VALUES (?, ?, ?, ?, 0, ?)",
            (session_id, user["user_id"], token_hash, expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        )
    conn.close()
    headers = {'Authorization': f'Bearer {token}'}

    # TEST 4: Backend API Submit Real Demo Limit Order
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8002', timeout=20.0) as client:
        order_payload = {
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'order_type': 'LIMIT',
            'quantity': 0.0005,
            'price': 50000.0,
            'exchange': 'BINANCE',
            'profile_id': 'CONN-DK-BIN-DEMO-MIGRATED',
            'idempotency_key': f'IDEMP-{secrets.token_hex(8).upper()}'
        }

        resp = await client.post('/api/v1/orders/demo/submit', json=order_payload, headers=headers)
        print(f'Submit response HTTP: {resp.status_code}')
        data = resp.json()
        assert resp.status_code == 200, f'Submit failed: {data}'
        receipt = data.get('receipt', {})
        numeric_id = receipt.get('exchange_order_id')
        client_oid = receipt.get('client_order_id')
        status_val = receipt.get('status')

        print(f'Order Submitted: client_order_id={client_oid}, exchange_order_id={numeric_id}, status={status_val}')
        assert numeric_id is not None, 'FAILED: exchange_order_id is None!'
        assert str(numeric_id).isdigit(), f'FAILED: exchange_order_id must be numeric, got {numeric_id}'
        assert not str(numeric_id).startswith('CUST-SIM-'), f'FAILED: Found synthetic CUST-SIM- order ID!'
        assert receipt.get('execution_type') == 'REAL_EXCHANGE_DEMO', f'FAILED: Execution type: {receipt.get("execution_type")}'
        print('✓ TEST 4 PASSED: Genuine Binance numeric order ID returned from Binance matching engine.')

        # TEST 5: Verify Order in Open Orders via API
        open_resp = await client.get('/api/v1/orders/open?environment=DEMO&symbol=BTCUSDT', headers=headers)
        open_data = open_resp.json()
        orders_list = open_data.get('orders', [])
        found_in_open = any(str(o.get('exchange_order_id')) == str(numeric_id) or str(o.get('order_id')) == str(numeric_id) for o in orders_list)
        print(f'Open orders count on Binance Demo: {len(orders_list)}, Found new order: {found_in_open}')
        assert found_in_open, f'FAILED: Order {numeric_id} not found resting in open orders!'
        print('✓ TEST 5 PASSED: Order verified resting on Binance Demo orderbook.')

        # TEST 6: Cancel Order via API
        cancel_resp = await client.post('/api/v1/orders/cancel', json={
            'symbol': 'BTCUSDT',
            'client_order_id': client_oid,
            'profile_id': 'CONN-DK-BIN-DEMO-MIGRATED',
            'exchange': 'BINANCE',
            'environment': 'DEMO'
        }, headers=headers)
        assert cancel_resp.status_code == 200, f'Cancel failed: {cancel_resp.text}'
        print(f'Cancel response: {cancel_resp.json()}')
        print('✓ TEST 6 PASSED: Order successfully cancelled on Binance Demo matching engine.')

        # TEST 7: Reconcile Order Status
        rec_resp = await client.post('/api/v1/orders/reconcile', json={
            'symbol': 'BTCUSDT',
            'client_order_id': client_oid,
            'exchange_order_id': str(numeric_id),
            'profile_id': 'CONN-DK-BIN-DEMO-MIGRATED',
            'exchange': 'BINANCE',
            'environment': 'DEMO'
        }, headers=headers)
        assert rec_resp.status_code == 200, f'Reconcile failed: {rec_resp.text}'
        rec_data = rec_resp.json()
        assert rec_data.get('receipt', {}).get('status') == 'CANCELLED', f'Expected CANCELLED status, got {rec_data}'
        print('✓ TEST 7 PASSED: Signed read-back reconciled CANCELLED status on Binance matching engine.')

        # TEST 8: Rejection / Failure Handling (No Silent Simulation Fallback)
        bad_order = {
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'order_type': 'LIMIT',
            'quantity': 0.0005,
            'price': 10000.0,
            'exchange': 'BINANCE',
            'profile_id': 'CONN-DK-BIN-DEMO-MIGRATED',
            'idempotency_key': f'IDEMP-FAIL-{secrets.token_hex(8).upper()}'
        }
        bad_resp = await client.post('/api/v1/orders/demo/submit', json=bad_order, headers=headers)
        bad_data = bad_resp.json()
        print(f'Rejected order response: {bad_data}')
        assert bad_data.get('status') == 'REJECTED', f'Expected REJECTED, got {bad_data}'
        assert 'PERCENT_PRICE_BY_SIDE' in bad_data.get('message', ''), 'Expected Binance filter rejection message'
        print('✓ TEST 8 PASSED: Honest rejection returned on filter failure without simulation fallback.')

    print('\nALL TESTS PASSED WITH 100% SUCCESS!')

if __name__ == '__main__':
    asyncio.run(run_tests())
