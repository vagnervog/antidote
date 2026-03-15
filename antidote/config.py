"""Configuration loader — singleton, merges defaults, reads secrets."""

import json
import os
from pathlib import Path

_DEFAULTS = {
    "name": "Antidote",
    "version": "0.1.0",
    "providers": {
        "default": "openrouter",
        "openrouter": {"model": "anthropic/claude-sonnet-4-20250514"},
        "ollama": {"model": "llama3.2", "base_url": "http://localhost:11434"},
    },
    "channels": {"telegram": {"enabled": True}},
    "memory": {"db_path": "~/.antidote/memory.db", "max_context_memories": 10},
    "workspace": "~/.antidote/workspace",
    "identity": {
        "soul": "workspace/SOUL.md",
        "agents": "workspace/AGENTS.md",
        "user": "workspace/USER.md",
    },
    "safety": {
        "blocked_commands": [
            "rm -rf /",
            "mkfs",
            "dd if=",
            "shutdown",
            "reboot",
            "> /dev/sd",
        ],
        "max_command_timeout": 60,
    },
}

CONFIG_DIR = Path.home() / ".antidote"
CONFIG_PATH = CONFIG_DIR / "config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _expand_paths(obj):
    """Expand ~ in string values that look like paths."""
    if isinstance(obj, str) and "~" in obj:
        return os.path.expanduser(obj)
    if isinstance(obj, dict):
        return {k: _expand_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_paths(v) for v in obj]
    return obj


class Config:
    _instance = None
    _data: dict

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        user_config = {}
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                user_config = json.load(f)
        self._data = _expand_paths(_deep_merge(_DEFAULTS, user_config))

    def reload(self):
        self._load()

    def get(self, *keys, default=None):
        """Get a nested config value. Usage: config.get('providers', 'default')"""
        obj = self._data
        for key in keys:
            if isinstance(obj, dict) and key in obj:
                obj = obj[key]
            else:
                return default
        return obj

    @property
    def data(self) -> dict:
        return self._data

    def get_secret(self, name: str) -> str | None:
        """Get a secret from encrypted store, falling back to env var."""
        try:
            from antidote.security.secrets import SecretStore

            store = SecretStore()
            value = store.get_secret(name)
            if value:
                return value
        except Exception:
            pass
        return os.environ.get(name)

    @staticmethod
    def exists() -> bool:
        return CONFIG_PATH.exists()
