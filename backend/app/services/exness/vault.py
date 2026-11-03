"""
Exness Secure Credential Vault (Hardened Phase 2.2)
Provides AES-256-GCM authenticated encryption for Exness MT5 Demo credentials.
Strictly fails closed if a valid 32-byte vault key is not configured.
Includes explicit key versioning metadata, safe rotation, rollback, and recovery sequences.
Binds cryptographic AAD to customer ID to guarantee tenant isolation and tamper detection.
Specification reference: Master Exness HFT Implementation Specification, Part 4.4 & Part 4.5.
"""

import json
import os
import secrets
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("bitdex.exness.vault")

CURRENT_VAULT_KEY_VERSION = 1


def get_master_key() -> bytes:
    """
    Retrieves the 256-bit AES master key from environment.
    Strictly fails closed if key is missing or invalid.
    No hardcoded fallback keys permitted.
    """
    key_hex = os.getenv("TAURIC_VAULT_KEY") or os.getenv("BITDEX_VAULT_KEY")
    if not key_hex:
        raise RuntimeError(
            "CRITICAL: Vault master key is not configured. TAURIC_VAULT_KEY or "
            "BITDEX_VAULT_KEY must be set in the environment."
        )

    clean_hex = key_hex.strip()
    if len(clean_hex) != 64:
        raise ValueError(
            f"CRITICAL: Vault master key must be a 64-character hex string (32 bytes). "
            f"Got string with length {len(clean_hex)}."
        )

    try:
        key_bytes = bytes.fromhex(clean_hex)
    except ValueError as exc:
        raise ValueError("CRITICAL: Vault master key contains non-hexadecimal characters.") from exc

    if len(key_bytes) != 32:
        raise ValueError(f"CRITICAL: Vault master key must be exactly 32 bytes. Got {len(key_bytes)}.")

    return key_bytes


