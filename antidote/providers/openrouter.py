"""OpenRouter provider via LiteLLM."""

import asyncio
import logging
import os

import litellm

from antidote.config import Config
from antidote.providers.base import BaseProvider, LLMResponse, Message, ToolDefinition

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseProvider):
    def __init__(self):
        config = Config()
        self._model = config.get("providers", "openrouter", "model",
                                  default="anthropic/claude-sonnet-4-20250514")
        self._api_key = config.get_secret("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not found. Run 'antidote setup' to configure."
            )

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        model_name = f"openrouter/{model or self._model}"
        msgs = [self._format_message(m) for m in messages]

        kwargs = {
            "model": model_name,
            "messages": msgs,
            "temperature": temperature,
            "api_key": self._api_key,
            "timeout": 120,
        }
        if tools:
            kwargs["tools"] = [self._format_tool(t) for t in tools]

        last_error = None
        for attempt in range(3):
            try:
                response = await litellm.acompletion(**kwargs)
                return self._parse_response(response)
            except Exception as e:
                last_error = e
                error_str = str(e)
                if "429" in error_str or "5" == error_str[:1]:
                    wait = 2 ** attempt
                    logger.warning(f"Retry {attempt + 1}/3 after {wait}s: {e}")
                    await asyncio.sleep(wait)
                else:
                    raise

        raise last_error

    def _format_message(self, msg: Message) -> dict:
        d = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            d["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        return d

    def _format_tool(self, tool: ToolDefinition) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _parse_response(self, response) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in msg.tool_calls
            ]

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
            logger.info(f"Tokens: {usage}")

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            usage=usage,
        )
