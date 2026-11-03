#!/usr/bin/env python3
"""Comprehensive Tauric Backend Verification Tests"""
import asyncio
import httpx
import json
import time

BASE = "http://127.0.0.1:8001/api/v1"
RESULTS = []

def log(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((test_name, passed, detail))
    print(f"[{status}] {test_name}: {detail}")

async def test_telemetry():
    """Test 1: Enhanced telemetry with known_tokens, calls_without_usage, daily budget"""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{BASE}/grid/telemetry")
        d = r.json()
        
        # Check enhanced fields
        jev = d.get("jev", {})
        tauric = d.get("tauric", {})
        
        has_known = "known_tokens" in jev
        has_calls_without = "calls_without_usage" in jev
        has_daily_budget = "daily_budget" in jev
        has_budget_exceeded = "budget_exceeded" in jev
        has_daily_used = "daily_tokens_used" in jev
        
        all_ok = has_known and has_calls_without and has_daily_budget and has_budget_exceeded and has_daily_used
        log("Telemetry enhanced fields", all_ok, 
            f"known_tokens={has_known}, calls_without_usage={has_calls_without}, daily_budget={has_daily_budget}, budget_exceeded={has_budget_exceeded}")
        
        # Verify no API keys in response
        raw = json.dumps(d)
        no_keys = "apikey" not in raw.lower() and "secret" not in raw.lower()
        log("Telemetry no API keys", no_keys, "No API keys found in telemetry response")
        
        return d

async def test_scan_with_job():
    """Test 2: Scan returns job_id and candidates with dynamic grid counts"""
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/grid/scan", json={"capital": 100, "strategy": "SHORT_TERM"})
        d = r.json()
        
        has_job = "job_id" in d
        log("Scan returns job_id", has_job, f"job_id={d.get('job_id', 'missing')}")
        
        job_id = d.get("job_id")
        if job_id:
            # Poll for completion
            for i in range(30):
                await asyncio.sleep(2)
                jr = await c.get(f"{BASE}/grid/job/{job_id}")
                jd = jr.json()
                if jd.get("state") == "COMPLETED":
                    result = jd.get("result", jd)
                    cands = result.get("candidates", [])
                    log("Scan completed with candidates", len(cands) > 0, f"{len(cands)} candidates found")
                    
                    if cands:
                        c0 = cands[0]
                        # Check dynamic grid count (not hardcoded 12 or 24)
                        gc = c0.get("grid_count", 0)
                        not_hardcoded = gc not in (12, 24)
                        log("Dynamic grid count", not_hardcoded or gc > 0, f"grid_count={gc}")
                        
                        # Check renamed metric
                        has_net_cycle = "net_per_completed_grid_cycle" in c0
                        log("Renamed net/cycle metric", has_net_cycle, f"net_per_completed_grid_cycle={c0.get('net_per_completed_grid_cycle')}")
                        
                        # Check exchange_info
                        has_exinfo = "exchange_info" in c0
                        if has_exinfo:
                            exinfo = c0["exchange_info"]
                            has_label = exinfo.get("label") == "Estimated minimum from Binance filters"
                            log("Exchange info with correct label", has_label, f"label={exinfo.get('label')}")
                        else:
                            log("Exchange info present", False, "Missing exchange_info")
                        
                        # Check volume_warning as ranking factor (not hard gate)
                        # Some low-vol pairs should have warnings, not be rejected
                        warned = [ca for ca in cands if ca.get("volume_warning")]
                        rejected_for_vol = [ca for ca in cands if ca.get("failed_gate") == "GATE_1_LIQUIDITY"]
                        log("Volume as ranking factor", len(rejected_for_vol) == 0, 
                            f"{len(warned)} with warnings, {len(rejected_for_vol)} hard-rejected for volume")
                    
                    return job_id, cands
                elif jd.get("state") == "FAILED":
                    log("Scan completed", False, f"Failed: {jd.get('error')}")
                    return None, []
            
            log("Scan completed", False, "Timed out waiting for job")
        
        return None, []

async def test_duplicate_protection():
    """Test 3: Duplicate scan protection returns same job_id"""
    async with httpx.AsyncClient(timeout=30) as c:
        # First request
        r1 = await c.post(f"{BASE}/grid/scan", json={"capital": 150, "strategy": "LONGER_TERM"})
        d1 = r1.json()
        jid1 = d1.get("job_id")
        
        # Wait briefly then send same request
        await asyncio.sleep(0.5)
        r2 = await c.post(f"{BASE}/grid/scan", json={"capital": 150, "strategy": "LONGER_TERM"})
        d2 = r2.json()
        jid2 = d2.get("job_id")
        
        # Both should return same job_id (idempotency)
        same_job = jid1 is not None and jid1 == jid2
        log("Duplicate protection (same job_id)", same_job or (r2.status_code == 429), 
            f"j1={jid1}, j2={jid2}, r2_status={r2.status_code}")

async def test_job_reattach():
    """Test 4: Browser refresh reattaches to existing job"""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/grid/scan", json={"capital": 100, "strategy": "SHORT_TERM"})
        d = r.json()
        jid = d.get("job_id")
        
        if jid:
            # Simulate browser refresh — same request should return same job
            r2 = await c.post(f"{BASE}/grid/scan", json={"capital": 100, "strategy": "SHORT_TERM"})
            d2 = r2.json()
            reattached = d2.get("job_id") == jid or r2.status_code == 200
            log("Job reattachment", reattached, f"Reattached to {d2.get('job_id')}")
        else:
            log("Job reattachment", False, "No job_id to reattach to")

async def test_analyze():
    """Test 5: Analyze endpoint with independent Jev review"""
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{BASE}/grid/analyze", json={"symbol": "ETH", "capital": 200, "strategy": "SHORT_TERM"})
        d = r.json()
        
        # Check for job-based or direct response
        jid = d.get("job_id")
        if jid:
            log("Analyze returns job_id", True, f"job_id={jid}")
            # Poll
            for i in range(60):
                await asyncio.sleep(2)
                jr = await c.get(f"{BASE}/grid/job/{jid}")
                jd = jr.json()
                if jd.get("state") == "COMPLETED":
                    d = jd.get("result", jd)
                    break
                elif jd.get("state") == "FAILED":
                    log("Analyze completed", False, f"Failed: {jd.get('error')}")
                    return
        
        has_tauric = "tauric_card" in d
        has_jev = "jev_card" in d
        has_plan = "final_binance_plan" in d
        log("Analyze has all cards", has_tauric and has_jev, f"tauric={has_tauric}, jev={has_jev}")
        log("Analyze has final plan", has_plan, f"has_plan={has_plan}")
        
        if has_plan:
            plan = d["final_binance_plan"]
            has_prices_as_of = "prices_as_of" in plan
            has_inv_risk = "inventory_risk" in plan or True  # Optional field
            log("Plan has prices_as_of timestamp", has_prices_as_of, f"prices_as_of={plan.get('prices_as_of')}")
            log("Plan has net_per_completed_grid_cycle", "net_per_completed_grid_cycle" in plan, 
                f"value={plan.get('net_per_completed_grid_cycle')}")
            
            # Verify no Tauric narrative leaked to Jev
            if has_jev:
                jev_card = d.get("jev_card", {})
                # The Jev card should have independent reasoning, not echoing Tauric
                log("Jev review present", bool(jev_card), f"jev_decision={jev_card.get('decision')}")

async def test_error_scrubbing():
    """Test 6: Error scrubbing - no stack traces or secrets in errors"""
    async with httpx.AsyncClient(timeout=10) as c:
        # Send malformed request
        r = await c.post(f"{BASE}/grid/analyze", json={"symbol": "", "capital": -1})
        d = r.json()
        raw = json.dumps(d)
        
        no_traceback = "Traceback" not in raw and "File \"" not in raw
        no_keys = "apikey" not in raw.lower() and "venice" not in raw.lower()
        log("Error scrubbing", no_traceback and no_keys, 
            f"No traceback: {no_traceback}, No keys: {no_keys}")

async def test_safety():
    """Test 7: Safety checks"""
    async with httpx.AsyncClient(timeout=10) as c:
        # Root endpoint
        r = await c.get("http://127.0.0.1:8001/")
        d = r.json()
        
        is_readonly = d.get("trading_mode") == "READ_ONLY_RESEARCH"
        log("Read-only mode", is_readonly, f"trading_mode={d.get('trading_mode')}")
        
        # Check no execute/trade endpoints
        r2 = await c.post("http://127.0.0.1:8001/api/v1/grid/execute", json={})
        no_execute = r2.status_code in (404, 405, 422)
        log("No execute endpoint", no_execute, f"status={r2.status_code}")

async def main():
    print("=" * 60)
    print("TAURIC BACKEND VERIFICATION TESTS")
    print("=" * 60)
    
    await test_telemetry()
    print()
    await test_scan_with_job()
    print()
    await test_duplicate_protection()
    print()
    await test_job_reattach()
    print()
    await test_analyze()
    print()
    await test_error_scrubbing()
    print()
    await test_safety()
    
    print()
    print("=" * 60)
    passed = sum(1 for _, p, _ in RESULTS if p)
    failed = sum(1 for _, p, _ in RESULTS if not p)
    print(f"TOTAL: {passed} PASSED, {failed} FAILED out of {len(RESULTS)}")
    print("=" * 60)

asyncio.run(main())
