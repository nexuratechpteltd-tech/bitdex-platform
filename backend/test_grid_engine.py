import asyncio
import math
import httpx

class DynamicSpotGridEngine:
    async def fetch_exchange_info(self, symbol: str):
        clean = symbol.upper().replace('/USDT', '').replace('-USD', '').replace('USDT', '')
        url = f"https://api.binance.com/api/v3/exchangeInfo?symbol={clean}USDT"
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                res = await client.get(url)
                if res.status_code != 200:
                    return None
                data = res.json()
                sym_info = data["symbols"][0]
                filters = {f["filterType"]: f for f in sym_info["filters"]}
                min_notional = float(filters.get("NOTIONAL", {}).get("minNotional", 5.0))
                min_qty = float(filters.get("LOT_SIZE", {}).get("minQty", 0.001))
                step_size = float(filters.get("LOT_SIZE", {}).get("stepSize", 0.001))
                tick_size = float(filters.get("PRICE_FILTER", {}).get("tickSize", 0.01))
                min_price = float(filters.get("PRICE_FILTER", {}).get("minPrice", 0.01))
                return {
                    "minNotional": min_notional,
                    "minQty": min_qty,
                    "stepSize": step_size,
                    "tickSize": tick_size,
                    "minPrice": min_price,
                    "label": "Estimated minimum from Binance filters"
                }
            except Exception:
                return None

    async def fetch_klines_atr(self, symbol: str, interval: str = '1h', limit: int = 24):
        clean = symbol.upper().replace('/USDT', '').replace('-USD', '').replace('USDT', '')
        url = f"https://api.binance.com/api/v3/klines?symbol={clean}USDT&interval={interval}&limit={limit}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                res = await client.get(url)
                if res.status_code != 200:
                    return {"atr": 0.0, "high": 0.0, "low": 0.0}
                klines = res.json()
                if not klines:
                    return {"atr": 0.0, "high": 0.0, "low": 0.0}
                true_ranges = []
                highs = []
                lows = []
                for i in range(len(klines)):
                    high = float(klines[i][2])
                    low = float(klines[i][3])
                    highs.append(high)
                    lows.append(low)
                    if i == 0:
                        tr = high - low
                    else:
                        prev_close = float(klines[i-1][4])
                        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                    true_ranges.append(tr)
                atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
                return {
                    "atr": atr,
                    "high": max(highs),
                    "low": min(lows)
                }
            except Exception:
                return {"atr": 0.0, "high": 0.0, "low": 0.0}

    async def evaluate_pair(self, symbol: str, current_price: float, change_24h: float, volume_24h: float, user_capital: float, strategy: str = "SHORT_TERM"):
        is_short_term = (strategy.upper() == "SHORT_TERM")
        ex_info = await self.fetch_exchange_info(symbol)
        if not ex_info:
            return {"symbol": symbol, "status": "REJECTED", "reason": "Exchange info unavailable"}
            
        min_notional = ex_info["minNotional"]
        
        # 1. Price Range Derivation from Market Volatility
        if is_short_term:
            atr_data = await self.fetch_klines_atr(symbol, interval='1h', limit=24)
            atr = atr_data["atr"]
            if atr <= 0:
                atr = current_price * 0.015  # Fallback 1.5%
            range_span = 3 * atr
            lower_price = current_price - range_span
            upper_price = current_price + range_span
            grid_mode = "Arithmetic"
            target_spacing_pct = 0.55  # Target ~0.55% spacing for short-term mean-reversion
        else:
            atr_1d = await self.fetch_klines_atr(symbol, interval='1d', limit=7)
            if atr_1d["low"] > 0 and atr_1d["high"] > 0:
                lower_price = atr_1d["low"] * 0.90
                upper_price = atr_1d["high"] * 1.10
            else:
                lower_price = current_price * 0.85
                upper_price = current_price * 1.15
            grid_mode = "Geometric"
            target_spacing_pct = 1.40  # Target ~1.40% spacing for longer-term structure
            
        lower_price = max(lower_price, ex_info["minPrice"])
        total_range_pct = ((upper_price - lower_price) / current_price) * 100.0

        # 2. Friction & Cost Floor Parameters
        maker_fee = 0.0010      # 0.10%
        taker_fee = 0.0010      # 0.10%
        slippage = 0.0005       # 0.05%
        total_friction_pct = (maker_fee + taker_fee + slippage) * 100.0  # 0.25%
        min_profitable_spacing_pct = total_friction_pct + 0.10           # 0.35% minimum spacing

        # 3. Dynamic Grid Count Calculation based on Constraints:
        # Constraint A: Capital limit (how many grids can user afford at minNotional + 5% buffer)
        max_grids_capital = math.floor(user_capital / (min_notional * 1.05))
        
        # Constraint B: Spacing limit (maximum grids before spacing falls below 0.35%)
        max_grids_spacing = max(3, math.floor(total_range_pct / min_profitable_spacing_pct))
        
        # Constraint C: Target strategy grid count based on range and strategy target spacing
        target_grids = max(3, round(total_range_pct / target_spacing_pct))
        
        # Dynamic grid count: optimal target capped by capital and spacing
        computed_grid_count = min(target_grids, max_grids_capital, max_grids_spacing)
        grid_count = max(3, min(150, computed_grid_count))
        
        # 4. Spacing & Cost Floor Evaluation
        if grid_mode == "Arithmetic":
            grid_spacing_usd = (upper_price - lower_price) / grid_count
            avg_spacing_pct = (grid_spacing_usd / current_price) * 100.0
        else:
            ratio = (upper_price / lower_price) ** (1.0 / grid_count)
            avg_spacing_pct = (ratio - 1.0) * 100.0

        net_per_cycle = round(avg_spacing_pct - total_friction_pct, 2)
        
        # If net_per_cycle is below 0.05%, try reducing grid count to restore profitability
        if net_per_cycle < 0.05:
            viable_grids = math.floor(total_range_pct / min_profitable_spacing_pct)
            if viable_grids >= 3:
                grid_count = min(viable_grids, max_grids_capital)
                if grid_mode == "Arithmetic":
                    avg_spacing_pct = (((upper_price - lower_price) / grid_count) / current_price) * 100.0
                else:
                    avg_spacing_pct = (((upper_price / lower_price) ** (1.0 / grid_count)) - 1.0) * 100.0
                net_per_cycle = round(avg_spacing_pct - total_friction_pct, 2)

        # Gate 0 Capital Requirements
        floor_capital = math.ceil(3 * min_notional * 1.05)
        required_capital = math.ceil(grid_count * min_notional * 1.05)
        
        # Failure checks
        if user_capital < floor_capital:
            return {
                "symbol": symbol,
                "strategy": strategy,
                "user_capital": user_capital,
                "status": "REJECTED",
                "grid_count": grid_count,
                "reason": f"Capital ${user_capital} below minimum ${floor_capital} required for 3 grids at Binance min notional ${min_notional}."
            }
            
        if net_per_cycle < 0.05:
            return {
                "symbol": symbol,
                "strategy": strategy,
                "user_capital": user_capital,
                "status": "REJECTED",
                "grid_count": grid_count,
                "reason": f"FAILED COST FLOOR: Grid spacing ({avg_spacing_pct:.2f}%) cannot clear 0.25% round-trip friction and leave a viable profit margin."
            }
            
        capital_status = "SUITABLE" if user_capital >= required_capital else "CAPITAL_ADJUSTMENT"
        
        reduced_alt = None
        if capital_status == "CAPITAL_ADJUSTMENT":
            alt_grids = max_grids_capital
            if alt_grids >= 3:
                if grid_mode == "Arithmetic":
                    alt_spacing = (((upper_price - lower_price) / alt_grids) / current_price) * 100.0
                else:
                    alt_spacing = (((upper_price / lower_price) ** (1.0 / alt_grids)) - 1.0) * 100.0
                alt_net = round(alt_spacing - total_friction_pct, 2)
                if alt_net >= 0.05:
                    reduced_alt = {"grid_count": alt_grids, "net_per_cycle": alt_net}

        gov = "Capital Limit" if max_grids_capital < min(target_grids, max_grids_spacing) else ("Spacing Limit" if max_grids_spacing < target_grids else "Strategy Target Density")

        return {
            "symbol": symbol,
            "strategy": strategy,
            "user_capital": user_capital,
            "current_price": current_price,
            "grid_range": {"lower": round(lower_price, 4), "upper": round(upper_price, 4)},
            "total_range_pct": round(total_range_pct, 2),
            "grid_count": grid_count,
            "grid_mode": grid_mode,
            "avg_spacing_pct": round(avg_spacing_pct, 3),
            "net_per_completed_grid_cycle": net_per_cycle,
            "status": capital_status,
            "constraints": {
                "max_grids_by_capital": max_grids_capital,
                "max_grids_by_spacing": max_grids_spacing,
                "target_grids_by_strategy": target_grids,
                "governing_constraint": gov
            },
            "reduced_grid_alternative": reduced_alt
        }

