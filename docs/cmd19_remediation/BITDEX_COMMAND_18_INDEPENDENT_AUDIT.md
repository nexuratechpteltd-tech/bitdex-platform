# BITDEX COMMAND 18 — INDEPENDENT ADVERSARIAL EXECUTION-RELIABILITY AUDIT

**Audit Date:** 2026-11-18 UTC  
**Repository:** `nexuratechpteltd-tech/bitdex-platform` (Branch: `research/eurusd-recovery-and-audit-20261117`, Commit: `09482a9`)  
**Staging Backend:** `/opt/tauric-platform-staging/backend`  
**Research Directory:** `/opt/bitdex-research-v2/`  
**Audit Mode:** Strictly Read-Only Independent Inspection & Adversarial Offline Probing (Zero code modifications made during audit)  
**Final Verdict:** `INDEPENDENT AUDIT FAILED — EXECUTION DISABLED`

---

## 1. Executive Summary & Checksum Verification

An independent adversarial audit was performed against the actual Command 17 staging implementation in `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` (`a71547c932ed231a189453737457091e597e6924d84bf3730e8a3020fd72bbdd`) and `/opt/bitdex-research-v2/tests_cmd17_verification.py`.

While Command 17 resolved the primary nominal cases from Command 16, **adversarial source inspection and offline fault-injection probes uncovered 6 concrete vulnerabilities across the 5 audited areas** (`CMD18-F1-IDEM-KEY-DROPPED`, `CMD18-F2-TRACK-FILTER-MISMATCH`, `CMD18-F3-BLIND-SNAPSHOT-MATCH`, `CMD18-F3-UNINITIALIZED-ATTR`, `CMD18-F4-SPLIT-SQLITE-TRANSACTION`, and `CMD18-F5-DISK-FULL-SQLITE-ONLY-UNLOCK`). Per Command 18 instructions, **zero code modifications were made to hide or patch these failures**.

### Verified SHA256 Checksums

| File Path | SHA256 Checksum | Status |
|---|---|---|
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py` | `a71547c932ed231a189453737457091e597e6924d84bf3730e8a3020fd72bbdd` | Inspected (Unmodified) |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd17_20261118` | `c9a95123ab27797acbeb501dd6cbbe9242465dbe4547a9d7f99ace6b31049738` | Verified |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd15_20261118` | `68bbb9386e81599449847fe4ec1efba9fe4bad1418a36f5e99536fd0d9bce3f9` | Verified |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd13_20261117` | `f4fb399e2d170f119723c74c5d679849feab3b4947498eb46b343f23e1467d66` | Verified |
| `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py.bak_cmd11_20261117` | `34c1e7eda926e0e4dfce3672b8d9e548339ecb823fef40886fa48a1b5f04a37a` | Verified |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.py` | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` | **PASS** (Frozen v2.0 intact) |
| `/opt/bitdex-research-v2/strategies/eurusd_structure_a2.frozen_v2_0.py` | `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` | **PASS** (Frozen v2.0 intact) |
| `/opt/tauric-platform-staging/backend/app/services/trade_memory_service.py` | `61290279942ea8c878dcbf24d1b5a0c306da4e51b289f39404e67bc3a9ac7366` | Verified |
| `/opt/tauric-platform-staging/backend/app/services/exness/trader_api_adapter.py` | `1d9e0f20366779971f09060ebcb38fc7d4e615a5bb29ab58dc829f53d5646f32` | Verified |
| `/opt/tauric-platform-staging/backend/app/services/brokers/mt5_broker_adapter.py` | `124ebff6d21970745017c10c2a70a6bc9031da9e96bf4000f8df2352c4598d73` | Verified |
| `/opt/tauric-platform-staging/backend/app/services/brokers/shared_risk_manager.py` | `646d83b29ea2e47ad2fd76e751d03e620f5d864d0871a9f0f38a440283d61fb5` | Verified |
| `/opt/tauric-platform-staging/backend/app/services/brokers/execution_router.py` | `e199dc7c590ce79874b34ebf14fa2b6948fba866b19b4b8dbbddaa8a904f6016` | Verified |

