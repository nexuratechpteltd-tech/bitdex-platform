import time
import threading
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import contextmanager

class TelemetryManager:
    """
    Thread-safe telemetry and usage tracking manager for Tauric (DeepSeek) and Jev.
    Tracks live in-flight activity, token counts, request rates, budgets, and detailed audit logs.
    """
    def __init__(self, daily_budget: int = 500000):
        self._lock = threading.Lock()
        self.daily_budget = daily_budget
        self.active_requests = {"tauric": 0, "jev": 0}
        self.last_active_until = {"tauric": 0.0, "jev": 0.0}
        
        self.model_breakdown = {
            "deepseek-v4-flash": {"requests": 0, "total_tokens": 0, "tier": "standard"},
            "deepseek-v4-pro-0813": {"requests": 0, "total_tokens": 0, "tier": "premium"}
        }

        # Audit log of all provider requests (in-memory circular buffer, max 500 records)
        self.audit_logs: List[Dict[str, Any]] = []
        
        self.session_data = {
            "tauric": {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
                "calls_without_usage": 0,
                "tokens_tracked": False,
                "last_request_at": None,
                "last_model": "deepseek-v4-flash",
                "last_duration_ms": 0,
                "current_operation": "Idle",
                "daily_tokens_used": 0,
                "budget_exceeded": False,
                "retry_count": 0,
                "failed_calls": 0,
                "cancelled_before_call": 0
            },
            "jev": {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
                "calls_without_usage": 0,
                "tokens_tracked": False,
                "last_request_at": None,
                "last_model": "jev-1.13.0",
                "last_duration_ms": 0,
                "current_operation": "Idle",
                "daily_tokens_used": 0,
                "budget_exceeded": False,
                "retry_count": 0,
                "failed_calls": 0,
                "cancelled_before_call": 0
            }
        }

    def log_provider_call(
        self,
        provider: str,
        model: str,
        job_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        created_by_action: str = "EXPLICIT_ACTION",
        strategy: str = "UNKNOWN",
        pair: str = "UNKNOWN",
        status: str = "SUCCESS",
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        req_id = request_id or str(uuid.uuid4())
        record = {
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "provider": provider,
            "model": model,
            "job_id": job_id,
            "parent_id": parent_id,
            "created_by_action": created_by_action,
            "strategy": strategy,
            "pair": pair,
            "request_id": req_id,
            "status": status,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens or (input_tokens + output_tokens)
        }
        with self._lock:
            self.audit_logs.append(record)
            if len(self.audit_logs) > 500:
                self.audit_logs = self.audit_logs[-500:]
        return record

    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self.audit_logs[-limit:]))

    @contextmanager
    def track_request(self, provider: str, operation: str = "Request", model: Optional[str] = None):
        provider_key = provider.lower()
        if provider_key not in self.active_requests:
            provider_key = "tauric"

        start_time = time.time()
        with self._lock:
            self.active_requests[provider_key] += 1
            self.session_data[provider_key]["current_operation"] = operation
            if model:
                self.session_data[provider_key]["last_model"] = model
                if model in self.model_breakdown:
                    self.model_breakdown[model]["requests"] += 1

        try:
            yield
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            now_iso = datetime.now().strftime("%H:%M:%S")
            with self._lock:
                self.active_requests[provider_key] = max(0, self.active_requests[provider_key] - 1)
                # Apply visual latch of 1.0s only if real in-flight requests just finished
                if self.active_requests[provider_key] == 0:
                    self.last_active_until[provider_key] = time.time() + 1.0
                self.session_data[provider_key]["request_count"] += 1
                self.session_data[provider_key]["last_request_at"] = now_iso
                self.session_data[provider_key]["last_duration_ms"] = duration_ms
                if self.active_requests[provider_key] == 0:
                    self.session_data[provider_key]["current_operation"] = "Idle"

    def record_retry(self, provider: str = "tauric"):
        provider_key = provider.lower()
        with self._lock:
            if provider_key in self.session_data:
                self.session_data[provider_key]["retry_count"] += 1

    def record_failure(self, provider: str = "tauric"):
        provider_key = provider.lower()
        with self._lock:
            if provider_key in self.session_data:
                self.session_data[provider_key]["failed_calls"] += 1

    def record_cancelled_before_call(self, provider: str = "tauric"):
        provider_key = provider.lower()
        with self._lock:
            if provider_key in self.session_data:
                self.session_data[provider_key]["cancelled_before_call"] += 1

    def clear_active(self, provider: Optional[str] = None):
        with self._lock:
            provs = [provider.lower()] if provider else ["tauric", "jev"]
            for p in provs:
                if p in self.active_requests:
                    self.active_requests[p] = 0
                    self.last_active_until[p] = 0.0
                    self.session_data[p]["current_operation"] = "Idle"

    def record_token_usage(self, provider: str, usage_dict: Optional[Dict[str, Any]], model: Optional[str] = None):
        provider_key = provider.lower()
        if provider_key not in self.session_data:
            provider_key = "tauric"

        with self._lock:
            data = self.session_data[provider_key]
            if model:
                data["last_model"] = model

            if not usage_dict or not isinstance(usage_dict, dict):
                data["calls_without_usage"] += 1
                return

            inp = usage_dict.get("input_tokens") or usage_dict.get("prompt_tokens") or 0
            out = usage_dict.get("output_tokens") or usage_dict.get("completion_tokens") or 0
            cached = usage_dict.get("cached_tokens") or usage_dict.get("prompt_cache_hit_tokens") or 0
            tot = usage_dict.get("total_tokens") or (inp + out)

            if inp > 0 or out > 0 or tot > 0:
                data["tokens_tracked"] = True
                data["input_tokens"] += inp
                data["output_tokens"] += out
                data["cached_tokens"] += cached
                data["total_tokens"] += tot
                data["daily_tokens_used"] += tot
                
                if model and model in self.model_breakdown:
                    self.model_breakdown[model]["total_tokens"] += tot

                if data["daily_tokens_used"] >= self.daily_budget:
                    data["budget_exceeded"] = True
            else:
                data["calls_without_usage"] += 1

    def reset_daily_budget(self):
        with self._lock:
            for prov in self.session_data:
                self.session_data[prov]["daily_tokens_used"] = 0
                self.session_data[prov]["budget_exceeded"] = False

    def is_budget_exceeded(self, provider: str) -> bool:
        provider_key = provider.lower()
        if provider_key not in self.session_data:
            provider_key = "tauric"
        with self._lock:
            return self.session_data[provider_key]["budget_exceeded"]

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            result = {}
            now = time.time()
            for prov in ["tauric", "jev"]:
                is_real_active = self.active_requests[prov] > 0
                is_recently_active = now < self.last_active_until.get(prov, 0.0)
                is_active_for_ui = is_real_active or is_recently_active
                
                s = self.session_data[prov]
                result[prov] = {
                    "provider": "Tauric (DeepSeek)" if prov == "tauric" else "TypeSafe Jev",
                    "status": "WORKING" if is_active_for_ui else "CONNECTED",
                    "is_active": is_active_for_ui,
                    "is_real_in_flight": is_real_active,
                    "recently_active": is_recently_active,
                    "active_requests_count": self.active_requests[prov],
                    "current_operation": s["current_operation"],
                    "request_count": s["request_count"],
                    "tokens_available": s["tokens_tracked"],
                    "known_tokens": s["total_tokens"],
                    "calls_without_usage": s["calls_without_usage"],
                    "input_tokens": s["input_tokens"] if s["tokens_tracked"] else None,
                    "output_tokens": s["output_tokens"] if s["tokens_tracked"] else None,
                    "cached_tokens": s["cached_tokens"] if s["tokens_tracked"] else None,
                    "total_tokens": s["total_tokens"] if s["tokens_tracked"] else None,
                    "daily_tokens_used": s["daily_tokens_used"],
                    "daily_budget": self.daily_budget,
                    "budget_exceeded": s["budget_exceeded"],
                    "retry_count": s["retry_count"],
                    "failed_calls": s["failed_calls"],
                    "cancelled_before_call": s["cancelled_before_call"],
                    "tokens_display": f"{s['total_tokens']:,}" if s["tokens_tracked"] else "Usage unavailable",
                    "last_request_at": s["last_request_at"],
                    "last_model": s["last_model"] or ("deepseek-v4-flash" if prov == "tauric" else "jev-1.13.0"),
                    "last_duration_ms": s["last_duration_ms"]
                }
            result["model_breakdown"] = self.model_breakdown
            return result

telemetry_manager = TelemetryManager()