async def run_tests():
    engine = DynamicSpotGridEngine()
    symbols = ["AVAXUSDT", "SOLUSDT", "BTCUSDT"]
    capitals = [20, 50, 100, 250, 1000]
    prices = {"AVAXUSDT": 11.38, "SOLUSDT": 119.5, "BTCUSDT": 83500.0}
    
    print("=" * 95)
    print("DYNAMIC GRID DERIVATION & CONSTRAINT TESTS")
    print("=" * 95)
    
    for sym in symbols:
        price = prices[sym]
        print(f"\n>>> PAIR: {sym} (Price: ${price:,.2f}) <<<")
        for cap in capitals:
            for strat in ["SHORT_TERM", "LONGER_TERM"]:
                res = await engine.evaluate_pair(sym, price, 1.5, 20_000_000, cap, strat)
                if res.get("status") == "REJECTED":
                    print(f"  Cap ${cap:<5} | {strat:<11} | STATUS: REJECTED | Reason: {res.get('reason')}")
                else:
                    c = res["constraints"]
                    print(f"  Cap ${cap:<5} | {strat:<11} | Grids: {res['grid_count']:<3} ({res['grid_mode']:<10}) | Range: {res['total_range_pct']:>5.2f}% | Spacing: {res['avg_spacing_pct']:>5.3f}% | Net/Cycle: {res['net_per_completed_grid_cycle']:>5.2f}% | Gov: {c['governing_constraint']}")

asyncio.run(run_tests())
