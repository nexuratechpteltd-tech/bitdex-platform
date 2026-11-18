# BITDEX COMMAND 14 — INDEPENDENT COMMAND 13 REMEDIATION AUDIT

**Audit Date:** 2026-11-17 UTC  
**Audit Mode:** Strictly Read-Only Independent Inspection & Behavioral Verification  
**Final Verdict:** `COMMAND 13 INDEPENDENT AUDIT FAILED — EXECUTION DISABLED`

---

## 1. Executive Summary & Checksum Verification

An independent read-only audit of the Command 13 staging remediation in `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` was conducted against the backups, frozen `LT_STRUCTURE_EURUSD_A2` v2.0 files, broker adapters (`ExnessTerminalBrokerAdapter`, `ExnessTraderAPIClient`, `ExnessMT5BrokerAdapter`), `SharedCentralRiskManager`, `PostFillRiskBreachGuard`, and `TradeMemoryService`.

While **Remediation A** (closed-candle filtering) and **Execution Safety** (`authorized: false`, `REAL_TRADING_PERMANENTLY_LOCKED = True`, frozen strategy integrity) **PASSED**, the independent audit uncovered **four concrete engineering defects** across **Remediation C** (post-fill protection & TradeMemory recording) and **Remediation B** (premature state mutation before preflight/execution) that were masked in Command 13's verification script because `TradeMemoryService.record_trade` was mocked out (`patch.object(runner.TradeMemoryService, "record_trade", ...)`).

### Verified File Checksums (SHA256)

| File | SHA256 Checksum | Status |
|---|---|---|
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` | `68bbb9386e81599449847fe4ec1efba9fe4bad1418a36f5e99536fd0d9bce3f9` | Inspected (Command 13 output) |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd13_20261117` | `f4fb399e2d170f119723c74c5d679849feab3b4947498eb46b343f23e1467d66` | Verified (Command 11 baseline) |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd11_20261117` | `34c1e7eda926e0e4dfce3672b8d9e548339ecb823fef40886fa48a1b5f04a37a` | Verified (Pre-Command 11 baseline) |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py` | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` | **PASS** (Frozen v2.0 intact) |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py` | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` | **PASS** (Frozen v2.0 intact) |
| `/opt/tauric-platform-staging/backend/app/services/brokers/shared_risk_manager.py` | `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5` | **PASS** (Unmodified) |
| `/opt/tauric-platform-staging/backend/app/services/brokers/execution_router.py` | `e199dc7c590ce79874b34ebf14fa2b6948fba866b19b4b8dbbddaa8a904f6016` | **PASS** (Unmodified) |
| `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py` | `61290279942ea8c878dcbf24d1b5a0c306da4e51b289f39404e67bc3a9ac7366` | **PASS** (Unmodified) |
| `/opt/bitdex-research-v2/docs/cmd13_remediation_verification.json` | `d5891164c86f615dd084034ce2c649c28e9ef33bcff277aea9c3f80fc1fc2cc4` | Inspected |

---

## 2. Independent Verification by Audit Area

### A. Candle Integrity (`filter_closed_candles`) — `PASS`

**Inspected Code:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` lines `215–277` and `427–445`.

