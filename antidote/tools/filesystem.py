"""File system tools — read, write, list."""

import os
from pathlib import Path

from antidote.tools.base import BaseTool, ToolResult

MAX_READ_SIZE = 100 * 1024  # 100KB


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"}
        },
        "required": ["path"],
    }

    def __init__(self, config):
        self._workspace = config.get("workspace", default="")

    def _resolve(self, path: str) -> str:
        p = os.path.expanduser(path)
        if not os.path.isabs(p):
            p = os.path.join(self._workspace, p)
        return os.path.realpath(p)

    async def execute(self, **kwargs) -> ToolResult:
        path = self._resolve(kwargs["path"])
        if not path.startswith(os.path.realpath(self._workspace)):
            return ToolResult(False, "", "Path outside workspace")
        try:
            size = os.path.getsize(path)
            if size > MAX_READ_SIZE:
                return ToolResult(False, "", f"File too large: {size} bytes (max {MAX_READ_SIZE})")
            content = Path(path).read_text()
            return ToolResult(True, content)
        except Exception as e:
            return ToolResult(False, "", str(e))


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file. Creates parent directories if needed."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, config):
        self._workspace = config.get("workspace", default="")

    def _resolve(self, path: str) -> str:
        p = os.path.expanduser(path)
        if not os.path.isabs(p):
            p = os.path.join(self._workspace, p)
        return os.path.realpath(p)

    async def execute(self, **kwargs) -> ToolResult:
        path = self._resolve(kwargs["path"])
        if not path.startswith(os.path.realpath(self._workspace)):
            return ToolResult(False, "", "Path outside workspace")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Path(path).write_text(kwargs["content"])
            return ToolResult(True, f"Written to {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class ListDirTool(BaseTool):
    name = "list_directory"
    description = "List files and folders in a directory with sizes."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list"}
        },
        "required": ["path"],
    }

    def __init__(self, config):
        self._workspace = config.get("workspace", default="")

    def _resolve(self, path: str) -> str:
        p = os.path.expanduser(path)
        if not os.path.isabs(p):
            p = os.path.join(self._workspace, p)
        return os.path.realpath(p)

    async def execute(self, **kwargs) -> ToolResult:
        path = self._resolve(kwargs["path"])
        if not path.startswith(os.path.realpath(self._workspace)):
            return ToolResult(False, "", "Path outside workspace")
        try:
            entries = []
            for entry in sorted(os.listdir(path)):
                full = os.path.join(path, entry)
                if os.path.isdir(full):
                    entries.append(f"  {entry}/")
                else:
                    size = os.path.getsize(full)
                    entries.append(f"  {entry}  ({size} bytes)")
            return ToolResult(True, "\n".join(entries))
        except Exception as e:
            return ToolResult(False, "", str(e))
