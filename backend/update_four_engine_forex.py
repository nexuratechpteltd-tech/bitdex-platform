with open("/opt/tauric-platform-staging/backend/app/services/four_engine_orchestrator.py", "r") as f:
    content = f.read()

# 1. Update snapshot creation for Forex
old_snap = """                snapshot = {
                    "snapshot_id": f"SNAP-FX-{int(time.time())}-{clean_sym.replace('/', '')}",
                    "content_hash": ticker.get("provider_cache_key", f"hash-{now_ms}"),
                    "symbol": ticker.get("clean_symbol", clean_sym),
                    "canonical_symbol": ticker.get("clean_symbol", clean_sym),
                    "asset_class": "FOREX",
                    "timeframe": timeframe,
                    "market_data": {
                        "price": curr_price,
                        "bid": ticker.get("bid", curr_price),
                        "ask": ticker.get("ask", curr_price),
                        "spread_bps": round(((ticker.get("ask", curr_price) - ticker.get("bid", curr_price)) / curr_price) * 10000, 2) if curr_price > 0 else 1.0,
                        "change_24h": ticker.get("change_pct_24h", 0.0),
                        "status": "PASS",
                        "market_status": "NORMAL",
                        "data_freshness_sec": 2,
                        "timestamp_utc": start_iso
                    },"""

new_snap = """                session = ticker.get("session") or forex_market_data.get_current_session()
                is_fx_closed = session.get("market_status") == "CLOSED" or not session.get("market_open", True)
                snapshot = {
                    "snapshot_id": f"SNAP-FX-{int(time.time())}-{clean_sym.replace('/', '')}",
                    "content_hash": ticker.get("provider_cache_key", f"hash-{now_ms}"),
                    "symbol": ticker.get("clean_symbol", clean_sym),
                    "canonical_symbol": ticker.get("clean_symbol", clean_sym),
                    "asset_class": "FOREX",
                    "timeframe": timeframe,
                    "market_data": {
                        "price": curr_price,
                        "bid": ticker.get("bid", curr_price),
                        "ask": ticker.get("ask", curr_price),
                        "spread_bps": round(((ticker.get("ask", curr_price) - ticker.get("bid", curr_price)) / curr_price) * 10000, 2) if curr_price > 0 else 1.0,
                        "change_24h": ticker.get("change_pct_24h", 0.0),
                        "status": "PASS",
                        "market_status": "CLOSED" if is_fx_closed else "NORMAL",
                        "is_market_closed": is_fx_closed,
                        "price_stale": is_fx_closed,
                        "latest_quote_timestamp": ticker.get("quote_ts_utc") or start_iso,
                        "closed_market_notice": "Forex market is closed. The latest available quote is shown as stale." if is_fx_closed else None,
                        "data_freshness_sec": 3600 if is_fx_closed else 2,
                        "timestamp_utc": ticker.get("quote_ts_utc") or start_iso
                    },"""

if "is_fx_closed" not in content:
    assert old_snap in content, "old_snap not found!"
    content = content.replace(old_snap, new_snap, 1)

# 2. Update consensus handling for Market Closed
old_consensus = """        if is_blackout:
            final_decision = "NO_TRADE"
            meter_state = "NO_TRADE"
            consensus_label = "MACRO_EVENT_BLACKOUT"
            reason = "High-impact macroeconomic event catalyst window is active. All directional entries suspended."
        elif has_conflict:"""

new_consensus = """        is_market_closed = bool(snapshot.get("market_data", {}).get("is_market_closed", False))

        if is_market_closed:
            final_decision = "HOLD"
            meter_state = "HOLD"
            consensus_label = "MARKET_CLOSED"
            reason = "Forex market is closed. The latest available quote is shown as stale. Live order execution is unavailable."
        elif is_blackout:
            final_decision = "NO_TRADE"
            meter_state = "NO_TRADE"
            consensus_label = "MACRO_EVENT_BLACKOUT"
            reason = "High-impact macroeconomic event catalyst window is active. All directional entries suspended."
        elif has_conflict:"""

if "is_market_closed = bool" not in content:
    assert old_consensus in content, "old_consensus not found!"
    content = content.replace(old_consensus, new_consensus, 1)

# 3. Add is_market_closed to top-level contract dict
old_contract_end = """            "market_snapshot_id": snapshot.get("snapshot_id", "N/A"),
            "market_data_timestamp": snapshot.get("market_data", {}).get("timestamp_utc", start_iso),"""

new_contract_end = """            "market_snapshot_id": snapshot.get("snapshot_id", "N/A"),
            "market_data_timestamp": snapshot.get("market_data", {}).get("timestamp_utc", start_iso),
            "is_market_closed": is_market_closed,
            "closed_market_notice": "Forex market is closed. The latest available quote is shown as stale." if is_market_closed else None,"""

if '"is_market_closed": is_market_closed' not in content:
    assert old_contract_end in content, "old_contract_end not found!"
    content = content.replace(old_contract_end, new_contract_end, 1)

with open("/opt/tauric-platform-staging/backend/app/services/four_engine_orchestrator.py", "w") as f:
    f.write(content)

print("four_engine_orchestrator.py updated with market closed handling successfully!")