| Sub-Check | Classification | Evidence & Line Numbers |
|---|---|---|
| Filtering before every strategy evaluation | **PASS** | `scan_market_opportunities()` (lines `429–435`) calls `self.filter_closed_candles(...)` on `d1_raw`, `h4_raw`, and `h1_raw` immediately before constructing `EurUsdStructureA2(d1_df, h4_df, er_thr=0.20)` (line `443`). |
| H1 / H4 / D1 boundaries (`+3600s`, `+14400s`, `+86400s`) | **PASS** | Line `245`: `if open_ts + tf_sec > now_ts + 1e-6: continue` with `86400` for D1 (line `433`), `14400` for H4 (line `434`), and `3600` for H1 (line `435`). |
| Consistent UTC conversion | **PASS** | Lines `229–240`: Epoch numbers and ISO-8601 strings (`Z` or explicit offsets) are normalized to `timezone.utc`. |
| Forming and future candle rejection | **PASS** | Independently tested: forming candle (`16:00:00Z` at `now=16:30:00Z`) and future candle (`18:00:00Z`) are excluded; exact boundary candle (`15:30:00Z` + `3600s` == `16:30:00Z`) is retained. |
| Invalid OHLC, malformed timestamps, duplicate bars | **PASS** | Line `225`: `raw_t = c.get("timestamp") if c.get("timestamp") is not None else c.get("time")` prioritizes raw ISO `timestamp` over `ExnessTraderAPIClient`'s fallback integer `time` (`trader_api_adapter.py:1578`), rejecting malformed timestamps (`A_EXNESS_MALFORMED_REJECTED: True`). Lines `262–265` reject non-finite/non-positive prices, `bh < max(bo, bc)`, `bl > min(bo, bc)`, `ah < max(ao, ac)`, `al > min(ao, ac)`, and inverted spread (`bc > ac + 1e-6`). Duplicate timestamps are deduplicated via `by_ts[open_ts]` and sorted ascending (line `277`). |
| Missing history fails safely (`NO_TRADE`) | **PASS** | Lines `437–439`: `if len(d1_closed) < 65 or len(h4_closed) < 40 or len(h1_closed) < 260: return []`. Note: `ExnessTraderAPIClient.get_historical_candles` (`trader_api_adapter.py:1546`) clamps `safe_count = min(count, 500)`, so requesting `count=530` on H1 returns up to `500` bars (`499` closed), which safely exceeds the `260` minimum (`EMA200 + 60`). |

---

### B. Persistent Deduplication (`load_a2_leg_state` / `save_a2_leg_state`) — `FAIL`

**Inspected Code:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` lines `279–330` and `422–460`.

| Sub-Check | Classification | Evidence & Line Numbers |
|---|---|---|
| Account-scoped state file, `fcntl.flock`, atomic `os.replace` | **PASS** | Lines `280–330`: State path `/opt/tauric-platform-staging/backend/data/a2_leg_state_{safe_id}.json` is scoped by `account_id`, locked with `LOCK_SH`/`LOCK_EX`, flushed + `os.fsync()`, and atomically replaced via `os.replace(tmp_path, path)`. Tested with 4-process `multiprocessing.Pool` (20 concurrent writes/reads): `B_MULTIPROCESS_CONCURRENCY_OK: True`. |
| Corrupt state file fails closed (`NO_TRADE`) | **PASS** | Lines `296–300` & `422–425`: Invalid JSON, missing `last_leg_id`, or mismatched `account_id` returns `(False, None)` and halts scanning (`return []`). |
| Repeated leg vs new leg across process restart | **PASS** | Independently tested across separate `OperatorExperimentSupervisor` instances: first signal on leg `BUY:1.07500:1.08500` emits `1` signal; second supervisor instance on same leg emits `0` signals; third supervisor instance on new leg `BUY:1.07900:1.08900` emits `1` signal (`B_LEG_LIFECYCLE: 1 0 1`). |
| **Defect B-1: Premature leg state persistence before quote/sizing/preflight/fill** | **FAIL** | In `scan_market_opportunities()` (lines `449–451`), `self.save_a2_leg_state(account_id, a2.last_leg_id)` is executed **inside `scan_market_opportunities()` before** `adapter.get_live_quote("EURUSD")` (line `453`), before `compute_risk_lots(...)` (line `458`), before `SharedCentralRiskManager.preflight_check(...)` (`run()` line `506`), and before `adapter.place_market_order(...)` (line `514`). If `get_live_quote` raises a transient network timeout, or if `compute_risk_lots` returns `None` due to a momentary spread spike, or if `preflight_check` temporarily blocks the order, the structural leg is permanently burned in `a2_leg_state_{account_id}.json` even though no order was ever placed. Conversely, if the state file is deleted on disk while an open position from that leg exists, `load_a2_leg_state()` returns `(True, None)` on line `290` without cross-checking open positions or `TradeMemoryService` history. |

---

### C. Post-Fill Protection (`process_broker_fill_response`) — `FAIL`

**Inspected Code:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` lines `331–406`, `514–523`, `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py` lines `180–196`, and `/opt/tauric-platform-staging/backend/app/services/exness/trader_api_adapter.py` lines `1819–1842`.

