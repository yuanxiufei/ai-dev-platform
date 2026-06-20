"""
Remote Agent — secure remote agent protocol, port forwarding, and workspace trust.

Borrows concepts from:
- OpenVSCode Server's remoteAgentConnection (handshake/multiplexing)
- VS Code's workspace trust model
"""

from app.core.remote.agent_protocol import (
    ConnectionType,
    AgentState,
    AgentSession,
    ConnectionTokenManager,
    HandshakeEngine,
    HandshakeResult,
    AuthRequest,
    SignRequest,
    ConnectionTypeRequest,
    OKMessage,
    ErrorMessage,
    HeartbeatMessage,
)
from app.core.remote.port_forward import (
    PortMapping,
    PortStatus,
    PortVisibility,
    PortForwardManager,
    init_port_forward_manager,
    get_port_forward_manager,
)
from app.core.remote.workspace_trust import (
    TrustLevel,
    TrustReason,
    WorkspaceTrust,
    WorkspaceTrustManager,
    TRUST_CAPABILITIES,
    init_workspace_trust_manager,
    get_workspace_trust_manager,
)
from app.core.remote.session_manager import (
    RemoteSessionManager,
    init_remote_session_manager,
    get_remote_session_manager,
)

__all__ = [
    # Agent protocol
    "ConnectionType",
    "AgentState",
    "AgentSession",
    "ConnectionTokenManager",
    "HandshakeEngine",
    "HandshakeResult",
    "AuthRequest",
    "SignRequest",
    "ConnectionTypeRequest",
    "OKMessage",
    "ErrorMessage",
    "HeartbeatMessage",
    # Port forwarding
    "PortMapping",
    "PortStatus",
    "PortVisibility",
    "PortForwardManager",
    "init_port_forward_manager",
    "get_port_forward_manager",
    # Workspace trust
    "TrustLevel",
    "TrustReason",
    "WorkspaceTrust",
    "WorkspaceTrustManager",
    "TRUST_CAPABILITIES",
    "init_workspace_trust_manager",
    "get_workspace_trust_manager",
    # Session manager
    "RemoteSessionManager",
    "init_remote_session_manager",
    "get_remote_session_manager",
]
