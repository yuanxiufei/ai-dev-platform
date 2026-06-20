"""
Workspace Trust Model — security levels for remote agent workspaces.

Borrows concepts from VS Code's workspace trust system:
- Trust levels: TRUSTED / UNTRUSTED / RESTRICTED
- Restricted mode limitations (no shell exec, no unverified plugins, etc.)
- Trust transition events and callbacks
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TrustLevel(str, Enum):
    """Workspace trust levels.

    - TRUSTED: Full access — shell execution, all plugins, network I/O.
    - UNTRUSTED: Safe mode — no shell exec, no file writes outside workspace, no downloads.
    - RESTRICTED: Minimal access — read-only, no exec, no network calls.
    """
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    RESTRICTED = "restricted"


class TrustReason(str, Enum):
    """Why a workspace is trusted/untrusted."""
    USER_APPROVED = "user_approved"       # User explicitly trusted
    FIRST_OPEN = "first_open"             # Never opened before
    PARENT_TRUSTED = "parent_trusted"     # Parent folder trusted
    SOURCE_EXTERNAL = "source_external"   # Downloaded from external source
    SOURCE_GIT_TRUSTED = "source_git_trusted"  # From trusted git remote
    SOURCE_GIT_UNKNOWN = "source_git_unknown"  # From unknown git remote
    PATH_SENSITIVE = "path_sensitive"     # In a sensitive system path


# ── Trust capabilities: what each level allows ────

TRUST_CAPABILITIES: dict[TrustLevel, set[str]] = {
    TrustLevel.TRUSTED: {
        "shell_exec",           # Run arbitrary shell commands
        "file_write",           # Write files outside workspace
        "file_delete",          # Delete any file
        "network_outbound",     # Make HTTP/WS outbound requests
        "plugin_install",       # Install new plugins
        "plugin_load",          # Load any plugin
        "execute_binary",       # Run compiled binaries
        "download_files",       # Download files from internet
        "read_env",             # Read environment variables
        "git_operations",       # Perform git operations
    },
    TrustLevel.UNTRUSTED: {
        "file_write",           # Write only within workspace
        "network_outbound",     # Limited network (whitelist only)
        "plugin_load",          # Only pre-verified plugins
        "read_env",             # Read limited env vars
        "git_operations",       # Read-only git
    },
    TrustLevel.RESTRICTED: {
        # Read-only mode — no capabilities beyond reading workspace files
    },
}


@dataclass
class WorkspaceTrust:
    """Tracks trust state for a workspace directory."""
    workspace_path: str
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    reason: TrustReason = TrustReason.FIRST_OPEN
    granted_at: float = 0.0
    granted_by: str = ""
    last_verified: float = 0.0

    def allows(self, capability: str) -> bool:
        """Check if the current trust level allows a capability."""
        allowed = TRUST_CAPABILITIES.get(self.trust_level, set())
        return capability in allowed

    @property
    def can_exec_shell(self) -> bool:
        return self.allows("shell_exec")

    @property
    def can_write_files(self) -> bool:
        return self.allows("file_write")

    @property
    def can_network(self) -> bool:
        return self.allows("network_outbound")

    @property
    def can_install_plugins(self) -> bool:
        return self.allows("plugin_install")


class WorkspaceTrustManager:
    """Manages trust levels for multiple workspaces."""

    def __init__(self):
        self._trusts: dict[str, WorkspaceTrust] = {}  # workspace_path → trust
        self._change_callbacks: list[Callable[[str, TrustLevel, TrustLevel], None]] = []

    def get_trust(self, workspace_path: str) -> WorkspaceTrust:
        """Get or create trust state for a workspace."""
        if workspace_path not in self._trusts:
            import time
            self._trusts[workspace_path] = WorkspaceTrust(
                workspace_path=workspace_path,
                trust_level=TrustLevel.UNTRUSTED,
                reason=TrustReason.FIRST_OPEN,
                granted_at=time.time(),
            )
        return self._trusts[workspace_path]

    def grant_trust(
        self,
        workspace_path: str,
        level: TrustLevel = TrustLevel.TRUSTED,
        granted_by: str = "user",
    ) -> WorkspaceTrust:
        """Grant a trust level to a workspace."""
        import time
        old_trust = self.get_trust(workspace_path)
        old_level = old_trust.trust_level

        trust = WorkspaceTrust(
            workspace_path=workspace_path,
            trust_level=level,
            reason=TrustReason.USER_APPROVED,
            granted_at=time.time(),
            granted_by=granted_by,
            last_verified=time.time(),
        )
        self._trusts[workspace_path] = trust

        logger.info("Workspace trust: %s → %s (by %s)", workspace_path, level.value, granted_by)

        # Notify callbacks
        for cb in self._change_callbacks:
            try:
                cb(workspace_path, old_level, level)
            except Exception as e:
                logger.error("Trust change callback error: %s", e)

        return trust

    def revoke_trust(self, workspace_path: str) -> WorkspaceTrust:
        """Revoke trust for a workspace, resetting to UNTRUSTED."""
        return self.grant_trust(workspace_path, TrustLevel.UNTRUSTED, "system")

    def restrict(self, workspace_path: str) -> WorkspaceTrust:
        """Set workspace to RESTRICTED mode."""
        return self.grant_trust(workspace_path, TrustLevel.RESTRICTED, "system")

    def on_trust_change(self, callback: Callable[[str, TrustLevel, TrustLevel], None]) -> None:
        """Register a callback for trust level changes."""
        self._change_callbacks.append(callback)

    def is_trusted(self, workspace_path: str) -> bool:
        return self.get_trust(workspace_path).trust_level == TrustLevel.TRUSTED

    def check_capability(self, workspace_path: str, capability: str) -> bool:
        """Check if a capability is allowed for a workspace."""
        return self.get_trust(workspace_path).allows(capability)


# ── Global singleton ──────────────────────────────
_trust_manager: Optional[WorkspaceTrustManager] = None


def init_workspace_trust_manager() -> WorkspaceTrustManager:
    global _trust_manager
    if _trust_manager is None:
        _trust_manager = WorkspaceTrustManager()
    return _trust_manager


def get_workspace_trust_manager() -> Optional[WorkspaceTrustManager]:
    return _trust_manager
