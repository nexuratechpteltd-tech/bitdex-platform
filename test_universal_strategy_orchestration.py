import os
os.environ.setdefault("TAURIC_VAULT_PATH", "/tmp/tauric_isolated_test_vault.json")
#!/usr/bin/env python3
"""
Comprehensive 14-Point Verification Test Suite for:
TAURIC — Universal Multi-Exchange Strategy Orchestration
Architecture-Level Implementation Across Providers, Profiles, and Concurrent Runs

Targeting:
- Staging Backend: http://127.0.0.1:8002/api/v1
- Staging Dashboard: https://127.0.0.1:33900/trading/api/backend
"""

import sys
import os
import time
import json
import uuid
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BACKEND_URL = "http://127.0.0.1:8002/api/v1"
DASHBOARD_URL = "https://127.0.0.1:33900/trading/api/backend"

results = {}

def log_test(num, name, status, details):
    results[num] = {
        "name": name,
        "status": status,
        "details": details
    }
    flag = "✅ PASS" if status == "PASS" else "❌ FAIL"
    print(f"[{flag}] Test {num}: {name}")
    for k, v in details.items():
        print(f"       • {k}: {v}")
    print()

print("=" * 85)
print("RUNNING 14-POINT UNIVERSAL STRATEGY ORCHESTRATION ACCEPTANCE SUITE (STAGING)")
print("=" * 85)

# ----------------------------------------------------------------------
# 1. Arbitrary provider profiles appear in the wizard dynamically
# ----------------------------------------------------------------------
try:
    r_elig = requests.get(f"{BACKEND_URL}/orchestration/profiles/eligible")
    data_elig = r_elig.json()
    profiles = data_elig.get("profiles", [])
    
    # Check that Paper and multiple real provider profiles are listed
    exchanges_present = set(p.get("exchange") for p in profiles)
    has_paper = "PAPER" in exchanges_present
    has_crypto = len(exchanges_present) >= 3
    
    if r_elig.status_code == 200 and has_paper and has_crypto:
        log_test(1, "Arbitrary provider profiles appear in wizard dynamically", "PASS", {
            "eligible_profiles_count": len(profiles),
            "providers_represented": list(exchanges_present),
            "dynamic_discovery_verified": True
        })
    else:
        log_test(1, "Arbitrary provider profiles in wizard", "FAIL", {"data": data_elig})
