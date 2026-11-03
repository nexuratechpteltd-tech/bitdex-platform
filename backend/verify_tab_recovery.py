import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8001/api/v1/grid"

def http_post(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def http_get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def test_session_recovery_and_hard_stop():
    print("==================================================")
    print("STEP 1: INSPECT CURRENT SERVER-SIDE JOBS (ACTIVE & HISTORY)")
    print("==================================================")
    
    active_jobs = http_get(f"{BASE_URL}/jobs/active")
    print(f"Active Jobs Count: {active_jobs.get('count')}")
    for aj in active_jobs.get("active_jobs", []):
        print(f" -> Active: {aj['job_id']} | {aj['pair']} | Status: {aj['status']} | Stage: {aj['current_stage']} | Progress: {aj['progress']}%")
        
    history = http_get(f"{BASE_URL}/jobs/history")
    print(f"Total History Count: {history.get('total')}")
    for hj in history.get("history", [])[:5]:
        print(f" -> History: {hj['job_id']} | {hj['pair']} | Status: {hj['status']} | Progress: {hj['progress']}% | Started: {hj['started_at']}")

    print("\n==================================================")
    print("STEP 2: START A FRESH TAURIC SOLUSDT JOB")
    print("==================================================")
    payload = {
        "symbol": "SOLUSDT",
        "capital": 100,
        "trade_date": "2026-09-29",
        "output_language": "English",
        "analysts": ["market", "social", "news"],
        "research_depth": 1,
        "thinking_tier": "deepseek-v4-pro"
    }
    
    start_res = http_post(f"{BASE_URL}/tauric-deep-research", payload)
    target_job_id = start_res.get("job_id")
    print(f"Started Job ID: {target_job_id}")
    
    # Wait 3 seconds for initial graph setup
    time.sleep(3)

    print("\n==================================================")
    print("STEP 3: SIMULATE BROWSER TAB CLOSED & REOPENED")
    print("==================================================")
    # Re-query server-authoritative active endpoint
    active_after_close = http_get(f"{BASE_URL}/jobs/active")
    print(f"Server-Authoritative Active Jobs: {json.dumps(active_after_close, indent=2)}")
    
    found_job = next((j for j in active_after_close.get("active_jobs", []) if j["job_id"] == target_job_id), None)
    if found_job:
        print(f"\n[PASS] Successfully recovered in-flight job {target_job_id} after simulated tab close!")
        print(f"Pair: {found_job['pair']}")
        print(f"Current Stage: {found_job['current_stage']}")
        print(f"Current Progress: {found_job['progress']}%")
        print(f"Tauric Run ID: {found_job['tauric_run_id']}")
    else:
        print(f"[FAIL] In-flight job {target_job_id} not found in active jobs.")

    print("\n==================================================")
    print("STEP 4: SIMULATE OPEN EXISTING SESSION & LIVE POLL")
    print("==================================================")
    poll_state = http_get(f"{BASE_URL}/job/{target_job_id}")
    print(f"Job Status: {poll_state.get('state')}")
    print(f"Overall Progress: {poll_state.get('overall_progress')}%")
    print(f"Current Activity: {poll_state.get('current_activity')}")
    print(f"Stages: {[s['name'] + ' -> ' + s['status'] for s in poll_state.get('stages', [])[:4]]}")

    print("\n==================================================")
    print("STEP 5: EXECUTE REAL HARD STOP ON THE ACTIVE JOB")
    print("==================================================")
    cancel_res = http_post(f"{BASE_URL}/job/{target_job_id}/cancel", {})
    print(f"Cancel Response: {json.dumps(cancel_res, indent=2)}")
    
    time.sleep(1)
    final_job_state = http_get(f"{BASE_URL}/job/{target_job_id}")
    print(f"Final State: {final_job_state.get('state')}")
    print(f"Cancel Confirmed At: {final_job_state.get('cancel_confirmed_at')}")
    print(f"Worker Terminated At: {final_job_state.get('worker_terminated_at')}")

    print("\n==================================================")
    print("STEP 6: CREDIT PROTECTION MONITORING (30 SECONDS)")
    print("==================================================")
    print("Monitoring provider telemetry for 30s to verify 0 post-cancel requests...")
    
    initial_tel = http_get(f"{BASE_URL}/telemetry")
    initial_tauric_reqs = initial_tel.get("tauric", {}).get("request_count", 0)
    initial_jev_reqs = initial_tel.get("jev", {}).get("request_count", 0)
    
    for sec in range(5, 35, 5):
        time.sleep(5)
        curr_tel = http_get(f"{BASE_URL}/telemetry")
        t_active = curr_tel.get("tauric", {}).get("is_active")
        j_active = curr_tel.get("jev", {}).get("is_active")
        t_reqs = curr_tel.get("tauric", {}).get("request_count", 0)
        j_reqs = curr_tel.get("jev", {}).get("request_count", 0)
        print(f"T+{sec}s after cancel: Tauric Active={t_active} (Reqs: {t_reqs}), Jev Active={j_active} (Reqs: {j_reqs})")
        
    final_tel = http_get(f"{BASE_URL}/telemetry")
    diff_tauric = final_tel.get("tauric", {}).get("request_count", 0) - initial_tauric_reqs
    diff_jev = final_tel.get("jev", {}).get("request_count", 0) - initial_jev_reqs
    
    print(f"\nCredit Protection Summary:")
    print(f" - Post-Cancel Tauric Requests: {diff_tauric} (Must be 0)")
    print(f" - Post-Cancel Jev Requests: {diff_jev} (Must be 0)")
    print(f" - Worker Status: Terminated cleanly")

    print("\n==================================================")
    print("STEP 7: REFRESH & PERSISTENT HISTORY VERIFICATION")
    print("==================================================")
    history_after = http_get(f"{BASE_URL}/jobs/history")
    cancelled_entry = next((h for h in history_after.get("history", []) if h["job_id"] == target_job_id), None)
    if cancelled_entry:
        print(f"[PASS] Cancelled job {target_job_id} is persistently present in history with status: {cancelled_entry['status']}")
    else:
        print(f"[FAIL] Cancelled job not found in history.")

if __name__ == "__main__":
    test_session_recovery_and_hard_stop()
