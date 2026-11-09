"""
Execution gate token.

The final broker submission functions refuse live (non-dry-run) orders unless they are called
inside CentralRiskGate's execution context. This makes it structurally impossible for routes,
workers or scripts to submit a live Exness order without passing every risk check.
"""
import contextvars

_GATE_CONTEXT: contextvars.ContextVar = contextvars.ContextVar("bitdex_risk_gate_context", default=None)


class RiskGateBypassError(PermissionError):
    pass


def enter_gate(account_id: str, gate_ref: str):
    return _GATE_CONTEXT.set({"account_id": str(account_id), "gate_ref": gate_ref})


def exit_gate(token) -> None:
    _GATE_CONTEXT.reset(token)


def require_gate(account_id: str) -> None:
    ctx = _GATE_CONTEXT.get()
    if not ctx:
        raise RiskGateBypassError(
            "ERR_RISK_GATE_BYPASS: Live order submission is only permitted through CentralRiskGate."
        )
    if str(ctx.get("account_id")) != str(account_id):
        raise RiskGateBypassError(
            f"ERR_RISK_GATE_ACCOUNT_MISMATCH: Gate authorised account {ctx.get('account_id')}, not {account_id}."
        )
