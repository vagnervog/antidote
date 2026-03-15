"""Telegram channel — long-polling, private DMs only."""

import logging
import os
import tempfile

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, MessageHandler, filters

from antidote.channels.base import BaseChannel, IncomingMessage, OutgoingMessage
from antidote.config import Config

logger = logging.getLogger(__name__)

MAX_MSG_LEN = 4096


def _split_message(text: str) -> list[str]:
    """Split long text at paragraph boundaries to fit Telegram's limit."""
    if len(text) <= MAX_MSG_LEN:
        return [text]

    chunks = []
    while text:
        if len(text) <= MAX_MSG_LEN:
            chunks.append(text)
            break
        # Find last paragraph break within limit
        cut = text.rfind("\n\n", 0, MAX_MSG_LEN)
        if cut == -1:
            cut = text.rfind("\n", 0, MAX_MSG_LEN)
        if cut == -1:
            cut = MAX_MSG_LEN
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


class TelegramChannel(BaseChannel):
    def __init__(self, config: Config):
        self._config = config
        token = config.get_secret("TELEGRAM_BOT_TOKEN") or os.environ.get(
            "TELEGRAM_BOT_TOKEN"
        )
        if not token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN not found. Run 'antidote setup' to configure."
            )
        self._app = Application.builder().token(token).build()
        self._on_message = None

    async def start(self, on_message: callable) -> None:
        self._on_message = on_message
        self._app.add_handler(
            MessageHandler(filters.ALL & filters.ChatType.PRIVATE, self._handle)
        )
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram channel started (long-polling)")
        # Keep running
        import asyncio
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

    async def send(self, message: OutgoingMessage) -> None:
        chunks = _split_message(message.text)
        for chunk in chunks:
            try:
                await self._app.bot.send_message(
                    chat_id=int(message.chat_id),
                    text=chunk,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                # Fallback to plain text if Markdown fails
                await self._app.bot.send_message(
                    chat_id=int(message.chat_id),
                    text=chunk,
                )

    async def stop(self) -> None:
        logger.info("Stopping Telegram channel...")
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    async def _handle(self, update: Update, context) -> None:
        if not update.message or not self._on_message:
            return

        msg = update.message
        text = msg.text or msg.caption or ""
        media = None

        # Handle photos
        if msg.photo:
            photo = msg.photo[-1]  # Largest size
            file = await context.bot.get_file(photo.file_id)
            path = os.path.join(tempfile.gettempdir(), f"antidote_{photo.file_id}.jpg")
            await file.download_to_drive(path)
            media = [{"type": "photo", "url": path, "caption": msg.caption}]

        # Handle voice
        if msg.voice:
            file = await context.bot.get_file(msg.voice.file_id)
            path = os.path.join(tempfile.gettempdir(), f"antidote_{msg.voice.file_id}.ogg")
            await file.download_to_drive(path)
            media = [{"type": "voice", "url": path, "caption": "[Voice message — transcription coming soon]"}]
            if not text:
                text = "[Voice message received]"

        # Handle documents
        if msg.document:
            file = await context.bot.get_file(msg.document.file_id)
            path = os.path.join(tempfile.gettempdir(), f"antidote_{msg.document.file_name}")
            await file.download_to_drive(path)
            media = [{"type": "document", "url": path, "caption": msg.document.file_name}]

        if not text and not media:
            return

        # Typing indicator
        await context.bot.send_chat_action(
            chat_id=msg.chat_id, action=ChatAction.TYPING
        )

        incoming = IncomingMessage(
            text=text,
            sender_id=str(msg.from_user.id),
            sender_name=msg.from_user.first_name or "User",
            chat_id=str(msg.chat_id),
            timestamp=msg.date.timestamp(),
            media=media,
        )

        try:
            response_text = await self._on_message(incoming)
            outgoing = OutgoingMessage(text=response_text, chat_id=str(msg.chat_id))
            await self.send(outgoing)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send(
                OutgoingMessage(
                    text="Sorry, something went wrong. Please try again.",
                    chat_id=str(msg.chat_id),
                )
            )
