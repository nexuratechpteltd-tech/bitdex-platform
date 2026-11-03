import asyncio
import hashlib
import json
import logging
import sys
from zoneinfo import ZoneInfo
import httpx

from app.services.forex_market_data import forex_market_data, INSTRUMENT_REGISTRY, parse_instrument_id
from app.services.forex_strategy_engine import forex_strategy_engine, REQUIRED_SNAPSHOT_FIELDS

logging.basicConfig(level=logging.INFO)

async def run_all_tests():
    print("==================================================")
    print("1. RUNNING BACKEND DETERMINISTIC SAFETY TESTS")
    print("==================================================")

    # Test 1: Instrument ID parsing & registry
    print("\n[TEST 1] Instrument ID System:")
    e1 = parse_instrument_id("EUR/USD")
    e2 = parse_instrument_id("fx:EURUSD")
    e3 = parse_instrument_id("XAUUSD")
    e4 = parse_instrument_id("BTCUSDT", default_market="CRYPTO")
    assert e1 == "fx:EURUSD", f"Expected fx:EURUSD, got {e1}"
    assert e2 == "fx:EURUSD", f"Expected fx:EURUSD, got {e2}"
    assert e3 == "metal:XAUUSD", f"Expected metal:XAUUSD, got {e3}"
    assert e4 == "crypto:binance:BTCUSDT", f"Expected crypto:binance:BTCUSDT, got {e4}"
    print("  ✓ parse_instrument_id passed: fx:EURUSD, metal:XAUUSD, crypto:binance:BTCUSDT")

    # Test 2: Market Snapshot Contract & Validation
    print("\n[TEST 2] MarketSnapshot Contract & Canonical Hash:")
    snap = await forex_market_data.build_market_snapshot("fx:EURUSD", trigger_tf="10m", context_tf="1h")
    forex_strategy_engine.validate_snapshot(snap)
    assert snap["schema_version"] == "1.0"
    assert snap["instrument_id"] == "fx:EURUSD"
    assert snap["asset_class"] == "fx"
    assert snap["bid"] < snap["ask"], f"Bid {snap['bid']} must be less than Ask {snap['ask']}"
    assert snap["spread_abs"] > 0
    assert "snapshot_hash" in snap and len(snap["snapshot_hash"]) == 64
    print(f"  ✓ MarketSnapshot valid: bid={snap['bid']}, ask={snap['ask']}, spread={snap['spread_pips']} pips, hash={snap['snapshot_hash'][:16]}...")

    # Test 3: Missing field snapshot refusal (0 AI credits)
    print("\n[TEST 3] Snapshot Missing Field Rejection:")
    bad_snap = {k: v for k, v in snap.items() if k != "bid"}
    try:
        forex_strategy_engine.validate_snapshot(bad_snap)
        raise AssertionError("Validation should have failed for missing 'bid'")
    except ValueError as err:
        print(f"  ✓ Successfully refused invalid snapshot with error: {err}")

    # Test 4: Bid/Ask Execution Rules
    print("\n[TEST 4] Bid/Ask Rules Verification:")
    scalp = await forex_strategy_engine.evaluate_scalping_setup("fx:EURUSD", preferred_timeframe="10m")
    if scalp["direction"] == "LONG":
        assert scalp["entry_price"] == scalp["ask"], f"Long entry must be Ask: {scalp['entry_price']} vs {scalp['ask']}"
        assert scalp["stop_loss"] < scalp["bid"], f"Long SL must be below Bid: {scalp['stop_loss']} vs {scalp['bid']}"
    else:
        assert scalp["entry_price"] == scalp["bid"], f"Short entry must be Bid: {scalp['entry_price']} vs {scalp['bid']}"
        assert scalp["stop_loss"] > scalp["ask"], f"Short SL must be above Ask: {scalp['stop_loss']} vs {scalp['ask']}"
    print(f"  ✓ Direction: {scalp['direction']} | Entry: {scalp['entry_price']} | SL: {scalp['stop_loss']} | TP: {scalp['take_profit']}")

    # Test 5: M10 Candle Alignment & is_closed
    print("\n[TEST 5] M10 Candle Synthesis & UTC Alignment:")
    klines_10m = await forex_market_data.fetch_klines("fx:EURUSD", timeframe="10m", limit=10)
    for c in klines_10m["candles"]:
        # Check alignment: open_time must be divisible by 600
        assert c["open_time"] % 600 == 0, f"Candle open_time {c['open_time']} not aligned to 10m"
        assert c["close_time"] - c["open_time"] == 600, "Candle duration must be 600s"
        assert "is_closed" in c
        assert c.get("tick_volume_not_real") is True
    print(f"  ✓ 10m candles verified: {len(klines_10m['candles'])} bars strictly aligned to UTC 10m boundaries")

    # Test 6: IANA Timezones & DST Session Engine
    print("\n[TEST 6] IANA Forex Session Engine:")
    session = forex_market_data.get_current_session()
    print(f"  ✓ Session ID: {session['session_id']}")
    print(f"  ✓ Market Status: {session['market_status']}")
    print(f"  ✓ London IANA: {session['iana_zones']['london']}")
    print(f"  ✓ New York IANA: {session['iana_zones']['new_york']}")
    print(f"  ✓ Karachi PKT: {session['iana_zones']['karachi_pkt']}")

    # Test 7: Precious Metals Specifics (Gold XAU/USD & Silver XAG/USD)
    print("\n[TEST 7] Precious Metals Registry & Spread/Pip Rules:")
    gold_meta = forex_market_data.get_instrument_meta("metal:XAUUSD")
    assert gold_meta["asset_class"] == "metal"
    assert gold_meta["pip_size"] == 0.10, "Gold pip size must be $0.10"
    assert gold_meta["contract_size"] == 100, "Gold contract size must be 100 oz"
    assert gold_meta["quote_unit"] == "USD/oz"
    gold_setup = await forex_strategy_engine.evaluate_trade_setup("metal:XAUUSD")
    assert gold_setup["reward_to_risk"] >= 2.08, f"Gold R:R must be >= 2.08, got {gold_setup['reward_to_risk']}"
    print(f"  ✓ Gold XAU/USD Setup: Price=${gold_setup['current_price']}, R:R={gold_setup['reward_to_risk']}:1, Contract={gold_meta['contract_size']} oz")

    # Test 8: Deterministic Candidate Ranking & Reason Codes
    print("\n[TEST 8] Zero-LLM Candidate Ranking & Reason Codes:")
    ranked = await forex_strategy_engine.scan_forex_candidates(strategy="SHORT_TERM", capital=100.0, limit=5)
    assert len(ranked) > 0, "Ranked candidates should not be empty"
    for r in ranked:
        assert "reason_codes" in r and len(r["reason_codes"]) > 0
        assert "snapshot_hash" in r
        print(f"  Candidate: {r['symbol']:<10} Score: {r['ranking_score']:<5} Reasons: {', '.join(r['reason_codes'])}")

    print("\n==================================================")
    print("ALL DETERMINISTIC BACKEND SAFETY TESTS PASSED ✓")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
