"""
Refresh Token Manager — long-lived refresh tokens with rotation and revocation.

Extends the existing JWT access token system with a refresh token flow:
1. Login → access_token (short-lived, 30 min) + refresh_token (long-lived, 7 days)
2. Access token expires → POST /auth/refresh with refresh_token
3. Issue new access_token + rotate refresh_token (one-time use)
4. Revocation on logout or token reuse detection
"""

import logging
import secrets
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

REFRESH_TOKEN_BYTES = 48  # 96 hex chars


def generate_refresh_token() -> str:
    """Generate a cryptographically random refresh token."""
    return secrets.token_hex(REFRESH_TOKEN_BYTES)


class RefreshTokenManager:
    """Manages refresh token lifecycle with rotation and reuse detection."""

    def __init__(self, default_ttl_seconds: int = 7 * 24 * 3600):
        """
        Args:
            default_ttl_seconds: Default token lifetime (default 7 days).
        """
        self._default_ttl = default_ttl_seconds
        self._tokens: dict[str, dict] = {}       # token_hash → {user_id, family_id, ...}
        self._families: dict[str, dict] = {}     # family_id → {token_hash, issued_at, ...}
        self._used_tokens: set[str] = set()      # Reuse detection set

    def issue(self, user_id: str, family_id: Optional[str] = None) -> Tuple[str, str]:
        """Issue a new refresh token.

        Args:
            user_id: User identifier.
            family_id: Token family for rotation (None = new family).

        Returns:
            Tuple of (refresh_token_string, token_family_id).
        """
        token = generate_refresh_token()
        token_hash = _hash_token(token)

        if family_id is None:
            family_id = secrets.token_hex(8)

        now = time.time()
        record = {
            "user_id": user_id,
            "family_id": family_id,
            "issued_at": now,
            "expires_at": now + self._default_ttl,
            "last_rotated_at": now,
        }
        self._tokens[token_hash] = record
        self._families[family_id] = record

        logger.debug("Refresh token issued for user=%s, family=%s", user_id, family_id[:8])
        return token, family_id

    def rotate(self, old_token: str) -> Optional[Tuple[str, str, str]]:
        """Rotate a refresh token — invalidate old, issue new in same family.

        Returns:
            Tuple of (new_token, user_id, family_id) or None if invalid/reused.
        """
        old_hash = _hash_token(old_token)

        # Reuse detection: if this token was already used → revoke entire family
        if old_hash in self._used_tokens:
            record = self._tokens.get(old_hash)
            if record:
                self.revoke_family(record["family_id"])
                logger.warning("Refresh token reuse detected! Family %s revoked.",
                               record["family_id"][:8])
            return None

        # Mark as used
        self._used_tokens.add(old_hash)

        # Validate
        record = self._tokens.pop(old_hash, None)
        if record is None:
            return None
        if record["expires_at"] < time.time():
            return None

        # Issue new token in same family
        family_id = record["family_id"]
        new_token, _ = self.issue(record["user_id"], family_id)

        now = time.time()
        self._families[family_id]["last_rotated_at"] = now

        logger.debug("Refresh token rotated for family=%s", family_id[:8])
        return new_token, record["user_id"], family_id

    def verify(self, token: str) -> Optional[dict]:
        """Verify a refresh token is valid without rotating.

        Returns:
            Token record dict or None if invalid/expired.
        """
        token_hash = _hash_token(token)
        record = self._tokens.get(token_hash)
        if record is None:
            return None
        if token_hash in self._used_tokens:
            return None
        if record["expires_at"] < time.time():
            return None
        return record

    def revoke(self, token: str) -> bool:
        """Revoke a single refresh token."""
        token_hash = _hash_token(token)
        record = self._tokens.pop(token_hash, None)
        if record:
            self._used_tokens.add(token_hash)
            return True
        return False

    def revoke_family(self, family_id: str) -> int:
        """Revoke all tokens in a family (on reuse detection)."""
        count = 0
        to_remove = [
            h for h, r in self._tokens.items()
            if r["family_id"] == family_id
        ]
        for h in to_remove:
            self._used_tokens.add(h)
            del self._tokens[h]
            count += 1
        self._families.pop(family_id, None)
        return count

    def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user."""
        count = 0
        to_remove = [
            h for h, r in self._tokens.items()
            if r["user_id"] == user_id
        ]
        for h in to_remove:
            self._used_tokens.add(h)
            self._families.pop(self._tokens[h]["family_id"], None)
            del self._tokens[h]
            count += 1
        return count

    def cleanup_expired(self) -> int:
        """Remove expired tokens."""
        now = time.time()
        expired = [
            h for h, r in self._tokens.items()
            if r["expires_at"] < now
        ]
        for h in expired:
            del self._tokens[h]
        expired_families = [
            fid for fid, r in self._families.items()
            if r["expires_at"] < now
        ]
        for fid in expired_families:
            del self._families[fid]

        # Clean up used tokens set (>1 day old tokens don't need tracking)
        if len(self._used_tokens) > 10000:
            self._used_tokens.clear()
            logger.info("Cleared used tokens cache (size exceeded 10000)")

        return len(expired) + len(expired_families)

    @property
    def active_token_count(self) -> int:
        return len(self._tokens)


def _hash_token(token: str) -> str:
    """Hash a token for storage (SHA-256, not a password hash — speed matters here)."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


# ── Global singleton ──────────────────────────────
_refresh_token_manager: Optional[RefreshTokenManager] = None


def init_refresh_token_manager(ttl_seconds: int = 7 * 24 * 3600) -> RefreshTokenManager:
    global _refresh_token_manager
    if _refresh_token_manager is None:
        _refresh_token_manager = RefreshTokenManager(default_ttl_seconds=ttl_seconds)
    return _refresh_token_manager


def get_refresh_token_manager() -> Optional[RefreshTokenManager]:
    return _refresh_token_manager
