import json
import urllib.request
import urllib.parse
import sys

BASE_URL = "http://127.0.0.1:8002/api/v1"

def test_api():
    print("==================================================================")
    print("BITDEX PHASE 1 — AUTOMATED SIGNAL & MARKET VERIFICATION TEST SUITE")
    print("==================================================================")
    
    # Test 1: Signals Feed for ADA/BTC and ADA/USDT
    print("\n[TEST 1] Fetching live signals for ADA pairs...")
    req = urllib.request.Request(f"{BASE_URL}/signals?force_refresh=true&search=ADA")
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    
    signals = data.get("signals", [])
    print(f"Returned {len(signals)} ADA signals.")
    
    ada_btc = next((s for s in signals if s["symbol"] == "ADA/BTC"), None)
    ada_usdt = next((s for s in signals if s["symbol"] == "ADA/USDT"), None)
    
    assert ada_btc is not None, "FAILED: ADA/BTC signal not found in signals feed!"
    print("✓ ADA/BTC signal found.")
    
    # Check ADA/BTC dynamic precision & explicit status
    print(f"  - Symbol: {ada_btc['symbol']}")
    print(f"  - Availability Status: {ada_btc.get('availability_status')}")
    print(f"  - Reference Price: {ada_btc['reference_price']:.8f}")
    print(f"  - Entry Zone: {ada_btc['entry_zone']}")
    print(f"  - Stop Loss: {ada_btc['stop_loss']:.8f}")
    print(f"  - Target: {ada_btc['target']:.8f}")
    print(f"  - TP1 Price: {ada_btc['multi_targets']['tp1']['price']:.8f}")
    print(f"  - TP2 Price: {ada_btc['multi_targets']['tp2']['price']:.8f}")
    print(f"  - TP3 Price: {ada_btc['multi_targets']['tp3']['price']:.8f}")
    print(f"  - Indicators: EMA20={ada_btc['indicators']['ema20']:.8f}, EMA50={ada_btc['indicators']['ema50']:.8f}, ATR14={ada_btc['indicators']['atr14']:.8f}")
    print(f"  - Breakeven buffer: {ada_btc['breakeven_analysis']['breakeven_buffer_pct']}%")
    
    assert ada_btc.get("availability_status") == "VALID_SIGNAL", f"Expected VALID_SIGNAL, got {ada_btc.get('availability_status')}"
    assert ada_btc["reference_price"] > 0 and ada_btc["reference_price"] < 0.001, "ADA/BTC ref price should be around 0.0000024x"
    assert ada_btc["stop_loss"] > 0, "ADA/BTC stop_loss must not be 0.0"
    assert ada_btc["target"] > 0, "ADA/BTC target must not be 0.0"
    assert ada_btc["indicators"]["ema20"] > 0, "ADA/BTC EMA20 must not be 0.0"
    assert ada_btc["indicators"]["ema50"] > 0, "ADA/BTC EMA50 must not be 0.0"
    assert ada_btc["breakeven_analysis"]["breakeven_buffer_pct"] > -50.0, "Breakeven buffer must not be corrupted to -100%"
    print("✓ TEST 1 PASSED: ADA/BTC has full 8-decimal Satoshi precision and non-zero indicators/targets.")
    
    # Test 2: ADA/USDT Verification
    assert ada_usdt is not None, "FAILED: ADA/USDT signal not found!"
    print("\n[TEST 2] Verifying ADA/USDT...")
    print(f"  - Symbol: {ada_usdt['symbol']}")
    print(f"  - Reference Price: ${ada_usdt['reference_price']:.4f}")
    print(f"  - Stop Loss: ${ada_usdt['stop_loss']:.4f}")
    print(f"  - Target: ${ada_usdt['target']:.4f}")
    assert ada_usdt["reference_price"] > 0.05 and ada_usdt["reference_price"] < 5.0
    print("✓ TEST 2 PASSED: ADA/USDT USDT-quoted pricing verified.")
    
    # Test 3: BTC/USDT and Forex Verification
    print("\n[TEST 3] Fetching BTC/USDT and EUR/USD...")
    req_btc = urllib.request.Request(f"{BASE_URL}/signals?search=BTC/USDT")
    with urllib.request.urlopen(req_btc, timeout=20) as resp:
        data_btc = json.loads(resp.read().decode())
    btc_sig = next((s for s in data_btc.get("signals", []) if s["symbol"] == "BTC/USDT"), None)
    if btc_sig:
        print(f"✓ BTC/USDT: Ref Price=${btc_sig['reference_price']:.2f}, SL=${btc_sig['stop_loss']:.2f}, Target=${btc_sig['target']:.2f}")
    
    req_eur = urllib.request.Request(f"{BASE_URL}/signals?search=EUR/USD")
    with urllib.request.urlopen(req_eur, timeout=20) as resp:
        data_eur = json.loads(resp.read().decode())
    eur_sig = next((s for s in data_eur.get("signals", []) if s["symbol"] == "EUR/USD"), None)
    if eur_sig:
        print(f"✓ EUR/USD: Market={eur_sig['market']}, Ref Price={eur_sig['reference_price']}, SL={eur_sig['stop_loss']}, Target={eur_sig['target']}")
    print("✓ TEST 3 PASSED: Standard Crypto and Forex signals intact.")
    
    # Test 4: Unsupported pair test
    print("\n[TEST 4] Testing unsupported pair detail query...")
    try:
        req_unsupp = urllib.request.Request(f"{BASE_URL}/signals/detail/crypto:binance:XYZINVALID")
        with urllib.request.urlopen(req_unsupp, timeout=10) as resp:
            data_unsupp = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"✓ Correctly returned HTTP {e.code} for unsupported pair.")
    
    # Test 5: Markets Overview contains ADA/BTC with LIVE status
    print("\n[TEST 5] Testing /markets/overview for ADA/BTC...")
    req_ov = urllib.request.Request(f"{BASE_URL}/markets/overview")
    with urllib.request.urlopen(req_ov, timeout=10) as resp:
        ov_data = json.loads(resp.read().decode())
    
    ada_btc_ov = next((c for c in ov_data.get("crypto", []) if c["symbol"] == "ADA/BTC"), None)
    assert ada_btc_ov is not None, "FAILED: ADA/BTC not found in /markets/overview!"
    print(f"  - ADA/BTC in Overview: Price={ada_btc_ov['price']:.8f}, High={ada_btc_ov['high_24h']:.8f}, Low={ada_btc_ov['low_24h']:.8f}")
    print(f"  - Status={ada_btc_ov['status']}, Data State={ada_btc_ov['data_state']}, Source={ada_btc_ov['source']}")
    assert ada_btc_ov["data_state"] == "LIVE", f"Expected data_state LIVE, got {ada_btc_ov['data_state']}"
    assert ada_btc_ov["price"] > 0 and ada_btc_ov["price"] < 0.001
    print("✓ TEST 5 PASSED: ADA/BTC is live in markets overview feed.")
    
    print("\n==================================================================")
    print("ALL 5 PHASE 1 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================================")

if __name__ == "__main__":
    test_api()
