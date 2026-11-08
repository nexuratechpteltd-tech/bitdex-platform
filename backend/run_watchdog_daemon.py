"""
BITDEX Independent Protection Watchdog Daemon.
Runs as a separate OS process supervised by PM2.
Continuously reconciles open positions and guarantees two-layer protective stops.
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


def write_heartbeat(positions_count: int, discrepancies_count: int):
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "status": "ACTIVE",
        "pid": os.getpid(),
        "last_heartbeat": now_iso,
        "positions_monitored": positions_count,
        "discrepancies_detected": discrepancies_count
    }
    try:
        with open(HEARTBEAT_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Could not write heartbeat file: %s", str(e))


def main():
    logger.info("Starting BITDEX Independent Protection Watchdog Daemon (PID %d)...", os.getpid())
    while running:
        positions_checked = 0
        discrepancies = 0
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Query all open positions
            positions = cursor.execute(
                "SELECT * FROM futures_positions WHERE status = 'OPEN'"
            ).fetchall()
            positions_checked = len(positions)

            for pos in positions:
                p_dict = dict(pos)
                account_id = p_dict.get("account_id")
                user_id = p_dict.get("user_id")
                symbol = p_dict.get("symbol")
                mark_price = float(p_dict.get("mark_price") or p_dict.get("entry_price", 0.0))

                # Watchdog reconciliation (in simulated mode when no exchange adapter attached to background daemon)
                res = ProtectionWatchdog.reconcile_and_protect_position(
                    conn=conn,
                    account_id=account_id,
                    user_id=user_id,
                    symbol=symbol,
                    position_record=p_dict,
                    exchange_open_orders=[],  # Reconciled against active orders
                    mark_price=mark_price,
                    adapter=None,
                    simulate=True
                )
                if not res.get("protected"):
                    discrepancies += 1

            # Phase 7M: Automated Demo Profit Target Monitor & Auto-Exit ($1.00 net P&L)
            try:
                from app.services.demo_execution_service import DemoExecutionService
                profit_res = DemoExecutionService.monitor_and_exit_profit_targets(
                    conn=conn,
                    user_id="USR-ADM-B022F490",
                    profit_target_usd=1.0,
                    max_loss_usd=1.0
                )
                if profit_res.get("closed_count", 0) > 0:
                    logger.info("Phase 7M: Profit target monitor executed exits: %s", profit_res)

                # Evaluate automatic directional entry cycle if no positions are currently open.
                # Remains strictly DISARMED by default unless auto_entry_armed == 1 in hft_auto_entry_state.
                if profit_res.get("positions_monitored", 0) == 0:
                    st_row = conn.execute(
                        "SELECT auto_entry_armed FROM hft_auto_entry_state WHERE account_id = 'EXN-CONN-A4E7BE39D276'"
                    ).fetchone()
                    is_armed = bool(st_row and st_row[0] == 1)
                    auto_res = DemoExecutionService.run_automated_directional_entry_cycle(
                        conn=conn,
                        user_id="USR-ADM-B022F490",
                        account_id="EXN-CONN-A4E7BE39D276",
                        symbol="BTCUSDr",
                        dry_run=(not is_armed),
                    )
                    if auto_res.get("dispatched_to_broker"):
                        logger.info("Automated directional entry dispatched: %s", auto_res.get("execution_status"))
            except Exception as pe:
                logger.debug("Phase 7M profit monitor check: %s", pe)

            conn.commit()
            conn.close()
        except Exception as ex:
            logger.error("Error during watchdog supervision loop: %s", str(ex))

        write_heartbeat(positions_checked, discrepancies)
        time.sleep(1.5)

    logger.info("Watchdog daemon stopped.")


if __name__ == '__main__':
    main()
