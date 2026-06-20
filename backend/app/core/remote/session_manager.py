"""
Remote Agent Session Manager — connection lifecycle and session tracking.

Orchestrates handshake, session tracking, heartbeat, and graceful disconnect.
"""

import asyncio
import logging
import time
from typing import Optional

from app.core.remote.agent_protocol import (
    AgentSession,
    AgentState,
    ConnectionType,
    ConnectionTokenManager,
    HandshakeEngine,
    AuthRequest,
    ConnectionTypeRequest,
    SignRequest,
    OKMessage,
    ErrorMessage,
    HeartbeatMessage,
    HandshakeResult,
)

logger = logging.getLogger(__name__)


class RemoteSessionManager:
    """Manages remote agent connection sessions."""

    def __init__(self):
        self._token_manager = ConnectionTokenManager()
        self._handshake = HandshakeEngine(self._token_manager)
        self._sessions: dict[str, AgentSession] = {}         # connection_id → session
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_timeout: float = 120.0               # seconds

    # ── Session Lifecycle ─────────────────────────
    def create_connection(self, metadata: dict = None) -> tuple[str, str]:
        """Create a new connection. Returns (connection_id, token)."""
        import uuid
        connection_id = uuid.uuid4().hex[:16]
        token = self._token_manager.generate_token(connection_id, metadata)
        return connection_id, token

    def start_session(self, connection_id: str, conn_type: ConnectionType) -> AgentSession:
        """Start tracking a session after successful handshake."""
        session = AgentSession(
            connection_id=connection_id,
            connection_type=conn_type,
            state=AgentState.CONNECTED,
        )
        self._sessions[connection_id] = session
        logger.info("Session started: %s (type=%s)", connection_id, conn_type.value)
        return session

    def end_session(self, connection_id: str) -> bool:
        """End a session and revoke its token."""
        session = self._sessions.pop(connection_id, None)
        if session:
            session.state = AgentState.SHUTDOWN
            self._token_manager.revoke_token(connection_id)
            logger.info("Session ended: %s", connection_id)
            return True
        return False

    def get_session(self, connection_id: str) -> Optional[AgentSession]:
        return self._sessions.get(connection_id)

    def list_sessions(self) -> list[AgentSession]:
        return list(self._sessions.values())

    def list_active_sessions(self) -> list[AgentSession]:
        return [s for s in self._sessions.values() if s.state == AgentState.CONNECTED]

    # ── Heartbeat ─────────────────────────────────
    def heartbeat(self, connection_id: str) -> bool:
        """Record a heartbeat for a session."""
        session = self._sessions.get(connection_id)
        if session is None:
            return False
        session.last_heartbeat = time.time()
        return True

    async def start_heartbeat_monitor(self, interval: float = 30.0) -> None:
        """Start periodic heartbeat monitoring."""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
        logger.info("Heartbeat monitor started (interval=%ss, timeout=%ss)",
                     interval, self._heartbeat_timeout)

    async def stop_heartbeat_monitor(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            now = time.time()
            timed_out = []
            for cid, session in self._sessions.items():
                if session.state != AgentState.CONNECTED:
                    continue
                if now - session.last_heartbeat > self._heartbeat_timeout:
                    timed_out.append(cid)
            for cid in timed_out:
                logger.warning("Session heartbeat timeout: %s", cid)
                self._sessions[cid].state = AgentState.DISCONNECTED

    # ── Token & Handshake ─────────────────────────
    def verify_token(self, token: str) -> Optional[str]:
        return self._token_manager.verify_token(token)

    def process_auth(self, req: AuthRequest) -> SignRequest | ErrorMessage:
        return self._handshake.process_auth(req)

    def process_connection_type(self, req: ConnectionTypeRequest, connection_id: str) -> HandshakeResult:
        return self._handshake.process_connection_type(req, connection_id)

    def cleanup_expired_tokens(self) -> int:
        return self._token_manager.cleanup_expired()


# ── Global singleton ──────────────────────────────
_remote_session_manager: Optional[RemoteSessionManager] = None


def init_remote_session_manager() -> RemoteSessionManager:
    global _remote_session_manager
    if _remote_session_manager is None:
        _remote_session_manager = RemoteSessionManager()
    return _remote_session_manager


def get_remote_session_manager() -> Optional[RemoteSessionManager]:
    return _remote_session_manager
