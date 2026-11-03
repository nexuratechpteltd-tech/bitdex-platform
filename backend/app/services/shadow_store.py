import os
import json
import sqlite3
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
SHADOW_DATA_DIR = Path(os.getenv("SHADOW_DATA_DIR", str(BACKEND_DIR / "data" / "shadow_validation")))
DB_PATH = SHADOW_DATA_DIR / "shadow_validation.db"
DECISIONS_DIR = SHADOW_DATA_DIR / "decisions"

def init_db(db_path: Path = DB_PATH):
    SHADOW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shadow_decisions (
        decision_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        current_price REAL NOT NULL,
        market_regime TEXT NOT NULL,
        market_snapshot_json TEXT,
        
        -- Track A: Tauric Only
        tauric_decision TEXT,
        tauric_direction TEXT,
        tauric_entry REAL,
        tauric_stop REAL,
        tauric_tp1 REAL,
        tauric_tp2 REAL,
        tauric_size TEXT,
        tauric_horizon TEXT,
        tauric_latency_ms INTEGER,
        
        -- Track B: Tauric + Jev
        reconciliation_result TEXT,
        agreement_status TEXT,
        veto_reason TEXT,
        blind_review_decision TEXT,
        blind_review_prob_agree REAL,
        blind_review_prob_disagree REAL,
        blind_review_confidence REAL,
        blind_review_risk_profile TEXT,
        blind_review_latency_ms INTEGER,
        
        -- Track C: Jev Fast Only
        jev_fast_decision TEXT,
        jev_fast_direction TEXT,
        jev_fast_entry REAL,
        jev_fast_stop REAL,
        jev_fast_tp1 REAL,
        jev_fast_tp2 REAL,
        jev_fast_confidence REAL,
        jev_fast_probabilities_json TEXT,
        jev_fast_latency_ms INTEGER,
        
        -- Outcomes Track A
        track_a_outcome TEXT DEFAULT 'PENDING',
        track_a_mfe REAL DEFAULT 0.0,
        track_a_mae REAL DEFAULT 0.0,
        track_a_gross_pnl REAL DEFAULT 0.0,
        track_a_fees REAL DEFAULT 0.0,
        track_a_slippage REAL DEFAULT 0.0,
        track_a_net_pnl REAL DEFAULT 0.0,
        
        -- Outcomes Track B
        track_b_outcome TEXT DEFAULT 'PENDING',
        track_b_mfe REAL DEFAULT 0.0,
        track_b_mae REAL DEFAULT 0.0,
        track_b_gross_pnl REAL DEFAULT 0.0,
        track_b_fees REAL DEFAULT 0.0,
        track_b_slippage REAL DEFAULT 0.0,
        track_b_net_pnl REAL DEFAULT 0.0,
        
        -- Outcomes Track C
        track_c_outcome TEXT DEFAULT 'PENDING',
        track_c_mfe REAL DEFAULT 0.0,
        track_c_mae REAL DEFAULT 0.0,
        track_c_gross_pnl REAL DEFAULT 0.0,
        track_c_fees REAL DEFAULT 0.0,
        track_c_slippage REAL DEFAULT 0.0,
        track_c_net_pnl REAL DEFAULT 0.0,
        
        last_evaluated_at TEXT,
        is_evaluated INTEGER DEFAULT 0,
        run_ref_id TEXT
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_events (
        event_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        provider TEXT NOT NULL,
        latency_ms INTEGER,
        status TEXT NOT NULL,
        details_json TEXT
    );
    """)
    
    conn.commit()
    conn.close()

class ShadowValidationStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        init_db(self.db_path)

    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def record_decision(self, data: Dict[str, Any]) -> str:
        """Persists a complete 3-track shadow decision record."""
        symbol = data.get("symbol", "UNKNOWN").upper().replace("/", "-")
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = str(uuid.uuid4())[:8]
        decision_id = data.get("decision_id") or f"SHD-{symbol}-{ts_str}-{uid}"
        now_iso = datetime.now().isoformat()

        # Write full raw payload to JSON file
        json_file = DECISIONS_DIR / f"{decision_id}.json"
        full_payload = {**data, "decision_id": decision_id, "created_at": now_iso}
        try:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(full_payload, f, indent=2)
        except Exception as e:
            print(f"[ShadowStore File Warning]: {e}")

        # Insert into SQLite
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
        INSERT OR REPLACE INTO shadow_decisions (
            decision_id, timestamp, symbol, timeframe, current_price, market_regime, market_snapshot_json,
            tauric_decision, tauric_direction, tauric_entry, tauric_stop, tauric_tp1, tauric_tp2, tauric_size, tauric_horizon, tauric_latency_ms,
            reconciliation_result, agreement_status, veto_reason, blind_review_decision,
            blind_review_prob_agree, blind_review_prob_disagree, blind_review_confidence, blind_review_risk_profile, blind_review_latency_ms,
            jev_fast_decision, jev_fast_direction, jev_fast_entry, jev_fast_stop, jev_fast_tp1, jev_fast_tp2,
            jev_fast_confidence, jev_fast_probabilities_json, jev_fast_latency_ms,
            track_a_outcome, track_a_net_pnl, track_b_outcome, track_b_net_pnl, track_c_outcome, track_c_net_pnl,
            run_ref_id
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?
        )
        """, (
            decision_id,
            data.get("timestamp", now_iso),
            symbol,
            data.get("timeframe", "1h"),
            float(data.get("current_price", 0.0)),
            data.get("market_regime", "range_chop"),
            json.dumps(data.get("market_snapshot", {})),
            
            # Track A
            data.get("tauric_decision", "HOLD"),
            data.get("tauric_direction", "FLAT"),
            float(data.get("tauric_entry") or data.get("current_price") or 0.0),
            float(data.get("tauric_stop") or 0.0),
            float(data.get("tauric_tp1") or 0.0),
            float(data.get("tauric_tp2") or 0.0),
            str(data.get("tauric_size", "1.0")),
            str(data.get("tauric_horizon", "Intraday")),
            int(data.get("tauric_latency_ms", 0)),
            
            # Track B
            data.get("reconciliation_result", "NO_TRADE"),
            data.get("agreement_status", "DISAGREE"),
            data.get("veto_reason", ""),
            data.get("blind_review_decision", "DISAGREE"),
            float(data.get("blind_review_prob_agree", 0.0)),
            float(data.get("blind_review_prob_disagree", 0.0)),
            float(data.get("blind_review_confidence", 0.0)),
            str(data.get("blind_review_risk_profile", "acceptable_risk")),
            int(data.get("blind_review_latency_ms", 0)),
            
            # Track C
            data.get("jev_fast_decision", "WAIT"),
            data.get("jev_fast_direction", "FLAT"),
            float(data.get("jev_fast_entry") or data.get("current_price") or 0.0),
            float(data.get("jev_fast_stop") or 0.0),
            float(data.get("jev_fast_tp1") or 0.0),
            float(data.get("jev_fast_tp2") or 0.0),
            float(data.get("jev_fast_confidence", 0.0)),
            json.dumps(data.get("jev_fast_probabilities", {})),
            int(data.get("jev_fast_latency_ms", 0)),
            
            data.get("track_a_outcome", "PENDING"),
            float(data.get("track_a_net_pnl", 0.0)),
            data.get("track_b_outcome", "PENDING"),
            float(data.get("track_b_net_pnl", 0.0)),
            data.get("track_c_outcome", "PENDING"),
            float(data.get("track_c_net_pnl", 0.0)),
            data.get("run_ref_id", "")
        ))
        
        conn.commit()
        conn.close()
        return decision_id

    def update_outcomes(self, decision_id: str, outcomes: Dict[str, Any]):
        """Updates hypothetical trade outcomes and P/L metrics for a decision."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        now_iso = datetime.now().isoformat()
        cursor.execute("""
        UPDATE shadow_decisions SET
            track_a_outcome = ?,
            track_a_mfe = ?,
            track_a_mae = ?,
            track_a_gross_pnl = ?,
            track_a_fees = ?,
            track_a_slippage = ?,
            track_a_net_pnl = ?,
            
            track_b_outcome = ?,
            track_b_mfe = ?,
            track_b_mae = ?,
            track_b_gross_pnl = ?,
            track_b_fees = ?,
            track_b_slippage = ?,
            track_b_net_pnl = ?,
            
            track_c_outcome = ?,
            track_c_mfe = ?,
            track_c_mae = ?,
            track_c_gross_pnl = ?,
            track_c_fees = ?,
            track_c_slippage = ?,
            track_c_net_pnl = ?,
            
            last_evaluated_at = ?,
            is_evaluated = 1
        WHERE decision_id = ?
        """, (
            outcomes.get("track_a_outcome", "PENDING"),
            float(outcomes.get("track_a_mfe", 0.0)),
            float(outcomes.get("track_a_mae", 0.0)),
            float(outcomes.get("track_a_gross_pnl", 0.0)),
            float(outcomes.get("track_a_fees", 0.0)),
            float(outcomes.get("track_a_slippage", 0.0)),
            float(outcomes.get("track_a_net_pnl", 0.0)),
            
            outcomes.get("track_b_outcome", "PENDING"),
            float(outcomes.get("track_b_mfe", 0.0)),
            float(outcomes.get("track_b_mae", 0.0)),
            float(outcomes.get("track_b_gross_pnl", 0.0)),
            float(outcomes.get("track_b_fees", 0.0)),
            float(outcomes.get("track_b_slippage", 0.0)),
            float(outcomes.get("track_b_net_pnl", 0.0)),
            
            outcomes.get("track_c_outcome", "PENDING"),
            float(outcomes.get("track_c_mfe", 0.0)),
            float(outcomes.get("track_c_mae", 0.0)),
            float(outcomes.get("track_c_gross_pnl", 0.0)),
            float(outcomes.get("track_c_fees", 0.0)),
            float(outcomes.get("track_c_slippage", 0.0)),
            float(outcomes.get("track_c_net_pnl", 0.0)),
            
            now_iso,
            decision_id
        ))
        conn.commit()
        conn.close()

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Calculates 3-track performance, Jev veto telemetry, and agreement metrics."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM shadow_decisions ORDER BY timestamp DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        total_decisions = len(rows)

        # Helper to compute track performance
        def compute_track_stats(track_prefix: str, rows_subset: List[Dict[str, Any]]):
            decisions = len(rows_subset)
            wins = 0
            losses = 0
            ambiguous = 0
            net_pnl = 0.0
            pnl_series = []
            
            for r in rows_subset:
                out = r.get(f"{track_prefix}_outcome") or "PENDING"
                pnl = float(r.get(f"{track_prefix}_net_pnl") or 0.0)
                net_pnl += pnl
                pnl_series.append(pnl)
                
                if out.startswith("WIN"):
                    wins += 1
                elif out.startswith("LOSS"):
                    losses += 1
                elif out == "AMBIGUOUS":
                    ambiguous += 1

            # Max drawdown calculation
            peak = 0.0
            cum = 0.0
            max_dd = 0.0
            for p in pnl_series:
                cum += p
                if cum > peak:
                    peak = cum
                dd = peak - cum
                if dd > max_dd:
                    max_dd = dd

            return {
                "decisions": decisions,
                "wins": wins,
                "losses": losses,
                "ambiguous": ambiguous,
                "net_hypothetical_pnl": round(net_pnl, 2),
                "max_drawdown": round(max_dd, 2),
                "win_rate_percent": round((wins / (wins + losses) * 100), 1) if (wins + losses) > 0 else 0.0
            }

        # Track A: All decisions where Tauric had a trade direction (LONG or SHORT)
        tauric_active = [r for r in rows if r.get("tauric_direction") in ["LONG", "SHORT", "BUY", "SELL"]]
        tauric_stats = compute_track_stats("track_a", tauric_active if tauric_active else rows)
        tauric_stats["decisions"] = len(rows)

        # Track B: Only decisions approved by Jev (or where Tauric+Jev reconciled a trade)
        track_b_active = [r for r in rows if r.get("reconciliation_result") in ["APPROVED", "SHADOW_DECISION", "TRADE"]]
        track_b_stats = compute_track_stats("track_b", track_b_active)
        track_b_stats["decisions"] = len(rows)
        track_b_stats["jev_approvals"] = len(track_b_active)
        track_b_stats["jev_vetoes"] = len(rows) - len(track_b_active)

        # Track C: Jev Fast Only
        track_c_active = [r for r in rows if r.get("jev_fast_direction") in ["LONG", "SHORT"]]
        track_c_stats = compute_track_stats("track_c", track_c_active if track_c_active else rows)
        track_c_stats["decisions"] = len(rows)

        # Jev Veto Telemetry:
        # 1. Tauric proposed trade + Jev AGREED
        # 2. Tauric proposed trade + Jev VETOED
        vetoed_rows = [r for r in rows if r.get("tauric_direction") in ["LONG", "SHORT", "BUY", "SELL"] and r.get("agreement_status") == "DISAGREE"]
        agreed_rows = [r for r in rows if r.get("tauric_direction") in ["LONG", "SHORT", "BUY", "SELL"] and r.get("agreement_status") == "AGREE"]
        
        vetoed_trades_count = len(vetoed_rows)
        vetoed_that_would_have_lost = sum(1 for r in vetoed_rows if (r.get("track_a_outcome") or "").startswith("LOSS"))
        vetoed_that_would_have_won = sum(1 for r in vetoed_rows if (r.get("track_a_outcome") or "").startswith("WIN"))
        vetoed_ambiguous = sum(1 for r in vetoed_rows if r.get("track_a_outcome") == "AMBIGUOUS")
        vetoed_pending = sum(1 for r in vetoed_rows if r.get("track_a_outcome") in ["PENDING", None])

        # Agreement Telemetry
        agreed_count = sum(1 for r in rows if r.get("agreement_status") == "AGREE")
        disagreed_count = sum(1 for r in rows if r.get("agreement_status") == "DISAGREE")
        agreement_rate = round((agreed_count / total_decisions * 100), 1) if total_decisions > 0 else 0.0
        disagreement_rate = round((disagreed_count / total_decisions * 100), 1) if total_decisions > 0 else 0.0

        # Latencies
        tauric_latencies = [r.get("tauric_latency_ms", 0) for r in rows if r.get("tauric_latency_ms")]
        blind_latencies = [r.get("blind_review_latency_ms", 0) for r in rows if r.get("blind_review_latency_ms")]
        fast_latencies = [r.get("jev_fast_latency_ms", 0) for r in rows if r.get("jev_fast_latency_ms")]

        avg_tauric_lat = round(sum(tauric_latencies) / len(tauric_latencies)) if tauric_latencies else 0
        avg_blind_lat = round(sum(blind_latencies) / len(blind_latencies)) if blind_latencies else 0
        avg_fast_lat = round(sum(fast_latencies) / len(fast_latencies)) if fast_latencies else 0

        # Regime breakdown
        regimes: Dict[str, int] = {}
        for r in rows:
            reg = r.get("market_regime", "range_chop")
            regimes[reg] = regimes.get(reg, 0) + 1

        # Anomaly Detection Flags
        anomaly_flags = []
        if total_decisions >= 5:
            if agreement_rate >= 85.0:
                anomaly_flags.append({
                    "severity": "WARNING",
                    "code": "RUBBER_STAMPING_RISK",
                    "message": f"Agreement rate is {agreement_rate}%, approaching high threshold (>85%). Investigate possible rubber-stamping."
                })
            if disagreement_rate >= 90.0:
                anomaly_flags.append({
                    "severity": "INFO",
                    "code": "HIGH_DISAGREEMENT_REGIME",
                    "message": f"Disagreement rate is {disagreement_rate}%. Checking timeframe alignment and trade plan normalization."
                })

        return {
            "current_shadow_sample": total_decisions,
            "target_sample_goal": "Sufficient sample across multiple market regimes (100+ target)",
            "tracks": {
                "tauric_only": tauric_stats,
                "tauric_plus_jev": track_b_stats,
                "jev_fast_only": track_c_stats
            },
            "jev_veto_analysis": {
                "tauric_trades_vetoed_by_jev": vetoed_trades_count,
                "vetoed_trades_that_would_have_lost": vetoed_that_would_have_lost,
                "vetoed_trades_that_would_have_won": vetoed_that_would_have_won,
                "vetoed_ambiguous": vetoed_ambiguous,
                "vetoed_pending": vetoed_pending,
                "tauric_trades_jev_agreed": len(agreed_rows)
            },
            "agreement_telemetry": {
                "total_decisions": total_decisions,
                "agreed_count": agreed_count,
                "disagreed_count": disagreed_count,
                "agreement_rate_percent": agreement_rate,
                "disagreement_rate_percent": disagreement_rate,
                "api_failure_rate_percent": 0.0,
                "malformed_response_rate_percent": 0.0,
                "stale_data_rate_percent": 0.0,
                "avg_latencies_ms": {
                    "tauric_analysis": avg_tauric_lat,
                    "jev_blind_review": avg_blind_lat,
                    "jev_fast_screening": avg_fast_lat
                }
            },
            "market_regimes_covered": regimes,
            "anomaly_flags": anomaly_flags,
            "updated_at": datetime.now().isoformat()
        }

    def list_decisions(self, limit: int = 50, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        query = "SELECT * FROM shadow_decisions"
        params = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol.upper().replace("/", "-"))
            
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shadow_decisions WHERE decision_id = ?", (decision_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        res = dict(row)
        
        # Load full payload if JSON exists
        json_file = DECISIONS_DIR / f"{decision_id}.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    res["full_payload"] = json.load(f)
            except Exception:
                pass
        return res

shadow_store = ShadowValidationStore()
