# BITDEX COMMAND 16 — INDEPENDENT COMMAND 15 FILL-HANDLING AUDIT

**Audit Date:** 2026-11-18 UTC  
**Audit Mode:** Strictly Read-Only Independent Source Inspection & Behavioral Probe Verification  
**Final Verdict:** `COMMAND 15 INDEPENDENT AUDIT FAILED — EXECUTION DISABLED`

---

## 1. Executive Summary & Checksum Verification

An independent, strictly read-only audit was conducted on the Command 15 staging implementation (`/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py`), its timestamped backups, the Command 15 test suite (`/opt/bitdex-research-v2/tests_cmd15_verification.py`), `TradeMemoryService` (`trade_memory_service.py`), `ExnessTraderAPIClient` (`trader_api_adapter.py`), `ExnessMT5BrokerAdapter` (`mt5_broker_adapter.py`), `SharedCentralRiskManager` (`shared_risk_manager.py`), and `CentralExecutionRouter` (`execution_router.py`).

While Command 15's 37 unit tests returned `PASS` against synthetic test fixtures—and all **Execution Safety** invariants (`experiment_lock.json` `authorized: false`, `REAL_TRADING_PERMANENTLY_LOCKED = True`, `16000629657` blocked, `17000109575` read-only, frozen `LT_STRUCTURE_EURUSD_A2` v2.0 SHA256 intact) **PASSED**—independent source inspection and adversarial probing uncovered **five concrete engineering defects** across the deduplication crash lifecycle, Exness response schema reconciliation, cross-restart multi-deal idempotency, and post-fill breach persistence.

### Verified File Checksums (SHA256)

| File | SHA256 Checksum | Audit Status |
|---|---|---|
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` | `c9a95123ab27797acbeb501dd6cbbe9242465dbe4547a9d7f99ace6b31049738` | Inspected (Unmodified during Command 16) |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd15_20261118` | `68bbb9386e81599449847fe4ec1efba9fe4bad1418a36f5e99536fd0d9bce3f9` | **PASS** (Matches Command 13 baseline) |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd13_20261117` | `f4fb399e2d170f119723c74c5d679849feab3b4947498eb46b343f23e1467d66` | **PASS** (Matches Command 11 baseline) |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd11_20261117` | `34c1e7eda926e0e4dfce3672b8d9e548339ecb823fef40886fa48a1b5f04a37a` | **PASS** (Matches Pre-Command 11 baseline) |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py` | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` | **PASS** (Frozen v2.0 intact) |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py` | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` | **PASS** (Frozen v2.0 intact) |
| `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py` | `61290279942ea8c878dcbf24d1b5a0c306da4e51b289f39404e67bc3a9ac7366` | **PASS** (Unmodified) |
| `/opt/tauric-platform-staging/backend/app/services/exness/trader_api_adapter.py` | `1d9e0f20366779971f09060ebcb38fc7d4e615a5bb29ab58dc829f53d5646f32` | **PASS** (Unmodified) |
| `/opt/tauric-platform-staging/backend/app/services/brokers/mt5_broker_adapter.py` | `124ebff6d21970745017c10c2a70a6bc9031da9e96bf4000f8df2352c4598d73` | **PASS** (Unmodified) |
| `/opt/tauric-platform-staging/backend/app/services/brokers/shared_risk_manager.py` | `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5` | **PASS** (Unmodified) |
| `/opt/tauric-platform-staging/backend/app/services/brokers/execution_router.py` | `e199dc7c590ce79874b34ebf14fa2b6948fba866b19b4b8dbbddaa8a904f6016` | **PASS** (Unmodified) |
| `/opt/bitdex-research-v2/tests_cmd15_verification.py` | `977fa0eb68c3e12cb84600c5404b8e78c18b35e733554275bf45158c3c09d072` | Inspected |
| `/opt/bitdex-research-v2/docs/cmd15_fill_handling_verification.json` | `27ad1eb2e804354f4f173bf47cad8c34bf4aa1475911d856a3b8e2f41f80feeb` | Inspected |

---

## 2. Deduplication Audit (Section 2) — `FAIL`

**Inspected Code:** `run_operator_experiment_runner.py` lines `281–775` and `1502–1673`.

