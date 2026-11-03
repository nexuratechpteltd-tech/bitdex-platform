"""
Exness Secure Credential Vault
Provides AES-256-GCM authenticated encryption for Exness MT5 Demo credentials.
Binds cryptographic AAD to customer ID to guarantee tenant isolation and tamper detection.
Specification reference: Master Exness HFT Implementation Specification, Part 4.4 & Part 4.5.
"""

import json
import os
import secrets
import logging
from typing import Dict, Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("bitdex.exness.vault")


def _get_master_key() -> bytes:
    """Retrieves or derives the 256-bit AES master key from environment."""
    key_hex = os.getenv("TAURIC_VAULT_KEY") or os.getenv("BITDEX_VAULT_KEY")
    if key_hex:
        try:
            k = bytes.fromhex(key_hex)
            if len(k) == 32:
                return k
        except Exception:
            pass
    # Fallback to persistent local key or deterministic derivation
    seed = os.getenv("TAURIC_JWT_SECRET", "bitdex_exness_vault_master_secret_2026_xyz_secure")
    import hashlib
    return hashlib.sha256(seed.encode("utf-8")).digest()


class ExnessCredentialVault:
    """
    Cryptographic vault managing Exness MT5 credentials.
    Guarantees:
    - Passwords never stored in plaintext.
    - Passwords never written to logs.
    - Passwords never returned to frontend JavaScript.
    - Tenant isolation: Ciphertext bound to user_id via AES-GCM Associated Data (AAD).
    """

    @classmethod
    def encrypt_credentials(
        cls, user_id: str, login: str, password: str, server: str, account_type: str = "DEMO"
    ) -> Dict[str, str]:
        """
        Encrypts Exness credentials using AES-256-GCM authenticated encryption.
        AAD is bound to f'{user_id}:{login}:{server}'.
        """
        if not user_id or not login or not password or not server:
            raise ValueError("user_id, login, password, and server are required.")

        aad = f"{user_id}:{login}:{server}"
        payload = {
            "login": str(login).strip(),
            "password": str(password).strip(),
            "server": str(server).strip(),
            "account_type": account_type.upper(),
        }
        plaintext = json.dumps(payload)

        master_key = _get_master_key()
        aesgcm = AESGCM(master_key)
        nonce = secrets.token_bytes(12)  # 96-bit unique nonce

        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))

        return {
            "cipher": "AES-256-GCM",
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "aad_hash": str(hash(aad)),
        }

    @classmethod
    def decrypt_credentials(
        cls, user_id: str, login: str, server: str, enc_payload: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Decrypts Exness credentials and validates cryptographic integrity tag.
        Raises PermissionError if ciphertext, nonce, or user_id has been tampered with.
        """
        aad = f"{user_id}:{login}:{server}"
        master_key = _get_master_key()
        aesgcm = AESGCM(master_key)

        try:
            nonce = bytes.fromhex(enc_payload["nonce"])
            ciphertext = bytes.fromhex(enc_payload["ciphertext"])
            decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, aad.encode("utf-8"))
            return json.loads(decrypted_bytes.decode("utf-8"))
        except Exception as exc:
            logger.error(f"Vault decryption failed for user_id={user_id}: tampering or invalid key.")
            raise PermissionError(
                "Cryptographic vault verification failed. Credentials tampered or invalid tenant context."
            ) from exc

    @classmethod
    def mask_credentials(cls, creds: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns safe representation of credentials for client-side API response.
        Password is completely masked.
        """
        login_str = str(creds.get("login", ""))
        masked_login = login_str if len(login_str) <= 4 else f"{login_str[:2]}****{login_str[-2:]}"
        return {
            "login_masked": masked_login,
            "server": creds.get("server", ""),
            "account_type": creds.get("account_type", "DEMO"),
            "has_credentials": True,
            "password_masked": "••••••••",
        }
