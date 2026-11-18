# BITDEX COMMAND 17 — FIVE CRITICAL EXECUTION-RELIABILITY FIXES

**Remediation Date:** 2026-11-18 UTC  
**Environment:** Staging (`/opt/tauric-platform-staging/backend` & `/opt/bitdex-research-v2`)  
**Final Verdict:** `COMMAND 17 PASSED — ALL FIVE EXECUTION-RELIABILITY FIXES VERIFIED — EXECUTION DISABLED`

---

## 1. Original and Final SHA256 Hashes, Modified Files & Backups

| File | Role | SHA256 Checksum |
|---|---|---|
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd17_20261118` | Pre-Command 17 Timestamped Backup (Original) | `c9a95123ab27797acbeb501dd6cbbe9242465dbe4547a9d7f99ace6b31049738` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` | Remediated Staging Runner (Final) | `a71547c932ed231a189453737457091e597e6924d84bf3730e8a3020fd72bbdd` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd15_20261118` | Command 15 Backup (Preserved) | `68bbb9386e81599449847fe4ec1efba9fe4bad1418a36f5e99536fd0d9bce3f9` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd13_20261117` | Command 13 Backup (Preserved) | `f4fb399e2d170f119723c74c5d679849feab3b4947498eb46b343f23e1467d66` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd11_20261117` | Command 11 Backup (Preserved) | `34c1e7eda926e0e4dfce3672b8d9e548339ecb823fef40886fa48a1b5f04a37a` |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py` | Frozen Strategy A2 v2.0 (Unmodified) | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py` | Frozen Strategy A2 v2.0 Archive (Unmodified) | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` |
| `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py` | `TradeMemoryService` (Unmodified) | `61290279942ea8c878dcbf24d1b5a0c306da4e51b289f39404e67bc3a9ac7366` |
| `/opt/tauric-platform-staging/backend/app/services/brokers/shared_risk_manager.py` | `SharedCentralRiskManager` (Unmodified) | `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5` |
| `/opt/tauric-platform-staging/backend/app/services/brokers/execution_router.py` | `CentralExecutionRouter` (Unmodified) | `e199dc7c590ce79874b34ebf14fa2b6948fba866b19b4b8dbbddaa8a904f6016` |
| `/opt/bitdex-research-v2/tests_cmd17_verification.py` | Command 17 Offline Verification Suite | Created |
| `/opt/bitdex-research-v2/docs/cmd17_verification.json` | Command 17 Machine-Readable Verification JSON | Created |

---

## 2. Detailed Remediation of All Five Command 16 Findings

### Fix 1 — Persist `order_submitted = True` Atomically BEFORE Broker Submission (`Defect D-AUDIT-1`)
- Implemented `mark_a2_leg_order_submitting(account_id, leg_id, reservation_id, idempotency_key)` in `OperatorExperimentSupervisor`.
- In `execute_signal_Cycle()`, after `SharedCentralRiskManager.preflight_check()` passes and **before** `await adapter.place_market_order(...)` is called, `mark_a2_leg_order_submitting()` acquires `fcntl.flock(LOCK_EX)` on `a2_leg_state_{safe_id}.lock` and atomically writes `pending_reservation.signal_meta.order_submitted = True` (along with `submitted_at_utc` and `idempotency_key`) via `os.replace()` + `os.fsync()`.
- If persisting `order_submitted = True` fails on disk, order submission is immediately aborted (`PRE_SUBMISSION_STATE_PERSIST_FAILED`) and new entries are disabled.
- If the process crashes during or immediately after `place_market_order()`, `reconcile_or_initialize_a2_leg_state()` detects `order_submitted == True` on restart and fails closed (`PENDING_SUBMITTED_ORDER_UNRECONCILABLE`), preventing any duplicate submission.

