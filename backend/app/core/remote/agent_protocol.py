"""
Remote Agent Protocol — secure handshake and connection multiplexing.

Borrows concepts from OpenVSCode Server's remoteAgentConnection.ts:
- Three-step handshake protocol (Auth → Sign → ConnectionType)
- Connection type multiplexing (management / agent / tunnel)
- Connection token generation and verification

The protocol is transport-agnostic (works over WebSocket, SSE, or raw TCP).
"""

import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# Connection Types & States
# ═══════════════════════════════════════════════════

class ConnectionType(str, Enum):
    """Connection purpose — mirrors VS Code's ConnectionType enum."""
    MANAGEMENT = "management"        # Orchestration/control channel
    AGENT = "agent"                  # AI agent execution channel
    TUNNEL = "tunnel"               # Port forwarding / proxy channel
    STREAM = "stream"                # SSE / streaming channel


class AgentState(str, Enum):
    """Remote agent lifecycle states."""
    DISCONNECTED = "disconnected"
    HANDSHAKING = "handshaking"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    SHUTDOWN = "shutdown"


# ═══════════════════════════════════════════════════
# Protocol Messages
# ═══════════════════════════════════════════════════

@dataclass
class AuthRequest:
    """Step 1: Client sends authentication challenge."""
    type: str = "auth"
    token: str = ""                  # Connection token
    client_version: str = "1.0"
    client_id: str = ""
    timestamp: int = 0


@dataclass
class SignRequest:
    """Step 2: Server sends signing challenge."""
    type: str = "sign"
    nonce: str = ""                  # Random nonce for client to sign
    server_version: str = "1.0"
    server_id: str = ""


@dataclass
class ConnectionTypeRequest:
    """Step 3: Client specifies desired connection type."""
    type: str = "connection_type"
    desired_type: ConnectionType = ConnectionType.AGENT
    signed_nonce: str = ""           # HMAC of nonce with token
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OKMessage:
    """Success response."""
    type: str = "ok"
    connection_id: str = ""
    assigned_type: ConnectionType = ConnectionType.AGENT
    reconnection_grace_period: int = 30  # seconds


@dataclass
class ErrorMessage:
    """Error response."""
    type: str = "error"
    code: str = ""
    reason: str = ""
    retry_after: int = 5  # seconds before retry allowed


@dataclass
class HeartbeatMessage:
    """Periodic keep-alive."""
    type: str = "heartbeat"
    connection_id: str = ""
    timestamp: int = 0


# ═══════════════════════════════════════════════════
# Connection Token Manager
# ═══════════════════════════════════════════════════

class ConnectionTokenManager:
    """Manages secure connection tokens for remote agent authentication."""

    TOKEN_BYTES = 32
    HMAC_KEY_BYTES = 32

    def __init__(self):
        self._hmac_key = secrets.token_bytes(self.HMAC_KEY_BYTES)
        self._active_tokens: dict[str, dict] = {}  # connection_id → {token_hash, metadata}
        self._token_connection_map: dict[str, str] = {}  # token → connection_id

    def generate_token(self, connection_id: str, metadata: dict = None) -> str:
        """Generate a new connection token."""
        token = secrets.token_hex(self.TOKEN_BYTES)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self._active_tokens[connection_id] = {
            "token_hash": token_hash,
            "created_at": time.time(),
            "metadata": metadata or {},
        }
        self._token_connection_map[token] = connection_id
        return token

    def verify_token(self, token: str) -> Optional[str]:
        """Verify a token and return the connection_id, or None if invalid."""
        connection_id = self._token_connection_map.get(token)
        if connection_id is None:
            return None
        record = self._active_tokens.get(connection_id)
        if record is None:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(token_hash, record["token_hash"]):
            return None
        return connection_id

    def revoke_token(self, connection_id: str) -> bool:
        """Revoke a connection token."""
        for token, cid in list(self._token_connection_map.items()):
            if cid == connection_id:
                del self._token_connection_map[token]
                break
        return self._active_tokens.pop(connection_id, None) is not None

    def sign_nonce(self, nonce: str, connection_id: str) -> Optional[str]:
        """Sign a nonce for a connection (used in step 2-3 of handshake)."""
        record = self._active_tokens.get(connection_id)
        if record is None:
            return None
        payload = f"{nonce}:{connection_id}:{record['token_hash']}"
        return hmac.new(self._hmac_key, payload.encode(), hashlib.sha256).hexdigest()

    def verify_signed_nonce(self, nonce: str, connection_id: str, signed: str) -> bool:
        """Verify a signed nonce matches."""
        expected = self.sign_nonce(nonce, connection_id)
        if expected is None:
            return False
        return hmac.compare_digest(expected, signed)

    def cleanup_expired(self, max_age_seconds: int = 3600) -> int:
        """Remove tokens older than max_age_seconds."""
        now = time.time()
        expired = [
            cid for cid, record in self._active_tokens.items()
            if now - record["created_at"] > max_age_seconds
        ]
        for cid in expired:
            self.revoke_token(cid)
        return len(expired)


