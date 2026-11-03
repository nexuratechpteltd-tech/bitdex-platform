#!/usr/bin/env python3
"""
Backend Patch: Authoritative Server-Side Administrator Fee Exemption
Files:
  - /opt/tauric-platform-staging/backend/app/services/fee_engine.py
  - /opt/tauric-platform-staging/backend/app/routes/orders.py
  - /opt/tauric-platform-staging/backend/app/routes/saas_customer.py
"""

# 1. Patch fee_engine.py
with open("/opt/tauric-platform-staging/backend/app/services/fee_engine.py", "r") as f:
    fe_src = f.read()

# In get_user_fee_policy: add is_admin_fee_waiver_active enrichment
old_policy_ret = """            res = dict(row)
            if "ai_research_fee_cents" not in res or res["ai_research_fee_cents"] is None:
                res["ai_research_fee_cents"] = int(round(float(res.get("ai_research_fee_usd", 1.00)) * 100))
            return res"""

new_policy_ret = """            res = dict(row)
            if "ai_research_fee_cents" not in res or res["ai_research_fee_cents"] is None:
                res["ai_research_fee_cents"] = int(round(float(res.get("ai_research_fee_usd", 1.00)) * 100))
            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            if is_admin_waived:
                res["is_admin_exempt"] = True
                res["fee_waived"] = 1
                res["activation_fee_charged"] = 1
                res["activation_fee_enabled"] = 0
                res["execution_fee_enabled"] = 0
                res["ai_research_fee_enabled"] = 0
                res["waiver_reason"] = admin_reason
            else:
                res["is_admin_exempt"] = False
            return res"""

if old_policy_ret in fe_src:
    fe_src = fe_src.replace(old_policy_ret, new_policy_ret, 1)
    print("Patched get_user_fee_policy in fee_engine.py")

# In get_billing_account: add is_admin_exempt
old_acct_ret = """            res = dict(row)
            res["prepaid_credits_cents"] = int(round(float(res.get("prepaid_credits_usd", 0.0)) * 100))
            return res"""

new_acct_ret = """            res = dict(row)
            res["prepaid_credits_cents"] = int(round(float(res.get("prepaid_credits_usd", 0.0)) * 100))
            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            res["is_admin_exempt"] = is_admin_waived
            if is_admin_waived:
                res["admin_exemption_reason"] = admin_reason
            return res"""

if old_acct_ret in fe_src:
    fe_src = fe_src.replace(old_acct_ret, new_acct_ret, 1)
    print("Patched get_billing_account in fee_engine.py")

# In check_trading_preflight_eligibility: exempt admin unconditionally
old_preflight = """            if user["status"] == "SUSPENDED":
                return False, "Trading suspended: Account status is suspended."

            if environment.upper() == "LIVE":
                if user["kyc_status"] in ("REQUESTED", "PENDING"):
                    return False, "Trading blocked: KYC identity verification is required and currently pending."
                if user["kyc_status"] == "REJECTED":
                    return False, "Trading blocked: KYC identity verification was rejected."

            policy = FeeEngine.get_user_fee_policy(user_id)"""

new_preflight = """            if user["status"] == "SUSPENDED":
                return False, "Trading suspended: Account status is suspended."

            # Authoritative Server-Side Admin Fee Waiver Check
            is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id, conn=conn)
            if is_admin_waived:
                return True, None

            if environment.upper() == "LIVE":
                if user["kyc_status"] in ("REQUESTED", "PENDING"):
                    return False, "Trading blocked: KYC identity verification is required and currently pending."
                if user["kyc_status"] == "REJECTED":
                    return False, "Trading blocked: KYC identity verification was rejected."

            policy = FeeEngine.get_user_fee_policy(user_id)"""

if old_preflight in fe_src:
    fe_src = fe_src.replace(old_preflight, new_preflight, 1)
    print("Patched check_trading_preflight_eligibility in fee_engine.py")

with open("/opt/tauric-platform-staging/backend/app/services/fee_engine.py", "w") as f:
    f.write(fe_src)

# 2. Patch orders.py
with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "r") as f:
    orders_src = f.read()

# Fix fee_assessed fallback in grid order
old_orders_fee = """        fee_assessed = fee_receipt.get("fee_charged_usd", 0.30)"""
new_orders_fee = """        fee_assessed = fee_receipt.get("fee_charged_usd", 0.0)"""

if old_orders_fee in orders_src:
    orders_src = orders_src.replace(old_orders_fee, new_orders_fee, 1)
    print("Patched fee_assessed fallback in orders.py")

# In receipt, add admin_fee_exempt flag
old_receipt_fee = """        "fee_charged_usd": fee_assessed,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")"""

new_receipt_fee = """        "fee_charged_usd": fee_assessed,
        "admin_fee_exempt": bool(fee_receipt.get("status") == "ADMIN_EXEMPT"),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")"""

if old_receipt_fee in orders_src:
    orders_src = orders_src.replace(old_receipt_fee, new_receipt_fee, 1)
    print("Patched receipt admin_fee_exempt in orders.py")

with open("/opt/tauric-platform-staging/backend/app/routes/orders.py", "w") as f:
    f.write(orders_src)

# 3. Patch saas_customer.py
with open("/opt/tauric-platform-staging/backend/app/routes/saas_customer.py", "r") as f:
    cust_src = f.read()

old_me = """@customer_router.get("/customer/me")
async def get_my_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["user_id"]
    billing = FeeEngine.get_billing_account(user_id)
    policy = FeeEngine.get_user_fee_policy(user_id)
    ai_pricing = FeeEngine.get_effective_ai_analysis_price(user_id)
    return {
        "status": "SUCCESS",
        "user": current_user,
        "billing_summary": {
            "prepaid_credits_usd": billing.get("prepaid_credits_usd", 0.0),
            "prepaid_credits_cents": billing.get("prepaid_credits_cents", 0),
            "total_deposited_usd": billing.get("total_deposited_usd", 0.0),
            "total_fees_paid_usd": billing.get("total_fees_paid_usd", 0.0)
        },
        "fee_policy": policy,
        "ai_pricing": ai_pricing
    }"""

new_me = """@customer_router.get("/customer/me")
async def get_my_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["user_id"]
    billing = FeeEngine.get_billing_account(user_id)
    policy = FeeEngine.get_user_fee_policy(user_id)
    ai_pricing = FeeEngine.get_effective_ai_analysis_price(user_id)
    is_admin_waived, admin_reason = FeeEngine.is_admin_fee_waiver_active(user_id)
    return {
        "status": "SUCCESS",
        "user": current_user,
        "billing_summary": {
            "prepaid_credits_usd": billing.get("prepaid_credits_usd", 0.0),
            "prepaid_credits_cents": billing.get("prepaid_credits_cents", 0),
            "total_deposited_usd": billing.get("total_deposited_usd", 0.0),
            "total_fees_paid_usd": billing.get("total_fees_paid_usd", 0.0),
            "is_admin_exempt": is_admin_waived,
            "admin_exemption_reason": admin_reason if is_admin_waived else None
        },
        "fee_policy": policy,
        "ai_pricing": ai_pricing,
        "is_admin_exempt": is_admin_waived,
        "admin_exemption_reason": admin_reason if is_admin_waived else None
    }"""

if old_me in cust_src:
    cust_src = cust_src.replace(old_me, new_me, 1)
    print("Patched get_my_profile in saas_customer.py")

with open("/opt/tauric-platform-staging/backend/app/routes/saas_customer.py", "w") as f:
    f.write(cust_src)

print("All backend administrator fee exemption patches completed successfully!")
