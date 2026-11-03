import sys, sqlite3, json, hmac, hashlib, time, httpx
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
from app.routes.saas_customer import _decrypt_credentials_payload

db_path = '/opt/tauric-platform-staging/backend/data/tauric_saas.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT account_id, provider, environment, label, encrypted_credentials 
    FROM user_exchange_connections 
    WHERE provider = 'BINANCE' AND is_active = 1
""").fetchall()

print(f"Found {len(rows)} Binance connections in DB.")

for row in rows:
    acc_id = row['account_id']
    env = row['environment']
    lbl = row['label']
    print(f"\n=======================================================")
    print(f"Checking Connection: {acc_id} ({env}) - {lbl}")
    print(f"=======================================================")
    creds = _decrypt_credentials_payload(row['encrypted_credentials'])
    api_key = creds.get('api_key') or creds.get('apiKey')
    api_secret = creds.get('api_secret') or creds.get('secret') or creds.get('secretKey')
    if not api_key or not api_secret:
        print("No API key/secret found in credentials.")
        continue

    # Test against both Mock Trading and Testnet.binance.vision
    endpoints = [
        ("Binance Mock Trading", "https://demo-api.binance.com/api/v3"),
        ("Binance Spot Testnet", "https://testnet.binance.vision/api/v3")
    ]

    for name, base_url in endpoints:
        print(f"\n--- Testing {name} ({base_url}) ---")
        ts = int(time.time() * 1000)
        query = f"timestamp={ts}"
        sig = hmac.new(api_secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        url = f"{base_url}/account?{query}&signature={sig}"
        headers = {"X-MBX-APIKEY": api_key}
        
        try:
            r = httpx.get(url, headers=headers, timeout=10.0)
            print(f"Account HTTP status: {r.status_code}")
            if r.status_code == 200:
                acc_data = r.json()
                bals = [b for b in acc_data.get('balances', []) if float(b['free']) > 0 or float(b['locked']) > 0]
                print(f"Active balances ({len(bals)}):")
                for b in bals:
                    print(f"   {b['asset']}: free={b['free']}, locked={b['locked']}")
                
                # Check for Order 537182101 or BCHUSDT orders
                ts2 = int(time.time() * 1000)
                q2 = f"symbol=BCHUSDT&timestamp={ts2}"
                sig2 = hmac.new(api_secret.encode('utf-8'), q2.encode('utf-8'), hashlib.sha256).hexdigest()
                r_orders = httpx.get(f"{base_url}/allOrders?{q2}&signature={sig2}", headers=headers, timeout=10.0)
                print(f"BCHUSDT allOrders HTTP status: {r_orders.status_code}")
                if r_orders.status_code == 200:
                    orders = r_orders.json()
                    print(f"Found {len(orders)} BCHUSDT orders:")
                    for o in orders:
                        print(f"  OrderId: {o.get('orderId')}, ClientId: {o.get('clientOrderId')}, Side: {o.get('side')}, Qty: {o.get('origQty')}, ExecQty: {o.get('executedQty')}, Price: {o.get('price')}, Status: {o.get('status')}, Time: {o.get('time')}")
                else:
                    print(f"  allOrders error: {r_orders.text}")

                # Check myTrades
                ts3 = int(time.time() * 1000)
                q3 = f"symbol=BCHUSDT&timestamp={ts3}"
                sig3 = hmac.new(api_secret.encode('utf-8'), q3.encode('utf-8'), hashlib.sha256).hexdigest()
                r_trades = httpx.get(f"{base_url}/myTrades?{q3}&signature={sig3}", headers=headers, timeout=10.0)
                print(f"BCHUSDT myTrades HTTP status: {r_trades.status_code}")
                if r_trades.status_code == 200:
                    trades = r_trades.json()
                    print(f"Found {len(trades)} BCHUSDT trades:")
                    for t in trades:
                        print(f"  TradeId: {t.get('id')}, OrderId: {t.get('orderId')}, Price: {t.get('price')}, Qty: {t.get('qty')}, Comm: {t.get('commission')} {t.get('commissionAsset')}, Time: {t.get('time')}")
                else:
                    print(f"  myTrades error: {r_trades.text}")

                # Also specifically query OrderId 537182101
                ts4 = int(time.time() * 1000)
                q4 = f"symbol=BCHUSDT&orderId=537182101&timestamp={ts4}"
                sig4 = hmac.new(api_secret.encode('utf-8'), q4.encode('utf-8'), hashlib.sha256).hexdigest()
                r_spec = httpx.get(f"{base_url}/order?{q4}&signature={sig4}", headers=headers, timeout=10.0)
                print(f"Query specific order 537182101 HTTP status: {r_spec.status_code}")
                if r_spec.status_code == 200:
                    print(f"Order 537182101 details: {r_spec.json()}")
                else:
                    print(f"Order 537182101 response: {r_spec.text}")

            else:
                print(f"Auth failed on {name}: {r.text}")
        except Exception as e:
            print(f"Error connecting to {name}: {e}")

conn.close()