### Fix 2 — Read-Only Exness Snapshot, Order-History & Deal-History Reconciliation (`Defect D-AUDIT-2`)
- Implemented `_extract_eurusd_broker_history(raw_orders, raw_deals)` and integrated `adapter.get_open_positions()`, `adapter.get_order_history(limit=100)`, and `adapter.get_trade_history(limit=100)` into `reconcile_or_initialize_a2_leg_state()`.
- During restart recovery (whether the state file is `OK`, `PENDING`, or `MISSING`), the reconciler cross-references all open `EURUSD` positions, `EURUSD` broker orders (excluding `sltp` child orders), and `EURUSD` broker deals against `TradeMemoryService` and `a2_deal_ledger`.
- If a position opened and already closed via SL/TP during a crash window (so `get_open_positions()` is empty, but `get_order_history()` / `get_trade_history()` contains an untracked `EURUSD` order or deal), `reconcile_or_initialize_a2_leg_state()` fails closed (`PENDING_RESERVATION_WITH_UNTRACKED_BROKER_HISTORY` or `MISSING_STATE_UNRECONCILABLE_BROKER_HISTORY`), disables new entries, and records a critical incident.

### Fix 3 — Reconcile Actual Exness Terminal Operation Responses Against Genuine Broker Execution Records (`Defect E-AUDIT-1`)
- Implemented `reconcile_exness_terminal_operation(adapter, raw_res, sig, account_id)` in `OperatorExperimentSupervisor`.
- When `ExnessTraderAPIClient.submit_order()` returns its actual operation-only structure (`{'status': 'FILLED', 'operation_id': '...', 'ack': {...}, 'operation': {'operation_id': '...', 'status': 'confirmed', ...}, 'payload': {...}}`), `reconcile_exness_terminal_operation()` queries read-only broker interfaces (`get_trading_snapshot(force_refresh=True)`, `get_open_positions()`, `get_order_history()`, `get_trade_history()`) to match the genuine `position_id` / `broker_ticket`, genuine `order_id` (excluding `sltp` protective orders and never using `operation_id`), genuine `deal_id` / `deals` list, `fill_price`, and `filled_volume`.
- If complete reconciliation is impossible (e.g., no matching position/order or multiple ambiguous untracked positions), no identifier is ever fabricated, and `normalize_exness_order_response()` fails closed as `AMBIGUOUS` (`MISSING_BROKER_TICKET` / `MISSING_GENUINE_ORDER_ID`), locking the state and disabling new entries.

### Fix 4 — Persist Individual Deal IDs Independently (`a2_deal_ledger`) for Cross-Process & Cross-Restart Idempotency (`Defect TM-AUDIT-1`)
- Created the SQLite table `a2_deal_ledger` (`PRIMARY KEY (account_id, deal_id)`) alongside `trade_memory`, and also persisted `reconciled_deal_ids` in `a2_leg_state_{account_id}.json`.
- For every confirmed single-deal or multi-deal fill, each individual `deal_id` is recorded as its own row in `a2_deal_ledger` with its exact `deal_id`, `broker_ticket`, `order_id`, `leg_id`, `volume_lots`, and `fill_price`.
- Before processing any fill in `process_broker_fill_response()`, incoming `deal_ids` are checked against:
  1. In-memory `self._reconciled_deal_ids`
  2. Persisted `reconciled_deal_ids` in `a2_leg_state_{account_id}.json`
  3. SQLite `a2_deal_ledger WHERE account_id = ? AND deal_id IN (...)`
  4. SQLite `trade_memory` (`deal_id` split on commas and `signal_reason_json.deal_ids`)
- Replaying an individual deal from a multi-deal partial fill after a process restart is deterministically blocked (`DUPLICATE_FILL_IGNORED`).

### Fix 5 — Persist Post-Fill Safety Incidents & Entry-Disable State Durably Across Restart (`Defect PF-AUDIT-1`)
- Updated `record_critical_incident()` and `_persist_disable_in_state_file()` so every post-fill risk breach (`within_budget == False`), post-fill guard exception, state-persistence failure, or `TradeMemoryService` failure writes both:
  1. An append-only JSONL record in `a2_post_fill_incidents_{account_id}.jsonl` (`os.fsync()`), and
  2. `"new_entries_disabled": True` and `"state": "HALTED_POST_FILL_BREACH_OR_INCIDENT"` inside `a2_leg_state_{account_id}.json`.