---

## 2. Adversarial Audit of the Five Critical Fixes

### Fix 1 — Atomic Pre-Submission Persistence — `FAIL`

- **Write Ordering & Crash Blocking (`PASS`):** In `execute_signal_Cycle()` (`run_operator_experiment_runner.py:2270–2280`), `self.mark_a2_leg_order_submitting(account_id, leg_id, reservation_id=res_id, idempotency_key=idem_key)` is called synchronously and flushed with `os.fsync()` + `os.replace()` under `fcntl.flock(LOCK_EX)` (`lines 592–637`) **before** `await adapter.place_market_order(...)` (`line 2282`). Process termination before `mark_a2_leg_order_submitting` leaves `order_submitted: False`; termination during or after `place_market_order()` leaves `order_submitted: True`, which causes `reconcile_or_initialize_a2_leg_state()` (`lines 1267–1274`) to fail closed (`PENDING_SUBMITTED_ORDER_UNRECONCILABLE`).
- **Vulnerability `CMD18-F1-IDEM-KEY-DROPPED` (`FAIL`):**
  - **File & Lines:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py:2270–2286`
  - **Code Inspected:**
    ```python
    idem_key = f"a2-ord-{account_id}-{int(time.time() * 1000)}"
    if leg_id:
        if not self.mark_a2_leg_order_submitting(account_id, leg_id, reservation_id=res_id, idempotency_key=idem_key):
            ...
    order_res = await adapter.place_market_order(
        symbol=sig["symbol"], side=sig["side"], volume=sig["volume"],
        sl=sig["sl_price"], tp=sig["tp_price"], dry_run=False,
        comment=f"OPEXP_{sig['engine_type'][:4]}"
    )
    ```
  - **Defect & Reproduction (`Probe F`):** `execute_signal_Cycle()` generates `idem_key` and persists it to disk in `pending_reservation.signal_meta.idempotency_key`, **but omits `idempotency_key=idem_key` when calling `adapter.place_market_order()`!** Consequently, `ExnessTraderAPIClient.submit_order()` (`trader_api_adapter.py:1798`) generates a completely different random UUID (`bitdex-ord-...`) for the HTTP `X-Request-ID` / `client_request_id` header. The persisted `idem_key` on disk never matches the broker's `client_request_id`.

---

### Fix 2 — Broker History Reconciliation — `FAIL`

- **Untracked Closed Position & Missing State Detection (`PASS`):** `reconcile_or_initialize_a2_leg_state()` (`lines 1037–1059, 1175–1211, 1258–1265, 1291–1298`) queries `get_open_positions()`, `get_order_history(limit=100)`, and `get_trade_history(limit=100)` and fails closed when untracked `EURUSD` deals/orders exist.
- **Vulnerability `CMD18-F2-TRACK-FILTER-MISMATCH` (`FAIL`):**
  - **File & Lines:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py:1061–1067` and `1179–1190`
  - **Defect & Reproduction (`Probe A`):**
    On lines `1061–1067`, `reconcile_or_initialize_a2_leg_state()` queries `TradeMemoryService.get_trade_history()` filtered strictly by `track="LT_STRUCTURE_EURUSD_A2"`, whereas `adapter.get_order_history()` and `adapter.get_trade_history()` return **account-wide** broker history across all strategies on account `17000694512`.
    In **Adversarial Probe A**, recording a legitimate historical `EURUSD` trade under another strategy track (`strategy_track="Forex Long-Term (EURUSD)"`, `broker_ticket="70000001"`, `order_id="150000001"`, `deal_id="140000001"`) and running `reconcile_or_initialize_a2_leg_state()` caused a permanent false-positive halt:
    ```text
    PROBE_A_NON_A2_EURUSD_HISTORY_FALSE_ALARM: False MISSING_STATE_UNRECONCILABLE_BROKER_HISTORY
    ```
    Additionally, when an `LT_STRUCTURE_EURUSD_A2` position is closed at the broker by SL/TP or market close, Exness Deal History records an `OUT` / `close` deal with a **new** `deal_id` (not in `tm_deal_ids`). Although its `position_id` is in `tm_by_ticket`, `TradeMemoryService.get_trade_history(..., limit=100)` only loads the last 100 A2 trades; if an older deal or a manual/other-strategy EURUSD deal exists in the 7-day broker window, it bricks the runner.

