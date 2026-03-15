"""Shell command execution tool with safety checks."""

import asyncio
import logging

from antidote.security.safety import get_timeout, is_safe
from antidote.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_OUTPUT = 10 * 1024  # 10KB


class RunCommandTool(BaseTool):
    name = "run_command"
    description = "Execute a shell command. Commands are checked against a safety blocklist."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"}
        },
        "required": ["command"],
    }

    def __init__(self, config):
        self._config = config

    async def execute(self, **kwargs) -> ToolResult:
        command = kwargs["command"]

        safe, reason = is_safe(command)
        if not safe:
            return ToolResult(False, "", f"Command blocked: {reason}")

        timeout = get_timeout()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
            if len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + "\n... (truncated)"
            return ToolResult(
                success=proc.returncode == 0,
                output=output,
                error=f"Exit code: {proc.returncode}" if proc.returncode != 0 else None,
            )
        except asyncio.TimeoutError:
            return ToolResult(False, "", f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, "", str(e))
