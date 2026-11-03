# TAURIC — Final Bitget Private Authentication Verification
Date: 2026-10-23 (UTC). Scope: /opt/tauric-platform-staging/ only. Production untouched.

## Verdict
**Private authentication: NOT ATTEMPTED — blocked by MISSING_PASSPHRASE (preflight).**
Real Bitget private read-only authentication has NOT succeeded and is not proven either way. No private request was sent.

## 1. Saved profile metadata (no credentials printed)
| Field | Value |
|---|---|
| Profile ID | prof_bitget_demo_a2bb3478 |
| Label | Master |
| Environment | DEMO |
| Product | FUTURES_USDT (USDT-FUTURES / SUSDT demo, paptrading: 1) |
| Active | true |
| Created | 2026-10-23T11:46:29Z |
| API key present | yes (35 chars) |
| Secret present | yes |
| Passphrase present | **NO** |
| Last stored status | AUTHENTICATION_FAILED |

## 2. Action taken
- No profile created, edited, or overwritten.
- Passphrase absent -> result MISSING_PASSPHRASE; stopped before any private request.
- Therefore no HTTP status / provider code / signed request exists for this profile in this run (none fabricated).
- Intended request had it been present: GET /api/v2/mix/account/accounts?productType=USDT-FUTURES (read-only) with paptrading: 1.

## 3. Public vs private
Public Bitget market data (server time, contracts, ticker) succeeded in earlier runs. That does NOT count as authentication success. Private auth: unverified.

## 4. Root-cause assessment
Evidence points to **missing passphrase (credentials/configuration)**. Timestamp, signing, environment mismatch, IP restriction and adapter defect cannot be assessed or blamed: no private request has been made with a complete credential set. Not guessed.
**Required user action:** edit profile Master and enter the API passphrase set when the Bitget key was created (leave key/secret blank to keep them), then retest. Confirm the key was created for Bitget Demo trading, and whitelist egress IP 169.58.218.168 if IP-restricted.

## 5. Regression tests (fresh run on staging)
- test_claude_audit_repairs.py: 12/12 passed, exit 0
- test_add_api_ux_and_bitget_auth.py: 7/7 passed, exit 0

## 6. Safety
- POST /api/v1/orders/live/submit -> HTTP 403
- config: live_trading_locked=True, read_only_mode=True
- No orders placed/amended/cancelled, no fund movement. Production PM2 (ids 0,1) online, restart counts unchanged (16/17).

## 7. Caveats found
- The staging vault holds ~12 leftover Bitget TEST-FIXTURE profiles (labels 'Renamed Profile Label After Edit', 'Retest Override Invariant Test') that fail vault integrity decryption (AAD mismatch from tests that switched environment, and fixtures created under a different vault key). They use dummy keys, were not queried, and should be cleaned up with approval. The test suites should use an isolated vault path (TAURIC_VAULT_PATH).
- The earlier '46/46' claim covers mocked/unit tests; none performed real Bitget private auth.
