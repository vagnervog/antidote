"""Tool interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Run the tool with given parameters. Return result."""
        ...
