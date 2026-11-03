#!/usr/bin/env python3
"""
TAURIC Platform — Phase 1 Staging Implementation Script (Corrected)
Applies Product/Account Abstraction, Error Normalization Taxonomy,
and Retest Consistency strictly to /opt/tauric-platform-staging/.
Zero production modifications.
"""

import sys
import re

CONNECTIONS_FILE = "/opt/tauric-platform-staging/backend/app/routes/connections.py"

print("--- Patching connections.py ---")
with open(CONNECTIONS_FILE, "r") as f:
    conn_content = f.read()

# 1. Update imports
import_target = '''from ..services.exchange_framework import (
    credential_vault,
    exchange_framework,
    Environment,
    ExchangeId,
    VerificationLabel,
    ConnectionStatus,
    SigningMethod,
    validate_endpoint_url,
    SSRFValidationError
)'''

import_replacement = '''from ..services.exchange_framework import (
    credential_vault,
    exchange_framework,
    Environment,
    ExchangeId,
    VerificationLabel,
    ConnectionStatus,
    SigningMethod,
    ProductType,
    ErrorClassification,
    PROVIDER_SCHEMAS,
    validate_endpoint_url,
    SSRFValidationError
)'''

if "ProductType" not in conn_content:
    if import_target in conn_content:
        conn_content = conn_content.replace(import_target, import_replacement, 1)
        print("✓ Updated imports in connections.py")
    else:
        print("✗ Target for imports in connections.py not found")
        sys.exit(1)

# 2. Add product_type to request models
if "product_type: Optional[str] = Field(" not in conn_content:
    conn_content = conn_content.replace(
        'market_type: str = Field(default="CRYPTO", description="Market category: CRYPTO or FOREX")',
        'market_type: str = Field(default="CRYPTO", description="Market category: CRYPTO or FOREX")\n    product_type: Optional[str] = Field(None, description="Product category: SPOT, FUTURES_USDT, UNIFIED, FOREX_STANDARD, MT5_HEDGING, etc.")',
        1
    )
    conn_content = conn_content.replace(
        'market_type: Optional[str] = None  # Immutability strictly validated',
        'market_type: Optional[str] = None  # Immutability strictly validated\n    product_type: Optional[str] = None',
        1
    )
    conn_content = conn_content.replace(
        'market_type: Optional[str] = Field("CRYPTO", description="Market type (CRYPTO or FOREX)")',
        'market_type: Optional[str] = Field("CRYPTO", description="Market type (CRYPTO or FOREX)")\n    product_type: Optional[str] = Field(None, description="Product category: SPOT, FUTURES_USDT, UNIFIED, FOREX_STANDARD, etc.")',
        1
    )
    print("✓ Added product_type field to request models in connections.py")

# 3. Update save_profile endpoint
save_target = '''    try:
        profile = credential_vault.save_profile(
            exchange=exch,
            environment=env,
            market_type=market,
            label=req.label.strip(),
            api_key=req.api_key.strip(),
            api_secret=req.api_secret.strip(),
            passphrase=req.passphrase.strip() if req.passphrase else None,
            custom_config=req.custom_config,
            environment_preference=req.environment_preference,
            is_read_only=req.is_read_only,
            intended_permissions=req.intended_permissions
        )'''

save_replacement = '''    # Validate product_type and environment against provider schema
    schema = PROVIDER_SCHEMAS.get(exch)
    req_product = req.product_type
    if not req_product and req.custom_config:
        req_product = req.custom_config.get("product_type")
    req_product = str(req_product).strip().upper() if req_product else (schema.get("default_product") if schema else (ProductType.MT5_HEDGING.value if market == "FOREX" else ProductType.SPOT.value))

    if schema:
        valid_prods = [p["id"] for p in schema.get("supported_products", [])]
        if req_product not in valid_prods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product '{req_product}' is not supported by {exch}. Supported: {valid_prods}"
            )
        # Validate environment against selected product
        for p_info in schema.get("supported_products", []):
            if p_info["id"] == req_product:
                allowed_envs = p_info.get("supported_environments", ["LIVE"])
                if env not in allowed_envs:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Provider {exch} does not support {env} for product {req_product}. Supported: {allowed_envs}. {p_info.get('notes', '')}"
                    )

    saved_cfg = dict(req.custom_config or {})
    saved_cfg["product_type"] = req_product
    saved_cfg["environment"] = env

    try:
        profile = credential_vault.save_profile(
            exchange=exch,
            environment=env,
            market_type=market,
            label=req.label.strip(),
            api_key=req.api_key.strip(),
            api_secret=req.api_secret.strip(),
            passphrase=req.passphrase.strip() if req.passphrase else None,
            custom_config=saved_cfg,
            environment_preference=req.environment_preference,
            is_read_only=req.is_read_only,
            intended_permissions=req.intended_permissions,
            product_type=req_product
        )'''

