# BITDEX COMMAND 19 — COMMAND 18 FAILURE REMEDIATION

**Remediation Date:** 2026-11-18 UTC  
**Repository:** `nexuratechpteltd-tech/bitdex-platform`  
**Staging Backend:** `/opt/tauric-platform-staging/backend`  
**Research Directory:** `/opt/bitdex-research-v2/`  
**Final Verdict:** `COMMAND 19 PASSED — ALL FIVE COMMAND 18 FINDINGS REMEDIATED`

---

## 1. Before-and-After SHA256 Checksums, Modified Files & Backups

| File Path | Role | SHA256 Checksum |
|---|---|---|
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd19_20261118` | Pre-Command 19 Runner Backup (Before) | `a71547c932ed231a189453737457091e597e6924d84bf3730e8a3020fd72bbdd` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` | Remediated Staging Runner (After) | `4c725e3e542cfac01d809aacfba303a92d11af6f63d0660a79cd48c58ed009ea` |
| `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py.bak_cmd19_20261118` | Pre-Command 19 TradeMemoryService Backup (Before) | `61290279942ea8c878dcbf24d1b5a0c306da4e51b289f39404e67bc3a9ac7366` |
| `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py` | Remediated TradeMemoryService with Shared-Connection Transaction Support (After) | `926e802abed07d5fb53eedc6d75faae1fc61e7621b71f7ffa2cc0dd4950cda3b` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd17_20261118` | Command 17 Backup (Preserved) | `c9a95123ab27797acbeb501dd6cbbe9242465dbe4547a9d7f99ace6b31049738` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd15_20261118` | Command 15 Backup (Preserved) | `68bbb9386e81599449847fe4ec1efba9fe4bad1418a36f5e99536fd0d9bce3f9` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd13_20261117` | Command 13 Backup (Preserved) | `f4fb399e2d170f119723c74c5d679849feab3b4947498eb46b343f23e1467d66` |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd11_20261117` | Command 11 Backup (Preserved) | `34c1e7eda926e0e4dfce3672b8d9e548339ecb823fef40886fa48a1b5f04a37a` |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py` | Frozen Strategy A2 v2.0 (Unmodified) | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py` | Frozen Strategy A2 v2.0 Archive (Unmodified) | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` |
| `/opt/bitdex-research-v2/tests_cmd19_verification.py` | Command 19 Adversarial & Remediation Test Suite | Created |
| `/opt/bitdex-research-v2/docs/cmd19_verification.json` | Command 19 Machine-Readable Verification JSON | Created |

---

## 2. Detailed Remediation of All Five Command 18 Failures

### F1 — Broker Idempotency Correlation (`CMD18-F1-IDEM-KEY-DROPPED`)
- **Root Cause Fixed:** Previously, `execute_signal_Cycle()` persisted `idem_key` on disk via `mark_a2_leg_order_submitting()` but omitted `idempotency_key=persisted_idem` when calling `adapter.place_market_order()`.
- **Remediation Implemented:**
  1. In `scan_market_opportunities()` and `reserve_a2_leg_pending()`, a deterministic `idempotency_key` is generated and persisted inside `pending_reservation.signal_meta.idempotency_key` when the leg is reserved.
  2. In `mark_a2_leg_order_submitting()`, if `pending_reservation.signal_meta.idempotency_key` already exists on disk, it is **preserved unchanged** (never overwritten with a replacement UUID) and returned as `(True, persisted_idem)`.
  3. In `execute_signal_Cycle()`, `persisted_idem` is passed directly into `await adapter.place_market_order(..., idempotency_key=persisted_idem, dry_run=False)`.
  4. Verified against the real `ExnessTerminalBrokerAdapter` -> `ExnessTraderAPIAdapter.submit_order()` -> `_ap_request()` pipeline (`F1_1` & `F1_2`): the outbound POST request carries the exact persisted `idempotency_key` as `client_request_id`.

### F2 — Account-Wide History Reconciliation (`CMD18-F2-TRACK-FILTER-MISMATCH`)
- **Root Cause Fixed:** Previously, `reconcile_or_initialize_a2_leg_state()` queried `TradeMemoryService.get_trade_history()` filtered by `track="LT_STRUCTURE_EURUSD_A2"`, causing historical `EURUSD` trades from other strategy tracks on the same account (or their closing `OUT` deals) to trigger false-positive `UNTRACKED_EURUSD_BROKER_DEAL_HISTORY_DETECTED` / `MISSING_STATE_UNRECONCILABLE_BROKER_HISTORY` halts.
- **Remediation Implemented:**
  1. `reconcile_or_initialize_a2_leg_state()` now queries `TradeMemoryService.get_trade_history(account_id=str(account_id), track=None, execution_type=None, limit=5000)` alongside `a2_deal_ledger` to build account-wide sets (`known_account_tickets`, `known_account_order_ids`, `known_account_deal_ids`) for all `ACTUAL_DEMO` trades on the operator account.
  2. Only rows where `strategy_track == "LT_STRUCTURE_EURUSD_A2"` are used to reconstruct `last_confirmed_leg_id` and `confirmed_legs` (never attributing legacy/other-strategy `EURUSD` trades to A2's `last_confirmed_leg_id`).
  3. Any `EURUSD` open position, order, or deal whose `position_id` / `order_id` / `deal_id` is genuinely absent from `known_account_tickets` / `known_account_order_ids` / `known_account_deal_ids` still fails closed (`F2_1`, `F2_2`, `F2_3`).

### F3 — Eliminate Blind Position Matching (`CMD18-F3-BLIND-SNAPSHOT-MATCH`, `CMD18-F3-UNINITIALIZED-ATTR`, `CMD18-F3-CLOSED-POS-NO-MATCH`)
- **Root Causes Fixed:**
  1. `OperatorExperimentSupervisor.__init__()` now initializes `self.post_fill_guard`, `self._reconciled_fill_tickets = set()`, `self._reconciled_deal_ids = set()`, and `self.critical_incidents = []` on every construction path, and `reconcile_exness_terminal_operation()` calls `self.ensure_post_fill_guard()` on entry (`F3_1`).
  2. Removed side-only single-position matching (`if len(eur_open) == 1:`). `reconcile_exness_terminal_operation()` now queries broker instrument specifications (`vol_step`, `tick_size`) and requires strict multi-factor correlation across:
     - Unconsumed `position_id`, `order_id`, and `deal_id` (excluding all account-wide `TradeMemoryService` and `a2_deal_ledger` records)
     - Matching `client_request_id` (when present)
     - Matching direction (`BUY` / `SELL`)
     - Aggregate filled volume `> 0` and `<= requested_volume + vol_tol`
     - Execution price within broker tick tolerance of `entry_price`
     - Execution timestamp within the operation creation window (`[op_created_ts - 5s, op_created_ts + 120s]`)
     - Exactly one unique corroborating entry `order_id` (excluding `sltp` child orders and never using `operation_id`).
  3. Supports positions that opened and closed before reconciliation (`open_positions == []`) by correlating entry (`IN`) deals and market orders by `position_id`, timestamp (`event_time` / `created_at`), volume, and price (`F3_4`), while rejecting unrelated open positions (`F3_2`) and failing closed (`AMBIGUOUS`) when multiple simultaneous candidate positions exist (`F3_3`).

### F4 — Atomic Fill Recording (`CMD18-F4-SPLIT-SQLITE-TRANSACTION`)
- **Root Cause Fixed:** Previously, `TradeMemoryService.record_trade()` opened and committed its own SQLite connection before a second connection inserted into `a2_deal_ledger`.
- **Remediation Implemented:**
  1. Updated `TradeMemoryService.record_trade(cls, trade_data, conn: Optional[sqlite3.Connection] = None)` so that when a caller passes an active `sqlite3.Connection`, `record_trade()` executes its `INSERT` on that shared connection without committing or closing it prematurely.
  2. In `process_broker_fill_response()`, a single `shared_conn` executes `BEGIN IMMEDIATE`, runs `TradeMemoryService.record_trade(..., conn=shared_conn)`, inserts all individual deals into `a2_deal_ledger` (`PRIMARY KEY (account_id, deal_id)`), and executes a single atomic `shared_conn.commit()`.
  3. If any error occurs at any step (including a constraint/trigger failure on the second deal in `a2_deal_ledger`), `shared_conn.rollback()` rolls back **both** `trade_memory` and `a2_deal_ledger` (`tm_count == 0`, `dl_count == 0`), sets `recorded = False`, disables new entries, and persists a safety lock (`F4_1`, `F4_2`).

### F5 — Durable Safety Lock Independent of Flat-File Success (`CMD18-F5-DISK-FULL-SQLITE-ONLY-UNLOCK`)
- **Root Cause Fixed:** Previously, if a within-budget fill succeeded in SQLite while flat-file writes (`a2_leg_state_*.json` and `a2_post_fill_incidents_*.jsonl`) failed due to a filesystem error, no halt record was stored in SQLite, allowing a subsequent restart to reconstruct a clean state.
- **Remediation Implemented:**
  1. Created the transactionally persisted SQLite table `a2_safety_locks` (`account_id TEXT PRIMARY KEY, new_entries_disabled INTEGER NOT NULL DEFAULT 1, incident_code TEXT, detail TEXT, context_json TEXT, halted_at_utc TEXT`).
  2. Every call to `record_critical_incident()`, `mark_a2_leg_ambiguous()`, or any post-fill failure (`guard_error`, `state_error`, `tm_error`, or `not within_budget`) persists a lock row into `a2_safety_locks` in SQLite in addition to the JSONL incident log and JSON state file.
  3. Before any strategy evaluation (`reconcile_or_initialize_a2_leg_state()`, `load_a2_leg_state()`, `reserve_a2_leg_pending()`), `_check_sqlite_safety_lock(account_id)` queries `a2_safety_locks`. If `new_entries_disabled == 1` **or** if SQLite itself is unreadable/unavailable (`SQLITE_SAFETY_LOCK_UNAVAILABLE`), the runner immediately fails closed (`F5_1`, `F5_2`).

---

## 3. Complete Test Results (`cmd19_verification.json` + Full Regression of Command 17 & Command 15 Suites)

All **20/20 Command 19 checks**, **19/19 Command 17 checks**, and **37/37 Command 15 checks** (76 total verification checks) passed:

| Category | Test ID | Result |
|---|---|---|
| **F1: Idempotency Correlation** | `F1_1_never_replaces_existing_persisted_idem_key` | `PASS` |
| **F1: Idempotency Correlation** | `F1_2_exact_persisted_idem_key_reaches_exness_ap_request` | `PASS` |
| **F2: Account-Wide History** | `F2_1_legacy_other_strategy_eurusd_trades_reconciled_without_false_halt` | `PASS` |
| **F2: Account-Wide History** | `F2_2_legacy_trades_never_attributed_to_a2_leg_id` | `PASS` |
| **F2: Account-Wide History** | `F2_3_genuinely_untracked_eurusd_execution_fails_closed` | `PASS` |
| **F3: No Blind Matching** | `F3_1_fresh_supervisor_attributes_initialized_on_init` | `PASS` |
| **F3: No Blind Matching** | `F3_2_unrelated_open_position_rejected_and_fails_closed` | `PASS` |
| **F3: No Blind Matching** | `F3_3_multiple_simultaneous_ambiguous_positions_fail_closed` | `PASS` |
| **F3: No Blind Matching** | `F3_4_closed_position_with_multiple_deals_reconciled_accurately` | `PASS` |
| **F4: Atomic Fill Recording** | `F4_1_deal_ledger_failure_rolls_back_trade_memory_atomically` | `PASS` |
| **F4: Atomic Fill Recording** | `F4_2_shared_transaction_commits_both_tables_consistently` | `PASS` |
| **F5: Durable SQLite Lock** | `F5_1_filesystem_failure_after_fill_persists_halt_in_sqlite_across_restart` | `PASS` |
| **F5: Durable SQLite Lock** | `F5_2_sqlite_safety_lock_unavailable_fails_closed` | `PASS` |
| **Adversarial & Regression** | `A1_concurrent_processes_single_reservation_winner` | `PASS` |
| **Adversarial & Regression** | `A2_corrupt_incident_jsonl_fails_closed` | `PASS` |
| **Adversarial & Regression** | `R1_frozen_a2_sha256_unchanged` (`231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032`) | `PASS` |
| **Adversarial & Regression** | `S1_experiment_lock_authorized_false` (`authorized: false`) | `PASS` |
| **Adversarial & Regression** | `S2_real_trading_permanently_locked` (`True`) | `PASS` |
| **Adversarial & Regression** | `S3_real_account_16000629657_blocked` (`True`) | `PASS` |
| **Adversarial & Regression** | `S4_a2_execution_eligible_false` (`False`) | `PASS` |

---

## 4. Unresolved Issues

- **None.** All five Command 18 findings (`F1`–`F5`) and all adversarial scenarios are resolved and verified.

---

## 5. Final Verdict

`COMMAND 19 PASSED — ALL FIVE COMMAND 18 FINDINGS REMEDIATED`
