"""
Port Forwarding Manager — multiplexed port forwarding for remote agent access.

Allows the remote agent to expose local services (e.g., dev server on :3000)
through the master server. Borrows concepts from VS Code's port forwarding system.

Supports:
- Auto-detection of service ports
- Port mapping with local/remote translation
- Access control (public/private per port)
- Lifecycle tracking (open/close/error)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class PortStatus(str, Enum):
    LISTENING = "listening"
    CONNECTED = "connected"
    CLOSED = "closed"
    ERROR = "error"


class PortVisibility(str, Enum):
    PRIVATE = "private"    # Only accessible to the session owner
    PUBLIC = "public"      # Accessible to anyone with the URL


@dataclass
class PortMapping:
    """A single port forwarding mapping."""
    mapping_id: str
    local_port: int          # Port on the remote agent machine
    proxy_port: int          # Port on the master server (exposed to user)
    service_name: str = ""   # e.g., "React Dev Server", "Jupyter"
    status: PortStatus = PortStatus.LISTENING
    visibility: PortVisibility = PortVisibility.PRIVATE
    connection_id: str = ""
    created_at: float = 0.0
    bytes_forwarded: int = 0
    connections_active: int = 0


class PortForwardManager:
    """Manages port forwarding mappings for remote agent sessions."""

    def __init__(self, port_range_start: int = 10000, port_range_end: int = 20000):
        """
        Args:
            port_range_start: Start of the proxy port range.
            port_range_end: End of the proxy port range (exclusive).
        """
        self._port_range = (port_range_start, port_range_end)
        self._mappings: dict[str, PortMapping] = {}  # mapping_id → PortMapping
        self._port_usage: set[int] = set()           # Used proxy ports
        self._next_port = port_range_start
        self._listeners: dict[str, asyncio.AbstractServer] = {}  # mapping_id → server

    # ── Port Mapping CRUD ─────────────────────────
    def create_mapping(
        self,
        connection_id: str,
        local_port: int,
        service_name: str = "",
        visibility: PortVisibility = PortVisibility.PRIVATE,
    ) -> Optional[PortMapping]:
        """Create a new port forwarding mapping."""
        import time
        proxy_port = self._allocate_port()
        if proxy_port is None:
            logger.error("No available proxy ports in range %s", self._port_range)
            return None

        mapping_id = f"pf-{connection_id[:8]}-{local_port}"
        mapping = PortMapping(
            mapping_id=mapping_id,
            local_port=local_port,
            proxy_port=proxy_port,
            service_name=service_name or f"port-{local_port}",
            visibility=visibility,
            connection_id=connection_id,
            created_at=time.time(),
        )
        self._mappings[mapping_id] = mapping
        self._port_usage.add(proxy_port)
        logger.info("Port forward: %s:%d → proxy:%d (%s)",
                     mapping_id, local_port, proxy_port, service_name)
        return mapping

    def get_mapping(self, mapping_id: str) -> Optional[PortMapping]:
        return self._mappings.get(mapping_id)

    def list_mappings(self, connection_id: Optional[str] = None) -> list[PortMapping]:
        """List all mappings, optionally filtered by connection."""
        if connection_id:
            return [m for m in self._mappings.values() if m.connection_id == connection_id]
        return list(self._mappings.values())

    def close_mapping(self, mapping_id: str) -> bool:
        """Close a port mapping and release the proxy port."""
        mapping = self._mappings.pop(mapping_id, None)
        if mapping is None:
            return False
        self._port_usage.discard(mapping.proxy_port)
        mapping.status = PortStatus.CLOSED

        # Close listener if active
        server = self._listeners.pop(mapping_id, None)
        if server:
            server.close()

        logger.info("Port forward closed: %s (local:%d)", mapping_id, mapping.local_port)
        return True

    def close_all_for_connection(self, connection_id: str) -> int:
        """Close all port mappings for a connection."""
        to_close = [
            mid for mid, m in self._mappings.items()
            if m.connection_id == connection_id
        ]
        for mid in to_close:
            self.close_mapping(mid)
        return len(to_close)

    # ── Auto-detection ────────────────────────────
    async def detect_ports(
        self,
        connection_id: str,
        common_ports: list[int] | None = None,
    ) -> list[PortMapping]:
        """Auto-detect and forward common dev server ports."""
        if common_ports is None:
            common_ports = [
                3000,   # React/Next.js
                5173,   # Vite
                8080,   # Common dev server
                8000,   # Python/Django (legacy)
                8888,   # Jupyter
                18000,  # AI Fullstack Platform
                3001,   # Express
                4000,   # SvelteKit
                4200,   # Angular
            ]
        created: list[PortMapping] = []
        for port in common_ports:
            # Check if port is already mapped
            existing = [
                m for m in self._mappings.values()
                if m.local_port == port and m.connection_id == connection_id
            ]
            if existing:
                created.extend(existing)
                continue

            mapping = self.create_mapping(connection_id, port, f"auto-{port}")
            if mapping:
                created.append(mapping)
        return created

    # ── Internal ──────────────────────────────────
    def _allocate_port(self) -> Optional[int]:
        """Allocate an unused proxy port from the configured range."""
        start, end = self._port_range
        for _ in range(end - start):
            port = self._next_port
            self._next_port = start if self._next_port >= end - 1 else self._next_port + 1
            if port not in self._port_usage:
                return port
        return None

    def get_port_url(self, mapping_id: str, base_url: str = "http://localhost") -> Optional[str]:
        """Get the accessible URL for a port mapping."""
        mapping = self._mappings.get(mapping_id)
        if mapping is None:
            return None
        return f"{base_url}:{mapping.proxy_port}"


# ── Global singleton ──────────────────────────────
_port_forward_manager: Optional[PortForwardManager] = None


def init_port_forward_manager(
    port_range_start: int = 10000,
    port_range_end: int = 20000,
) -> PortForwardManager:
    global _port_forward_manager
    if _port_forward_manager is None:
        _port_forward_manager = PortForwardManager(port_range_start, port_range_end)
    return _port_forward_manager


def get_port_forward_manager() -> Optional[PortForwardManager]:
    return _port_forward_manager