---

### Fix 3 — Terminal Operation Reconciliation — `FAIL`

- **Refusal to Fabricate Unreconciled Identifiers (`PASS`):** When `reconcile_exness_terminal_operation()` cannot match a position or order, `normalize_exness_order_response()` (`lines 1581–1597`) rejects the response as `AMBIGUOUS` (`MISSING_BROKER_TICKET` / `MISSING_GENUINE_ORDER_ID`).
- **Vulnerability 3A: `CMD18-F3-BLIND-SNAPSHOT-MATCH` (`FAIL`):**
  - **File & Lines:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py:871–895`
  - **Defect & Reproduction (`Probe D`):**
    In `reconcile_exness_terminal_operation()`, lines `871–895` select any single open `EURUSD` position on the snapshot whose ticket is not in `known_tickets` and whose side matches `exp_side`:
    ```python
    if len(eur_open) == 1:
        pos = eur_open[0]
        matched_pos_id = str(pos.get("position_id") or pos.get("ticket") or "").strip()
    ```
    It **never checks** whether `pos["volume"]` matches the requested volume, whether `pos["open_price"]` is near the execution quote, or whether `pos["open_time"]` occurred at/after the operation's `created_at` timestamp!
    In **Adversarial Probe D**, an unrelated pre-existing `0.50`-lot `EURUSD` BUY position at `1.06000` (`position_id="77777777"`, `order_id="188888888"`, `deal_id="166666666"`) was on the snapshot when a `0.03`-lot A2 operation (`operation_id="379999999999999999"`) was reconciled before the new position appeared in `/snapshot`. `reconcile_exness_terminal_operation()` blindly bound the `0.50`-lot position at `1.06000` to the `0.03`-lot A2 signal:
    ```text
    PROBE_D_UNRELATED_POSITION_MATCHED: 77777777 deals: [{'deal_id': '166666666', 'position_id': '77777777', 'order_id': '188888888', 'price': 1.06, 'volume': 0.5}]
    ```
- **Vulnerability 3B: `CMD18-F3-UNINITIALIZED-ATTR` (`FAIL`):**
  - **File & Lines:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py:842`
  - **Defect & Reproduction (`Probe E0`):** `reconcile_exness_terminal_operation()` accesses `self._reconciled_fill_tickets` on line `842` and `self._reconciled_deal_ids` on line `844` **without calling `self.ensure_post_fill_guard()` first**. Calling `reconcile_exness_terminal_operation()` on a fresh `OperatorExperimentSupervisor()` instance raises:
    ```text
    PROBE_E0_FRESH_INSTANCE_ATTR_ERROR: 'OperatorExperimentSupervisor' object has no attribute '_reconciled_fill_tickets'
    ```