| Sub-Item | Classification | Evidence & Line References |
|---|---|---|
| 1. Reservation creation and release (`reserve_a2_leg_pending` / `release_a2_leg_reservation`) | **PASS** | Lines `453–525`: Atomically transitions `AVAILABLE` -> `PENDING` and releases to `REJECTED_OR_EXPIRED` when quote, spread, sizing, preflight, or broker rejection occurs before any fill. |
| 2. Atomic state persistence | **PASS** | Lines `309–332`: Writes to `a2_leg_state_{safe_id}.json.tmp.{pid}.{ns}`, flushes, calls `os.fsync()`, and atomically replaces via `os.replace()` under `fcntl.flock(LOCK_EX)`. |
| 3. Concurrent reservation protection | **PASS** | Lines `462–488`: Exclusive lock on `a2_leg_state_{safe_id}.lock` ensures only one process can reserve a leg (`D5_concurrent_reservations_single_winner: True`). |
| 4. Confirmed-fill commitment (`confirm_a2_leg_fill`) | **PASS** | Lines `527–562`: Commits `state = "CONFIRMED_FILLED"` and `last_confirmed_leg_id = leg_str` with full broker identifiers under `confirmed_legs[leg_str]`. |
| 5. Ambiguous response locking (`mark_a2_leg_ambiguous`) | **PASS** | Lines `564–587`: Sets `state = "AMBIGUOUS_LOCKED"`, preventing retries until manual intervention. |
| 6. No premature consumption on quote / spread / sizing / preflight rejection | **PASS** | Lines `1565–1594` & `1632–1648`: Verified that quote exceptions, wide spreads, `lots is None`, and `preflight_check` rejections all release the `PENDING` reservation without setting `last_confirmed_leg_id`. |
| 7. Corrupt-state fail-closed (`CORRUPT_DEDUPLICATION_STATE`) | **PASS** | Lines `610–616`: Corrupt JSON or mismatched `account_id` immediately records a critical incident and disables new entries. |
| 8. Account and tenant isolation | **PASS** | Lines `281–293` & `339`: State, lock, and incident files are strictly scoped per `account_id` and verified on load. |
| **9. Defect D-AUDIT-1: Dead `order_submitted` flag allows duplicate order after crash between broker submission and local post-fill persistence** | **FAIL** | In `scan_market_opportunities()` (line `1556`), `reserve_a2_leg_pending()` sets `signal_meta = {"direction": ..., "order_submitted": False}`. In `reconcile_or_initialize_a2_leg_state()` (line `756`), the reconciler checks:<br>`if (pend.get("signal_meta") or {}).get("order_submitted"):`<br>However, **`execute_signal_Cycle()` (lines `1616–1673`) NEVER updates `order_submitted` to `True` before calling `adapter.place_market_order(...)` (line `1651`)!**<br>**Independent Probe 2 Result:** When `reserve_a2_leg_pending` is called (`order_submitted: False`) and the process crashes during or immediately after `place_market_order()` (before `process_broker_fill_response()` runs)—and the position either closed via SL/TP before restart or is not yet in `open_positions`—`reconcile_or_initialize_a2_leg_state()` hits line `766` (`self.release_a2_leg_reservation(..., "EXPIRED_PRE_SUBMISSION_ON_RESTART")`) and returns `(True, None, "RECONCILED_PENDING_EXPIRED")`, **permitting a duplicate order on the same structural leg!** |
| **10. Defect D-AUDIT-2: Missing-state & pending-state reconciliation does NOT inspect broker order/deal history (`get_order_history` / `get_trade_history`)** | **FAIL** | In `reconcile_or_initialize_a2_leg_state()` (lines `620–637`), only `adapter.get_open_positions()` and local `TradeMemoryService.get_trade_history()` are queried; broker deal/order history (`adapter.get_order_history()`) is never checked. If the process crashed after a broker fill (before `TradeMemoryService.record_trade()` ran) and the position already hit SL/TP before restart (or the state file was lost), `get_open_positions()` is empty and `TradeMemoryService` has no record, so the reconciler silently treats the account as having no prior fill. |

---

## 3. Exness Response Audit (Section 3) — `FAIL`

**Inspected Code:** `run_operator_experiment_runner.py` lines `777–1218` vs `trader_api_adapter.py` lines `1756–1842` (`ExnessTraderAPIClient.submit_order`) and `mt5_broker_adapter.py` lines `296–334` (`ExnessMT5BrokerAdapter.place_market_order`).

