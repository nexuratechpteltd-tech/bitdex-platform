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

def test_full_pipeline():
    print("==================================================")
    print("1. RUNNING TEST B: REAL HARD CANCELLATION MID-FLIGHT")
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
    
    res = http_post(f"{BASE_URL}/tauric-deep-research", payload)
    job_id = res.get("job_id")
    print(f"[TEST B] Initiated Job ID: {job_id}")
    
    # Poll for 2-3 seconds to see it enter active stage
    time.sleep(2)
    poll1 = http_get(f"{BASE_URL}/job/{job_id}")
    print(f"[TEST B] Active State: {poll1.get('state')} | Progress: {poll1.get('overall_progress')}% | Activity: {poll1.get('current_activity')}")
    print(f"[TEST B] Stages sample: {[s['name'] + ':' + s['status'] for s in poll1.get('stages', [])[:3]]}")
    
    # Trigger cancel
    print(f"[TEST B] Triggering hard cancellation on {job_id}...")
    cancel_res = http_post(f"{BASE_URL}/job/{job_id}/cancel", {})
    print(f"[TEST B] Cancel Response: {json.dumps(cancel_res, indent=2)}")
    
    # Verify cancellation idempotency
    cancel_res_again = http_post(f"{BASE_URL}/job/{job_id}/cancel", {})
    print(f"[TEST B] Second Cancel Call (Idempotency Check): {json.dumps(cancel_res_again, indent=2)}")
    
    # Verify final cancelled job state
    time.sleep(1)
    poll_cancel = http_get(f"{BASE_URL}/job/{job_id}")
    print(f"[TEST B] Poll after cancel - State: {poll_cancel.get('state')} | Activity: {poll_cancel.get('current_activity')}")
    print(f"[TEST B] Cancel Stages: {[s['name'] + ':' + s['status'] for s in poll_cancel.get('stages', [])]}")
    
    # Check telemetry is idle
    tel = http_get(f"{BASE_URL}/telemetry")
    print(f"[TEST B] Telemetry after cancel - Tauric Active: {tel.get('tauric', {}).get('is_active')}, In Flight: {tel.get('tauric', {}).get('active_requests_count')}")

    print("\n==================================================")
    print("2. RUNNING TEST A: COMPLETE TAURIC RESEARCH PIPELINE")
    print("==================================================")
    
    res_a = http_post(f"{BASE_URL}/tauric-deep-research", payload)
    job_id_a = res_a.get("job_id")
    print(f"[TEST A] Initiated Job ID: {job_id_a}")
    
    stage_history = []
    completed = False
    final_res = None
    
    for i in range(120):
        time.sleep(2)
        poll_a = http_get(f"{BASE_URL}/job/{job_id_a}")
        st = poll_a.get("state")
        prog = poll_a.get("overall_progress", 0)
        act = poll_a.get("current_activity", "")
        
        active_stages = [s["name"] for s in poll_a.get("stages", []) if s.get("status") == "RUNNING"]
        done_stages = [s["name"] for s in poll_a.get("stages", []) if s.get("status") == "COMPLETED"]
        
        summary_str = f"Progress: {prog}% | Active: {active_stages} | Done: {len(done_stages)}/10"
        if not stage_history or stage_history[-1] != summary_str:
            stage_history.append(summary_str)
            print(f"[TEST A T+{i*2}s] {summary_str} | Current: {act}")
            
        if st == "COMPLETED":
            completed = True
            final_res = poll_a.get("result")
            break
        elif st == "FAILED":
            print(f"[TEST A FAILED]: {poll_a.get('error')}")
            break
            
    if completed:
        print("\n[TEST A SUCCESS] Job completed 100%!")
        print(f"Symbol: {final_res.get('symbol')}")
        print(f"Source Metadata: {json.dumps(final_res.get('source_metadata'), indent=2)}")
        print(f"Tauric Plan: Direction={final_res.get('tauric_card', {}).get('direction')}, Entry={final_res.get('tauric_card', {}).get('entry_zone')}, TP={final_res.get('tauric_card', {}).get('take_profit')}, SL={final_res.get('tauric_card', {}).get('stop_loss')}")
        print(f"Jev Review: Direction={final_res.get('jev_card', {}).get('direction')}, Agreement={final_res.get('jev_card', {}).get('agreement_status')}, Decision={final_res.get('jev_card', {}).get('decision')}")
        print(f"Deterministic Comparison: {json.dumps(final_res.get('comparison'), indent=2)}")

if __name__ == "__main__":
    test_full_pipeline()
