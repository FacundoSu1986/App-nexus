"""Telegram bot interface for the Dovha modding agent."""

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)


class DovhaTelegramBot:
    """Asynchronous Telegram bot that forwards prompts to an AI agent.

    Parameters
    ----------
    bot_token : str
        Telegram Bot API token.
    allowed_user_id : int
        Telegram user ID allowed to interact with the bot.
    agent
        An AI agent instance that exposes a synchronous ``.chat()`` method.
    """

    def __init__(self, bot_token: str, allowed_user_id: int, agent) -> None:
        self.bot_token = bot_token
        self.allowed_user_id = allowed_user_id
        self.agent = agent

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    async def _is_authorized(self, update: Update) -> bool:
        """Return *True* only when the message comes from the allowed user."""
        user_id = update.effective_user.id
        if user_id != self.allowed_user_id:
            logger.warning(
                "Unauthorized access attempt from user %s", user_id
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def handle_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle the ``/start`` command."""
        if not await self._is_authorized(update):
            return
        await update.message.reply_text(
            "Greetings, Dragonborn. I am Dovha, your modding agent. "
            "Awaiting your commands."
        )

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Forward a text message to the AI agent and reply with its answer."""
        if not await self._is_authorized(update):
            return
        response = await asyncio.to_thread(
            self.agent.chat, update.message.text
        )
        await update.message.reply_text(str(response))

    # ------------------------------------------------------------------
    # Runner
    # ------------------------------------------------------------------

    def start_polling(self) -> None:
        """Build the Telegram application and start long-polling."""
        application = Application.builder().token(self.bot_token).build()
        application.add_handler(CommandHandler("start", self.handle_start))
        application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, self.handle_message
            )
        )
        logger.info("Dovha Telegram bot is starting...")
        application.run_polling()
