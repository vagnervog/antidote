"""Fernet-encrypted secret store, keyed to machine identity."""

import base64
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SECRETS_PATH = Path.home() / ".antidote" / ".secrets"
SALT = b"antidote-secret-salt-v1"


def _get_machine_id() -> str:
    """Get a machine-specific identifier for key derivation."""
    # macOS: hardware UUID
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        except Exception:
            pass
    # Linux: machine-id
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            return Path(path).read_text().strip()
        except Exception:
            pass
    # Fallback: hostname + username
    return f"{platform.node()}-{os.getlogin()}"


def _derive_key(machine_id: str) -> bytes:
    """Derive a Fernet key from the machine ID using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=480_000,
    )
    key = kdf.derive(machine_id.encode())
    return base64.urlsafe_b64encode(key)


class SecretStore:
    def __init__(self):
        self._key = _derive_key(_get_machine_id())
        self._fernet = Fernet(self._key)
        self._secrets: dict[str, str] = {}
        self._load()

    def _load(self):
        if SECRETS_PATH.exists():
            with open(SECRETS_PATH) as f:
                self._secrets = json.load(f)

    def _save(self):
        SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SECRETS_PATH, "w") as f:
            json.dump(self._secrets, f, indent=2)
        os.chmod(SECRETS_PATH, 0o600)

    def save_secret(self, name: str, value: str) -> None:
        encrypted = self._fernet.encrypt(value.encode()).decode()
        self._secrets[name] = encrypted
        self._save()

    def get_secret(self, name: str) -> str | None:
        encrypted = self._secrets.get(name)
        if encrypted is None:
            return None
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            return None

    def list_secrets(self) -> list[str]:
        return list(self._secrets.keys())

    def delete_secret(self, name: str) -> None:
        self._secrets.pop(name, None)
        self._save()