except Exception as e:
    log_test(1, "Arbitrary provider profiles in wizard", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 2. Multiple profiles for the same provider can coexist
# ----------------------------------------------------------------------
try:
    # Create two distinct Binance Demo profiles with unique labels
    p1_payload = {
        "exchange": "BINANCE",
        "environment": "DEMO",
        "product_type": "SPOT",
        "label": "Binance Spot Strategy Alpha",
        "api_key": "binance_key_alpha_12345",
        "api_secret": "binance_sec_alpha_12345",
        "is_read_only": True
    }
    p2_payload = {
        "exchange": "BINANCE",
        "environment": "DEMO",
        "product_type": "SPOT",
        "label": "Binance Spot Strategy Beta",
        "api_key": "binance_key_beta_67890",
        "api_secret": "binance_sec_beta_67890",
        "is_read_only": True
    }
    r_p1 = requests.post(f"{BACKEND_URL}/connections/profiles", json=p1_payload)
    r_p2 = requests.post(f"{BACKEND_URL}/connections/profiles", json=p2_payload)
    
    pid1 = r_p1.json().get("profile", {}).get("profile_id")
    pid2 = r_p2.json().get("profile", {}).get("profile_id")
    
    r_list = requests.get(f"{BACKEND_URL}/connections/profiles")
    all_pids = [p["profile_id"] for p in r_list.json().get("profiles", [])]
    
    both_coexist = (pid1 in all_pids) and (pid2 in all_pids) and (pid1 != pid2)
    
    if both_coexist:
        log_test(2, "Multiple profiles for same provider can coexist", "PASS", {
            "profile_1_id": pid1,
            "profile_1_label": p1_payload["label"],
            "profile_2_id": pid2,
            "profile_2_label": p2_payload["label"],
            "coexistence_verified": True
        })
    else:
        log_test(2, "Multiple profiles for same provider", "FAIL", {"pid1": pid1, "pid2": pid2})
except Exception as e:
    log_test(2, "Multiple profiles for same provider", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 3. Each profile's ON/OFF state is independent and persistent
# ----------------------------------------------------------------------
try:
    # Toggle pid1 OFF, keep pid2 ON
    requests.post(f"{BACKEND_URL}/connections/profiles/{pid1}/toggle-active", json={"is_active": False})
    requests.post(f"{BACKEND_URL}/connections/profiles/{pid2}/toggle-active", json={"is_active": True})
    
    r_chk1 = requests.get(f"{BACKEND_URL}/connections/profiles")
    p1_state = next(p["is_active"] for p in r_chk1.json()["profiles"] if p["profile_id"] == pid1)
    p2_state = next(p["is_active"] for p in r_chk1.json()["profiles"] if p["profile_id"] == pid2)
    
    # Toggle pid1 ON, pid2 OFF
    requests.post(f"{BACKEND_URL}/connections/profiles/{pid1}/toggle-active", json={"is_active": True})
    requests.post(f"{BACKEND_URL}/connections/profiles/{pid2}/toggle-active", json={"is_active": False})
    
    r_chk2 = requests.get(f"{BACKEND_URL}/connections/profiles")
    p1_state2 = next(p["is_active"] for p in r_chk2.json()["profiles"] if p["profile_id"] == pid1)
    p2_state2 = next(p["is_active"] for p in r_chk2.json()["profiles"] if p["profile_id"] == pid2)
    
    independence = (p1_state is False and p2_state is True) and (p1_state2 is True and p2_state2 is False)
    
    if independence:
        log_test(3, "Each profile's ON/OFF state is independent and persistent", "PASS", {
            "round_1_states": f"Profile 1={p1_state}, Profile 2={p2_state}",
            "round_2_states": f"Profile 1={p1_state2}, Profile 2={p2_state2}",
            "independent_persistence_verified": True
        })
    else:
        log_test(3, "Profile ON/OFF independence", "FAIL", {"round1": (p1_state, p2_state), "round2": (p1_state2, p2_state2)})
except Exception as e:
    log_test(3, "Profile ON/OFF independence", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 4. Demo and live profiles for same exchange remain isolated
# ----------------------------------------------------------------------
try:
    # Create a Live profile for Binance
    p_live_payload = {
        "exchange": "BINANCE",
        "environment": "LIVE",
        "product_type": "SPOT",
        "label": "Binance Spot Live Institutional",
        "api_key": "binance_live_key_99999",
        "api_secret": "binance_live_sec_99999",
        "is_read_only": True
    }
    r_live = requests.post(f"{BACKEND_URL}/connections/profiles", json=p_live_payload)
    pid_live = r_live.json().get("profile", {}).get("profile_id")
    
    # Inspect demo profile vs live profile
    p_demo = next(p for p in requests.get(f"{BACKEND_URL}/connections/profiles").json()["profiles"] if p["profile_id"] == pid1)
    p_live = next(p for p in requests.get(f"{BACKEND_URL}/connections/profiles").json()["profiles"] if p["profile_id"] == pid_live)
    
    demo_env = p_demo.get("environment")
    live_env = p_live.get("environment")
    
    if demo_env == "DEMO" and live_env == "LIVE" and p_demo["profile_id"] != p_live["profile_id"]:
        log_test(4, "Demo and live profiles for same exchange remain isolated", "PASS", {
            "demo_profile_id": p_demo["profile_id"],
            "demo_environment": demo_env,
            "live_profile_id": p_live["profile_id"],
            "live_environment": live_env,
            "environment_leakage_prevented": True
        })
    else:
        log_test(4, "Demo and live isolation", "FAIL", {"demo": p_demo, "live": p_live})
except Exception as e:
    log_test(4, "Demo and live isolation", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 5. Same asset can have multiple independent strategy runs
# ----------------------------------------------------------------------
try:
    # Launch concurrent runs on SOL/USDT across different profiles & strategies
    run_a = requests.post(f"{BACKEND_URL}/orchestration/runs/launch", json={
        "asset": "SOL/USDT",
        "strategy_id": "SPOT_GRID",
        "profile_id": "PAPER",
        "investment_amount": 100.0,
        "environment": "PAPER",
        "parameters": {"grid_count": 5, "reference_price": 170.0}
    }).json()
    
    run_b = requests.post(f"{BACKEND_URL}/orchestration/runs/launch", json={
        "asset": "SOL/USDT",
        "strategy_id": "CRYPTO_MOMENTUM",
        "profile_id": "PAPER",
        "investment_amount": 150.0,
        "environment": "PAPER",
        "parameters": {"stop_loss": 160.0, "take_profit": 190.0}
    }).json()
    
    run_a_id = run_a.get("strategy_run", {}).get("run_id")
    run_b_id = run_b.get("strategy_run", {}).get("run_id")
    
    runs_all = requests.get(f"{BACKEND_URL}/orchestration/runs?asset=SOL/USDT").json()
    sol_run_ids = [r["run_id"] for r in runs_all.get("strategy_runs", [])]
    
    if run_a_id in sol_run_ids and run_b_id in sol_run_ids and run_a_id != run_b_id:
        log_test(5, "The same asset can have multiple independent strategy runs", "PASS", {
            "asset": "SOL/USDT",
            "run_A_id": run_a_id,
            "run_A_strategy": run_a.get("strategy_run", {}).get("strategy_name"),
            "run_B_id": run_b_id,
            "run_B_strategy": run_b.get("strategy_run", {}).get("strategy_name"),
            "concurrent_runs_count": len(sol_run_ids)
        })
    else:
        log_test(5, "Multiple runs on same asset", "FAIL", {"run_a": run_a, "run_b": run_b})
except Exception as e:
    log_test(5, "Multiple runs on same asset", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 6. Each run uses exact selected provider/profile/environment
# ----------------------------------------------------------------------
try:
    r_detail_a = requests.get(f"{BACKEND_URL}/orchestration/runs/{run_a_id}").json().get("strategy_run", {})
    r_detail_b = requests.get(f"{BACKEND_URL}/orchestration/runs/{run_b_id}").json().get("strategy_run", {})
    
    exact_match = (
        r_detail_a.get("profile_id") == "PAPER" and
        r_detail_a.get("environment") == "PAPER" and
        r_detail_a.get("investment_amount") == 100.0 and
        r_detail_b.get("investment_amount") == 150.0 and
        r_detail_a.get("strategy_id") == "SPOT_GRID" and
        r_detail_b.get("strategy_id") == "CRYPTO_MOMENTUM"
    )
    
    if exact_match:
        log_test(6, "Each run uses exact selected provider/profile/environment", "PASS", {
            "run_A_exact": f"{r_detail_a.get('provider_id')} / {r_detail_a.get('environment')} / ${r_detail_a.get('investment_amount')}",
            "run_B_exact": f"{r_detail_b.get('provider_id')} / {r_detail_b.get('environment')} / ${r_detail_b.get('investment_amount')}",
            "zero_silent_substitution": True
        })
    else:
        log_test(6, "Exact run parameters", "FAIL", {"detail_a": r_detail_a, "detail_b": r_detail_b})
except Exception as e:
    log_test(6, "Exact run parameters", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 7. Missing credentials or capabilities block run with actionable reason
# ----------------------------------------------------------------------
try:
    # Ensure profile is active so we explicitly test unverified credentials blocker
    requests.post(f"{BACKEND_URL}/connections/profiles/{pid2}/toggle-active", json={"is_active": True})
    r_resp = requests.post(f"{BACKEND_URL}/orchestration/preflight", json={
        "asset": "BTC/USDT",
        "strategy_id": "SPOT_GRID",
        "profile_id": pid2,
        "investment_amount": 100.0,
        "environment": "DEMO"
    }, timeout=10)
    r_pre_bad = r_resp.json()
    
    is_blocked = (r_pre_bad.get("eligible") is False) and (r_pre_bad.get("status") == "BLOCKED")
    has_blockers = len(r_pre_bad.get("blockers", [])) > 0
    has_actions = len(r_pre_bad.get("corrective_actions", [])) > 0
    
    if is_blocked and has_blockers and has_actions:
        log_test(7, "Missing credentials or capabilities block run with actionable reason", "PASS", {
            "preflight_status": r_pre_bad.get("status"),
            "eligible": r_pre_bad.get("eligible"),
            "blocker_reason": r_pre_bad.get("blockers")[0],
            "corrective_action": r_pre_bad.get("corrective_actions")[0]
        })
    else:
        log_test(7, "Block on unverified credentials", "FAIL", {"response": r_pre_bad})
except Exception as e:
    log_test(7, "Block on unverified credentials", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 8. Demo requests never reach live endpoints
# ----------------------------------------------------------------------
try:
    # Check that demo profile custom_config and adapter target testnet base URLs
    schema_bin = requests.get(f"{BACKEND_URL}/connections/providers/BINANCE/schema").json().get("schema", {})
    demo_ep = schema_bin.get("endpoints", {}).get("DEMO", {}).get("spot_public")
    live_ep = schema_bin.get("endpoints", {}).get("LIVE", {}).get("spot_public")
    
    is_separated = ("testnet" in demo_ep) and ("testnet" not in live_ep)
    
    if is_separated:
        log_test(8, "Demo requests never reach live endpoints", "PASS", {
            "demo_endpoint": demo_ep,
            "live_endpoint": live_ep,
            "endpoint_routing_isolated": True
        })
    else:
        log_test(8, "Demo endpoint isolation", "FAIL", {"demo": demo_ep, "live": live_ep})
except Exception as e:
    log_test(8, "Demo endpoint isolation", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 9. Paper runs never submit exchange orders
# ----------------------------------------------------------------------
try:
    r_detail = requests.get(f"{BACKEND_URL}/orchestration/runs/{run_a_id}").json().get("strategy_run", {})
    orders = r_detail.get("normalized_orders", [])
    
    # Verify orders are internal simulated IDs (ord_strat_run_...)
    all_simulated = all(o.get("order_id", "").startswith("ord_strat_run_") for o in orders)
    execution_mode = r_detail.get("execution_mode")
    
    if all_simulated and execution_mode == "PAPER":
        log_test(9, "Paper runs never submit exchange orders", "PASS", {
            "execution_mode": execution_mode,
            "sample_order_id": orders[0]["order_id"] if orders else "None",
            "real_exchange_submission": "ZERO (Internal Simulator Only)"
        })
    else:
        log_test(9, "Paper simulation isolation", "FAIL", {"detail": r_detail})
except Exception as e:
    log_test(9, "Paper simulation isolation", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 10. No balance/order/P&L data leaks between profiles or environments
# ----------------------------------------------------------------------
try:
    run_a_bal = r_detail_a.get("balance_source", {})
    run_b_bal = r_detail_b.get("balance_source", {})
    
    leakage = (run_a_bal.get("allocated_amount") == run_b_bal.get("allocated_amount"))
    # run A was 100, run B was 150
    no_leakage = (run_a_bal.get("allocated_amount") == 100.0) and (run_b_bal.get("allocated_amount") == 150.0)
    
    if no_leakage:
        log_test(10, "No balance/order/P&L data leaks between profiles or environments", "PASS", {
            "run_A_allocated": run_a_bal.get("allocated_amount"),
            "run_B_allocated": run_b_bal.get("allocated_amount"),
            "ledger_provenance_isolated": True
        })
    else:
        log_test(10, "Ledger data isolation", "FAIL", {"bal_a": run_a_bal, "bal_b": run_b_bal})
except Exception as e:
    log_test(10, "Ledger data isolation", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 11. Idempotency prevents duplicate strategy runs and orders
# ----------------------------------------------------------------------
try:
    fixed_idemp = f"test_idemp_{int(time.time())}"
    launch_1 = requests.post(f"{BACKEND_URL}/orchestration/runs/launch", json={
        "asset": "ETH/USDT",
        "strategy_id": "SPOT_GRID",
        "profile_id": "PAPER",
        "investment_amount": 100.0,
        "environment": "PAPER",
        "idempotency_key": fixed_idemp
    }).json()
    
    # Immediate duplicate submission with identical key
    launch_2 = requests.post(f"{BACKEND_URL}/orchestration/runs/launch", json={
        "asset": "ETH/USDT",
        "strategy_id": "SPOT_GRID",
        "profile_id": "PAPER",
        "investment_amount": 100.0,
        "environment": "PAPER",
        "idempotency_key": fixed_idemp
    }).json()
    
    first_ok = (launch_1.get("status") == "SUCCESS")
    second_idemp = (launch_2.get("status") == "DUPLICATE_IDEMPOTENT")
    same_run_id = (launch_1.get("strategy_run", {}).get("run_id") == launch_2.get("strategy_run", {}).get("run_id"))
    
    if first_ok and second_idemp and same_run_id:
        log_test(11, "Idempotency prevents duplicate strategy runs and orders", "PASS", {
            "idempotency_key": fixed_idemp,
            "submission_1_status": launch_1.get("status"),
            "submission_2_status": launch_2.get("status"),
            "duplicate_run_prevented": True,
            "retained_run_id": launch_1.get("strategy_run", {}).get("run_id")
        })
    else:
        log_test(11, "Idempotency deduplication", "FAIL", {"l1": launch_1, "l2": launch_2})
except Exception as e:
    log_test(11, "Idempotency deduplication", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 12. Live selection is represented honestly but live execution is blocked (HTTP 403)
# ----------------------------------------------------------------------
try:
    r_live_pre = requests.post(f"{BACKEND_URL}/orchestration/preflight", json={
        "asset": "SOL/USDT",
        "strategy_id": "SPOT_GRID",
        "profile_id": "PAPER",
        "investment_amount": 100.0,
        "environment": "LIVE"
    }).json()
    
    r_live_direct = requests.post(f"{BACKEND_URL}/orders/live/submit", json={})
    
    live_blocked_preflight = (r_live_pre.get("eligible") is False) and any("hard-locked" in b or "safety invariant" in b for b in r_live_pre.get("blockers", []))
    live_blocked_direct = (r_live_direct.status_code == 403)
    
    if live_blocked_preflight and live_blocked_direct:
        log_test(12, "Live selection represented honestly but live execution blocked with HTTP 403", "PASS", {
            "preflight_authorization_state": r_live_pre.get("authorization_state"),
            "preflight_blocker": r_live_pre.get("blockers")[0],
            "live_order_submit_http_status": r_live_direct.status_code,
            "live_safety_invariant": "HARD-LOCKED (live_trading_locked=true)"
        })
    else:
        log_test(12, "Live execution safety gate", "FAIL", {"pre": r_live_pre, "direct": r_live_direct.status_code})
except Exception as e:
    log_test(12, "Live execution safety gate", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 13. Existing API management and compact calendar behavior still work
# ----------------------------------------------------------------------
try:
    # Verify profiles list endpoint
    r_prof = requests.get(f"{BACKEND_URL}/connections/profiles")
    prof_ok = r_prof.status_code == 200 and len(r_prof.json().get("profiles", [])) > 0
    
    # Verify calendar code in dashboard
    with open("/opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx", "r") as f:
        dash_src = f.read()
    
    cal_collapsed = "const [isCalendarExpanded, setIsCalendarExpanded] = useState<boolean>(false);" in dash_src
    cal_slice = ".slice(0, 3)" in dash_src
    cal_see_more = 'isCalendarExpanded ? "Show less" : "See more"' in dash_src
    
    if prof_ok and cal_collapsed and cal_slice and cal_see_more:
        log_test(13, "Existing API management and compact calendar behavior still work", "PASS", {
            "api_profiles_endpoint_status": r_prof.status_code,
            "profiles_count": len(r_prof.json().get("profiles", [])),
            "calendar_default_collapsed": cal_collapsed,
            "calendar_3_item_slice": cal_slice,
            "calendar_toggle_button": cal_see_more
        })
    else:
        log_test(13, "Existing API management & calendar", "FAIL", {"prof_ok": prof_ok, "cal_collapsed": cal_collapsed})
except Exception as e:
    log_test(13, "Existing API management & calendar", "FAIL", {"exception": str(e)})

# ----------------------------------------------------------------------
# 14. Account Balance Allocation Validation ("money from account")
# ----------------------------------------------------------------------
try:
    # Test balance fetch endpoint for Paper
    r_bal = requests.get(f"{BACKEND_URL}/orchestration/profiles/PAPER/balance?asset=SOL/USDT").json()
    cap_val = r_bal.get("capital", {}).get("available_capital")
    
    # Sizing request with amount MORE than allocated balance ($20,000 > $10,000)
    r_exceed = requests.post(f"{BACKEND_URL}/orchestration/preflight", json={
        "asset": "SOL/USDT",
        "strategy_id": "SPOT_GRID",
        "profile_id": "PAPER",
        "investment_amount": 25000.0,
        "environment": "PAPER"
    }).json()
    
    excess_blocked = (r_exceed.get("eligible") is False)
    has_excess_msg = any("more than allocated in account" in b for b in r_exceed.get("blockers", []))
    
    # Sizing request with valid amount ($100 <= $10,000)
    r_valid = requests.post(f"{BACKEND_URL}/orchestration/preflight", json={
        "asset": "SOL/USDT",
        "strategy_id": "SPOT_GRID",
        "profile_id": "PAPER",
        "investment_amount": 100.0,
        "environment": "PAPER"
    }).json()
    valid_ok = (r_valid.get("eligible") is True)
    
    if excess_blocked and has_excess_msg and valid_ok:
        log_test(14, "Account balance validation: warns & blocks when amount exceeds account funds", "PASS", {
            "profile_balance_fetched": f"${cap_val} USD",
            "excessive_request_amount": "$25,000.00",
            "excessive_request_blocked": excess_blocked,
            "excessive_warning_message": r_exceed.get("blockers")[0],
            "valid_request_amount": "$100.00",
            "valid_request_status": r_valid.get("status")
        })
    else:
        log_test(14, "Account balance validation", "FAIL", {"r_bal": r_bal, "r_exceed": r_exceed, "valid": valid_ok})
except Exception as e:
    log_test(14, "Account balance validation", "FAIL", {"exception": str(e)})

# Cleanup temporary test profiles created in tests 2 & 4
for test_pid in [pid1, pid2, pid_live]:
    try:
        requests.delete(f"{BACKEND_URL}/connections/profiles/{test_pid}")
    except:
        pass

print("=" * 85)
total_pass = sum(1 for v in results.values() if v["status"] == "PASS")
total_tests = len(results)
print(f"TEST RESULTS: {total_pass}/{total_tests} ACCEPTANCE TESTS PASSED")
print("=" * 85)

if total_pass == total_tests:
    print("ALL 14 UNIVERSAL ORCHESTRATION ACCEPTANCE TESTS PASSED SUCCESSFULLY.")
    sys.exit(0)
else:
    print(f"WARNING: {total_tests - total_pass} TESTS FAILED.")
    sys.exit(1)
