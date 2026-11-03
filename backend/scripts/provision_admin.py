#!/usr/bin/env python3
"""
Tauric Platform — Secure Server-Side Administrator Provisioning Script
Phase 3.5.0

Provisions an initial administrator account (e.g., hello@nexura.ltd) securely on staging.
Controls:
1. Checks whether the account already exists. Rejects duplicates.
2. Enforces role='ADMIN', verified email, and mandatory 2FA.
3. Generates a one-time invitation token for initial password setup.
4. If an initial password is provided via --password, sets it securely with bcrypt.
5. Emits an audit log entry.
6. Never prints secrets or plaintext credentials to stdout/logs.
"""

import sys
import os
import argparse

# Ensure backend root is on sys.path
backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_root, ".env"))

from app.services.saas_db import init_saas_db
from app.services.auth_manager import AuthManager, mask_email

def main():
    parser = argparse.ArgumentParser(description="Secure Administrator Provisioning")
    parser.add_argument("--email", default="hello@nexura.ltd", help="Admin email address")
    parser.add_argument("--password", default=None, help="Initial password (optional)")
    parser.add_argument("--first-name", default="System", help="First name")
    parser.add_argument("--last-name", default="Administrator", help="Last name")
    parser.add_argument("--country", default="SG", help="Country")
    args = parser.parse_args()

    print("[*] Initializing database schema...")
    init_saas_db()

    print(f"[*] Provisioning administrator account for {mask_email(args.email)}...")
    res = AuthManager.provision_admin(
        email=args.email,
        first_name=args.first_name,
        last_name=args.last_name,
        country=args.country,
        initial_password=args.password
    )

    if res.get("status") == "ALREADY_EXISTS":
        print(f"[!] {res['message']}")
        print(f"    User ID: {res['user_id']}")
        print(f"    Role: {res['role']}")
        return

    print("[+] Administrator provisioned successfully!")
    print(f"    User ID: {res['user_id']}")
    print(f"    Email: {res['email_masked']}")
    print(f"    Role: {res['role']}")
    print(f"    Email Verified: {res['email_verified']}")
    print(f"    2FA Enforced: {res['two_factor_enforced']}")
    print(f"    Must Change Password: {res['must_change_password']}")
    if "invitation_token" in res:
        inv = res["invitation_token"]
        print(f"    Invitation Token: {inv[:6]}...{inv[-6:]} (Expires: {res.get('invitation_expires')})")

if __name__ == "__main__":
    main()
