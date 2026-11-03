#!/usr/bin/env python3
"""
Tauric Platform — Secure Server-Side Testnet Credential Provisioning Script
Phase 3.3.6

Security Controls:
- Prompts for API credentials via getpass (or reads strictly from stdin JSON), preventing exposure in shell history or `ps aux`.
- Encrypts credentials with authenticated AES-256-GCM under the rotated vault master key.
- Immediately tests permissions against the testnet matching engine.
- Never prints or logs raw secrets, passphrases, or the master vault key.
"""

import sys
import os
import json
import getpass
import asyncio
from typing import Optional

# Ensure backend root is on sys.path
backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_root, ".env"))

from app.services.exchange_framework import (
    CredentialVault,
    exchange_framework,
    Environment,
    ExchangeId,
    get_vault_master_key
)
from app.config import settings


async def provision_interactive():
    print("=" * 60)
    print("TAURIC SECURE TESTNET CREDENTIAL PROVISIONING")
    print("=" * 60)
    print("Note: Input is masked and never recorded in shell history or logs.")
    print()

    # 1. Exchange selection
    while True:
        exch_input = input("Select Exchange [1] Binance Spot Testnet, [2] Bybit Spot Testnet: ").strip()
        if exch_input in ("1", "binance", "BINANCE"):
            exchange = "BINANCE"
            break
        elif exch_input in ("2", "bybit", "BYBIT"):
            exchange = "BYBIT"
            break
        print("Invalid choice. Please enter 1 or 2.")

    # 2. Environment (strictly DEMO for testnet execution)
    environment = "DEMO"
    print(f"Target Environment: {environment} (Isolated Testnet)")

    # 3. Label
    label = input(f"Account Label [default: {exchange} Spot Testnet Primary]: ").strip()
    if not label:
        label = f"{exchange} Spot Testnet Primary"

    # 4. Sensitive inputs (getpass hides input from screen)
    api_key = getpass.getpass("Enter Testnet API Key: ").strip()
    if not api_key:
        print("Error: API Key cannot be empty.", file=sys.stderr)
        sys.exit(1)

    api_secret = getpass.getpass("Enter Testnet API Secret: ").strip()
    if not api_secret:
        print("Error: API Secret cannot be empty.", file=sys.stderr)
        sys.exit(1)

    passphrase = None
    if exchange == "BYBIT":
        passphrase = getpass.getpass("Enter Bybit Passphrase (optional, press Enter if none): ").strip()
        if not passphrase:
            passphrase = None

    print("\nEncrypting credentials with AES-256-GCM vault master key...")
    vault = CredentialVault(storage_path=os.path.join(backend_root, "data", "credential_vault.json"))
    public_profile = vault.save_profile(
        exchange=exchange,
        environment=environment,
        label=label,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )

    print("Profile successfully saved to encrypted vault.")
    print(f"  Profile ID:     {public_profile['profile_id']}")
    print(f"  Exchange:       {public_profile['exchange']}")
    print(f"  Environment:    {public_profile['environment']}")
    print(f"  Account Label:  {public_profile['label']}")
    print(f"  Masked API Key: {public_profile['api_key_masked']}")

    print("\nRunning Authenticated Preflight against Testnet endpoint...")
    adapter = exchange_framework.get_adapter(exchange)
    creds = {"api_key": api_key, "api_secret": api_secret}
    if passphrase:
        creds["passphrase"] = passphrase

    perm_res = await adapter.verify_permissions(Environment.DEMO, creds)
    verified = perm_res.get("verified", False)
    can_trade = bool(perm_res.get("can_trade", False))

    status_str = "VERIFIED" if verified else "FAILED"
    vault.update_verification_status(public_profile["profile_id"], status_str, perm_res.get("capabilities", []))

    if verified and can_trade:
        print("\n>>> PREFLIGHT CHECK: PASS <<<")
        print(f"Authenticated successfully with {exchange} Testnet.")
        print(f"Trading Permission (can_trade): {can_trade}")
        print(f"Verified Capabilities: {perm_res.get('capabilities', [])}")

        # Fetch balances
        try:
            balances = await adapter.fetch_balances(Environment.DEMO, creds)
            positive_bals = [b for b in balances if b.total > 0]
            print(f"Testnet Balances Found: {len(positive_bals)} assets with positive balance")
            for b in positive_bals[:5]:
                print(f"  - {b.asset}: Free={b.free:,.4f}, Total={b.total:,.4f}")
        except Exception as e:
            print(f"Balance fetch notice: {e}")
    else:
        print("\n>>> PREFLIGHT CHECK: FAILED <<<")
        print(f"Reason: {perm_res.get('error', 'Authentication rejected by exchange.')}")
        print("The profile remains saved in the vault, but execution remains BLOCKED until valid credentials are provided.")


async def provision_from_stdin():
    """Non-interactive stdin JSON ingestion for automated, secure pipeline execution."""
    raw = sys.stdin.read().strip()
    if not raw:
        print("Error: No JSON payload received on stdin.", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"Error parsing stdin JSON: {e}", file=sys.stderr)
        sys.exit(1)

    exchange = data.get("exchange", "BINANCE").upper()
    environment = data.get("environment", "DEMO").upper()
    label = data.get("label", f"{exchange} Testnet Primary")
    api_key = data.get("api_key", "").strip()
    api_secret = data.get("api_secret", "").strip()
    passphrase = data.get("passphrase")

    if not api_key or not api_secret:
        print("Error: api_key and api_secret are required.", file=sys.stderr)
        sys.exit(1)

    vault = CredentialVault(storage_path=os.path.join(backend_root, "data", "credential_vault.json"))
    public_profile = vault.save_profile(
        exchange=exchange,
        environment=environment,
        label=label,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )

    adapter = exchange_framework.get_adapter(exchange)
    creds = {"api_key": api_key, "api_secret": api_secret}
    if passphrase:
        creds["passphrase"] = passphrase

    perm_res = await adapter.verify_permissions(Environment.DEMO, creds)
    verified = perm_res.get("verified", False)
    status_str = "VERIFIED" if verified else "FAILED"
    vault.update_verification_status(public_profile["profile_id"], status_str, perm_res.get("capabilities", []))

    # Output JSON summary with secrets scrubbed
    out = {
        "status": "SUCCESS" if verified else "AUTHENTICATION_FAILED",
        "profile": public_profile,
        "preflight": {
            "verified": verified,
            "can_trade": perm_res.get("can_trade", False),
            "capabilities": perm_res.get("capabilities", []),
            "error": perm_res.get("error")
        }
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    if not sys.stdin.isatty():
        asyncio.run(provision_from_stdin())
    else:
        asyncio.run(provision_interactive())
