import math
import logging
import httpx
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class SpotGridEngine:
    """
    Spot Grid Calculation Engine for Binance Spot Trading.
    Dynamically computes grid bounds, counts, spacings, and fees based on Binance exchangeInfo and real ATR.
    """
    MAKER_FEE_PCT = 0.10
    TAKER_FEE_PCT = 0.10
    SLIPPAGE_SPREAD_BUFFER_PCT = 0.05
    ROUNDTRIP_FEES_PCT = 0.20  # 0.10% Maker + 0.10% Taker
    TOTAL_FRICTION_PCT = 0.25  # 0.20% fees + 0.05% buffer
    MIN_SAFETY_MARGIN_PCT = 0.35
    MIN_VIABLE_GROSS_SPACING_PCT = 0.60

    async def fetch_exchange_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Queries Binance exchangeInfo for real lot sizing and minimum notional requirements."""
        clean_symbol = symbol.upper().replace('/USDT', '').replace('-USD', '').replace('USDT', '')
        url = f"https://api.binance.com/api/v3/exchangeInfo?symbol={clean_symbol}USDT"
        
        async with httpx.AsyncClient(timeout=6.0) as client:
            try:
                res = await client.get(url)
                if res.status_code != 200:
                    logger.warning(f"Failed to fetch exchangeInfo for {symbol}: status {res.status_code}")
                    return None
                
                data = res.json()
                symbols_info = data.get("symbols", [])
                if not symbols_info:
                    return None
                
                info = symbols_info[0]
                filters = {f["filterType"]: f for f in info.get("filters", [])}
                
                min_notional = 5.0
                if "NOTIONAL" in filters:
                    min_notional = float(filters["NOTIONAL"].get("minNotional", 5.0))
                elif "MIN_NOTIONAL" in filters:
                    min_notional = float(filters["MIN_NOTIONAL"].get("minNotional", 5.0))
                    
                min_qty = 0.0001
                step_size = 0.0001
                if "LOT_SIZE" in filters:
                    min_qty = float(filters["LOT_SIZE"].get("minQty", 0.0001))
                    step_size = float(filters["LOT_SIZE"].get("stepSize", 0.0001))
                    
                tick_size = 0.01
                min_price = 0.01
                if "PRICE_FILTER" in filters:
                    tick_size = float(filters["PRICE_FILTER"].get("tickSize", 0.01))
                    min_price = float(filters["PRICE_FILTER"].get("minPrice", 0.01))
                    
                return {
                    "minNotional": min_notional,
                    "minQty": min_qty,
                    "stepSize": step_size,
                    "tickSize": tick_size,
                    "minPrice": min_price,
                    "label": "Estimated minimum from Binance filters"
                }
            except Exception as e:
                logger.error(f"Error fetching exchangeInfo for {symbol}: {e}")
                return None

    async def fetch_klines_atr(self, symbol: str, interval: str = '1h', limit: int = 24) -> Dict[str, float]:
        """Queries Binance klines to calculate ATR and dynamic range spans."""
        clean_symbol = symbol.upper().replace('/USDT', '').replace('-USD', '').replace('USDT', '')
        url = f"https://api.binance.com/api/v3/klines?symbol={clean_symbol}USDT&interval={interval}&limit={limit}"
        
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                res = await client.get(url)
                if res.status_code != 200:
                    return {"atr": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}
                
                klines = res.json()
                if not klines:
                    return {"atr": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}
                
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
                    "low": min(lows),
                    "close": float(klines[-1][4])
                }
            except Exception as e:
                logger.error(f"Error fetching klines for {symbol}: {e}")
                return {"atr": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}

    async def evaluate_pair_for_grid(
        self,
        symbol: str,
        current_price: float,
        change_24h: float,
        high_24h: float,
        low_24h: float,
        volume_24h: float,
        user_capital: float = 100.0,
        strategy_type: str = "SHORT_TERM"
    ) -> Dict[str, Any]:
        """
        Dynamically calculates optimal Spot Grid parameters for a given pair.
        """
        clean_sym = symbol.upper().replace('/USDT', '').replace('-USD', '').replace('USDT', '')
        
        # 1. Fetch real exchangeInfo filters
        ex_info = await self.fetch_exchange_info(clean_sym)
        min_notional = ex_info["minNotional"] if ex_info else 5.0

        # 2. Dynamic Price Range from ATR / Market Structure
        if strategy_type.upper() == "SHORT_TERM":
            atr_data = await self.fetch_klines_atr(clean_sym, interval='1h', limit=24)
            atr = atr_data["atr"]
            if atr > 0:
                lower_price = max(current_price - (2.5 * atr), current_price * 0.85)
                upper_price = min(current_price + (2.5 * atr), current_price * 1.15)
            else:
                lower_price = current_price * 0.95
                upper_price = current_price * 1.05
        else: # LONGER_TERM
            atr_data_1d = await self.fetch_klines_atr(clean_sym, interval='1d', limit=7)
            if atr_data_1d["high"] > 0 and atr_data_1d["low"] > 0:
                lower_price = atr_data_1d["low"] * 0.95
                upper_price = atr_data_1d["high"] * 1.05
            else:
                lower_price = current_price * 0.85
                upper_price = current_price * 1.15

        if lower_price >= upper_price:
            lower_price = current_price * 0.95
            upper_price = current_price * 1.05

        total_range_pct = ((upper_price - lower_price) / current_price) * 100.0

        # 3. Dynamic Grid Count Calculation
        order_cost_with_buffer = min_notional * 1.05
        max_grids_capital = max(3, math.floor(user_capital / order_cost_with_buffer))
        max_grids_spacing = max(3, math.floor(total_range_pct / self.MIN_VIABLE_GROSS_SPACING_PCT))

        target_grids = 8 if strategy_type.upper() == "SHORT_TERM" else 20
        grid_count = min(target_grids, max_grids_capital, max_grids_spacing)
        grid_count = max(3, min(150, grid_count))

        grid_mode = "Arithmetic" if strategy_type.upper() == "SHORT_TERM" else "Geometric"

        if grid_mode == "Arithmetic":
            step_size_price = (upper_price - lower_price) / grid_count
            gross_spacing_pct = (step_size_price / current_price) * 100.0
        else:
            ratio = (upper_price / lower_price) ** (1.0 / grid_count)
            gross_spacing_pct = (ratio - 1.0) * 100.0

        # 4. Net per completed grid cycle calculation
        net_profit_per_grid = round(gross_spacing_pct - self.TOTAL_FRICTION_PCT, 2)

        # 5. If net profit is below the 0.35% threshold, reduce grid count if viable
        if net_profit_per_grid < self.MIN_SAFETY_MARGIN_PCT:
            viable_grids = math.floor(total_range_pct / self.MIN_VIABLE_GROSS_SPACING_PCT)
            if viable_grids >= 3:
                grid_count = min(viable_grids, max_grids_capital)
                if grid_mode == "Arithmetic":
                    gross_spacing_pct = (((upper_price - lower_price) / grid_count) / current_price) * 100.0
                else:
                    gross_spacing_pct = (((upper_price / lower_price) ** (1.0 / grid_count)) - 1.0) * 100.0
                net_profit_per_grid = round(gross_spacing_pct - self.TOTAL_FRICTION_PCT, 2)

        # 6. Hard Cost-Floor Gate Check
        if net_profit_per_grid < self.MIN_SAFETY_MARGIN_PCT:
            return {
                "symbol": symbol,
                "strategy": strategy_type,
                "status": "REJECTED",
                "failed_gate": "FAILED_COST_FLOOR",
                "gross_grid_spacing_pct": round(gross_spacing_pct, 3),
                "roundtrip_fees_pct": self.ROUNDTRIP_FEES_PCT,
                "slippage_spread_pct": self.SLIPPAGE_SPREAD_BUFFER_PCT,
                "total_friction_pct": self.TOTAL_FRICTION_PCT,
                "net_per_completed_grid_cycle": net_profit_per_grid,
                "min_safety_margin_required": self.MIN_SAFETY_MARGIN_PCT,
                "reason": (
                    f"FAILED COST FLOOR: Net margin per completed cycle ({net_profit_per_grid:.2f}%) "
                    f"fails declared minimum {self.MIN_SAFETY_MARGIN_PCT:.2f}% threshold "
                    f"(Gross spacing {gross_spacing_pct:.2f}% < required {self.MIN_VIABLE_GROSS_SPACING_PCT:.2f}% over 0.25% friction)."
                )
            }

        # Gate 0 Capital Requirements
        floor_capital = math.ceil(3 * min_notional * 1.05)
        required_capital = math.ceil(grid_count * min_notional * 1.05)
        
        reduced_grid_alternative = None
        
        if user_capital < floor_capital:
            capital_status = "REJECTED"
            capital_rec = {
                "status": "REJECTED",
                "user_capital": user_capital,
                "recommended_capital": floor_capital,
                "additional_capital_needed": round(floor_capital - user_capital, 2),
                "reason": f"FAILED GATE 0: Entered capital (${user_capital}) cannot support minimum 3 grids (${floor_capital} floor)."
            }
        elif user_capital < required_capital:
            capital_status = "CAPITAL_ADJUSTMENT"
            alt_grid_count = max_grids_capital
            if alt_grid_count >= 3:
                if grid_mode == "Arithmetic":
                    alt_gross = (((upper_price - lower_price) / alt_grid_count) / current_price) * 100.0
                else:
                    alt_gross = (((upper_price / lower_price) ** (1.0 / alt_grid_count)) - 1.0) * 100.0
                alt_net = round(alt_gross - self.TOTAL_FRICTION_PCT, 2)
                if alt_net >= self.MIN_SAFETY_MARGIN_PCT:
                    reduced_grid_alternative = {
                        "grid_count": alt_grid_count,
                        "investment_amount": user_capital,
                        "net_per_cycle": alt_net
                    }
            capital_rec = {
                "status": "CAPITAL_ADJUSTMENT",
                "user_capital": user_capital,
                "recommended_capital": required_capital,
                "additional_capital_needed": round(required_capital - user_capital, 2),
                "reason": f"Requires additional capital (${required_capital}) for optimal {grid_count} grids."
            }
        else:
            capital_status = "SUITABLE"
            capital_rec = {
                "status": "SUITABLE",
                "user_capital": user_capital,
                "recommended_capital": required_capital,
                "additional_capital_needed": 0.0,
                "reason": "Capital fully satisfies Binance minimum order requirements and optimal grid spacing."
            }

        warnings = []
        if volume_24h > 0 and volume_24h < 5_000_000:
            warnings.append(f"Low 24h trading volume (${volume_24h:,.0f}).")
            
        if abs(change_24h) > 25.0:
            return {
                "symbol": symbol,
                "status": "REJECTED",
                "reason": f"Hazardous volatility detected (24h change: {change_24h:+.1f}% > 25%)."
            }
            
        if capital_status == "REJECTED":
            return {
                "symbol": symbol,
                "status": "REJECTED",
                "reason": capital_rec["reason"]
            }

        invalidation_price = round(lower_price * 0.965, 4)
        exit_price = round(upper_price * 1.035, 4)

        if abs(change_24h) < 3.0:
            risk_level = "Low"
            market_regime = "Controlled Consolidation"
        elif abs(change_24h) < 8.0:
            risk_level = "Medium"
            market_regime = "Moderate Trend Channel"
        else:
            risk_level = "Elevated"
            market_regime = "High Volatility Expansion"

        is_st = strategy_type.upper() == "SHORT_TERM"
        risk_flags = [
            f"Horizon: {'1-3 days' if is_st else '1-4 weeks'}",
            f"Maker fee: {self.MAKER_FEE_PCT:.2f}% | Taker fee: {self.TAKER_FEE_PCT:.2f}%",
            f"Slippage/Spread Buffer: {self.SLIPPAGE_SPREAD_BUFFER_PCT:.2f}%",
            f"24h change: {change_24h:+.1f}%"
        ]
        if warnings:
            risk_flags.extend(warnings)

        gov = "Capital Limit" if max_grids_capital < min(target_grids, max_grids_spacing) else ("Spacing Limit" if max_grids_spacing < target_grids else "Strategy Target Density")

        return {
            "symbol": symbol,
            "strategy": strategy_type,
            "status": capital_status,
            "warnings": warnings,
            "current_price": current_price,
            "change_24h": change_24h,
            "grid_range": {
                "lower": round(lower_price, 4),
                "upper": round(upper_price, 4)
            },
            "grid_count": grid_count,
            "grid_mode": grid_mode,
            "gross_grid_spacing_pct": round(gross_spacing_pct, 3),
            "roundtrip_fees_pct": self.ROUNDTRIP_FEES_PCT,
            "slippage_spread_pct": self.SLIPPAGE_SPREAD_BUFFER_PCT,
            "total_friction_pct": self.TOTAL_FRICTION_PCT,
            "net_per_completed_grid_cycle": net_profit_per_grid,
            "min_safety_margin_required": self.MIN_SAFETY_MARGIN_PCT,
            "net_per_completed_grid_cycle_desc": (
                f"Gross Spacing ({gross_spacing_pct:.2f}%) - Roundtrip Fees ({self.ROUNDTRIP_FEES_PCT:.2f}%) - "
                f"Slippage/Spread ({self.SLIPPAGE_SPREAD_BUFFER_PCT:.2f}%) = Net Margin ({net_profit_per_grid:.2f}%). "
                f"Meets declared hard floor threshold (>={self.MIN_SAFETY_MARGIN_PCT:.2f}%). "
                f"This is an order-level completed cycle metric, not a portfolio or annualized guarantee."
            ),
            "capital_evaluation": capital_rec,
            "reduced_grid_alternative": reduced_grid_alternative,
            "investment_amount": required_capital if capital_status == "CAPITAL_ADJUSTMENT" else user_capital,
            "invalidation_rule": f"Price closes below ${invalidation_price:,.2f}",
            "full_exit_rule": f"Price closes above ${exit_price:,.2f}",
            "exchange_info": ex_info,
            "risk_level": risk_level,
            "market_regime": market_regime,
            "risk_flags": risk_flags,
            "governing_constraint": gov
        }

    async def scan_spot_grid_candidates(self, user_capital: float = 100.0, strategy_type: str = "SHORT_TERM") -> List[Dict[str, Any]]:
        """
        Scans market pairs and evaluates dynamic spot grid opportunities based on live Binance market data.
        """
        from .market_data import fetch_live_market_data
        mkt_data = await fetch_live_market_data()
        candidates = []
        
        for sym, mkt in mkt_data.items():
            try:
                status = mkt.get("status", mkt.get("market_status"))
                price = mkt.get("price")
                if status not in ("PASS", "NORMAL") or price is None or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                    logger.info(f"Skipping {sym} for spot grid scan: market data unavailable (status={status}, price={price})")
                    continue

                eval_res = await self.evaluate_pair_for_grid(
                    symbol=f"{sym}USDT",
                    current_price=float(price),
                    change_24h=float(mkt.get("change_24h") or 0.0),
                    high_24h=float(mkt.get("high_24h") or (price * 1.02)),
                    low_24h=float(mkt.get("low_24h") or (price * 0.98)),
                    volume_24h=float(mkt.get("volume_24h") or 0.0),
                    user_capital=user_capital,
                    strategy_type=strategy_type
                )
                if eval_res.get("status") in ("SUITABLE", "CAPITAL_ADJUSTMENT"):
                    candidates.append(eval_res)
            except Exception as e:
                logger.error(f"Error evaluating {sym} for spot grid scan: {e}")
                
        # Sort candidates: prioritize SUITABLE and highest net_per_completed_grid_cycle
        candidates.sort(
            key=lambda x: (
                1 if x.get("status") == "SUITABLE" else 0,
                x.get("net_per_completed_grid_cycle", 0)
            ),
            reverse=True
        )
        return candidates

spot_grid_engine = SpotGridEngine()