| Sub-Check | Classification | Evidence & Line Numbers |
|---|---|---|
| **Defect C-1: `TradeMemoryService.record_trade()` crashes with `ValueError` on every real fill because `order_id` is omitted** | **FAIL** | `TradeMemoryService.record_trade()` (`trade_memory_service.py` lines `191–195`) enforces:<br>`if exec_type == "ACTUAL_DEMO":`<br>`    bt = str(trade_data.get("broker_ticket") or "").strip()`<br>`    oid = str(trade_data.get("order_id") or "").strip()`<br>`    if not bt or not oid:`<br>`        raise ValueError("ACTUAL_DEMO Trade Memory record requires non-empty broker_ticket and order_id.")`<br>In `run_operator_experiment_runner.py` lines `377–397`, `process_broker_fill_response()` passes `"broker_ticket": tkt` and `"execution_type": "ACTUAL_DEMO"`, **but completely omits `"order_id"`**! When tested against the real (unmocked) `TradeMemoryService.record_trade()`, `process_broker_fill_response()` raises `ValueError: ACTUAL_DEMO Trade Memory record requires non-empty broker_ticket and order_id.` Command 13's test script missed this because it mocked `TradeMemoryService.record_trade` with `patch.object(runner.TradeMemoryService, "record_trade", side_effect=_mock_record)`. |
| **Defect C-2: Exception in `TradeMemoryService.record_trade()` does NOT fail closed (`new_entries_disabled` remains `False`)** | **FAIL** | In `process_broker_fill_response()` (lines `373–397`), `self._reconciled_fill_tickets.add(tkt)` (line `373`) and `self.post_fill_guard.evaluate_fill(...)` (line `375`) run before `TradeMemoryService.record_trade(...)` (line `377`), and there is **no `try/except`** around `TradeMemoryService.record_trade(...)`. When `record_trade()` raises `ValueError` (or any SQLite error) on a normal within-budget fill (`actual_risk_usd <= 10.0`), the exception escapes to `run()`'s generic `except Exception as loop_err:` (line `522`), leaving `self.post_fill_guard.new_entries_disabled == False` and `self.trades_opened_count` unincremented after a live broker fill! |
| **Defect C-3: Schema mismatch between `ExnessTraderAPIClient.submit_order()` response and `process_broker_fill_response()`** | **FAIL** | For the operator DEMO account (`17000694512` on `dx.2.trial.raw`, `ExnessTerminalBrokerAdapter`), `place_market_order(..., dry_run=False)` delegates to `ExnessTraderAPIClient.submit_order()` (`trader_api_adapter.py:1830–1836`), which returns:<br>`{"status": "FILLED", "operation_id": op_id, "ack": data, "operation": op_status, "payload": payload}` (or for `ExnessMT5BrokerAdapter` line `333`: `{"status": "FILLED", "http_status": 200, "response": resp.json()}`).<br>However, `process_broker_fill_response()` (lines `350, 364–365`) looks only at top-level `order_res.get("ticket") or order_res.get("position_id") or order_res.get("deal_id")` and top-level `order_res.get("fill_price") or order_res.get("open_price") or order_res.get("price")`. It never inspects `order_res.get("operation")`, `order_res.get("ack")`, `order_res.get("response")`, or `operation_id`, nor does it reconcile the newly opened position via `adapter.get_open_positions()`. Consequently, any real Exness fill response would fail ticket/price extraction at line `351` or `369`. |
| Partial-fill VWAP reconciliation & idempotency (`_reconciled_fill_tickets`) | **PASS** | Lines `355–363` & `373`: Duplicate ticket IDs are ignored (`DUPLICATE_FILL_IGNORED`), and multi-deal `fills` lists are reconciled via `reconcile_partial_fills()` before risk calculation. |
| `PostFillRiskBreachGuard` disables new entries without force-closing open position | **PASS** | Lines `374–375` & `shared_risk_manager.py:424–435`: When `actual_risk_usd > 10.0`, `self.post_fill_guard.new_entries_disabled = True` is set without calling any position-close method. |

---

### D. Execution Safety — `PASS`

