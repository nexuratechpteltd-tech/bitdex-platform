# BITDEX COMMAND 15 — CRITICAL FILL-HANDLING & DEDUPLICATION REMEDIATION

**Remediation Date:** 2026-11-18 UTC  
**Environment:** Staging (`/opt/tauric-platform-staging/backend` & `/opt/bitdex-research-v2`)  
**Final Verdict:** `COMMAND 15 PASSED — FILL HANDLING VERIFIED — EXECUTION DISABLED`

---

## 1. Original and Final SHA256 Hashes, Modified Files & Backups

| File | Role | SHA256 Checksum |
|---|---|---|
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd15_20261118` | Pre-Command 15 Timestamped Backup (Original) | `68bbb9386e81599449847fe4ec1efba9fe4bad1418a36f5e99536fd0d9bce3f9` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` | Remediated Staging Runner (Final) | `c9a95123ab27797acbeb501dd6cbbe9242465dbe4547a9d7f99ace6b31049738` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd13_20261117` | Command 13 Backup (Preserved) | `f4fb399e2d170f119723c74c5d679849feab3b4947498eb46b343f23e1467d66` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd11_20261117` | Command 11 Backup (Preserved) | `34c1e7eda926e0e4dfce3672b8d9e548339ecb823fef40886fa48a1b5f04a37a` |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py` | Frozen Strategy A2 v2.0 (Unmodified) | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py` | Frozen Strategy A2 v2.0 Archive (Unmodified) | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` |
| `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py` | TradeMemoryService (Unmodified) | `61290279942ea8c878dcbf24d1b5a0c306da4e51b289f39404e67bc3a9ac7366` |
| `/opt/tauric-platform-staging/backend/app/services/brokers/shared_risk_manager.py` | SharedCentralRiskManager (Unmodified) | `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5` |
| `/opt/tauric-platform-staging/backend/app/services/brokers/execution_router.py` | CentralExecutionRouter (Unmodified) | `e199dc7c590ce79874b34ebf14fa2b6948fba866b19b4b8dbbddaa8a904f6016` |
| `/opt/bitdex-research-v2/tests_cmd15_verification.py` | Command 15 Offline Unit & Real-Service Test Suite | Created |
| `/opt/bitdex-research-v2/docs/cmd15_fill_handling_verification.json` | Machine-Readable Test Results | Created |

---

## 2. Remediation B-1 — Transactional Deduplication Lifecycle & Missing-State Reconciliation

Implemented in `OperatorExperimentSupervisor` (`run_operator_experiment_runner.py` lines `281–601` and `966–1088`):

### Conceptual States & Transitions
- `AVAILABLE`: No pending reservation; ready to evaluate new structural legs.
- `PENDING`: Atomically reserved via `reserve_a2_leg_pending(account_id, leg_id, signal_meta)` using a dedicated lock file (`a2_leg_state_{safe_id}.lock` with `fcntl.flock(LOCK_EX)`) and atomic `os.replace()` + `os.fsync()`. Prevents concurrent workers from submitting duplicate orders on the same structural leg.
- `REJECTED_OR_EXPIRED`: Transitioned via `release_a2_leg_reservation(account_id, leg_id, reason, reservation_id)` when a quote fetch fails (`QUOTE_FAILURE`), spread exceeds threshold (`SPREAD_REJECTED`), risk lot calculation returns `None` (`SIZING_REJECTED`), `SharedCentralRiskManager.preflight_check()` rejects (`PREFLIGHT_REJECTED`), or the broker explicitly rejects the order before fill (`ORDER_REJECTED`). The leg is **not** added to `confirmed_legs` or `last_confirmed_leg_id`, so it remains eligible on subsequent cycles.
- `CONFIRMED_FILLED`: Transitioned durably via `confirm_a2_leg_fill(account_id, leg_id, fill_meta)` **only after** a broker fill is confirmed. Records `last_confirmed_leg_id = leg_id` and stores the full broker identifier set (`broker_ticket`, `position_id`, `order_id`, `deal_id`, `deal_ids`, `operation_id`, `fill_price`, `filled_volume`) under `confirmed_legs[leg_id]`.
- `AMBIGUOUS_LOCKED`: Transitioned via `mark_a2_leg_ambiguous()` whenever a broker response is `ACCEPTED_NOT_FILLED`, `PENDING_OPERATION`, `AMBIGUOUS`, `MALFORMED_OR_CONTRADICTORY`, or when `place_market_order()` raises an exception. Prevents any automatic retry and disables new entries.

### Missing, Corrupt, or Pending State Reconciliation (`reconcile_or_initialize_a2_leg_state`)
- **Corrupt state file:** Immediately fails closed (`CORRUPT_STATE_FAIL_CLOSED`), sets `self.post_fill_guard.new_entries_disabled = True`, and writes a durable incident to `a2_post_fill_incidents_{account_id}.jsonl`.
- **Missing state file:** Never silently assumes a clean deduplication history. Queries read-only `adapter.get_open_positions()` and `TradeMemoryService.get_trade_history(account_id, track="LT_STRUCTURE_EURUSD_A2", execution_type="ACTUAL_DEMO")`.
  - Reconstructs all historical `leg_id` entries from `TradeMemoryService` (`signal_reason_json.leg_id`).
  - If any open `EURUSD` position exists on the broker snapshot whose ticket is missing from `TradeMemoryService` or lacks a `leg_id`, reconciliation fails closed (`MISSING_STATE_UNRECONCILABLE_OPEN_POSITION`), disables new entries, and records a critical incident.
- **Pending state on restart:** Checks `TradeMemoryService` and open broker positions before allowing another attempt. If an untracked open `EURUSD` position exists or `order_submitted=True` was recorded without a reconcilable fill, fails closed and disables new entries.

---

## 3. Remediation C-3 — Explicit Exness Response Normalisation Layer

Implemented in `OperatorExperimentSupervisor.normalize_exness_order_response()` (`run_operator_experiment_runner.py` lines `603–892`):

### Supported Schemas & Field Mappings
1. **`ExnessTraderAPIClient.submit_order()` (`EXNESS_TERMINAL_V1`):**
   - Outer keys: `status`, `operation_id`, `ack`, `operation`, `payload`.
   - `operation_id` is extracted from `raw_res["operation_id"]` or `ack["operation_id"]` and kept strictly distinct from `broker_ticket` and `order_id`.
   - Distinguishes `operation.status == "accepted"` (`ACCEPTED_NOT_FILLED`), `"pending"` / `"processing"` (`PENDING_OPERATION`), `"rejected"` / `"failed"` (`REJECTED`), and `"confirmed"` / `"filled"` / `"executed"` with `status == "FILLED"`.
   - Extracts `position_id` / `broker_ticket` from `operation["position_id"]` or `operation["ticket"]` (or verified deal records), `order_id` from `operation["order_id"]` or `operation["order"]`, `deal_id` / `deals` from `operation["deal_id"]` or `operation["deals"]` / `operation["fills"]`, `fill_price`, `filled_volume`, `instrument`, `side`, and timestamp.
2. **`ExnessMT5BrokerAdapter.place_market_order()` (`EXNESS_MT5_GATEWAY`):**
   - Outer keys: `status`, `http_status`, `response`.
   - Validates `http_status == 200` and `status == "FILLED"` without contradiction in `response`.
   - Extracts `broker_ticket` (`response["ticket"]` / `response["position_id"]`), `order_id` (`response["order_id"]`), `deal_id` (`response["deal_id"]` / `response["deals"]`), `fill_price`, `filled_volume`, `symbol` (normalising `EURUSDm`/`EURUSDr` to `EURUSD`), and `time_utc`.

### Strict Validation Rules
- Rejects any response where `operation_id` is used as `broker_ticket` or `order_id` (`OPERATION_ID_MISUSED_AS_TICKET_OR_ORDER_ID`).
- Rejects missing `broker_ticket` (`MISSING_BROKER_TICKET`), missing genuine `order_id` (`MISSING_GENUINE_ORDER_ID`), or missing `fill_price` / `filled_volume` (`MISSING_CONFIRMED_FILL_PRICE_OR_VOLUME`) as `AMBIGUOUS`, which disables new entries and raises a critical incident.
- Rejects non-`EURUSD` instruments (`WRONG_INSTRUMENT`), account mismatches (`ACCOUNT_OWNERSHIP_MISMATCH`), non-`ACTUAL_DEMO` execution types, and contradictory status combinations (`CONTRADICTORY_FILLED_AND_REJECTED`).

---

## 4. Remediation C-1 — TradeMemoryService Identifier Mapping & Real-Service Integration

Implemented in `process_broker_fill_response()` (`run_operator_experiment_runner.py` lines `894–1128`):
- Supplies genuine, distinct identifiers to `TradeMemoryService.record_trade()`:
  - `"trade_id": f"OPDEMO-{tkt}"`
  - `"broker_ticket": tkt` (genuine position ticket)
  - `"order_id": ord_id` (genuine broker order ID)
  - `"deal_id": deal_id` (genuine deal ID or comma-joined deduplicated deal IDs for multi-deal fills)
- Enforces idempotency both in-memory (`_reconciled_fill_tickets`, `_reconciled_deal_ids`) and against the SQLite `trade_memory` table (`WHERE account_id = ? AND (broker_ticket = ? OR (deal_id != '' AND deal_id = ?))`), preventing duplicate trade-memory rows even across process restarts.

---

## 5. Remediation C-2 & Section 7 — Post-Fill Fail-Closed Handling & Partial-Fill Reconciliation

- **Partial-Fill Reconciliation:** Multi-deal fills (`deals` / `fills`) are validated (every deal must have a genuine `deal_id`, matching `position_id`, positive finite `price` and `volume`), deduplicated by `deal_ticket` via `reconcile_partial_fills()`, and aggregated into VWAP `fill_price` and `filled_volume`. Requested volume is never substituted for filled volume; when `filled_volume < requested_volume`, `is_partial_fill = True` and `status = "PARTIAL_OPEN"` are recorded.
- **Post-Fill Fail-Closed Exception Handling:**
  - `PostFillRiskBreachGuard.evaluate_fill()`, `confirm_a2_leg_fill()`, and `TradeMemoryService.record_trade()` are each wrapped in dedicated `try/except` blocks after fill recognition.
  - If any of the three raises an exception (or returns failure), `self.post_fill_guard.new_entries_disabled = True` is set immediately, `record_critical_incident()` writes a durable JSONL incident containing the full `fill_recovery_context` (`broker_ticket`, `order_id`, `deal_ids`, `operation_id`, `fill_price`, `filled_volume`, `sl_price`, `tp_price`, `actual_risk_usd`), and no duplicate or automatic close order is ever submitted.

---

## 6. Test Execution Command & Complete Results

**Command Executed:**
```bash
/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/bitdex-research-v2/tests_cmd15_verification.py
```

**Summary of 37 Mandatory Verification Checks (All `True`):**
- **Deduplication (`D1`–`D11`):**
  - `D1_quote_failure_does_not_consume_leg`: `true`
  - `D2_spread_rejection_does_not_consume_leg`: `true`
  - `D3_sizing_failure_does_not_consume_leg`: `true`
  - `D4_preflight_rejection_does_not_consume_leg`: `true`
  - `D5_concurrent_reservations_single_winner`: `true` (12 concurrent requests across 6 processes -> exactly 1 winner)
  - `D6_confirmed_fill_consumes_leg_durably`: `true`
  - `D7_restart_preserves_confirmed_state`: `true`
  - `D8_missing_state_reconciles_from_tradememory_without_reset`: `true`
  - `D9_incomplete_reconciliation_disables_new_entries`: `true`
  - `D10_corrupt_state_fails_closed`: `true`
  - `D11_ambiguous_fill_prevents_retry`: `true`
- **Exness Response Parsing (`P1`–`P14`):**
  - `P1_nested_submit_order_confirmed_fill`: `true`
  - `P2_nested_mt5_place_market_order_confirmed_fill`: `true`
  - `P3_accepted_not_yet_filled`: `true`
  - `P4_pending_operation`: `true`
  - `P5_rejected_response`: `true`
  - `P6_partial_fill_recognized`: `true`
  - `P7_multiple_deals_vwap_and_dedup`: `true`
  - `P8_missing_ticket_rejected_as_ambiguous`: `true`
  - `P9_missing_genuine_order_id_rejected_as_ambiguous`: `true`
  - `P10_missing_fill_price_rejected_as_ambiguous`: `true`
  - `P11_wrong_instrument_rejected`: `true`
  - `P12_wrong_account_rejected`: `true`
  - `P13_malformed_nested_response_rejected`: `true`
  - `P14_contradnictory_response_fields_rejected`: `true`
- **Real TradeMemoryService Integration (`TM1`–`TM4`):**
  - `TM1_real_service_accepts_genuine_order_id`: `true`
  - `TM2_duplicate_broker_ticket_idempotent`: `true`
  - `TM3_duplicate_deal_id_idempotent`: `true`
  - `TM4_missing_order_id_fails_safely_no_fake_ids`: `true`
- **Post-Fill Fail-Closed Handling (`PF1`–`PF5`):**
  - `PF1_tradememory_exception_disables_entries_and_retains_ids`: `true`
  - `PF2_state_and_tm_exceptions_fail_closed_with_incident`: `true`
  - `PF3_guard_exception_fails_closed`: `true`
  - `PF4_partial_fill_incomplete_reconciliation_disables_entries`: `true`
  - `PF5_partial_fill_uses_filled_volume_and_trips_guard_on_breach`: `true`
- **Regression & Safety (`R1`–`R3` & `safety`):**
  - `R1_frozen_a2_sha256_unchanged`: `true` (`231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032`)
  - `R2_closed_candle_filtering_enforced`: `true`
  - `R3_tenant_account_isolation`: `true`
  - `experiment_lock_authorized_false`: `true`
  - `real_trading_permanently_locked`: `true`
  - `real_account_16000629657_blocked`: `true`
  - `a2_execution_eligible_false`: `true`

---

## 7. Lock, Account & Operational Safety Confirmation

- `experiment_lock.json`: `authorized: false`
- `REAL_TRADING_PERMANENTLY_LOCKED`: `True`
- Real account `16000629657`: Permanently blocked
- Customer account `17000109575`: Read-only / untouched (`updated_at: 2026-11-10T02:05:08Z`)
- Strategy `LT_STRUCTURE_EURUSD_A2`: `execution_eligible = False`
- Broker calls / Broker orders / Paper trading: **Zero**
- PM2 / Service restarts / Production changes: **Zero**
- Outstanding issues: **None**
- Rollback status: **Not required (all 37 mandatory verification checks passed)**

---

## 8. Final Verdict

`COMMAND 15 PASSED — FILL HANDLING VERIFIED — EXECUTION DISABLED`
