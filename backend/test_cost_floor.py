import asyncio
import math
import httpx

async def test():
    symbols = ['BTCUSDT', 'SOLUSDT', 'AVAXUSDT']
    
    async with httpx.AsyncClient(timeout=8.0) as client:
        for sym in symbols:
            # 1. exchangeInfo
            r_ex = await client.get(f'https://api.binance.com/api/v3/exchangeInfo?symbol={sym}')
            d_ex = r_ex.json()
            filters = {f['filterType']: f for f in d_ex['symbols'][0]['filters']}
            min_notional = float(filters.get('NOTIONAL', {}).get('minNotional', 5.0))
            
            # 2. 1h klines (for short-term)
            r_k1h = await client.get(f'https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&limit=24')
            k1h = r_k1h.json()
            trs = [max(float(k[2])-float(k[3]), abs(float(k[2])-float(k1h[i-1][4])) if i>0 else float(k[2])-float(k[3])) for i, k in enumerate(k1h)]
            atr_1h = sum(trs)/len(trs)
            curr_price = float(k1h[-1][4])
            
            # 3. 1d klines (for longer-term)
            r_k1d = await client.get(f'https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&limit=7')
            k1d = r_k1d.json()
            high_7d = max(float(k[2]) for k in k1d)
            low_7d = min(float(k[3]) for k in k1d)
            
            print(f"=== {sym} (Price: ${curr_price:.2f}) ===")
            print(f"1h ATR: ${atr_1h:.4f} ({atr_1h/curr_price*100:.2f}%), 7d Range: ${low_7d:.2f} - ${high_7d:.2f}")
            
            for strat in ['SHORT_TERM', 'LONGER_TERM']:
                if strat == 'SHORT_TERM':
                    span = 3 * atr_1h
                    lower = curr_price - span
                    upper = curr_price + span
                    mode = 'Arithmetic'
                    target_spacing = 0.70
                else:
                    lower = low_7d * 0.90
                    upper = high_7d * 1.10
                    mode = 'Geometric'
                    target_spacing = 1.50
                    
                range_pct = (upper - lower) / curr_price * 100.0
                
                # Rule constants
                fees_roundtrip = 0.20       # 0.10% maker + 0.10% taker
                slippage_spread = 0.05      # 0.05% slippage/spread buffer
                total_friction = fees_roundtrip + slippage_spread  # 0.25%
                min_safety_margin = 0.35    # Declared hard floor threshold for net margin
                min_viable_gross_spacing = total_friction + min_safety_margin  # 0.60%
                
                # Dynamic grid constraints
                max_grids_capital = math.floor(100 / (min_notional * 1.05))
                max_grids_spacing = max(3, math.floor(range_pct / min_viable_gross_spacing))
                target_grids = max(3, round(range_pct / target_spacing))
                
                grid_count = min(target_grids, max_grids_capital, max_grids_spacing)
                grid_count = max(3, min(150, grid_count))
                
                # 1. Gross Spacing
                if mode == 'Arithmetic':
                    gross_spacing = ((upper - lower) / grid_count) / curr_price * 100.0
                else:
                    gross_spacing = ((upper / lower) ** (1.0 / grid_count) - 1.0) * 100.0
                    
                # 4. Net per completed grid cycle
                net_per_cycle = round(gross_spacing - total_friction, 2)
                
                # 5 & 6. Hard Cost-Floor Gate
                if net_per_cycle < min_safety_margin:
                    status = "REJECTED - FAILED COST FLOOR"
                else:
                    status = "SUITABLE"
                
                print(f"  {strat:<11} | Range: {range_pct:>5.2f}% | Grids: {grid_count:<2} ({mode:<10}) | Gross: {gross_spacing:>5.3f}% | Friction: {total_friction}% | Net/Cycle: {net_per_cycle:>5.2f}% | Margin Req: {min_safety_margin}% | Status: {status}")

asyncio.run(test())