- **Vulnerability 3C: `CMD18-F3-CLOSED-POS-NO-MATCH` (`FAIL`):**
  - **File & Lines:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py:901–955`
  - **Defect & Reproduction (`Probe E`):** When a position opens and immediately closes before `reconcile_exness_terminal_operation()` runs (`open_positions == []`), `matched_pos_id` is `None`. Lines `914` and `950` attempt to match deals/orders using `d.get("operation_id") == op_id` or `d.get("client_request_id") == client_req_id`. However, Exness `/v1/history/accounts/{id}/deals` and `/orders` items (`trader_api_adapter.py:2116–2123`) are keyed by `order_id`, `deal_id`, `position_id`, and `event_time`—not `operation_id`. Thus, `cand_deals` and `cand_orders` remain empty and reconciliation fails with `AMBIGUOUS` (`MISSING_BROKER_TICKET`).

---

### Fix 4 — Deal Ledger — `FAIL`

- **SQLite Primary Key & Cross-Restart Replay Blocking (`PASS`):** `a2_deal_ledger` (`lines 350–364`) defines `PRIMARY KEY (account_id, deal_id)` and blocks cross-restart sub-deal replays (`lines 1882–1908`).
- **Vulnerability `CMD18-F4-SPLIT-SQLITE-TRANSACTION` (`FAIL`):**
  - **File & Lines:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py:1995–2077`
  - **Defect & Reproduction (`Probe G`):**
    In `process_broker_fill_response()`, `TradeMemoryService.record_trade(...)` (`line 1995`) opens its own SQLite connection, commits the trade to `trade_memory`, and closes its connection. Only **after** that commit finishes does `process_broker_fill_response()` open a **second, separate SQLite connection** (`dl_conn = TradeMemoryService.get_connection()`, `line 2031`) to insert individual deals into `a2_deal_ledger` (`lines 2033–2076`).
    Because both operations are inside the same `try ... except Exception as tm_exc:` block (`lines 1994–2085`), if the second connection (`dl_conn`) fails (e.g., `sqlite3.OperationalError: table locked`), `trade_memory` is **already committed** (`1` row), `a2_deal_ledger` is **uncommitted** (`0` rows), and `process_broker_fill_response()` sets `tm_recorded = False` (`"recorded": False`), leaving the two SQLite tables inconsistent:
    ```text
    PROBE_G_SPLIT_TX (TM committed=1, but res['recorded']=False!): tm_rows: 1 res_recorded: False status: CRITICAL_POST_FILL_PROTECTION_OR_PERSISTENCE_FAILURE
    ```

---

### Fix 5 — Durable Post-Fill Lock — `FAIL`

