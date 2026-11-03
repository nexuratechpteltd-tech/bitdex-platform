import httpx
import json
import sys

STAGING_BASE = "https://127.0.0.1:33900/trading/api/backend"

def run_tests():
    client = httpx.Client(verify=False, timeout=15)
    print("=== Testing Staging Connections API ===")
    
    # 1. Capability endpoint
    r = client.get(f"{STAGING_BASE}/connections/capabilities/")
    assert r.status_code == 200, f"Capabilities failed: {r.status_code}"
    print("✓ Capabilities endpoint OK (200)")

    # 2. Pre-save test probe
    test_payload = {
        "exchange": "BITGET",
        "environment": "DEMO",
        "api_key": "test_staging_key",
        "api_secret": "test_staging_secret",
        "passphrase": "test_passphrase"
    }
    r = client.post(f"{STAGING_BASE}/connections/test/", json=test_payload)
    assert r.status_code == 200, f"Pre-save test failed: {r.status_code} {r.text}"
    probe_data = r.json()
    assert "endpoints" in probe_data, "Missing endpoints probe data"
    assert probe_data["connection_status"] == "AUTHENTICATION_FAILED", "Expected auth failed for dummy key"
    print("✓ Pre-save test probe OK (200, granular endpoints returned)")

    # 3. Create profile
    create_payload = {
        "exchange": "BITGET",
        "environment": "DEMO",
        "label": "Staging Verification Profile",
        "api_key": "bg_stage_test_key_12345",
        "api_secret": "bg_stage_secret_67890",
        "passphrase": "bg_stage_phrase",
        "is_read_only": True
    }
    r = client.post(f"{STAGING_BASE}/connections/profiles/", json=create_payload)
    assert r.status_code == 200, f"Create profile failed: {r.status_code} {r.text}"
    profile = r.json().get("profile", {})
    profile_id = profile.get("profile_id")
    assert profile_id, "Missing profile_id in creation response"
    assert profile.get("api_key_masked") != "bg_stage_test_key_12345", "Key not masked"
    assert "api_secret" not in profile, "Secret leaked in public profile!"
    print(f"✓ Create profile OK: {profile_id}")

    # 4. Get profiles
    r = client.get(f"{STAGING_BASE}/connections/profiles/")
    assert r.status_code == 200
    profiles = r.json().get("profiles", [])
    assert any(p["profile_id"] == profile_id for p in profiles), "Created profile not in list"
    print("✓ Get profiles list OK")

    # 5. PUT update profile (verifies PUT handler works!)
    edit_payload = {
        "label": "Staging Updated Profile",
        "is_read_only": True
    }
    r = client.put(f"{STAGING_BASE}/connections/profiles/{profile_id}/", json=edit_payload)
    assert r.status_code == 200, f"PUT profile failed with {r.status_code}: {r.text}"
    updated = r.json().get("profile", {})
    assert updated.get("label") == "Staging Updated Profile", "Label did not update"
    print("✓ PUT update profile OK (200, proxy handles PUT)")

    # 6. Retest profile
    r = client.post(f"{STAGING_BASE}/connections/profiles/{profile_id}/retest/")
    assert r.status_code == 200, f"Retest failed: {r.status_code} {r.text}"
    print("✓ Retest profile OK (200)")

    # 7. Disconnect profile
    r = client.post(f"{STAGING_BASE}/connections/profiles/{profile_id}/disconnect/")
    assert r.status_code == 200, f"Disconnect failed: {r.status_code}"
    print("✓ Disconnect profile OK (200)")

    # 8. Delete profile (cleanup)
    r = client.delete(f"{STAGING_BASE}/connections/profiles/{profile_id}/")
    assert r.status_code == 200, f"Delete failed: {r.status_code}"
    print(f"✓ Delete profile OK: {profile_id}")

    # 9. Verify cleanup
    r = client.get(f"{STAGING_BASE}/connections/profiles/")
    assert r.status_code == 200
    rem = [p for p in r.json().get("profiles", []) if p["profile_id"] == profile_id]
    assert len(rem) == 0, "Profile was not deleted"
    print("✓ Profile cleanup verified")

    print("ALL STAGING ACCEPTANCE TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