| Sub-Item | Classification | Evidence & Line References |
|---|---|---|
| **Defect E-AUDIT-1: `ExnessTraderAPIClient.submit_order()` live return payload does NOT contain `position_id`, `order_id`, `deal_id`, `fill_price`, or `filled_volume` inside `operation`** | **FAIL** | Inspecting `trader_api_adapter.py` lines `1820–1836` and actual historical execution logs (`/opt/tauric-platform-staging/backend/data/operator_9h_experiment.log` lines `130, 743, 4176, 9966, 10414`) proves that `ExnessTraderAPIClient.submit_order()` returns:<br>`{'status': 'FILLED', 'operation_id': '379428714124935168', 'ack': {'operation_id': '379428714124935168', 'status': 'accepted', 'client_request_id': '...'}, 'operation': {'operation_id': '379428714124935168', 'status': 'confirmed', 'request_type': 'open_position', 'client_request_id': '...', 'created_at': '...', 'updated_at': '...'}, 'payload': {'instrument': 'EURUSD', 'side': 'buy', 'volume': '0.03', ...}}`<br>Because `GET /v1/trading/accounts/{id}/operations/{op_id}` only returns operation status (`confirmed`), **it does not contain `position_id`, `order_id`, `deal_id`, `fill_price`, or `filled_volume`** (which live in `/snapshot` and `/v1/history/accounts/{id}/orders` & `/deals`).<br>**Independent Probe 1 Result:** Passing the exact real `submit_order()` structure to `normalize_exness_order_response()` fails on every live Exness Terminal fill with:<br>`{'normalized_status': 'AMBIGUOUS', 'adapter_schema': 'EXNESS_TERMINAL_V1', 'operation_id': '379428714124935168', 'error_code': 'MISSING_BROKER_TICKET', 'detail': 'Confirmed fill response is missing genuine position_id / broker_ticket.'}`<br>Neither `execute_signal_Cycle()` nor `process_broker_fill_response()` reconciles the confirmed `operation_id` against `adapter.get_open_positions()` / `adapter.get_order_history()` to obtain the genuine `position_id`, `order_id`, `deal_id`, and `fill_price`. |
| Operation ID kept separate from `broker_ticket` and `order_id` | **PASS** | Lines `1042–1067`: Explicitly rejects any response where `operation_id` is used as `broker_ticket` or `order_id`. |
| Accepted-but-not-filled vs confirmed fill vs rejected vs pending | **PASS** | Lines `855–914` & `948–968`: Properly distinguishes `REJECTED`, `ACCEPTED_NOT_FILLED`, `PENDING_OPERATION`, `AMBIGUOUS`, and `MALFORMED_OR_CONTRADICTORY`. |
| Account and `EURUSD` instrument validation | **PASS** | Lines `978–1023`: Validates `account_id`, `execution_type == "ACTUAL_DEMO"`, `EURUSD` symbol, and side. |

---

## 4. TradeMemoryService Audit (Section 4) — `FAIL`

**Inspected Code:** `run_operator_experiment_runner.py` lines `1126–1130`, `1315–1356`, `1421–1456` and `trade_memory_service.py` lines `41–95`, `180–314`.

| Sub-Item | Classification | Evidence & Line References |
|---|---|---|
| Genuine `broker_ticket` and `order_id` supplied; no fabricated IDs | **PASS** | Lines `1043–1067` & `1422–1427`: Refuses to fabricate or copy `broker_ticket`/`operation_id` into `order_id`, and supplies genuine `broker_ticket`, `order_id`, and `deal_id` to `TradeMemoryService.record_trade()`. |
| Duplicate `broker_ticket` idempotency across restart | **PASS** | Lines `1330–1333`: Queries `SELECT trade_id FROM trade_memory WHERE account_id = ? AND (broker_ticket = ? OR (deal_id != '' AND deal_id = ?)) LIMIT 1`. |
| **Defect TM-AUDIT-1: Cross-restart individual `deal_id` idempotency fails for multi-deal partial fills due to comma-joined `deal_id` string** | **FAIL** | In `normalize_exness_order_response()` (line `1130`), when a fill has multiple deals (e.g., `["D-601", "D-602"]`), `primary_deal_id` is stored in SQLite `trade_memory.deal_id` as the comma-joined string `"D-601,D-602"`.<br>In `process_broker_fill_response()` (lines `1330–1333`), the SQLite duplicate check only tests exact equality `deal_id = ?` against the incoming `deal_id`, and does not inspect `signal_reason_json.deal_ids` or substring membership.<br>**Independent Probe 3 Result:** After a process restart (when in-memory `self._reconciled_deal_ids` is empty), replaying individual deal `"D-601"` under a different ticket bypassed the SQLite check (`"D-601,D-602" != "D-601"`) and recorded a duplicate trade (`PROBE_3_CROSS_RESTART_SUBDEAL_DEDUP: CONFIRMED_AND_PROTECTED recorded: True`). Furthermore, `trade_memory` table (`trade_memory_service.py:41–95`) has `PRIMARY KEY (trade_id)` (`OPDEMO-{tkt}`) but no `UNIQUE` index on `broker_ticket`, `order_id`, or `deal_id`. |

