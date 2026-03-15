"""Tool discovery and registration."""

from antidote.providers.base import ToolDefinition
from antidote.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def as_definitions(self) -> list[ToolDefinition]:
        """Convert all tools to ToolDefinition for LLM."""
        return [
            ToolDefinition(
                name=t.name, description=t.description, parameters=t.parameters
            )
            for t in self._tools.values()
        ]
