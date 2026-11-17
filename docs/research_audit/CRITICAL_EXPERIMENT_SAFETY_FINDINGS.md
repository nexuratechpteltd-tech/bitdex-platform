# Critical Experiment Safety Findings (Stage 1)
- **PM2 #16 Entrypoint:** `/opt/tauric-platform-staging/backend/run_operator_experiment_runner.py`
- **SHA256:** `34c1e7eda926e0e4dfce3672b8d9e548339ecb823fef40886fa48a1b5f04a37a`
- **Confirmed Discrepancies:**
  1. `authorized_strategies` from `experiment_lock.json` is NOT enforced in `run_operator_experiment_runner.py`.
  2. `max_concurrent_positions` is NOT enforced in `run_operator_experiment_runner.py`.
  3. `final_pre_execution_risk_check()` is NOT called by `run_operator_experiment_runner.py`.
- **Action Taken:** None (strictly read-only; PM2 #16 and #11 untouched). Separate operator approval requested before any remediation.
