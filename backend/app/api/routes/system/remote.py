"""
Remote Agent API — session management, port forwarding, and workspace trust.
"""

from fastapi import APIRouter, HTTPException, Query

from app.core.remote import (
    get_remote_session_manager,
    get_port_forward_manager,
    get_workspace_trust_manager,
)
from app.core.remote.agent_protocol import ConnectionType
from app.core.remote.port_forward import PortVisibility

router = APIRouter(prefix="/system/remote", tags=["Remote Agent"])


# ── Sessions ──────────────────────────────────────
@router.post("/sessions")
async def create_session(metadata: dict = None) -> dict:
    """Create a new remote agent connection (returns token)."""
    mgr = get_remote_session_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="Remote agent not available")
    connection_id, token = mgr.create_connection(metadata=metadata)
    return {"connection_id": connection_id, "token": token}


@router.get("/sessions")
async def list_sessions() -> dict:
    """List all active remote agent sessions."""
    mgr = get_remote_session_manager()
    if mgr is None:
        return {"data": [], "total": 0}
    sessions = mgr.list_active_sessions()
    return {
        "data": [
            {
                "connection_id": s.connection_id,
                "connection_type": s.connection_type.value,
                "state": s.state.value,
                "connected_at": s.connected_at,
                "last_heartbeat": s.last_heartbeat,
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.delete("/sessions/{connection_id}")
async def end_session(connection_id: str) -> dict:
    """End a remote agent session."""
    mgr = get_remote_session_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="Remote agent not available")
    success = mgr.end_session(connection_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": f"Session {connection_id} ended"}


# ── Port Forwarding ───────────────────────────────
@router.post("/ports")
async def create_port_mapping(
    connection_id: str,
    local_port: int,
    service_name: str = "",
) -> dict:
    """Create a port forwarding mapping."""
    pf = get_port_forward_manager()
    if pf is None:
        raise HTTPException(status_code=503, detail="Port forwarding not available")
    mapping = pf.create_mapping(connection_id, local_port, service_name)
    if mapping is None:
        raise HTTPException(status_code=500, detail="No available proxy ports")
    return {
        "mapping_id": mapping.mapping_id,
        "local_port": mapping.local_port,
        "proxy_port": mapping.proxy_port,
        "service_name": mapping.service_name,
    }


@router.get("/ports")
async def list_port_mappings(connection_id: str = "") -> dict:
    """List port forwarding mappings."""
    pf = get_port_forward_manager()
    if pf is None:
        return {"data": [], "total": 0}
    mappings = pf.list_mappings(connection_id=connection_id if connection_id else None)
    return {
        "data": [
            {
                "mapping_id": m.mapping_id,
                "local_port": m.local_port,
                "proxy_port": m.proxy_port,
                "service_name": m.service_name,
                "status": m.status.value,
                "visibility": m.visibility.value,
                "connection_id": m.connection_id,
            }
            for m in mappings
        ],
        "total": len(mappings),
    }


@router.delete("/ports/{mapping_id}")
async def close_port_mapping(mapping_id: str) -> dict:
    """Close a port forwarding mapping."""
    pf = get_port_forward_manager()
    if pf is None:
        raise HTTPException(status_code=503, detail="Port forwarding not available")
    success = pf.close_mapping(mapping_id)
    if not success:
        raise HTTPException(status_code=404, detail="Port mapping not found")
    return {"message": f"Port mapping {mapping_id} closed"}


# ── Workspace Trust ───────────────────────────────
@router.get("/trust/{workspace_path:path}")
async def get_workspace_trust(workspace_path: str = "/") -> dict:
    """Get trust level for a workspace."""
    tm = get_workspace_trust_manager()
    if tm is None:
        raise HTTPException(status_code=503, detail="Workspace trust not available")
    trust = tm.get_trust(workspace_path)
    return {
        "workspace_path": trust.workspace_path,
        "trust_level": trust.trust_level.value,
        "reason": trust.reason.value,
        "granted_at": trust.granted_at,
        "granted_by": trust.granted_by,
        "can_exec_shell": trust.can_exec_shell,
        "can_write_files": trust.can_write_files,
        "can_network": trust.can_network,
    }


@router.post("/trust/{workspace_path:path}/grant")
async def grant_workspace_trust(workspace_path: str = "/", level: str = "trusted") -> dict:
    """Grant trust to a workspace."""
    from app.core.remote.workspace_trust import TrustLevel

    tm = get_workspace_trust_manager()
    if tm is None:
        raise HTTPException(status_code=503, detail="Workspace trust not available")
    try:
        trust_level = TrustLevel(level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trust level: {level}")
    trust = tm.grant_trust(workspace_path, trust_level)
    return {
        "workspace_path": trust.workspace_path,
        "trust_level": trust.trust_level.value,
        "message": "Trust granted",
    }