| Safety Invariant | Classification | Evidence |
|---|---|---|
| `experiment_lock.json` remains `authorized: false` | **PASS** | `/opt/tauric-platform-staging/backend/data/experiment_lock.json` verified: `"authorized": false`. |
| `REAL_TRADING_PERMANENTLY_LOCKED = True` | **PASS** | `run_operator_experiment_runner.py` line `46` (`REAL_TRADING_PERMANENTLY_LOCKED = True`) and `shared_risk_manager.py` line `22` (`REAL_TRADING_PERMANENTLY_LOCKED: bool = True`). |
| Real account `16000629657` permanently blocked | **PASS** | `shared_risk_manager.py` lines `23` & `162`: `BLOCKED_REAL_ACCOUNTS = {"16000629657"}` hard-blocks `16000629657`. |
| Customer account `17000109575` untouched / read-only | **PASS** | Verified in `exness_demo_connections`: `account_login='17000109575'`, `updated_at='2026-11-10T02:05:08Z'` (completely untouched). |
| Strategy Centre `LT_STRUCTURE_EURUSD_A2` non-executable | **PASS** | `get_strategy_for_customer("LT_STRUCTURE_EURUSD_A2", ...)` returns `validation_status: "INCONCLUSIVE_STATISTICAL_CONFIDENCE"`, `execution_eligible: False`. |
| No broker orders, no paper trading, no service restarts, no production changes | **PASS** | Zero orders placed, runner was not executed, PM2 processes were not restarted during Command 13 or Command 14, and production `/opt/tauric-platform` was untouched. |

---

### E. Test Quality Audit — `FAIL`

**Inspected Artifact:** `/opt/bitdex-research-v2/docs/cmd13_remediation_verification.json` and the Command 13 test harness.

| Test Dimension | Classification | Finding |
|---|---|---|
| Mocking hid real `TradeMemoryService.record_trade` contract failure | **FAIL** | Command 13's verification script mocked `TradeMemoryService.record_trade` (`with patch.object(runner.TradeMemoryService, "record_trade", side_effect=_mock_record)`), which hid the mandatory `order_id` check in `TradeMemoryService.record_trade()` (`trade_memory_service.py:193–195`). |
| Broker adapter payload realism | **FAIL** | Command 13 tested synthetic flat dicts (`{"status": "FILLED", "ticket": "TKT-1001", "fill_price": ...}`) rather than the actual nested dict returned by `ExnessTraderAPIClient.submit_order()` (`{"status": "FILLED", "operation_id": ..., "ack": ..., "operation": ...}`) or `ExnessMT5BrokerAdapter.place_market_order()` (`{"status": "FILLED", "http_status": 200, "response": ...}`). |
| Concurrency & repeated-leg lifecycle coverage | **PASS (Verified in Cmd 14)** | Command 13 only tested single-process save/load; Command 14 independently executed a 4-process `multiprocessing.Pool` lock test and a full 3-step leg lifecycle test (`first=1, repeat_after_restart=0, new_leg=1`). |

---

## 3. Summary of Required Remediations Before Execution Readiness Can Be Re-Audited

1. **Fix `TradeMemoryService.record_trade()` payload & fail-closed exception handling in `process_broker_fill_response()` (`run_operator_experiment_runner.py:338–406`):**
   - Pass `"order_id": str(order_res.get("order_id") or order_res.get("operation_id") or tkt)` and `"deal_id": str(order_res.get("deal_id") or tkt)` so `TradeMemoryService.record_trade()`'s mandatory `ACTUAL_DEMO` check (`broker_ticket` and `order_id`) succeeds against the real SQLite service without mocking.
   - Wrap `TradeMemoryService.record_trade(...)` in a `try/except Exception` block that sets `self.post_fill_guard.new_entries_disabled = True` and returns `"status": "CRITICAL_TRADE_MEMORY_RECORD_FAILURE"` if trade persistence fails after a fill.
2. **Align `process_broker_fill_response()` with actual Exness adapter return schemas (`trader_api_adapter.py:1830–1836` & `mt5_broker_adapter.py:333`):**
   - Extract ticket/order_id/fill_price/filled_volume from nested `order_res.get("operation")`, `order_res.get("ack")`, and `order_res.get("response")` payloads (or fallback position reconciliation) in addition to top-level keys.
3. **Persist `save_a2_leg_state()` only after preflight/order submission (`run_operator_experiment_runner.py:449–451` & `513–521`):**
   - Do not burn `last_leg_id` inside `scan_market_opportunities()` before `get_live_quote()`, `compute_risk_lots()`, and `SharedCentralRiskManager.preflight_check()`. Persist `save_a2_leg_state()` when the signal is actually acted upon (or cross-check open positions / `TradeMemoryService` if state file is missing).

---

## 4. Final Audit Conclusion

`COMMAND 13 INDEPENDENT AUDIT FAILED — EXECUTION DISABLED`
