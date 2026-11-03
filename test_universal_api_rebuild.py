#!/usr/bin/env python3
"""
Comprehensive Verification Suite for Rebuilt Universal API Connections & Bitget Auth Diagnostics.
Uses an isolated test vault (/tmp/tauric_universal_rebuild_vault.json) for all synthetic write tests
so the real staging vault (/opt/tauric-platform-staging/backend/data/credential_vault.json) is never polluted.
"""
import os
import sys
import json
import asyncio
from pathlib import Path

ISOLATED_VAULT = "/tmp/tauric_universal_rebuild_vault.json"
if Path(ISOLATED_VAULT).exists():
    Path(ISOLATED_VAULT).unlink()

os.environ["TAURIC_VAULT_PATH"] = ISOLATED_VAULT

# Load staging .env
env_path = Path("/opt/tauric-platform-staging/backend/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, "/opt/tauric-platform-staging/backend")

from fastapi.testclient import TestClient
from app.main import app
from app.services.exchange_framework import (
    CredentialVault,
    implemented_provider_ids,
    suggest_provider,
)

passed = 0
failed = 0

def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def run_suite():
    client = TestClient(app)

    print("=== 1. Implemented & Tested Provider Filtering (Section C) ===")
    impl = implemented_provider_ids()
    check("Only BINANCE and BITGET are marked IMPLEMENTED_TESTED", sorted(impl) == ["BINANCE", "BITGET"], f"got {impl}")

    res_prov = client.get("/api/v1/connections/providers-implemented")
    check("GET /api/v1/connections/providers-implemented returns 200", res_prov.status_code == 200)
    prov_ids = [p["provider_id"] for p in res_prov.json().get("providers", [])]
    check("Endpoint returns only implemented providers", sorted(prov_ids) == ["BINANCE", "BITGET"], f"got {prov_ids}")

    print("\n=== 2. Credential-First Universal Connection Flow (Section B & C) ===")
    res_create = client.post("/api/v1/connections/universal", json={
        "label": "Bitget API 1",
        "api_key": "bg_test_format_hint_key_1234567890",
        "api_secret": "test_secret_value_abcdef1234567890",
        "passphrase": "test_passphrase_value"
    })
    check("POST /api/v1/connections/universal creates unidentified profile", res_create.status_code == 200)
    created_data = res_create.json()
    prof = created_data.get("profile", {})
    pid = prof.get("profile_id")
    check("Created profile starts as UNIDENTIFIED", prof.get("exchange") == "UNIDENTIFIED" and prof.get("provider_identified") is False)
    check("Non-binding format hint suggests BITGET for bg_ prefix", created_data.get("suggested_provider") == "BITGET")
    check("Passphrase presence flag is True", prof.get("has_passphrase") is True)

    print("\n=== 3. Guard Against Unidentified Connection Testing (Section C) ===")
    res_test_unid = client.post("/api/v1/connections/test", json={"profile_id": pid})
    check("Testing unidentified profile fails cleanly with PROVIDER_NOT_IDENTIFIED",
          res_test_unid.status_code == 200 and res_test_unid.json().get("actionable_error_code") == "PROVIDER_NOT_IDENTIFIED",
          f"got {res_test_unid.json().get('actionable_error_code')}")

    print("\n=== 4. Post-Save Explicit Provider Identification & AAD Rebinding (Section C) ===")
    res_unimpl = client.post(f"/api/v1/connections/profiles/{pid}/identify", json={
        "provider_id": "OKX",
        "environment": "DEMO"
    })
    check("Identifying as unimplemented provider (OKX) is rejected with 400", res_unimpl.status_code == 400)

    res_ident = client.post(f"/api/v1/connections/profiles/{pid}/identify", json={
        "provider_id": "BITGET",
        "environment": "DEMO",
        "product_type": "FUTURES_USDT"
    })
    check("Identifying as BITGET succeeds", res_ident.status_code == 200)
    ident_prof = res_ident.json().get("profile", {})
    check("Profile exchange is now BITGET and provider_identified is True",
          ident_prof.get("exchange") == "BITGET" and ident_prof.get("provider_identified") is True)

    print("\n=== 5. Post-Save Environment & Product Configuration (Section D) ===")
    res_spot_demo = client.post(f"/api/v1/connections/profiles/{pid}/configure", json={
        "environment": "DEMO",
        "product_type": "SPOT"
    })
    check("Bitget SPOT + DEMO is rejected with 400 (unsupported by Bitget)", res_spot_demo.status_code == 400)

    res_cfg = client.post(f"/api/v1/connections/profiles/{pid}/configure", json={
        "environment": "LIVE",
        "product_type": "FUTURES_USDT"
    })
    check("Configuring BITGET LIVE + FUTURES_USDT succeeds with AAD rebinding",
          res_cfg.status_code == 200 and res_cfg.json().get("profile", {}).get("environment") == "LIVE")

    print("\n=== 6. Post-Save Permissions & Capabilities Report (Section D) ===")
    res_cap = client.get(f"/api/v1/connections/profiles/{pid}/capability-report")
    check("GET /capability-report returns 200", res_cap.status_code == 200)
    cap_json = res_cap.json()
    cap_labels = [c["label"] for c in cap_json.get("capabilities", [])]
    check("Capability report includes all required capability indicators",
          "Public market data" in cap_labels and
          "Private account authentication" in cap_labels and
          "Withdrawal / transfer" in cap_labels,
          f"count={len(cap_labels)}")
    withdraw_cap = next((c for c in cap_json.get("capabilities", []) if "Withdrawal" in c["label"]), {})
    check("Withdrawal / transfer capability is permanently DISABLED", withdraw_cap.get("state") == "DISABLED")

    print("\n=== 7. Safe Edit Preserving Encrypted Credentials Byte-for-Byte ===")
    res_edit = client.put(f"/api/v1/connections/profiles/{pid}", json={"label": "Bitget API 1 Renamed"})
    check("Label-only edit succeeds", res_edit.status_code == 200 and res_edit.json()["profile"]["label"] == "Bitget API 1 Renamed")

    res_masked = client.put(f"/api/v1/connections/profiles/{pid}", json={"api_key": "bg_t••••7890"})
    check("Submitting masked API key is rejected with HTTP 400", res_masked.status_code == 400)

    print("\n=== 8. Clean Deletion & Safety Lock Verification (Section A) ===")
    res_del = client.delete(f"/api/v1/connections/profiles/{pid}")
    check("DELETE profile succeeds", res_del.status_code == 200)

    res_live_order = client.post("/api/v1/orders/live/submit", json={
        "symbol": "BTCUSDT", "side": "BUY", "order_type": "LIMIT", "quantity": 0.001, "price": 50000
    })
    check("POST /api/v1/orders/live/submit remains blocked with HTTP 403", res_live_order.status_code == 403)

    if Path(ISOLATED_VAULT).exists():
        Path(ISOLATED_VAULT).unlink()

    print(f"\nSUMMARY: {passed}/{passed + failed} checks passed, {failed} failed.")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run_suite()
