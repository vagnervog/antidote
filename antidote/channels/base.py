"""Channel interface and shared dataclasses."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class IncomingMessage:
    text: str
    sender_id: str
    sender_name: str
    chat_id: str
    timestamp: float
    media: list | None = None  # List of {type, url, caption}


@dataclass
class OutgoingMessage:
    text: str
    chat_id: str
    media: list | None = None
    reply_to: str | None = None


class BaseChannel(ABC):
    @abstractmethod
    async def start(self, on_message: callable) -> None:
        """Start listening. Call on_message(IncomingMessage) for each incoming."""
        ...

    @abstractmethod
    async def send(self, message: OutgoingMessage) -> None:
        """Send a message to the channel."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully disconnect."""
        ...
