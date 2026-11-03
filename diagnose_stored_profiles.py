#!/usr/bin/env python3
"""
Deep diagnostic script for stored profiles on staging
"""

import sys
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
import asyncio
from app.services.exchange_framework import exchange_framework, credential_vault

async def run_diagnostics():
    print("=" * 70)
    print("TAURIC STORED PROFILES DEEP DIAGNOSTIC")
    print("=" * 70)

    for pid in ["prof_binance_demo_93c40749", "prof_bitget_demo_a2bb3478"]:
        print("\n" + "-" * 50)
        print("Testing Profile ID:", pid)
        prof = credential_vault.get_profile_public(pid)
        if not prof:
            print("Profile not found in vault!")
            continue

        creds = credential_vault.get_credentials(pid)
        print(f"Exchange: {prof.get('exchange')}")
        print(f"Label: {prof.get('label')}")
        print(f"Product Type: {prof.get('product_type')}")
        print(f"Environment: {prof.get('environment')}")
        print(f"API Key Masked: {prof.get('api_key_masked')}")
        print(f"API Key Length: {len(creds.get('api_key', ''))}")
        print(f"API Secret Length: {len(creds.get('api_secret', ''))}")
        p_phrase = creds.get('passphrase') or ''
        print(f"Passphrase Present: {bool(p_phrase)} (Length: {len(p_phrase)})")

        res = await exchange_framework.detect_account_capabilities(
            exchange=prof.get("exchange"),
            credentials=creds,
            custom_config=prof.get("custom_config"),
            environment=prof.get("environment"),
            product_type=prof.get("product_type")
        )

        print("\nDetection Outcome:")
        print(f"  Overall Status: {res.get('status')}")
        print(f"  Connection Status: {res.get('connection_status')}")
        print(f"  Verification Label: {res.get('verification_label')}")
        print(f"  Error Classification: {res.get('error_classification')}")
        print(f"  Provider Error Code: {res.get('provider_error_code')}")
        print(f"  Summary / Message: {res.get('summary') or res.get('error')}")
        print(f"  Actionable Remedy: {res.get('guidance')}")

        print("\nGranular Endpoint Probes:")
        for ep in (res.get("endpoints") or res.get("endpoint_results") or []):
            cat = ep.get('category')
            url = ep.get('url')
            code = ep.get('http_status') or ep.get('status_code')
            st = ep.get('status')
            msg = ep.get('message') or ep.get('error')
            lat = ep.get('latency_ms')
            print(f"  [{st}] {cat} -> HTTP {code} ({lat}ms): {msg}")
            if ep.get('provider_error_code') or ep.get('provider_error_message'):
                print(f"       Provider Code: {ep.get('provider_error_code')} | Message: {ep.get('provider_error_message')}")
            if ep.get('guidance'):
                print(f"       Guidance: {ep.get('guidance')}")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
