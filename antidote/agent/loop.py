"""Core agent loop — receives messages, thinks, uses tools, responds."""

import json
import logging
from collections import defaultdict

from antidote.channels.base import IncomingMessage
from antidote.providers.base import Message

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_HISTORY = 50


class AgentLoop:
    def __init__(self, provider, context, memory, tools):
        self._provider = provider
        self._context = context
        self._memory = memory
        self._tools = tools
        self._histories: dict[str, list[Message]] = defaultdict(list)

    async def process_message(self, incoming: IncomingMessage) -> str:
        """Process an incoming message and return a response."""
        chat_id = incoming.chat_id
        history = self._histories[chat_id]

        # Add user message to history
        user_msg = Message(role="user", content=incoming.text)
        history.append(user_msg)

        # Trim history
        if len(history) > MAX_HISTORY:
            history[:] = history[-MAX_HISTORY:]

        # Build context with system prompt + memories + history
        messages = await self._context.build_conversation_context(
            history, incoming.text
        )

        # Get tool definitions (including built-in memory tools)
        tool_defs = self._tools.as_definitions()
        tool_defs.extend(self._memory_tool_definitions())

        # Agent loop: call LLM, execute tools, repeat
        for round_num in range(MAX_TOOL_ROUNDS):
            response = await self._provider.chat(
                messages=messages,
                tools=tool_defs if tool_defs else None,
            )

            if not response.tool_calls:
                # LLM responded with text — done
                result = response.content or "I have nothing to say."
                break
            else:
                # Execute tool calls
                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc)
                    # Add assistant message with tool call
                    messages.append(
                        Message(
                            role="assistant",
                            content=response.content or "",
                            tool_calls=[tc],
                        )
                    )
                    # Add tool result
                    messages.append(
                        Message(
                            role="tool",
                            content=tool_result,
                            tool_call_id=tc["id"],
                        )
                    )
        else:
            result = response.content or "I reached the maximum number of tool rounds."

        # Save to history
        history.append(Message(role="assistant", content=result))

        # Save conversation to memory if substantive
        if len(incoming.text.split()) > 3:
            try:
                summary = f"User: {incoming.text[:200]} → Assistant: {result[:200]}"
                await self._memory.save(summary, category="conversation")
            except Exception as e:
                logger.warning(f"Failed to save conversation memory: {e}")

        return result

    async def _execute_tool(self, tool_call: dict) -> str:
        """Execute a single tool call and return the result as a string."""
        name = tool_call["name"]
        try:
            args = json.loads(tool_call["arguments"]) if isinstance(tool_call["arguments"], str) else tool_call["arguments"]
        except json.JSONDecodeError:
            return f"Error: Invalid arguments for {name}"

        # Check built-in memory tools first
        if name == "save_memory":
            mid = await self._memory.save(
                args.get("content", ""), args.get("category", "fact")
            )
            return f"Memory saved (id: {mid})"

        if name == "search_memory":
            results = await self._memory.search(args.get("query", ""), args.get("limit", 5))
            if not results:
                return "No memories found."
            return "\n".join(f"[{m.id}] [{m.category}] {m.content}" for m in results)

        if name == "forget_memory":
            ok = await self._memory.forget(args.get("id", 0))
            return "Memory deleted." if ok else "Memory not found."

        # Regular tools
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'"

        try:
            result = await tool.execute(**args)
            if result.success:
                return result.output
            return f"Error: {result.error}"
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return f"Error executing {name}: {e}"

    def _memory_tool_definitions(self):
        """Built-in memory tools the LLM can call."""
        from antidote.providers.base import ToolDefinition

        return [
            ToolDefinition(
                name="save_memory",
                description="Save a fact, preference, or important information to long-term memory.",
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "What to remember"},
                        "category": {
                            "type": "string",
                            "enum": ["fact", "preference", "conversation", "solution"],
                            "description": "Memory category",
                        },
                    },
                    "required": ["content"],
                },
            ),
            ToolDefinition(
                name="search_memory",
                description="Search long-term memory for relevant information.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="forget_memory",
                description="Delete an outdated or incorrect memory by ID.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Memory ID to delete"}
                    },
                    "required": ["id"],
                },
            ),
        ]
