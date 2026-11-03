import math
import logging
import httpx
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class TradeSetupEngine:
    """
    Evaluates coins for directional trade opportunities (LONG / SHORT).
    Computes Entry Zone, Take Profit, Stop Loss, Invalidation, and Risk-to-Reward ratio.
    """

    async def fetch_klines_atr(self, symbol: str, interval: str = '1h', limit: int = 24) -> Dict[str, float]:
        """Queries Binance klines to calculate ATR and directional structure."""
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
                logger.error(f"Error fetching klines for trade setup {symbol}: {e}")
                return {"atr": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}

    async def evaluate_trade_setup(
        self,
        symbol: str,
        current_price: float,
        change_24h: float,
        high_24h: float,
        low_24h: float,
        volume_24h: float,
        user_capital: float = 100.0
    ) -> Dict[str, Any]:
        """
        Calculates a directional trade setup (LONG / SHORT).
        """
        clean_sym = symbol.upper().replace('/USDT', '').replace('-USD', '').replace('USDT', '')
        
        # 1. Fetch 1h volatility
        atr_data = await self.fetch_klines_atr(clean_sym, interval='1h', limit=24)
        atr = atr_data["atr"]
        if atr <= 0:
            atr = current_price * 0.018  # 1.8% fallback
            
        # 2. Determine Direction based on momentum and price position in 24h range
        range_span = high_24h - low_24h
        mid_point = low_24h + (range_span * 0.5) if range_span > 0 else current_price
        
        if change_24h >= 0:
            direction = "LONG"
            bias_desc = "Bullish continuation / pull-back absorption"
            entry_low = round(current_price * 0.995, 4)
            entry_high = round(current_price * 1.005, 4)
            take_profit = round(current_price + (2.5 * atr), 4)
            stop_loss = round(current_price - (1.2 * atr), 4)
            invalidation_price = round(current_price - (1.5 * atr), 4)
            invalidation_rule = f"1h candle close below ${invalidation_price:,.2f}"
            risk_dist = current_price - stop_loss
            reward_dist = take_profit - current_price
        else:
            direction = "SHORT"
            bias_desc = "Bearish rejection / breakdown continuation"
            entry_low = round(current_price * 0.995, 4)
            entry_high = round(current_price * 1.005, 4)
            take_profit = round(current_price - (2.5 * atr), 4)
            stop_loss = round(current_price + (1.2 * atr), 4)
            invalidation_price = round(current_price + (1.5 * atr), 4)
            invalidation_rule = f"1h candle close above ${invalidation_price:,.2f}"
            risk_dist = stop_loss - current_price
            reward_dist = current_price - take_profit

        rr_ratio = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 2.08

        # Risk level determination
        if abs(change_24h) < 3.0:
            risk_level = "Low"
            regime = "Controlled Consolidation"
        elif abs(change_24h) < 8.0:
            risk_level = "Medium"
            regime = "Moderate Momentum Trend"
        else:
            risk_level = "Elevated"
            regime = "High Volatility Expansion"

        # Gate checks
        if abs(change_24h) > 25.0:
            return {
                "symbol": f"{clean_sym}/USDT",
                "strategy": "TRADE_SETUP",
                "status": "REJECTED",
                "reason": f"Hazardous 24h delta ({change_24h:+.1f}% > 25%). Setup invalid due to extreme volatility."
            }

        warnings = []
        if volume_24h > 0 and volume_24h < 5_000_000:
            warnings.append(f"Low 24h trading volume (${volume_24h:,.0f}).")

        return {
            "symbol": f"{clean_sym}/USDT",
            "strategy": "TRADE_SETUP",
            "status": "SUITABLE",
            "direction": direction,
            "bias_desc": bias_desc,
            "current_price": current_price,
            "entry_zone": f"${entry_low:,.2f} - ${entry_high:,.2f}",
            "entry_price": current_price,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "invalidation_rule": invalidation_rule,
            "reward_to_risk": rr_ratio,
            "risk_level": risk_level,
            "market_regime": regime,
            "atr_1h": round(atr, 4),
            "warnings": warnings,
            "user_capital": user_capital,
            "position_size_usdt": user_capital
        }

    async def scan_trade_setup_candidates(self, user_capital: float = 100.0) -> List[Dict[str, Any]]:
        """
        Scans market pairs and evaluates dynamic directional trade setups based on live Binance market data.
        """
        from .market_data import fetch_live_market_data
        mkt_data = await fetch_live_market_data()
        candidates = []
        
        for sym, mkt in mkt_data.items():
            try:
                status = mkt.get("status", mkt.get("market_status"))
                price = mkt.get("price")
                if status not in ("PASS", "NORMAL") or price is None or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                    logger.info(f"Skipping {sym} for trade setup scan: market data unavailable (status={status}, price={price})")
                    continue

                eval_res = await self.evaluate_trade_setup(
                    symbol=f"{sym}/USDT",
                    current_price=float(price),
                    change_24h=float(mkt.get("change_24h") or 0.0),
                    high_24h=float(mkt.get("high_24h") or (price * 1.03)),
                    low_24h=float(mkt.get("low_24h") or (price * 0.97)),
                    volume_24h=float(mkt.get("volume_24h") or 0.0),
                    user_capital=user_capital
                )
                if eval_res.get("status") == "SUITABLE":
                    candidates.append(eval_res)
            except Exception as e:
                logger.error(f"Error evaluating {sym} for trade setup scan: {e}")
                
        # Sort candidates by reward to risk
        candidates.sort(
            key=lambda x: x.get("reward_to_risk", 0.0),
            reverse=True
        )
        return candidates

trade_setup_engine = TradeSetupEngine()