if save_target in conn_content:
    conn_content = conn_content.replace(save_target, save_replacement, 1)
    print("✓ Updated save_profile endpoint with product validation and persistence")
else:
    print("✗ Target for save_profile in connections.py not found")
    sys.exit(1)

# 4. Update retest_profile endpoint
retest_target = '''    try:
        detection = await exchange_framework.detect_account_capabilities(
            exchange=creds["exchange"],
            credentials=creds,
            custom_config=custom_cfg
        )'''

retest_replacement = '''    saved_env = creds.get("environment", "DEMO")
    saved_prod = creds.get("product_type") or (custom_cfg.get("product_type") if custom_cfg else None) or ProductType.SPOT.value
    if custom_cfg is None:
        custom_cfg = {}
    custom_cfg["environment"] = saved_env
    custom_cfg["product_type"] = saved_prod

    try:
        detection = await exchange_framework.detect_account_capabilities(
            exchange=creds["exchange"],
            credentials=creds,
            custom_config=custom_cfg,
            environment=saved_env,
            product_type=saved_prod
        )'''

if retest_target in conn_content:
    conn_content = conn_content.replace(retest_target, retest_replacement, 1)
    print("✓ Updated retest_profile endpoint to forward environment and product_type")
else:
    print("✗ Target for retest_profile not found")
    sys.exit(1)

# 5. Update test_connection endpoint
test_target = '''    # Register environment & market in custom_cfg
    custom_cfg["environment"] = test_env
    custom_cfg["market_type"] = market'''

test_replacement = '''    # Resolve and validate product_type
    target_prod = req.product_type
    if not target_prod and req.custom_config:
        target_prod = req.custom_config.get("product_type")
    if not target_prod and req.profile_id:
        target_prod = creds.get("product_type")

    if not target_prod:
        schema = PROVIDER_SCHEMAS.get(exch)
        target_prod = schema.get("default_product") if schema else (ProductType.MT5_HEDGING.value if market == "FOREX" else ProductType.SPOT.value)
    target_prod = str(target_prod).strip().upper()

    # Pre-validation for product/env compatibility (e.g. Bitget Spot Demo)
    schema = PROVIDER_SCHEMAS.get(exch)
    if schema:
        for p_info in schema.get("supported_products", []):
            if p_info["id"] == target_prod:
                allowed_envs = p_info.get("supported_environments", ["LIVE"])
                if test_env not in allowed_envs:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Provider {exch} does not support {test_env} for product {target_prod}. Supported: {allowed_envs}. {p_info.get('notes', '')}"
                    )

    # Register environment, market & product in custom_cfg
    custom_cfg["environment"] = test_env
    custom_cfg["market_type"] = market
    custom_cfg["product_type"] = target_prod'''

if test_target in conn_content:
    conn_content = conn_content.replace(test_target, test_replacement, 1)
    print("✓ Updated test_connection endpoint to resolve product_type")
else:
    print("✗ Target for test_target not found")
    sys.exit(1)

# In test_connection call to detect_account_capabilities:
test_call_target = '''        detection = await exchange_framework.detect_account_capabilities(
            exchange=exch,
            credentials=creds,
            custom_config=custom_cfg,
            environment=test_env
        )'''

test_call_replacement = '''        detection = await exchange_framework.detect_account_capabilities(
            exchange=exch,
            credentials=creds,
            custom_config=custom_cfg,
            environment=test_env,
            product_type=target_prod
        )'''

if test_call_target in conn_content:
    conn_content = conn_content.replace(test_call_target, test_call_replacement, 1)
    print("✓ Updated detect_account_capabilities call in test_connection with product_type")
else:
    print("✗ Target for test_call_target not found")
    sys.exit(1)

# 6. Add GET /connections/providers/{provider_id}/schema endpoint
schema_endpoint = '''@connections_router.get("/providers/{provider_id}/schema")
async def get_provider_schema(provider_id: str):
    """Returns validated non-secret configuration and product schema for a provider."""
    prov_clean = provider_id.strip().upper()
    schema = PROVIDER_SCHEMAS.get(prov_clean)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found in registry."
        )
    return {"status": "SUCCESS", "schema": schema}


'''

if "@connections_router.get(\"/providers/{provider_id}/schema\")" not in conn_content:
    conn_content = conn_content.replace(
        '@connections_router.get("/capabilities")',
        schema_endpoint + '@connections_router.get("/capabilities")',
        1
    )
    print("✓ Added GET /connections/providers/{provider_id}/schema route")

with open(CONNECTIONS_FILE, "w") as f:
    f.write(conn_content)
print("✓ Successfully saved connections.py")