- **Restart After Risk Breach, TradeMemory Failure & Malformed Incident JSONL (`PASS`):** `_has_durable_incidents_on_disk()` (`lines 421–437`) catches malformed/partial JSONL lines and returns `(True, [{"incident_code": "CORRUPT_INCIDENT_LOG", ...}])`, failing closed before strategy evaluation (`lines 1015–1019, 2141–2144`).
- **Vulnerability `CMD18-F5-DISK-FULL-SQLITE-ONLY-UNLOCK` (`FAIL`):**
  - **File & Lines:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py:399–419` and `1961–2028`
  - **Defect & Reproduction (`Probe C`):**
    If a confirmed fill is within budget (`within_budget = True`), `TradeMemoryService.record_trade()` writes `"post_fill_within_budget": true` to SQLite (`line 2026`). If `confirm_a2_leg_fill()` and `record_critical_incident()` both fail to write to `/opt/tauric-platform-staging/backend/data/a2_leg_state_*.json` and `a2_post_fill_incidents_*.jsonl` (e.g., transient filesystem / permission failure on flat files while SQLite succeeds), no halt flag is written to SQLite.
    When the process restarts (`Probe C`), `reconcile_or_initialize_a2_leg_state()` finds no incident JSONL file, no state JSON file, and `post_fill_within_budget == True` in `TradeMemoryService`, so it reconstructs `state = "CONFIRMED_FILLED"` with `new_entries_disabled = False`:
    ```text
    PROBE_C_IN_MEMORY_DISABLED: True TM_RECORDED: True
    PROBE_C_AFTER_RESTART (did it halt or reconstruct?): True BUY:1.07500:1.08500 RECONCILED_FROM_MISSING disabled: False
    ```

---

## 3. Summary Table of All Audited Items & Adversarial Scenarios

| Audit Item / Adversarial Scenario | Classification | Reference |
|---|---|---|
| **Fix 1:** Atomic pre-submission persistence (`order_submitted = True` before call) | **FAIL** | Write ordering passes, but `idem_key` is not passed to `adapter.place_market_order()` (`CMD18-F1-IDEM-KEY-DROPPED`, `lines 2270–2286`). |
| **Fix 2:** Broker history reconciliation (snapshot, orders, deals) | **FAIL** | Queries `TradeMemoryService` with `track='LT_STRUCTURE_EURUSD_A2'` against account-wide broker history (`CMD18-F2-TRACK-FILTER-MISMATCH`, `lines 1061–1067`). |
| **Fix 3:** Terminal operation reconciliation | **FAIL** | Blindly matches any single open EURUSD position without volume/price/timestamp validation (`CMD18-F3-BLIND-SNAPSHOT-MATCH`, `lines 871–895`); uninitialized `_reconciled_fill_tickets` on fresh instance (`line 842`). |
| **Fix 4:** Deal ledger (`a2_deal_ledger`) | **FAIL** | Split SQLite connections between `TradeMemoryService.record_trade()` and `a2_deal_ledger` (`CMD18-F4-SPLIT-SQLITE-TRANSACTION`, `lines 1995–2077`). |
| **Fix 5:** Durable post-fill lock across restart | **FAIL** | Flat-file write failure during within-budget fill is not recorded in SQLite, unlocking on restart (`CMD18-F5-DISK-FULL-SQLITE-ONLY-UNLOCK`, `lines 399–419, 1961–2028`). |
| **Scenario 1:** Broker accepts order, client times out | **PASS** | `place_market_order()` exception marks `AMBIGUOUS_LOCKED` and `order_submitted = True` blocks retry (`lines 2287–2296`). |
| **Scenario 2:** Broker returns acknowledgement without fill | **PASS** | `ACCEPTED_NOT_FILLED` / `PENDING_OPERATION` locks leg as `AMBIGUOUS_LOCKED` and disables new entries (`lines 1409–1416, 1844–1866`). |
| **Scenario 3:** Position opens and closes before local persistence | **FAIL** | `reconcile_exness_terminal_operation()` cannot match closed position in Exness deal history without `operation_id` (`Probe E`, `lines 901–955`). |
| **Scenario 4:** Multiple deals belong to one order | **PASS (Partial)** | VWAP and deal deduplication work, but `trade_memory` and `a2_deal_ledger` use separate SQLite transactions (`Probe G`). |
| **Scenario 5:** History API returns incomplete or delayed results | **FAIL** | If new position is delayed in `/snapshot` while a prior unrelated EURUSD position is open, `reconcile_exness_terminal_operation()` binds the wrong position (`Probe D`). |
| **Scenario 6:** SQLite unavailable during fill | **PASS** | `TradeMemoryService.record_trade()` exception disables new entries and writes durable JSONL incident (`lines 2078–2089`). |
| **Scenario 7:** Incident JSONL malformed or partially written | **PASS** | `_has_durable_incidents_on_disk()` catches `json.JSONDecodeError` and returns `(True, [{"incident_code": "CORRUPT_INCIDENT_LOG"}])` (`lines 421–437`). |
| **Scenario 8:** Two processes attempt same leg simultaneously | **PASS** | `fcntl.flock(LOCK_EX)` on `a2_leg_state_{id}.lock` guarantees a single winner (`lines 558–588`). |
| **Scenario 9:** Process restarts after ambiguous submission | **PASS** | `AMBIGUOUS_LOCKED` and `order_submitted = True` persist on disk and block retries (`lines 1165–1172, 1267–1274`). |
| **Scenario 10:** Adapter returns unexpected response structure | **PASS** | `normalize_exness_order_response()` returns `MALFORMED_OR_CONTRADICTORY` (`UNSUPPORTED_ADAPTER_SCHEMA`), locking leg and disabling entries (`lines 1342–1354`). |

---

## 4. Safety & Operational Verification

- `experiment_lock.json`: `"authorized": false`
- `REAL_TRADING_PERMANENTLY_LOCKED`: `True`
- Real account `16000629657`: Permanently blocked
- Customer account `17000109575`: Read-only / untouched (`updated_at: 2026-11-10T02:05:08Z`)
- Strategy `LT_STRUCTURE_EURUSD_A2`: `execution_eligible: False`
- Frozen A2 v2.0 SHA256: `231e0259c0a0a514537c5efef03139d2b4d5895c07ad8350164c3a04f2b19032` (Unchanged)
- Live staging `trade_memory` A2 rows: `0`
- Zero code edits, zero broker calls, zero orders, zero paper trading, zero PM2 restarts, zero production changes during Command 18.

---

## 5. Final Verdict

`INDEPENDENT AUDIT FAILED — EXECUTION DISABLED`
