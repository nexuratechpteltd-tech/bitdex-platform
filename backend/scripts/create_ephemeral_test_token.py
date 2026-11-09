#!/usr/bin/env python3
import sys
import os
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
import jwt

sys.path.insert(0, '/opt/tauric-platform-staging/backend')
from app.services.saas_db import get_db_connection
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM

def mint_ephemeral_token(user_id: str, duration_minutes: int = 60) -> str:
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        if not user:
            raise ValueError(f'User {user_id} not found')
        
        session_id = f"SES-EPH-{secrets.token_hex(8).upper()}"
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=duration_minutes)
        exp_iso = exp.strftime("%Y-%m-%dT%H:%M:%SZ")
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        payload = {
            "sub": user["user_id"],
            "email": user["email"],
            "role": user["role"],
            "session_id": session_id,
            "remember_me": False,
            "exp": int(exp.timestamp())
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        
        conn.execute('''
            INSERT INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
        ''', (session_id, user["user_id"], token_hash, exp_iso, now_iso))
        conn.commit()
        return token
    finally:
        conn.close()

if __name__ == '__main__':
    uid = sys.argv[1] if len(sys.argv) > 1 else 'USR-904424B4FB'
    t = mint_ephemeral_token(uid)
    print(t)
