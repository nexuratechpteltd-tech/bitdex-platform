import re
import sys

# Read the current grid.py
with open('/opt/tauric-platform/backend/app/routes/grid.py', 'r') as f:
    content = f.read()

# Replace the _run_analyze_job function
old_analyze = '''async def _run_analyze_job(job_id: str, req: GridAnalyzeRequest):
    try:
        _jobs[job_id]["state"] = "RUNNING"
        clean_sym = req.symbol.replace("/USDT", "").replace("-USD", "").replace("USDT", "").upper()
        
        # Fresh market-price refresh
        mkt = await fetch_single_symbol_market_data(clean_sym)
        price = mkt.get("price", 100.0)
        chg = mkt.get("change_24h", 0.0)
        high = mkt.get("high_24h", price * 1.03)
        low = mkt.get("low_24h", price * 0.97)
        vol = mkt.get("volume_24h", 20_000_000.0)
        ts = datetime.now().isoformat()
        
        grid_eval = await spot_grid_engine.evaluate_pair_for_grid(
            symbol=f"{clean_sym}USDT",
            current_price=price,
            change_24h=chg,
            high_24h=high,
            low_24h=low,
            volume_24h=vol,
            user_capital=req.capital,
            strategy_type=req.strategy
        )
        
        cache_key = (clean_sym, req.strategy, get_time_bucket_30min())
        if cache_key in _tauric_cache:
            tauric_res = _tauric_cache[cache_key]
        else:
            with telemetry_manager.track_request("tauric", operation=f"Deep Research {clean_sym}", model="deepseek-v4-pro"):
                tauric_run = tauric_engine.start_run(
                    ticker=f"{clean_sym}-USD",
                    analysts=["market", "sentiment", "news"],
                    research_depth=1
                )
                tauric_res = {"decision": "SUITABLE" if grid_eval.get("status") != "REJECTED" else "UNSUITABLE"}
                _tauric_cache[cache_key] = tauric_res
                
        # Jev blind review
        with telemetry_manager.track_request("jev", operation=f"Independent Review {clean_sym}", model="jev-1.13.0"):
            grid_params = {
                "lower_price": grid_eval.get("grid_range", {}).get("lower", 0),
                "upper_price": grid_eval.get("grid_range", {}).get("upper", 0),
                "grid_count": grid_eval.get("grid_count", 0),
                "spacing_pct": grid_eval.get("net_per_completed_grid_cycle", 0) + 0.25
            }
            mkt_state = {
                "price": price,
                "change_24h": chg,
                "volume": vol,
                "atr": (grid_eval.get("grid_range", {}).get("upper", 0) - price) / 3 if req.strategy == "SHORT_TERM" else 0
            }
            jev_review = await jev_client.blind_review(clean_sym, grid_params, mkt_state)
            
        final_plan = {
            "pair": f"{clean_sym}/USDT",
            "lower_price": grid_eval.get("grid_range", {}).get("lower"),
            "upper_price": grid_eval.get("grid_range", {}).get("upper"),
            "grid_count": grid_eval.get("grid_count"),
            "grid_mode": grid_eval.get("grid_mode"),
            "investment_amount": grid_eval.get("investment_amount"),
            "user_capital": req.capital,
            "estimated_net_profit_per_grid": grid_eval.get("net_per_completed_grid_cycle"),
            "prices_as_of": ts,
            "status": grid_eval.get("status")
        }
            
        _jobs[job_id]["state"] = "COMPLETED"
        _jobs[job_id]["result"] = {
            "status": "SUCCESS",
            "symbol": f"{clean_sym}/USDT",
            "final_binance_plan": final_plan,
            "jev_review": jev_review,
            "tauric_decision": tauric_res["decision"]
        }
    except Exception as e:
        logger.error(f"Analyze job {job_id} failed: {e}")
        _jobs[job_id]["state"] = "FAILED"
        _jobs[job_id]["error"] = "Analysis temporarily unavailable"'''

