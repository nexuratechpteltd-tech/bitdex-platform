import httpx, asyncio, json, jwt, secrets, hashlib, sqlite3
from datetime import datetime, timezone, timedelta
import sys
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM

async def test_fill():
    print('=== TESTING REAL BINANCE DEMO MARKET FILL & POSITION RECONCILIATION ===')
    conn = sqlite3.connect('/opt/tauric-platform-staging/backend/data/tauric_saas.db')
    user = conn.execute("SELECT user_id, email, role FROM users WHERE email = 'designkrao@gmail.com'").fetchone()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=1)
    session_id = f"SES-{secrets.token_hex(8).upper()}"
    payload = {
        'sub': user[0],
        'email': user[1],
        'role': user[2],
        'session_id': session_id,
        'remember_me': True,
        'exp': int(expires_at.timestamp())
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    with conn:
        conn.execute(
            'INSERT INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at) VALUES (?, ?, ?, ?, 0, ?)',
            (session_id, user[0], token_hash, expires_at.strftime('%Y-%m-%dT%H:%M:%SZ'), now.strftime('%Y-%m-%dT%H:%M:%SZ'))
        )
    conn.close()
    headers = {'Authorization': f'Bearer {token}'}

    async with httpx.AsyncClient(base_url='http://127.0.0.1:8002', timeout=20.0) as client:
        # First get ticker price
        ticker_resp = await client.get('https://demo-api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
        cur_px = float(ticker_resp.json().get('price', 77500.0))
        print(f'Current BTCUSDT Price on Binance Demo: ${cur_px:,.2f}')

        order_payload = {
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'order_type': 'MARKET',
            'quantity': 0.0001,
            'price': cur_px,
            'exchange': 'BINANCE',
            'profile_id': 'CONN-DK-BIN-DEMO-MIGRATED',
            'idempotency_key': f'IDEMP-FILL-{secrets.token_hex(8).upper()}'
        }
        resp = await client.post('/api/v1/orders/demo/submit', json=order_payload, headers=headers)
        print('Submit HTTP:', resp.status_code)
        data = resp.json()
        print('Response:', json.dumps(data, indent=2))
        
        receipt = data.get('receipt', {})
        status_val = receipt.get('status')
        numeric_id = receipt.get('exchange_order_id')
        exec_qty = receipt.get('executed_qty')
        avg_px = receipt.get('avg_fill_price')
        
        print(f'Market Fill Result: status={status_val}, exchange_order_id={numeric_id}, executed_qty={exec_qty}, avg_fill_price={avg_px}')
        assert status_val == 'FILLED', f'Expected FILLED, got {status_val}'
        assert numeric_id and str(numeric_id).isdigit(), f'Expected numeric exchange_order_id, got {numeric_id}'
        assert exec_qty > 0, 'Expected executed_qty > 0'
        assert avg_px > 0, 'Expected avg_fill_price > 0'
        
        # Verify position in positions store
        with open('/opt/tauric-platform-staging/backend/data/positions_store.json') as f:
            pos_data = json.load(f)
        
        btc_pos = pos_data.get('BINANCE_DEMO_BTCUSDT')
        print('BTC Position in Ledger:', json.dumps(btc_pos, indent=2))
        assert btc_pos is not None, 'Position not found in positions_store.json!'
        assert btc_pos.get('is_exchange_confirmed') is True, 'Position is_exchange_confirmed must be True!'
        assert btc_pos.get('origin') == 'EXCHANGE_CONFIRMED_DEMO', f'Expected origin EXCHANGE_CONFIRMED_DEMO, got {btc_pos.get("origin")}'
        assert any(str(h.get('order_id')) == str(numeric_id) for h in btc_pos.get('execution_history', [])), 'Execution history does not contain Binance numeric orderId!'
        print('✓ POSITION RECONCILIATION VERIFIED: Position backed 100% by genuine Binance execution.')

asyncio.run(test_fill())
