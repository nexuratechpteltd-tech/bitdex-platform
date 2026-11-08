"""
BITDEX Independent Background Watchdog Daemon (Task 3 / Phase 7M-7Q).
Runs as a separate OS process supervised by PM2.
Continuously reconciles open positions, enforces $1.00 net profit / -$1.00 loss targets,
and evaluates armed directional scalping sessions using the customer's selected symbol and capital.
"""

import os
import sys
import json
import time
import signal
import sqlite3
import logging
from datetime import datetime, timezone

sys.path.append('/opt/tauric-platform-staging/backend')
from app.services.protection_watchdog import ProtectionWatchdog

LOG_FILE = '/opt/tauric-platform-staging/backend/watchdog.log'
HEARTBEAT_FILE = '/opt/tauric-platform-staging/backend/watchdog_heartbeat.json'
DB_PATH = '/opt/tauric-platform-staging/backend/data/tauric_saas.db'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [WATCHDOG:%(process)d] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("bitdex.watchdog_daemon")

running = True


def handle_shutdown(signum, frame):
    global running
    logger.info("Shutdown signal received (%d). Terminating watchdog cleanly...", signum)
    running = False


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


def write_heartbeat(positions_count: int, discrepancies_count: int, armed_sessions: int = 0, last_cycle_status: str = "IDLE"):
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "status": "ACTIVE",
        "pid": os.getpid(),
        "last_heartbeat": now_iso,
        "positions_monitored": positions_count,
        "discrepancies_detected": discrepancies_count,
        "armed_sessions": armed_sessions,
        "last_cycle_status": last_cycle_status,
    }
    try:
        with open(HEARTBEAT_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Could not write heartbeat file: %s", str(e))


def main():
    logger.info("Starting BITDEX Independent Protection Watchdog Daemon (PID %d)...", os.getpid())
    last_auto_cycle_mono = 0.0
    last_cycle_status = "DISARMED"

    while running:
        positions_checked = 0
        discrepancies = 0
        armed_count = 0
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            positions = cursor.execute(
                "SELECT * FROM futures_positions WHERE status = 'OPEN'"
            ).fetchall()
            positions_checked = len(positions)

            for pos in positions:
                p_dict = dict(pos)
                res = ProtectionWatchdog.reconcile_and_protect_position(
                    conn=conn,
                    account_id=p_dict.get("account_id"),
                    user_id=p_dict.get("user_id"),
                    symbol=p_dict.get("symbol"),
                    position_record=p_dict,
                    exchange_open_orders=[],
                    mark_price=float(p_dict.get("mark_price") or p_dict.get("entry_price", 0.0)),
                    adapter=None,
                    simulate=True
                )
                if not res.get("protected"):
                    discrepancies += 1

            try:
                from app.services.demo_execution_service import DemoExecutionService
                profit_res = DemoExecutionService.monitor_and_exit_profit_targets(
                    conn=conn,
                    user_id="USR-ADM-B022F490",
                    profit_target_usd=1.0,
                    max_loss_usd=1.0
                )
                if profit_res.get("closed_count", 0) > 0:
                    logger.info("Profit target monitor executed exits: %s", profit_res)

                st_row = conn.execute(
                    "SELECT * FROM hft_auto_entry_state WHERE account_id = 'EXN-CONN-A4E7BE39D276'"
                ).fetchone()
                st_dict = dict(st_row) if st_row else {}
                is_armed = bool(st_dict.get("auto_entry_armed") == 1)
                live_dispatch_ok = bool(st_dict.get("live_broker_dispatch_approved") == 1)
                target_sym = str(st_dict.get("symbol") or "BTCUSDr")
                target_cap = float(st_dict.get("allocated_capital_usd") or 100.0)
                target_user = str(st_dict.get("user_id") or "USR-ADM-B022F490")
                armed_count = 1 if is_armed else 0

                # Evaluate cycle every 3.0s when armed (or every 6.0s when disarmed) if no open positions
                now_mono = time.monotonic()
                interval_sec = 3.0 if is_armed else 6.0
                if profit_res.get("positions_monitored", 0) == 0 and (now_mono - last_auto_cycle_mono) >= interval_sec:
                    last_auto_cycle_mono = now_mono
                    auto_res = DemoExecutionService.run_automated_directional_entry_cycle(
                        conn=conn,
                        user_id=target_user,
                        account_id="EXN-CONN-A4E7BE39D276",
                        symbol=target_sym,
                        allocated_capital_usd=target_cap,
                        dry_run=not (is_armed and live_dispatch_ok),
                    )
                    last_cycle_status = str(auto_res.get("execution_status") or "EVALUATED")
                    if auto_res.get("dispatched_to_broker"):
                        logger.info("Automated directional entry dispatched on %s: %s", target_sym, last_cycle_status)
            except Exception as pe:
                logger.debug("Watchdog cycle check: %s", pe)

            conn.commit()
            conn.close()
        except Exception as ex:
            logger.error("Error during watchdog supervision loop: %s", str(ex))

        write_heartbeat(positions_checked, discrepancies, armed_count, last_cycle_status)
        time.sleep(1.5)

    logger.info("Watchdog daemon stopped.")


if __name__ == '__main__':
    main()