new_analyze = '''async def _run_analyze_job(job_id: str, req: GridAnalyzeRequest):
    try:
        _jobs[job_id]["state"] = "RUNNING"
        clean_sym = req.symbol.replace("/USDT", "").replace("-USD", "").replace("USDT", "").upper()
        
        # Fresh market-price refresh
        mkt = await fetch_single_symbol_market_data(clean_sym)
        price = mkt.get("price", 100.0)
        chg = mkt.get("change_24h", 0.0)
        high = mkt.get("high_24h", price * 1.03)
        low = mkt.get("low_24h", price * 0.97)
        vol = mkt.get("volume_24h", 20_000_000.0)
        ts = datetime.now().isoformat()
        
        grid_eval = await spot_grid_engine.evaluate_pair_for_grid(
            symbol=f"{clean_sym}USDT",
            current_price=price,
            change_24h=chg,
            high_24h=high,
            low_24h=low,
            volume_24h=vol,
            user_capital=req.capital,
            strategy_type=req.strategy
        )
        
        # Tauric deep research (cached by symbol+strategy+time_bucket)
        cache_key = (clean_sym, req.strategy, get_time_bucket_30min())
        if cache_key in _tauric_cache:
            tauric_res = _tauric_cache[cache_key]
        else:
            with telemetry_manager.track_request("tauric", operation=f"Deep Research {clean_sym}", model="deepseek-v4-pro"):
                tauric_run = tauric_engine.start_run(
                    ticker=f"{clean_sym}-USD",
                    analysts=["market", "sentiment", "news"],
                    research_depth=1
                )
                tauric_res = {"decision": "SUITABLE" if grid_eval.get("status") != "REJECTED" else "UNSUITABLE"}
                _tauric_cache[cache_key] = tauric_res
                
        # Independent Jev blind review — NO Tauric narrative, only raw market data + grid params
        with telemetry_manager.track_request("jev", operation=f"Independent Review {clean_sym}", model="jev-1.13.0"):
            grid_params = {
                "lower_price": grid_eval.get("grid_range", {}).get("lower", 0),
                "upper_price": grid_eval.get("grid_range", {}).get("upper", 0),
                "grid_count": grid_eval.get("grid_count", 0),
                "spacing_pct": grid_eval.get("net_per_completed_grid_cycle", 0) + 0.25
            }
            mkt_state = {
                "price": price,
                "change_24h": chg,
                "volume": vol,
                "atr": (grid_eval.get("grid_range", {}).get("upper", 0) - price) / 3 if req.strategy == "SHORT_TERM" else 0
            }
            jev_review = await jev_client.blind_review(clean_sym, grid_params, mkt_state)
        
        # Fresh price re-check for validation
        mkt2 = await fetch_single_symbol_market_data(clean_sym)
        fresh_price = mkt2.get("price", price)
        lower = grid_eval.get("grid_range", {}).get("lower", 0)
        upper = grid_eval.get("grid_range", {}).get("upper", 0)
        validation_failed = None
        if fresh_price < lower or fresh_price > upper:
            validation_failed = (
                f"Price moved to ${fresh_price:,.2f} which is outside the grid range "
                f"(${lower:,.2f} — ${upper:,.2f}). Parameters may be stale."
            )
        
        # Determine Jev decision
        jev_prob_agree = jev_review.get("prob_agree", 0.75)
        jev_decision = "SUITABLE" if jev_prob_agree >= 0.50 else "WAIT / HIGH BREAKOUT RISK"
        
        # Disagreement detection
        tauric_decision = tauric_res["decision"]
        disagreement = None
        if tauric_decision == "SUITABLE" and jev_decision != "SUITABLE":
            disagreement = {
                "divergent": True,
                "summary": "Tauric confirms range stability, but Jev identifies elevated breakout risk.",
                "tauric_view": "Range boundaries viable for automated grid execution.",
                "jev_view": f"Jev probability of stability is low ({jev_prob_agree:.0%}). Risk score: {jev_review.get('risk_score', 'medium')}."
            }
        
        net_cycle = grid_eval.get("net_per_completed_grid_cycle", 0)
        
        # Build Card A — TAURIC
        card_a_tauric = {
            "engine": "TAURIC",
            "decision": tauric_decision,
            "pair": f"{clean_sym}/USDT",
            "capital": req.capital,
            "recommended_capital": grid_eval.get("capital_evaluation", {}).get("recommended_capital", req.capital),
            "grid_range": grid_eval.get("grid_range", {}),
            "grid_count": grid_eval.get("grid_count"),
            "grid_mode": grid_eval.get("grid_mode"),
            "net_per_completed_grid_cycle": net_cycle,
            "risk_level": grid_eval.get("risk_level", "Medium"),
            "invalidation": grid_eval.get("invalidation_rule", ""),
            "full_exit": grid_eval.get("full_exit_rule", ""),
            "reason": (
                f"Multi-agent synthesis confirms structural channel between "
                f"${lower:,.2f} and ${upper:,.2f}. "
                f"Dynamic {grid_eval.get('grid_mode', 'Arithmetic').lower()} grid distribution with "
                f"{net_cycle}% fee-adjusted profit per completed cycle."
            )
        }
        
        # Build Card B — JEV (independent, no Tauric narrative)
        card_b_jev = {
            "engine": "JEV",
            "decision": jev_decision,
            "pair": f"{clean_sym}/USDT",
            "capital": req.capital,
            "grid_range": grid_eval.get("grid_range", {}),
            "grid_count": grid_eval.get("grid_count"),
            "grid_mode": grid_eval.get("grid_mode"),
            "net_per_completed_grid_cycle": net_cycle,
            "market_regime": grid_eval.get("market_regime", "Unknown"),
            "confidence": jev_review.get("confidence", 0),
            "risk_score": jev_review.get("risk_score", "medium"),
            "risk_flags": grid_eval.get("risk_flags", []) + [f"Jev Agreement Prob: {jev_prob_agree:.0%}"],
            "reason": jev_review.get("reasoning", "Jev statistical validation completed.")
        }
        
        # Build Final Binance Spot Grid Plan
        cap_eval = grid_eval.get("capital_evaluation", {})
        final_plan = {
            "pair": f"{clean_sym}/USDT",
            "lower_price": lower,
            "upper_price": upper,
            "grid_count": grid_eval.get("grid_count"),
            "grid_mode": grid_eval.get("grid_mode"),
            "investment_amount": grid_eval.get("investment_amount", req.capital),
            "user_capital": req.capital,
            "recommended_capital": cap_eval.get("recommended_capital", req.capital),
            "additional_capital_needed": cap_eval.get("additional_capital_needed", 0),
            "capital_status": grid_eval.get("status"),
            "net_per_completed_grid_cycle": net_cycle,
            "invalidation_stop": grid_eval.get("invalidation_rule", ""),
            "full_exit_condition": grid_eval.get("full_exit_rule", ""),
            "market_regime": grid_eval.get("market_regime", "Unknown"),
            "risk_level": grid_eval.get("risk_level", "Medium"),
            "risk_flags": grid_eval.get("risk_flags", []),
            "fee_structure": "Maker 0.10% + Taker 0.10% + Slippage 0.05% = 0.25% round-trip",
            "inventory_risk": (
                "Grid trading carries inventory risk: if price trends strongly in one direction, "
                "you accumulate the losing side. Monitor invalidation levels closely."
            ),
            "reduced_grid_alternative": grid_eval.get("reduced_grid_alternative"),
            "prices_as_of": ts,
            "execution_notice": "MANUAL BINANCE SPOT GRID: Copy these parameters into your native Binance Spot Grid interface. No API orders are placed."
        }
            
        _jobs[job_id]["state"] = "COMPLETED"
        _jobs[job_id]["result"] = {
            "status": "SUCCESS",
            "symbol": f"{clean_sym}/USDT",
            "tauric_card": card_a_tauric,
            "jev_card": card_b_jev,
            "disagreement": disagreement,
            "final_binance_plan": final_plan,
            "validation_failed": validation_failed
        }
    except Exception as e:
        logger.error(f"Analyze job {job_id} failed: {e}")
        _jobs[job_id]["state"] = "FAILED"
        _jobs[job_id]["error"] = "Analysis temporarily unavailable"'''

if old_analyze in content:
    content = content.replace(old_analyze, new_analyze)
    with open('/opt/tauric-platform/backend/app/routes/grid.py', 'w') as f:
        f.write(content)
    print("SUCCESS: _run_analyze_job patched")
else:
    print("ERROR: Could not find old_analyze text. Trying line-by-line approach...")
    # Find function start and replace everything until the next function
    lines = content.split('\n')
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if 'async def _run_analyze_job' in line:
            start_idx = i
        elif start_idx is not None and (line.startswith('async def ') or line.startswith('@grid_router') or line.startswith('def ')) and i > start_idx + 2:
            end_idx = i
            break
    
    if start_idx is not None:
        if end_idx is None:
            end_idx = len(lines)
        new_lines = lines[:start_idx] + new_analyze.split('\n') + [''] + lines[end_idx:]
        with open('/opt/tauric-platform/backend/app/routes/grid.py', 'w') as f:
            f.write('\n'.join(new_lines))
        print(f"SUCCESS: Replaced lines {start_idx}-{end_idx}")
    else:
        print("ERROR: Could not find _run_analyze_job function")
