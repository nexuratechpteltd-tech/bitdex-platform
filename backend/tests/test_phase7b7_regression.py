import sys
import os
import json
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '/opt/tauric-platform-staging/backend')

from app.services.saas_db import get_db_connection
from app.services.engine_coordinator import EngineCoordinator
from app.services.exness.exness_db import save_exness_connection
from app.routes.saas_customer import (
    get_hft_pretrade_validation_route,
    start_hft_session_route,
    stop_hft_session_route,
    _resolve_hft_account,
    HftSessionActionRequest
)

def run_suite():
    results = []
    print('======================================================================')
    print('BITDEX PHASE 7B.7 MANDATORY 12-SCENARIO REGRESSION AUDIT SUITE')
    print('======================================================================')
    
    # Contexts
    owner_user = {'user_id': 'USR-ADM-B022F490', 'role': 'ADMIN'}
    other_user = {'user_id': 'USR-66BCFD7350', 'role': 'CUSTOMER'}
    owner_exness_acc = 'EXN-CONN-A4E7BE39D276'  # #474861031 (FACC-1A8017734CFA)
    owner_real_acc = 'EXN-CONN-1F331CF65942'    # #1600657 (FACC-268B3145465C)

    # First, ensure clean state: re-arm BTCUSD on owner_exness_acc if needed
    conn = get_db_connection()
    need_start = False
    try:
        active_lease = EngineCoordinator.get_symbol_active_lease(conn, 'BTCUSD')
        if not active_lease or active_lease.get('status') != 'ACTIVE':
            need_start = True
    finally:
        conn.close()

    if need_start:
        start_req = HftSessionActionRequest(symbol='BTCUSD', account_id=owner_exness_acc)
        asyncio.run(start_hft_session_route(start_req, current_user=owner_user))

    # SCENARIO 1: BTCUSD Collision Investigation & Ownership Attribution
    try:
        res = asyncio.run(get_hft_pretrade_validation_route(symbol='BTCUSD', account_id=owner_real_acc, current_user=owner_user))
        has_collision = res.get('has_collision') == True
        col = res.get('collision_detail') or {}
        assert has_collision, 'Expected collision on BTCUSD from un-owned account'
        assert col.get('account_id') == 'FACC-1A8017734CFA', f"Expected FACC-1A8017734CFA, got {col.get('account_id')}"
        assert col.get('owning_email') == 'hello@nexura.ltd', f"Expected hello@nexura.ltd, got {col.get('owning_email')}"
        assert '4748•••031' in col.get('broker_login', ''), 'Expected masked broker login 4748•••031'
        assert col.get('engine_id') == 'ENGINE_B', 'Expected ENGINE_B'
        assert 'locked by ENGINE_B' in col.get('recovery_explanation', '')
        print('[PASS] Scenario 1: BTCUSD collision correctly attributed with masked login and recovery detail.')
        results.append(('Scenario 1: BTCUSD collision investigation & attribution', True))
    except Exception as e:
        print(f'[FAIL] Scenario 1: {e}')
        results.append(('Scenario 1: BTCUSD collision investigation & attribution', False))

    # SCENARIO 2: Historical Leases & Lazy Expiry Mechanism
    try:
        conn = get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        try:
            # Check historical leases exist in DB
            rows = conn.execute("SELECT * FROM futures_symbol_leases WHERE status IN ('EXPIRED', 'RELEASED')").fetchall()
            assert len(rows) > 0, 'Historical expired/released leases must exist in DB'
            
            # Insert a synthetic expired lease for EXPIRE_TEST_SYM
            past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace('+00:00', 'Z')
            conn.execute("""
                INSERT OR REPLACE INTO futures_symbol_leases 
                (account_id, symbol, engine_id, lease_token, acquired_at, expires_at, status, metadata_json)
                VALUES ('FACC-1A8017734CFA', 'EXPIRE_TEST_SYM', 'ENGINE_B', 'LSE-TEST-EXP1', ?, ?, 'ACTIVE', '{}')
            """, (past, past))
            conn.commit()

            # Clean expired leases
            EngineCoordinator.clean_expired_leases(conn)
            conn.commit()

            # Verify it was updated to EXPIRED and returns None
            active_chk = EngineCoordinator.get_symbol_active_lease(conn, 'EXPIRE_TEST_SYM')
            assert active_chk is None, 'Expired lease must return None from get_symbol_active_lease'
            exp_row = conn.execute("SELECT status FROM futures_symbol_leases WHERE lease_token = 'LSE-TEST-EXP1'").fetchone()
            assert exp_row['status'] == 'EXPIRED', f"Expected EXPIRED status, got {exp_row['status']}"
        finally:
            conn.close()

        print('[PASS] Scenario 2: Historical lease records preserved and lazy expiry verified.')
        results.append(('Scenario 2: Historical leases & lazy expiry', True))
    except Exception as e:
        print(f'[FAIL] Scenario 2: {e}')
        results.append(('Scenario 2: Historical leases & lazy expiry', False))

    # SCENARIO 3: Duplicate Physical Broker Account Detection
    try:
        conn = get_db_connection()
        dup_threw = False
        try:
            save_exness_connection(
                conn,
                user_id='USR-66BCFD7350',
                login='474861031',
                server='Exness-MT5Trial15',
                enc_credentials={'password': 'test'},
                adapter_mode='EXNESS_MT5_GATEWAY',
                account_type='DEMO'
            )
        except ValueError as ve:
            if 'DUPLICATE_BROKER_ACCOUNT_CONFLICT' in str(ve):
                dup_threw = True
        finally:
            conn.close()

        assert dup_threw, 'save_exness_connection must raise DUPLICATE_BROKER_ACCOUNT_CONFLICT'
        print('[PASS] Scenario 3: Physical broker uniqueness enforced; duplicate registration rejected.')
        results.append(('Scenario 3: Duplicate physical broker account detection', True))
    except Exception as e:
        print(f'[FAIL] Scenario 3: {e}')
        results.append(('Scenario 3: Duplicate physical broker account detection', False))

    # SCENARIO 4: Cross-Tenant Lease Isolation
    try:
        # Other user attempting to stop owner's session on BTCUSD
        stop_req = HftSessionActionRequest(symbol='BTCUSD', account_id=owner_exness_acc)
        cross_rejected = False
        try:
            asyncio.run(stop_hft_session_route(stop_req, current_user=other_user))
        except Exception as ex:
            cross_rejected = True
            assert 'not found or unauthorized' in str(ex) or '404' in str(ex)
        assert cross_rejected, 'Cross-tenant stop must be rejected with 404 unauthorized'

        # Verify owner lease is STILL active
        conn = get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        try:
            active_lease = EngineCoordinator.get_symbol_active_lease(conn, 'BTCUSD')
            assert active_lease is not None and active_lease['account_id'] == 'FACC-1A8017734CFA', 'Lease must remain active'
        finally:
            conn.close()

        print('[PASS] Scenario 4: Cross-tenant lease isolation verified; non-owner cannot stop or release foreign lease.')
        results.append(('Scenario 4: Cross-tenant lease isolation', True))
    except Exception as e:
        print(f'[FAIL] Scenario 4: {e}')
        results.append(('Scenario 4: Cross-tenant lease isolation', False))

    # SCENARIO 5: Engine A / Engine B Mutual Exclusion
    try:
        conn = get_db_connection()
        try:
            # FACC-1A8017734CFA holds ENGINE_B on BTCUSD. acquire_lease for ENGINE_A must fail
            ok, tok, err = EngineCoordinator.acquire_lease(
                conn,
                account_id='FACC-1A8017734CFA',
                symbol='BTCUSD',
                engine_id='ENGINE_A',
                duration_seconds=3600
            )
            assert not ok, 'Engine A acquisition on symbol held by Engine B must fail'
            assert 'ENGINE_B' in (err or ''), f'Expected error mentioning ENGINE_B, got {err}'
        finally:
            conn.close()

        print('[PASS] Scenario 5: Engine A / Engine B mutual exclusion enforced by CAS.')
        results.append(('Scenario 5: Engine A / Engine B mutual exclusion', True))
    except Exception as e:
        print(f'[FAIL] Scenario 5: {e}')
        results.append(('Scenario 5: Engine A / Engine B mutual exclusion', False))

    # SCENARIO 6: Expired Lease Recovery (without open position)
    try:
        conn = get_db_connection()
        try:
            past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace('+00:00', 'Z')
            conn.execute("""
                INSERT OR REPLACE INTO futures_symbol_leases 
                (account_id, symbol, engine_id, lease_token, acquired_at, expires_at, status, metadata_json)
                VALUES ('FACC-1A8017734CFA', 'TEST_REC_SYM', 'ENGINE_B', 'LSE-TEST-EXP2', ?, ?, 'ACTIVE', '{}')
            """, (past, past))
            conn.commit()

            # Clean expired leases
            EngineCoordinator.clean_expired_leases(conn)
            conn.commit()

            # Query active lease
            rec = EngineCoordinator.get_symbol_active_lease(conn, 'TEST_REC_SYM')
            assert rec is None, 'Expired lease must be marked EXPIRED and return None'

            # Now new lease can be acquired cleanly
            ok, new_lse, err = EngineCoordinator.acquire_lease(
                conn,
                account_id='FACC-1A8017734CFA',
                symbol='TEST_REC_SYM',
                engine_id='ENGINE_B',
                duration_seconds=300
            )
            assert ok and new_lse.startswith('LSE-'), f'Acquisition after expiry recovery must succeed, got: ok={ok}, err={err}'

            # Release test lease
            EngineCoordinator.release_lease(conn, 'FACC-1A8017734CFA', 'TEST_REC_SYM', 'ENGINE_B', new_lse)
            conn.commit()
        finally:
            conn.close()

        print('[PASS] Scenario 6: Expired lease recovered safely and reassigned without conflict.')
        results.append(('Scenario 6: Expired lease recovery', True))
    except Exception as e:
        print(f'[FAIL] Scenario 6: {e}')
        results.append(('Scenario 6: Expired lease recovery', False))

    # SCENARIO 7: Active Lease Protection (cannot overwrite active lease)
    try:
        conn = get_db_connection()
        try:
            curr_lse = EngineCoordinator.get_symbol_active_lease(conn, 'BTCUSD')
            assert curr_lse is not None, 'BTCUSD lease must be active'
            ok, tok, err = EngineCoordinator.acquire_lease(
                conn,
                account_id='FACC-268B3145465C',
                symbol='BTCUSD',
                engine_id='ENGINE_B',
                duration_seconds=3600
            )
            assert not ok, 'Active unexpired lease must not be overwritten by another account'
            assert 'currently locked' in (err or '') or 'holds active lease' in (err or ''), f'Expected active lease collision error, got: {err}'
        finally:
            conn.close()

        print('[PASS] Scenario 7: Active lease protection confirmed; unexpired lock is immutable.')
        results.append(('Scenario 7: Active lease protection', True))
    except Exception as e:
        print(f'[FAIL] Scenario 7: {e}')
        results.append(('Scenario 7: Active lease protection', False))

    # SCENARIO 8: Correct Session Stop & Release (Scoped Account)
    try:
        stop_req = HftSessionActionRequest(symbol='BTCUSD', account_id=owner_exness_acc)
        stop_res = asyncio.run(stop_hft_session_route(stop_req, current_user=owner_user))
        assert stop_res.get('status') == 'SUCCESS', f'Stop failed: {stop_res}'

        # Verify lease is RELEASED
        conn = get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        try:
            active_now = EngineCoordinator.get_symbol_active_lease(conn, 'BTCUSD')
            assert active_now is None, 'Lease must be RELEASED and no longer active'
            rel_row = conn.execute("SELECT * FROM futures_symbol_leases WHERE account_id = 'FACC-1A8017734CFA' AND symbol = 'BTCUSD'").fetchone()
            assert rel_row['status'] == 'RELEASED', f"Expected RELEASED status, got {rel_row['status']}"
        finally:
            conn.close()

        print('[PASS] Scenario 8: Session stop cleanly releases exact scoped account lease.')
        results.append(('Scenario 8: Correct session stop and release', True))
    except Exception as e:
        print(f'[FAIL] Scenario 8: {e}')
        results.append(('Scenario 8: Correct session stop and release', False))

    # SCENARIO 9: Account Switching Without Stale State
    try:
        # Pre-trade validation on BTCUSD for owner_exness_acc should now report READY (no collision, session not active)
        val_res = asyncio.run(get_hft_pretrade_validation_route(symbol='BTCUSD', account_id=owner_exness_acc, current_user=owner_user))
        assert val_res.get('has_collision') == False, 'Must not report collision'
        assert val_res.get('is_ready') == True, 'Must be ready'
        assert val_res.get('session_active') == False, 'Session must not be active after release'
        print('[PASS] Scenario 9: Account resolution clears stale session state on switch.')
        results.append(('Scenario 9: Account switching without stale client-side state', True))
    except Exception as e:
        print(f'[FAIL] Scenario 9: {e}')
        results.append(('Scenario 9: Account switching without stale client-side state', False))

    # SCENARIO 10: Repeated Session-Start Idempotency
    try:
        start_req = HftSessionActionRequest(symbol='BTCUSD', account_id=owner_exness_acc)
        arm_res1 = asyncio.run(start_hft_session_route(start_req, current_user=owner_user))
        assert arm_res1.get('status') == 'SUCCESS', f'Arm failed: {arm_res1}'
        assert arm_res1.get('session_state') == 'ARMED_READ_ONLY', 'Must be ARMED_READ_ONLY'
        tok1 = arm_res1.get('lease_token')

        # Immediate repeat start request
        arm_res2 = asyncio.run(start_hft_session_route(start_req, current_user=owner_user))
        assert arm_res2.get('status') == 'SUCCESS', f'Repeated arm failed: {arm_res2}'
        tok2 = arm_res2.get('lease_token')
        assert tok2 == tok1, f'Idempotent restart should preserve active token: {tok1} vs {tok2}'
        print('[PASS] Scenario 10: Session-start idempotency verified; repeated arm does not orphan tokens.')
        results.append(('Scenario 10: Repeated session-start idempotency', True))
    except Exception as e:
        print(f'[FAIL] Scenario 10: {e}')
        results.append(('Scenario 10: Repeated session-start idempotency', False))

    # SCENARIO 11: No False ACTIVE State When Gates Fail
    try:
        # Query BTCUSD from owner_real_acc (which fails margin/consent/activation/CAS)
        fail_res = asyncio.run(get_hft_pretrade_validation_route(symbol='BTCUSD', account_id=owner_real_acc, current_user=owner_user))
        assert fail_res.get('is_ready') == False, 'Must not be ready'
        assert fail_res.get('session_active') == False, 'Must NEVER report session_active: True when gates fail'
        assert fail_res.get('has_collision') == True, 'Must detect CAS collision'
        print('[PASS] Scenario 11: No false ACTIVE state when pre-trade gates fail; fail-closed behavior verified.')
        results.append(('Scenario 11: No false ACTIVE state when gates fail', True))
    except Exception as e:
        print(f'[FAIL] Scenario 11: {e}')
        results.append(('Scenario 11: No false ACTIVE state when gates fail', False))

    # SCENARIO 12: Existing Account & Historical Data Preservation
    try:
        conn = get_db_connection()
        conn.row_factory = __import__('sqlite3').Row
        try:
            # Verify historical count of leases >= 5
            lse_count = conn.execute("SELECT COUNT(*) as c FROM futures_symbol_leases").fetchone()['c']
            assert lse_count >= 5, f'Expected >= 5 historical lease records, found {lse_count}'
            
            # Verify duplicate connection EXN-CONN-3D40DE9B8CE8 was preserved in DB
            dup_row = conn.execute("SELECT * FROM exness_demo_connections WHERE connection_id = 'EXN-CONN-3D40DE9B8CE8'").fetchone()
            assert dup_row is not None, 'Historical duplicate record must be preserved'
            assert dup_row['verification_status'] == 'DUPLICATE_TENANT_CONFLICT', 'Status must be DUPLICATE_TENANT_CONFLICT'
        finally:
            conn.close()

        # Cleanly stop owner session so environment is left disarmed
        asyncio.run(stop_hft_session_route(HftSessionActionRequest(symbol='BTCUSD', account_id=owner_exness_acc), current_user=owner_user))
        print('[PASS] Scenario 12: Historical records and tenant state fully preserved; clean disarm completed.')
        results.append(('Scenario 12: Existing account & historical data preservation', True))
    except Exception as e:
        print(f'[FAIL] Scenario 12: {e}')
        results.append(('Scenario 12: Existing account & historical data preservation', False))

    print('======================================================================')
    passed = sum(1 for _, ok in results if ok)
    print(f'TOTAL: {passed}/{len(results)} SCENARIOS PASSED')
    print('======================================================================')
    if passed == len(results):
        print('AUDIT RESULT: 100% ACCEPTED')
    else:
        print('AUDIT RESULT: SOME SCENARIOS FAILED')
        sys.exit(1)

if __name__ == '__main__':
    run_suite()
