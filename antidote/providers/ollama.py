"""Ollama local provider via LiteLLM."""

import logging

import litellm

from antidote.config import Config
from antidote.providers.base import BaseProvider, LLMResponse, Message, ToolDefinition

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    def __init__(self):
        config = Config()
        self._model = config.get("providers", "ollama", "model", default="llama3.2")
        self._base_url = config.get(
            "providers", "ollama", "base_url", default="http://localhost:11434"
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        model_name = f"ollama/{model or self._model}"
        msgs = [{"role": m.role, "content": m.content} for m in messages]

        kwargs = {
            "model": model_name,
            "messages": msgs,
            "temperature": temperature,
            "api_base": self._base_url,
            "timeout": 120,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return LLMResponse(
                content=f"Ollama is not available: {e}",
                tool_calls=None,
                usage=None,
            )

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

        return LLMResponse(content=msg.content, tool_calls=tool_calls, usage=usage)
