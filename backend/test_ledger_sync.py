import sys, asyncio
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
from app.services.ledger_db import init_ledger_tables, sync_binance_account, query_open_orders, query_order_history, query_trade_history, query_spot_holdings, get_order_audit_dossier

init_ledger_tables()
print('✓ Tables initialized.')

async def run_sync():
    res = await sync_binance_account(account_id='CONN-DK-BIN-DEMO-MIGRATED', user_id='USR-402F7BFE6D')
    print('Sync result:', res)

    # 1. Check Open Orders
    opens = query_open_orders(user_id='USR-402F7BFE6D')
    print(f'Open Orders ({len(opens)}):', opens)

    # 2. Check Order History
    orders, o_total = query_order_history(user_id='USR-402F7BFE6D', limit=15)
    print(f'Order History ({o_total} total, showing {len(orders)}):')
    for o in orders:
        print(f"   Order #{o['exchange_order_id']} | {o['display_pair']} | {o['side']} {o['order_type']} | status={o['status']} | origQty={o['orig_qty']} | execQty={o['executed_qty']} | avgPx={o['avg_fill_price']} | fills={len(o.get('fills', []))}")

    # 3. Check Trade History
    trades, t_total = query_trade_history(user_id='USR-402F7BFE6D', limit=15)
    print(f'Trade History ({t_total} total, showing {len(trades)}):')
    for t in trades:
        print(f"   Trade #{t['exchange_trade_id']} | Order #{t['exchange_order_id']} | {t['display_pair']} | {t['side']} | px={t['price']} | qty={t['qty']} | comm={t['commission']} {t['commission_asset']} | net={t.get('net_impact_str')}")

    # 4. Check Spot Holdings
    holdings = query_spot_holdings(user_id='USR-402F7BFE6D')
    print(f'Spot Holdings ({len(holdings)}):')
    for h in holdings:
        print(f"   {h['asset']}: free={h['free']} | locked={h['locked']} | total={h['total']} | val_usd=${h['valuation_usd']}")

    # 5. Check Dossier for Order 537182101
    dossier = get_order_audit_dossier(user_id='USR-402F7BFE6D', order_id_or_client_id='537182101')
    print('Order 537182101 Dossier Found:', bool(dossier))
    if dossier:
        print(f"   Dossier: pair={dossier['display_pair']}, side={dossier['side']}, status={dossier['status']}, fills={len(dossier['fills'])}, netBase={dossier.get('net_settlement_base')}, netQuote={dossier.get('net_settlement_quote')}")

asyncio.run(run_sync())