---

## 5. Post-Fill Failure Audit (Section 5) — `FAIL`

**Inspected Code:** `run_operator_experiment_runner.py` lines `338–376`, `1381–1500`, `1518–1526`.

| Sub-Item | Classification | Evidence & Line References |
|---|---|---|
| Exceptions in `PostFillRiskBreachGuard`, `confirm_a2_leg_fill`, and `TradeMemoryService.record_trade` disable new entries in-memory and write JSONL incident | **PASS** | Lines `1381–1475`: All three steps are wrapped in independent `try/except` blocks after fill recognition; any exception sets `self.post_fill_guard.new_entries_disabled = True` and writes `fill_recovery_context` (with all broker IDs) to `a2_post_fill_incidents_{account_id}.jsonl`. |
| **Defect PF-AUDIT-1: `new_entries_disabled` and `PostFillRiskBreachGuard` breach state are in-memory only and reset to `False` across process restart** | **FAIL** | Inspecting `ensure_post_fill_guard()` (lines `338–347`) and `reconcile_or_initialize_a2_leg_state()` (lines `589–775`) reveals that `self.post_fill_guard = PostFillRiskBreachGuard(max_risk_usd=10.0)` is initialized in-memory with `new_entries_disabled = False`, and **`reconcile_or_initialize_a2_leg_state()` never checks whether `a2_post_fill_incidents_{account_id}.jsonl` has unresolved critical incidents or whether `TradeMemoryService` has a trade with `"post_fill_within_budget": false`!**<br>Consequently:<br>1. If a confirmed fill breaches the `$10.00` risk budget (`PF5`: `within_budget = False`), `confirm_a2_leg_fill()` saves `state = "CONFIRMED_FILLED"` (not `AMBIGUOUS_LOCKED`) and does not write to the incident file. Upon process restart, `self.post_fill_guard.new_entries_disabled` resets to `False` and `reconcile_or_initialize_a2_leg_state()` returns `(True, persisted_leg, "OK")`, allowing new entries on subsequent legs despite the unrecovered risk breach!<br>2. Similarly, if `TradeMemoryService.record_trade()` fails (`PF1`) while `confirm_a2_leg_fill()` succeeds (`state = "CONFIRMED_FILLED"`), an incident is written to `a2_post_fill_incidents_{account_id}.jsonl`, but `reconcile_or_initialize_a2_leg_state()` never reads `a2_post_fill_incidents_{account_id}.jsonl` on restart! Thus, after a process restart, `new_entries_disabled` resets to `False`. |

---

## 6. Test-Quality Audit (Section 6) — `FAIL`

**Inspected File:** `/opt/bitdex-research-v2/tests_cmd15_verification.py` (lines `1–545`).

| Test Quality Dimension | Classification | Findings |
|---|---|---|
| Real local services used (`TradeMemoryService`, `PostFillRiskBreachGuard`, `SharedCentralRiskManager`, `EurUsdStructureA2`) | **PASS** | Tests use the real `TradeMemoryService` against an isolated temporary SQLite database (`TEST_DB_PATH`) that is cleaned up after execution, with zero pollution of live staging `tauric_saas.db`. |
| Process-level concurrency locking (`D5`) | **PASS** | Uses `multiprocessing.Pool(6)` across 12 concurrent reservation calls on real lock files. |
| **False-Positive Fixture in `P1`, `D6`, `TM1`, `PF1`–`PF5`: Augmented `ExnessTraderAPIClient.submit_order()` payload** | **FAIL** | `tests_cmd15_verification.py` (lines `166–182`) injected synthetic `"position_id": "75100001"`, `"order_id": "154100001"`, `"deal_id": "151900001"`, `"fill_price": 1.08110`, and `"filled_volume": 0.03` directly inside `operation: {...}`. In reality (`trader_api_adapter.py:1820–1836` and `operator_9h_experiment.log:130`), `ExnessTraderAPIClient.submit_order()` only returns `operation: {'operation_id': '...', 'status': 'confirmed', 'request_type': 'open_position', ...}` without position/order/deal/fill fields. |
| **Missing Restart Tests for Post-Fill Breach (`PF5`), Post-Fill DB Failure (`PF1`), Cross-Restart Multi-Deal Replay, and Mid-Submission Crash** | **FAIL** | `tests_cmd15_verification.py` tested restart persistence only for `D7` (normal confirmed fill) and `D11` (ambiguous response which sets `AMBIGUOUS_LOCKED`), but did **not** test creating a new `OperatorExperimentSupervisor()` after `PF1` (TradeMemory exception where `leg_state` is `CONFIRMED_FILLED`) or `PF5` (post-fill risk breach where `leg_state` is `CONFIRMED_FILLED`), nor did it test crashing between `reserve_a2_leg_pending` and `place_market_order`. |

