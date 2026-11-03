import sys
import json
import time
from datetime import datetime, timezone
import httpx
from app.services.saas_db import get_db_connection

def run_audit():
    print('=' * 80)
    print('PHASE 3.1 FORENSIC AUDIT & BASELINE DATASET RECONCILIATION')
    print('=' * 80)

    # 1. Inspect 1000 candles from Binance Futures API
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    for sym in symbols:
        url = 'https://fapi.binance.com/fapi/v1/klines'
        resp = httpx.get(url, params={'symbol': sym, 'interval': '5m', 'limit': 1000})
        data = resp.json()
        print(f'\n--- Symbol: {sym} (1,000 5m Candles) ---')
        first_t = int(data[0][0])
        last_t = int(data[-1][0])
        first_dt = datetime.fromtimestamp(first_t / 1000, tz=timezone.utc).isoformat()
        last_dt = datetime.fromtimestamp(last_t / 1000, tz=timezone.utc).isoformat()
        total_span_hours = (last_t - first_t) / (1000 * 3600)
        total_span_days = total_span_hours / 24.0

        print(f'Count: {len(data)}')
        print(f'First candle: {first_t} ({first_dt})')
        print(f'Last candle:  {last_t} ({last_dt})')
        print(f'Total span:   {total_span_hours:.2f} hours ({total_span_days:.2f} days)')

        # Check duplicates and missing intervals
        timestamps = [int(k[0]) for k in data]
        unique_ts = set(timestamps)
        duplicates = len(timestamps) - len(unique_ts)
        print(f'Duplicates:   {duplicates}')

        gaps = []
        for i in range(1, len(timestamps)):
            diff = timestamps[i] - timestamps[i - 1]
            if diff != 300000:  # 5 min = 300,000 ms
                gaps.append((i, timestamps[i-1], timestamps[i], diff))
        print(f'Missing interval gaps (>5m): {len(gaps)}')
        if gaps:
            for g in gaps[:5]:
                print(f'  Gap at index {g[0]}: prev {g[1]}, curr {g[2]}, diff {g[3]}ms')

    # 2. Inspect SQLite records from Phase 3.1 testnet run
    conn = get_db_connection()
    print('\n' + '=' * 80)
    print('RECONCILING PHASE 3.1 TESTNET RUN DATABASE RECORDS')
    print('=' * 80)

    # Check orders
    orders = conn.execute("""
        SELECT order_id, client_order_id, symbol, side, order_type, intent, 
               quantity, price, stop_price, status, executed_qty, avg_fill_price, created_at 
        FROM futures_orders 
        WHERE client_order_id LIKE 'TESTNET-%' 
        ORDER BY created_at DESC LIMIT 10
    """).fetchall()

    print(f'Recent Testnet Orders in DB: {len(orders)}')
    for o in orders:
        print(dict(o))

    # Check fills
    fills = conn.execute("""
        SELECT fill_id, order_id, client_order_id, symbol, side, price, quantity, fee_amount, fee_asset, created_at 
        FROM futures_fills 
        WHERE client_order_id LIKE 'TESTNET-%' 
        ORDER BY created_at DESC LIMIT 10
    """).fetchall()
    print(f'\nRecent Testnet Fills in DB: {len(fills)}')
    for f in fills:
        print(dict(f))

    # Check realized pnl
    pnls = conn.execute("""
        SELECT pnl_id, symbol, entry_price, exit_price, closed_qty, gross_pnl_usd, total_fees_usd, net_pnl_usd, created_at 
        FROM futures_realized_pnl 
        ORDER BY created_at DESC LIMIT 5
    """).fetchall()
    print(f'\nRecent Realized P&L Records in DB: {len(pnls)}')
    for p in pnls:
        print(dict(p))

    # Check scalp signals
    signals = conn.execute("""
        SELECT signal_id, symbol, direction, market_price, entry_price, stop_price, target_exit_price, 
               expected_net_pnl, signal_score, regime, status, rejection_reason, created_at 
        FROM futures_scalp_signals 
        ORDER BY created_at DESC LIMIT 5
    """).fetchall()
    print(f'\nRecent Scalp Signals in DB: {len(signals)}')
    for s in signals:
        print(dict(s))

if __name__ == '__main__':
    run_audit()
