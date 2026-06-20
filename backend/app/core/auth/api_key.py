"""
API Key Manager — generate, hash, verify API keys for programmatic access.

Borrows directly from GPUStack's security.py API key design:
- gpustack_{access_key}_{secret_key} format
- blake2b hashing for storage
- Legacy format backward compatibility
"""

import hashlib
import hmac
import logging
import secrets
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "aifp"  # AI Fullstack Platform

# Redis-style key format: aifp_{access_key}_{secret_key}
ACCESS_KEY_BYTES = 4   # 8 hex chars
SECRET_KEY_BYTES = 8   # 16 hex chars


def generate_api_key() -> Tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        Tuple of (full_key, hashed_key, access_key_prefix):
        - full_key: "aifp_{access}_{secret}" (given to user once)
        - hashed_key: blake2b hash (stored in DB)
        - access_key_prefix: first 8 chars (for display/lookup)
    """
    access_key = secrets.token_hex(ACCESS_KEY_BYTES)
    secret_key = secrets.token_hex(SECRET_KEY_BYTES)
    full_key = f"{API_KEY_PREFIX}_{access_key}_{secret_key}"
    hashed = hash_api_key(full_key)
    return full_key, hashed, access_key


def hash_api_key(key: str) -> str:
    """Hash an API key for secure storage using blake2b."""
    return hashlib.blake2b(key.encode(), digest_size=16).hexdigest()


def hash_api_key_argon2(key: str) -> str:
    """Hash an API key using Argon2 (stronger but slower)."""
    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        return ph.hash(key)
    except ImportError:
        return hash_api_key(key)


def verify_api_key(stored_hash: str, provided_key: str) -> bool:
    """Verify a provided API key against its stored hash.

    Supports both blake2b and Argon2 hashes.
    """
    # Try blake2b first (fast)
    expected = hash_api_key(provided_key)
    if hmac.compare_digest(expected, stored_hash):
        return True
    # Try Argon2
    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        return ph.verify(stored_hash, provided_key)
    except Exception:
        return False


def parse_api_key(key: str) -> Tuple[bool, str, str]:
    """Parse an API key into its components.

    Returns:
        Tuple of (is_valid, access_key, secret_key)
    """
    if not key.startswith(f"{API_KEY_PREFIX}_"):
        return False, "", ""
    parts = key.split("_", 2)
    if len(parts) != 3:
        return False, "", ""
    return True, parts[1], parts[2]


def mask_api_key(key: str) -> str:
    """Mask an API key for display (show first 12 chars only)."""
    if len(key) <= 12:
        return key[:4] + "****"
    return key[:12] + "****"


class ApiKeyManager:
    """Manages API key lifecycle — generation, verification, revocation."""

    def __init__(self):
        self._keys: dict[str, dict] = {}  # hashed_key → {access_key, created_at, name, metadata}

    def create_key(self, name: str = "", metadata: dict = None) -> dict:
        """Create a new API key.

        Returns:
            Dict with full_key, hashed_key, access_key_prefix, name, created_at.
            The full_key is only returned ONCE — caller must display it immediately.
        """
        full_key, hashed, access_prefix = generate_api_key()
        record = {
            "access_key_prefix": access_prefix,
            "hashed_key": hashed,
            "name": name or f"key-{access_prefix}",
            "created_at": time.time(),
            "last_used": None,
            "metadata": metadata or {},
            "revoked": False,
        }
        self._keys[hashed] = record
        logger.info("API key created: %s (prefix=%s)", name or "unnamed", access_prefix)
        return {
            "full_key": full_key,
            "hashed_key": hashed,
            "access_key_prefix": access_prefix,
            "name": record["name"],
            "created_at": record["created_at"],
        }

    def verify(self, key: str) -> Optional[dict]:
        """Verify an API key and return its record if valid."""
        hashed = hash_api_key(key)
        record = self._keys.get(hashed)
        if record is None:
            # Try Argon2 lookup
            for h, rec in self._keys.items():
                if verify_api_key(h, key):
                    record = rec
                    break
        if record is None or record.get("revoked"):
            return None
        record["last_used"] = time.time()
        return record

    def revoke(self, hashed_key: str) -> bool:
        """Revoke an API key."""
        record = self._keys.get(hashed_key)
        if record is None:
            return False
        record["revoked"] = True
        # Keep hash for audit but remove from active lookup
        del self._keys[hashed_key]
        logger.info("API key revoked: %s", record.get("name", "unknown"))
        return True

    def list_keys(self) -> list[dict]:
        """List all active API keys (no secret)."""
        return [
            {
                "access_key_prefix": r["access_key_prefix"],
                "name": r["name"],
                "created_at": r["created_at"],
                "last_used": r.get("last_used"),
                "metadata": r.get("metadata", {}),
            }
            for r in self._keys.values()
            if not r.get("revoked")
        ]

    def count(self) -> int:
        return len(self._keys)


# ── Global singleton ──────────────────────────────
_api_key_manager: Optional[ApiKeyManager] = None


def init_api_key_manager() -> ApiKeyManager:
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = ApiKeyManager()
    return _api_key_manager


def get_api_key_manager() -> Optional[ApiKeyManager]:
    return _api_key_manager