---

## 7. Execution Safety Verification (Section 7) — `PASS`

| Safety Invariant | Classification | Verification Evidence |
|---|---|---|
| `experiment_lock.json`: `authorized: false` | **PASS** | Verified `/opt/tauric-platform-staging/backend/data/experiment_lock.json`: `"authorized": false`. |
| `REAL_TRADING_PERMANENTLY_LOCKED = True` | **PASS** | Verified in `run_operator_experiment_runner.py:46` and `central_risk_gate.py`. |
| Real account `16000629657` permanently blocked | **PASS** | Verified in `shared_risk_manager.py:143` (`str(account_id).strip() == "16000629657"` -> hard reject). |
| Customer account `17000109575` read-only / untouched | **PASS** | Verified in `exness_demo_connections`: `account_login='17000109575'`, `updated_at='2026-11-10T02:05:08Z'`. |
| Strategy `LT_STRUCTURE_EURUSD_A2` `execution_eligible: false` | **PASS** | Verified via `get_strategy_for_customer("LT_STRUCTURE_EURUSD_A2", ...)`: `validation_status='INCONCLUSIVE_STATISTICAL_CONFIDENCE'`, `execution_eligible=False`. |
| Live staging `trade_memory` & `data/` unpolluted | **PASS** | `SELECT count(*) FROM trade_memory WHERE strategy_track='LT_STRUCTURE_EURUSD_A2'` is `0`; no stray `a2_*` files in `/opt/tauric-platform-staging/backend/data/`. |
| No alternate order path, no production changes, no PM2 restarts, zero broker orders, zero paper trading | **PASS** | Verified read-only execution and PM2 process uptimes unchanged. |

---

## 8. Summary of Remaining Defects Requiring Remediation

1. **Defect E-AUDIT-1 (Exness Terminal Post-Submit Fill Reconciliation):** `ExnessTraderAPIClient.submit_order()` returns only `operation_id` and `operation.status == "confirmed"` without `position_id`, `order_id`, `deal_id`, `fill_price`, or `filled_volume`. When `submit_order()` returns a confirmed `operation_id` lacking position/order/fill details, the runner must reconcile the fill via read-only broker snapshot/history (`get_open_positions()`, `get_order_history()`, `get_trade_history()`) before passing the enriched structure to `normalize_exness_order_response()` (or fail closed if reconciliation cannot uniquely match the position and order ID).
2. **Defect D-AUDIT-1 (Mark `order_submitted = True` Durably Before Calling `place_market_order()`):** In `execute_signal_Cycle()`, before invoking `adapter.place_market_order()`, atomically update the `PENDING` reservation on disk with `order_submitted = True` (and `submitted_at_utc` / `idempotency_key`), so a crash during order submission can never be mistaken for a pre-submission interruption (`EXPIRED_PRE_SUBMISSION_ON_RESTART`).
3. **Defect D-AUDIT-2 (Check Broker Order/Deal History During Missing/Pending State Reconciliation):** In `reconcile_or_initialize_a2_leg_state()`, inspect `await adapter.get_order_history(limit=50)` (and `get_trade_history` where available) in addition to `get_open_positions()` and `TradeMemoryService` so a position that opened and closed during a crash window or missing-state event is detected.
4. **Defect PF-AUDIT-1 (Persist `new_entries_disabled` Across Process Restarts):** Persist `new_entries_disabled = True` durably in the leg state document (`state = "HALTED_POST_FILL_INCIDENT_OR_BREACH"` or `"new_entries_disabled": True`) and check both `doc.get("new_entries_disabled")` and `a2_post_fill_incidents_{account_id}.jsonl` / `TradeMemoryService` (`post_fill_within_budget == False`) inside `reconcile_or_initialize_a2_leg_state()` so a process restart never re-enables entries after a post-fill risk breach or post-fill persistence failure.
5. **Defect TM-AUDIT-1 (Cross-Restart Multi-Deal Individual `deal_id` Idempotency):** In `process_broker_fill_response()`, check incoming `deal_ids` against both `trade_memory.deal_id` and the parsed `signal_reason_json.deal_ids` list in SQLite so individual deal replays from a multi-deal fill are rejected even after a process restart.

---

## 9. Final Verdict

`COMMAND 15 INDEPENDENT AUDIT FAILED — EXECUTION DISABLED`
