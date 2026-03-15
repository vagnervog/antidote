"""Provider factory."""

from antidote.providers.base import BaseProvider


def get_provider(name: str | None = None) -> BaseProvider:
    """Get provider by name. Defaults to config default."""
    from antidote.config import Config

    config = Config()
    name = name or config.get("providers", "default", default="openrouter")
    if name == "openrouter":
        from .openrouter import OpenRouterProvider
        return OpenRouterProvider()
    elif name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider()
    else:
        raise ValueError(f"Unknown provider: {name}")