# ═══════════════════════════════════════════════════
# Handshake Engine
# ═══════════════════════════════════════════════════

@dataclass
class HandshakeResult:
    """Result of a completed handshake."""
    success: bool
    connection_id: str
    connection_type: ConnectionType
    client_metadata: dict = field(default_factory=dict)
    error: Optional[ErrorMessage] = None


class HandshakeEngine:
    """Implements the three-step handshake protocol."""

    def __init__(self, token_manager: ConnectionTokenManager):
        self._token_manager = token_manager
        self._nonces: dict[str, tuple[str, float]] = {}  # connection_id → (nonce, created_at)

    def process_auth(self, req: AuthRequest) -> SignRequest | ErrorMessage:
        """Step 1: Validate auth token → return signing challenge."""
        connection_id = self._token_manager.verify_token(req.token)
        if connection_id is None:
            return ErrorMessage(
                code="AUTH_FAILED",
                reason="Invalid or expired connection token",
            )

        nonce = secrets.token_hex(16)
        self._nonces[connection_id] = (nonce, time.time())

        return SignRequest(
            nonce=nonce,
            server_version="1.0",
            server_id=connection_id,
        )

    def process_connection_type(self, req: ConnectionTypeRequest, connection_id: str) -> HandshakeResult:
        """Step 3: Validate signed nonce → establish connection."""
        nonce_record = self._nonces.get(connection_id)

        # Remove nonce (one-time use)
        if connection_id in self._nonces:
            del self._nonces[connection_id]

        if nonce_record is None:
            return HandshakeResult(
                success=False,
                connection_id=connection_id,
                connection_type=req.desired_type,
                error=ErrorMessage(code="NONCE_EXPIRED", reason="Nonce expired or already used"),
            )

        nonce, created_at = nonce_record
        if time.time() - created_at > 60:
            return HandshakeResult(
                success=False,
                connection_id=connection_id,
                connection_type=req.desired_type,
                error=ErrorMessage(code="NONCE_TIMEOUT", reason="Handshake timed out"),
            )

        if not self._token_manager.verify_signed_nonce(nonce, connection_id, req.signed_nonce):
            return HandshakeResult(
                success=False,
                connection_id=connection_id,
                connection_type=req.desired_type,
                error=ErrorMessage(code="SIGN_FAILED", reason="Invalid nonce signature"),
            )

        return HandshakeResult(
            success=True,
            connection_id=connection_id,
            connection_type=req.desired_type,
            client_metadata=req.metadata,
        )


# ═══════════════════════════════════════════════════
# Agent Session
# ═══════════════════════════════════════════════════

@dataclass
class AgentSession:
    """Tracks the state of a remote agent connection."""
    connection_id: str
    connection_type: ConnectionType
    state: AgentState = AgentState.HANDSHAKING
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    reconnection_attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    data_channels: dict[str, Any] = field(default_factory=dict)
