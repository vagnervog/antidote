"""System prompt builder — assembles identity files + memories + tools."""

import logging
import os
from pathlib import Path

from antidote.providers.base import Message

logger = logging.getLogger(__name__)

TOKEN_BUDGET = 8000  # Approximate max tokens for conversation context


class ContextBuilder:
    def __init__(self, config, memory, tools):
        self._config = config
        self._memory = memory
        self._tools = tools

    def _read_file(self, path: str) -> str:
        """Read a markdown file, return empty string if missing."""
        # Resolve relative to project workspace/ dir or absolute
        if not os.path.isabs(path):
            workspace = self._config.get("workspace", default="")
            full = os.path.join(workspace, path)
            if not os.path.exists(full):
                # Try relative to project root
                root = Path(__file__).parent.parent.parent
                full = str(root / path)
        else:
            full = path

        try:
            return Path(full).read_text()
        except FileNotFoundError:
            logger.warning(f"Identity file not found: {path}")
            return ""

    async def build_system_prompt(self) -> str:
        """Build the full system prompt from identity files + recent memories + tools."""
        identity = self._config.get("identity", default={})
        parts = []

        # Identity files
        for key in ["soul", "agents", "user"]:
            path = identity.get(key, "")
            if path:
                content = self._read_file(path)
                if content:
                    parts.append(content)

        # Recent memories
        try:
            memories = await self._memory.recent(
                limit=self._config.get("memory", "max_context_memories", default=10)
            )
            if memories:
                mem_section = "\n## Relevant Memories\n"
                for m in memories:
                    mem_section += f"- [{m.category}] {m.content}\n"
                parts.append(mem_section)
        except Exception as e:
            logger.warning(f"Failed to load memories: {e}")

        # Available tools
        tool_defs = self._tools.as_definitions()
        if tool_defs:
            tools_section = "\n## Available Tools\n"
            for t in tool_defs:
                tools_section += f"- **{t.name}**: {t.description}\n"
            parts.append(tools_section)

        return "\n\n".join(parts)

    async def build_conversation_context(
        self, history: list[Message], query: str
    ) -> list[Message]:
        """Build full message list with system prompt, relevant memories, and history."""
        system_prompt = await self.build_system_prompt()

        # Search for relevant memories
        try:
            relevant = await self._memory.search(query, limit=5)
            if relevant:
                memory_context = "\n\nRelevant memories:\n"
                for m in relevant:
                    memory_context += f"- {m.content}\n"
                system_prompt += memory_context
        except Exception:
            pass

        messages = [Message(role="system", content=system_prompt)]

        # Truncate history to fit token budget
        char_budget = TOKEN_BUDGET * 4  # rough estimate
        total_chars = len(system_prompt)
        kept = []
        for msg in reversed(history):
            msg_chars = len(msg.content)
            if total_chars + msg_chars > char_budget:
                break
            kept.insert(0, msg)
            total_chars += msg_chars

        messages.extend(kept)
        return messages
