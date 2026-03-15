"""Command safety — blocklist, path traversal protection, audit logging."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from antidote.config import Config

AUDIT_LOG = Path.home() / ".antidote" / "audit.log"

logger = logging.getLogger(__name__)


def _get_audit_logger() -> logging.Logger:
    audit = logging.getLogger("antidote.audit")
    if not audit.handlers:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(AUDIT_LOG)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        audit.addHandler(handler)
        audit.setLevel(logging.INFO)
    return audit


def is_safe(command: str) -> tuple[bool, str | None]:
    """Check if a command is safe to execute. Returns (safe, reason_if_blocked)."""
    config = Config()
    blocked = config.get("safety", "blocked_commands", default=[])

    # Check blocklist (substring match)
    cmd_lower = command.lower().strip()
    for pattern in blocked:
        if pattern.lower() in cmd_lower:
            reason = f"Blocked command pattern: {pattern}"
            _log_command(command, blocked=True, reason=reason)
            return False, reason

    # Check path traversal
    if ".." in command:
        workspace = config.get("workspace", default="")
        # Allow .. only if it doesn't escape workspace
        try:
            resolved = os.path.realpath(os.path.expanduser(command))
            ws_resolved = os.path.realpath(os.path.expanduser(workspace))
            if not resolved.startswith(ws_resolved):
                reason = "Path traversal detected outside workspace"
                _log_command(command, blocked=True, reason=reason)
                return False, reason
        except Exception:
            pass

    _log_command(command, blocked=False)
    return True, None


def get_timeout() -> int:
    """Get command timeout in seconds from config."""
    config = Config()
    return config.get("safety", "max_command_timeout", default=60)


def _log_command(command: str, blocked: bool, reason: str | None = None):
    audit = _get_audit_logger()
    status = "BLOCKED" if blocked else "ALLOWED"
    msg = f"[{status}] {command}"
    if reason:
        msg += f" — {reason}"
    audit.info(msg)