- On startup / before every scan (`reconcile_or_initialize_a2_leg_state()` and `load_a2_leg_state()`), the runner checks:
  1. `_has_durable_incidents_on_disk(account_id)` (`a2_post_fill_incidents_{account_id}.jsonl`)
  2. `doc.get("new_entries_disabled") is True` or `doc.get("state") in ("AMBIGUOUS_LOCKED", "HALTED_POST_FILL_BREACH_OR_INCIDENT")`
  3. Any record in `TradeMemoryService` with `"post_fill_within_budget": False`
- If any of the three is present, `self.post_fill_guard.new_entries_disabled = True` is restored immediately before any strategy evaluation can occur—even if the state file was deleted on disk (`F5_3_durable_incident_jsonl_blocks_entries_even_if_state_deleted: True`).

---

## 3. Verification Test Results (`cmd17_verification.json` & `cmd15_fill_handling_verification.json`)

Both `/opt/bitdex-research-v2/tests_cmd17_verification.py` (19/19 checks) and `/opt/bitdex-research-v2/tests_cmd15_verification.py` (37/37 checks) passed 100%:

| Test Group | Test ID | Result |
|---|---|---|
| **Fix 1: Crash Safety** | `F1_1_pre_submission_rejections_do_not_consume_leg` | `PASS` |
| **Fix 1: Crash Safety** | `F1_2_order_submitted_true_on_disk_before_broker_call` | `PASS` |
| **Fix 1: Crash Safety** | `F1_3_crash_during_submission_blocks_duplicate_on_restart` | `PASS` |
| **Fix 2: History Reconcile** | `F2_1_closed_position_in_deal_history_detected_on_restart` | `PASS` |
| **Fix 2: History Reconcile** | `F2_2_missing_state_with_untracked_broker_history_fails_closed` | `PASS` |
| **Fix 3: Terminal Reconcile** | `F3_1_unreconciled_operation_response_never_fabricated` | `PASS` |
| **Fix 3: Terminal Reconcile** | `F3_2_actual_terminal_operation_reconciled_with_genuine_ids` | `PASS` |
| **Fix 3: Terminal Reconcile** | `F3_3_restart_with_reconciled_open_position_preserves_dedup` | `PASS` |
| **Fix 4: Deal Ledger** | `F4_1_individual_deals_persisted_in_ledger` | `PASS` |
| **Fix 4: Deal Ledger** | `F4_2_cross_restart_subdeal_replay_blocked` | `PASS` |
| **Fix 5: Durable Lock** | `F5_1_post_fill_risk_breach_persists_across_restart` | `PASS` |
| **Fix 5: Durable Lock** | `F5_2_tradememory_exception_lock_persists_across_restart` | `PASS` |
| **Fix 5: Durable Lock** | `F5_3_durable_incident_jsonl_blocks_entries_even_if_state_deleted` | `PASS` |
| **Regression & Safety** | `R1_multiprocess_concurrent_reservation_single_winner` | `PASS` |
| **Regression & Safety** | `R2_frozen_a2_sha256_unchanged` | `PASS` |
| **Regression & Safety** | `S1_experiment_lock_authorized_false` | `PASS` |
| **Regression & Safety** | `S2_real_trading_permanently_locked` | `PASS` |
| **Regression & Safety** | `S3_real_account_16000629657_blocked` | `PASS` |
| **Regression & Safety** | `S4_a2_execution_eligible_false` | `PASS` |

---

## 4. Unresolved Issues

- **None.** All five findings from Command 16 (`D-AUDIT-1`, `D-AUDIT-2`, `E-AUDIT-1`, `TM-AUDIT-1`, `PF-AUDIT-1`) are resolved and verified.