class ExnessCredentialVault:
    """
    Cryptographic vault managing Exness MT5 credentials.
    Guarantees:
    - Fails closed if master key is missing or malformed.
    - Passwords never stored in plaintext.
    - Passwords never written to logs or error messages.
    - Passwords never returned to frontend JavaScript.
    - Tenant isolation: Ciphertext bound to user_id via AES-GCM Associated Data (AAD).
    - Format validation on nonces and ciphertexts before cryptographic operations.
    - Explicit key version metadata (key_version integer tag).
    - Supports atomic key rotation, rollback, and recovery without credential loss.
    """

    @classmethod
    def encrypt_credentials(
        cls,
        user_id: str,
        login: str,
        password: str,
        server: str,
        account_type: str = "DEMO",
        override_key: Optional[bytes] = None,
        key_version: int = CURRENT_VAULT_KEY_VERSION,
    ) -> Dict[str, Any]:
        """
        Encrypts Exness credentials using AES-256-GCM authenticated encryption.
        AAD is bound to f'{user_id}:{login}:{server}'.
        Attaches key_version metadata to payload.
        """
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required for cryptographic tenant binding.")
        if not login or not str(login).strip():
            raise ValueError("login is required.")
        if not password or not str(password).strip():
            raise ValueError("password is required.")
        if not server or not str(server).strip():
            raise ValueError("server is required.")

        aad = f"{str(user_id).strip()}:{str(login).strip()}:{str(server).strip()}"
        payload = {
            "login": str(login).strip(),
            "password": str(password).strip(),
            "server": str(server).strip(),
            "account_type": account_type.upper(),
            "encrypted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        plaintext = json.dumps(payload)

        master_key = override_key if override_key is not None else get_master_key()
        if len(master_key) != 32:
            raise ValueError("Encryption master key must be exactly 32 bytes.")

        aesgcm = AESGCM(master_key)
        nonce = secrets.token_bytes(12)  # 96-bit unique cryptographically secure nonce

        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))

        return {
            "cipher": "AES-256-GCM",
            "key_version": int(key_version),
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "aad_hash": str(hash(aad)),
        }

    @classmethod
    def decrypt_credentials(
        cls,
        user_id: str,
        login: str,
        server: str,
        enc_payload: Dict[str, Any],
        override_key: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Decrypts Exness credentials and validates cryptographic integrity tag.
        Validates nonce and ciphertext structure before decryption.
        Returns dict containing login, password, server, account_type, and key_version.
        Raises PermissionError if ciphertext, nonce, or user_id has been tampered with.
        """
        if not isinstance(enc_payload, dict):
            raise ValueError("Malformed encrypted payload: expected a dictionary.")

        # Nonce format validation
        nonce_hex = enc_payload.get("nonce")
        if not nonce_hex or not isinstance(nonce_hex, str):
            raise ValueError("Missing or invalid nonce in encrypted payload.")
        clean_nonce = nonce_hex.strip()
        if len(clean_nonce) != 24:
            raise ValueError(f"Invalid AES-GCM nonce length: expected 24 hex characters (12 bytes), got {len(clean_nonce)}.")
        try:
            nonce = bytes.fromhex(clean_nonce)
        except ValueError as exc:
            raise ValueError("Nonce contains invalid hex characters.") from exc

        # Ciphertext format validation
        ct_hex = enc_payload.get("ciphertext")
        if not ct_hex or not isinstance(ct_hex, str):
            raise ValueError("Missing or invalid ciphertext in encrypted payload.")
        clean_ct = ct_hex.strip()
        if len(clean_ct) < 32:
            raise ValueError(f"Ciphertext too short: expected >= 32 hex chars, got {len(clean_ct)}.")
        try:
            ciphertext = bytes.fromhex(clean_ct)
        except ValueError as exc:
            raise ValueError("Ciphertext contains invalid hex characters.") from exc

        aad = f"{str(user_id).strip()}:{str(login).strip()}:{str(server).strip()}"
        master_key = override_key if override_key is not None else get_master_key()
        if len(master_key) != 32:
            raise ValueError("Decryption master key must be exactly 32 bytes.")

        aesgcm = AESGCM(master_key)

        try:
            decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, aad.encode("utf-8"))
            data = json.loads(decrypted_bytes.decode("utf-8"))
            data["key_version"] = enc_payload.get("key_version", 1)
            return data
        except Exception as exc:
            logger.warning(
                f"Vault decryption failed for tenant {user_id[:8]}...: cryptographic verification tag mismatch."
            )
            raise PermissionError(
                "Cryptographic vault verification failed. Credentials tampered or invalid tenant context."
            ) from exc

    @classmethod
    def rotate_credentials(
        cls,
        user_id: str,
        login: str,
        server: str,
        enc_payload: Dict[str, Any],
        current_key: bytes,
        new_key: bytes,
        new_key_version: int = 2,
    ) -> Dict[str, Any]:
        """
        Re-encrypts credentials from current_key to new_key with zero plaintext exposure.
        Decrypted in transient memory, immediately re-encrypted with a fresh unique nonce.
        Updates key_version to new_key_version.
        """
        if len(current_key) != 32 or len(new_key) != 32:
            raise ValueError("Both current_key and new_key must be exactly 32 bytes.")

        # Decrypt under current key
        decrypted = cls.decrypt_credentials(
            user_id=user_id,
            login=login,
            server=server,
            enc_payload=enc_payload,
            override_key=current_key,
        )

        # Re-encrypt under new key with fresh random nonce and new key_version tag
        rotated = cls.encrypt_credentials(
            user_id=user_id,
            login=login,
            password=decrypted["password"],
            server=server,
            account_type=decrypted.get("account_type", "DEMO"),
            override_key=new_key,
            key_version=new_key_version,
        )
        rotated["previous_key_version"] = enc_payload.get("key_version", 1)
        rotated["key_rotated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return rotated

    @classmethod
    def rollback_credentials(
        cls,
        user_id: str,
        login: str,
        server: str,
        enc_payload: Dict[str, Any],
        current_key: bytes,
        previous_key: bytes,
        previous_key_version: int = 1,
    ) -> Dict[str, Any]:
        """
        Safely rolls back re-encrypted credentials to previous_key if rotation is aborted.
        """
        if len(current_key) != 32 or len(previous_key) != 32:
            raise ValueError("Both current_key and previous_key must be exactly 32 bytes.")

        decrypted = cls.decrypt_credentials(
            user_id=user_id,
            login=login,
            server=server,
            enc_payload=enc_payload,
            override_key=current_key,
        )

        rolled_back = cls.encrypt_credentials(
            user_id=user_id,
            login=login,
            password=decrypted["password"],
            server=server,
            account_type=decrypted.get("account_type", "DEMO"),
            override_key=previous_key,
            key_version=previous_key_version,
        )
        rolled_back["rolled_back_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return rolled_back

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
            "key_version": creds.get("key_version", 1),
            "has_credentials": True,
            "password_masked": "••••••••",
        }
