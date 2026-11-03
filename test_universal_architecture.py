#!/usr/bin/env python3
"""
Staging verification script for Tauric Universal Multi-Exchange & Multi-Broker Architecture
"""

import sys
sys.path.insert(0, '/opt/tauric-platform-staging/backend')

from app.services.exchange_framework import (
    PROVIDER_SCHEMAS,
    CANONICAL_FOREX_INSTRUMENTS,
    calculate_forex_margin,
    check_forex_market_session,
    exchange_framework
)

def test_universal_architecture():
    print("=== 1. CANONICAL PROVIDER REGISTRY ===")
    for k, v in PROVIDER_SCHEMAS.items():
        print(f"  [{k}] {v['name']} | Market: {v['market_type']} | Status: {v['implementation_status']} | Coverage: {v['test_coverage']} | Passphrase: {v.get('requires_passphrase')}")

    print("\n=== 2. CANONICAL FOREX MODEL & LOT SIZING ===")
    eurusd_spec = CANONICAL_FOREX_INSTRUMENTS.get("EURUSD")
    print(f"  EURUSD Contract Size: {eurusd_spec['contract_size']} (Standard Lot: 100,000 units)")
    print(f"  EURUSD Mini Lot: {eurusd_spec['mini_lot_size']}, Micro Lot: {eurusd_spec['micro_lot_size']}")
    print(f"  EURUSD Pip Size: {eurusd_spec['pip_size']}, Pip Digits: {eurusd_spec['pip_digits']}")

    margin_res = calculate_forex_margin("EURUSD", lots=1.0, base_price=1.0850, leverage=100.0)
    print(f"  Margin Calculation: 1.0 Lot @ 1.0850, Leverage 100x -> Notional: ${margin_res['notional_value_usd']}, Margin: ${margin_res['required_margin_usd']}")
    assert margin_res['required_margin_usd'] == 1085.0
    assert margin_res['notional_value_usd'] == 108500.0

    print("\n=== 3. FOREX TRADING SESSION & WEEKEND LOCK ===")
    session = check_forex_market_session()
    print(f"  Status: {session['status']} | Open: {session['is_market_open']} | Active Sessions: {session['active_sessions']}")
    if session['weekend_lock_active']:
        print(f"  Weekend Lock Active: {session['lock_reason']}")

    print("\n=== 4. EXPLICIT STRATEGY PREFLIGHT ROUTING ===")
    # Case A: Paper Simulation
    pf_paper = exchange_framework.strategy_preflight(profile_id="PAPER", strategy_id="SPOT_GRID")
    print(f"  Case A (Paper): {pf_paper['confirmation_summary']} | Status: {pf_paper['status']} | Eligible: {pf_paper['eligible']}")
    assert pf_paper['eligible'] is True

    # Case B: Unknown Profile
    pf_unknown = exchange_framework.strategy_preflight(profile_id="nonexistent-id", strategy_id="SPOT_GRID")
    print(f"  Case B (Nonexistent Profile): Status: {pf_unknown['status']} | Blockers: {pf_unknown['blockers']}")
    assert pf_unknown['eligible'] is False
    assert pf_unknown['status'] == "REJECTED"

    print("\n=== 5. UNIVERSAL PROVIDER LISTING ===")
    reg = exchange_framework.get_provider_registry()
    print(f"  Total Providers in Registry: {len(reg)}")
    crypto_providers = exchange_framework.get_provider_registry(market_type="CRYPTO")
    forex_providers = exchange_framework.get_provider_registry(market_type="FOREX")
    print(f"  Crypto Providers ({len(crypto_providers)}): {[p['id'] for p in crypto_providers]}")
    print(f"  Forex Providers ({len(forex_providers)}): {[p['id'] for p in forex_providers]}")

    print("\n✓ ALL CORE PYTHON VERIFICATIONS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_universal_architecture()
