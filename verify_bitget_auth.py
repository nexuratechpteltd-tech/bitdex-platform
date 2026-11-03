import sys, os, asyncio, json
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
for line in open('/opt/tauric-platform-staging/backend/.env'):
    if line.startswith('TAURIC_VAULT_KEY='):
        os.environ['TAURIC_VAULT_KEY'] = line.strip().split('=', 1)[1]
from app.services.exchange_framework import credential_vault, exchange_framework

pid = sys.argv[1] if len(sys.argv) > 1 else None
profs = [p for p in credential_vault.list_profiles() if p['exchange'] == 'BITGET']
if not pid:
    for p in profs:
        try:
            c = credential_vault.get_credentials(p['profile_id']) or {}
        except PermissionError:
            print(json.dumps({'profile_id': p['profile_id'], 'label': p.get('label'), 'decrypt': 'VAULT_INTEGRITY_FAIL (not queried)'})); continue
        print(json.dumps({
            'profile_id': p['profile_id'], 'label': p.get('label'), 'env': p['environment'],
            'product': p.get('product_type'), 'active': p.get('is_active'),
            'created': p.get('created_at_utc'), 'last_status': p.get('connection_status'),
            'has_key': bool(c.get('api_key')), 'has_secret': bool(c.get('api_secret')),
            'has_passphrase': bool(c.get('passphrase')), 'key_len': len(c.get('api_key') or ''),
        }))
    sys.exit(0)

c = credential_vault.get_credentials(pid)
if not c.get('passphrase'):
    print('RESULT: MISSING_PASSPHRASE - stopped before any private request'); sys.exit(0)
env, prod = c['environment'], c.get('product_type')
cfg = dict(c.get('custom_config') or {}); cfg['environment'] = env; cfg['product_type'] = prod
async def main():
    r = await exchange_framework.detect_account_capabilities(
        exchange='BITGET', credentials=c, custom_config=cfg, environment=env, product_type=prod)
    safe = {k: r.get(k) for k in ('status','connection_status','verification_label','actionable_error_code','provider_error_code','error','guidance','execution_ready')}
    safe['environment'], safe['product'] = env, prod
    safe['endpoints'] = [{k: e.get(k) for k in ('name','category','status','http_status','provider_error_code','error','url','path','method')} for e in r.get('endpoints', [])]
    safe['account_data_present'] = bool(r.get('account_data'))
    print(json.dumps(safe, indent=1, default=str))
try:
    asyncio.run(main())
except Exception as e:
    print('EXCEPTION:', type(e).__name__, str(e)[:300])
