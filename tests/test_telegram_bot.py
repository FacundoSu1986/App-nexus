"""Tests for the Dovha Telegram bot."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.telegram.bot import DovhaTelegramBot

ALLOWED_USER_ID = 12345
UNAUTHORIZED_USER_ID = 99999
BOT_TOKEN = "fake-token"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_update(user_id: int, text: str = "") -> MagicMock:
    """Create a mock ``Update`` object with the given user id and text."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _make_bot(agent: MagicMock | None = None) -> DovhaTelegramBot:
    """Create a ``DovhaTelegramBot`` with a mock agent."""
    if agent is None:
        agent = MagicMock()
        agent.chat = MagicMock(return_value="agent reply")
    return DovhaTelegramBot(
        bot_token=BOT_TOKEN,
        allowed_user_id=ALLOWED_USER_ID,
        agent=agent,
    )


# ------------------------------------------------------------------
# Authorization (whitelist) tests
# ------------------------------------------------------------------


class TestAuthorization:
    """Ensure the whitelist security guard works correctly."""

    @pytest.mark.asyncio
    async def test_authorized_user_returns_true(self):
        """An allowed user should pass the authorization check."""
        bot = _make_bot()
        update = _make_update(ALLOWED_USER_ID)
        assert await bot._is_authorized(update) is True

    @pytest.mark.asyncio
    async def test_unauthorized_user_returns_false(self):
        """A disallowed user should fail the authorization check."""
        bot = _make_bot()
        update = _make_update(UNAUTHORIZED_USER_ID)
        assert await bot._is_authorized(update) is False

    @pytest.mark.asyncio
    async def test_unauthorized_user_logged(self, caplog):
        """A warning should be logged for unauthorized access attempts."""
        bot = _make_bot()
        update = _make_update(UNAUTHORIZED_USER_ID)
        with caplog.at_level("WARNING"):
            await bot._is_authorized(update)
        assert "Unauthorized access attempt from user" in caplog.text


# ------------------------------------------------------------------
# /start command tests
# ------------------------------------------------------------------


class TestStartCommand:
    """Tests for the /start command handler."""

    @pytest.mark.asyncio
    async def test_authorized_start(self):
        """An authorized /start should reply with the greeting."""
        bot = _make_bot()
        update = _make_update(ALLOWED_USER_ID)
        context = MagicMock()

        await bot.handle_start(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "Dovha" in reply
        assert "modding agent" in reply

    @pytest.mark.asyncio
    async def test_unauthorized_start_ignored(self):
        """An unauthorized /start should be silently ignored."""
        bot = _make_bot()
        update = _make_update(UNAUTHORIZED_USER_ID)
        context = MagicMock()

        await bot.handle_start(update, context)

        update.message.reply_text.assert_not_awaited()


# ------------------------------------------------------------------
# Text message handler tests
# ------------------------------------------------------------------


class TestMessageHandler:
    """Tests for the text message handler."""

    @pytest.mark.asyncio
    async def test_authorized_message_calls_agent(self):
        """An authorized message should invoke agent.chat and reply."""
        agent = MagicMock()
        agent.chat = MagicMock(return_value="modded response")
        bot = _make_bot(agent)
        update = _make_update(ALLOWED_USER_ID, text="Install SKSE")
        context = MagicMock()

        await bot.handle_message(update, context)

        agent.chat.assert_called_once_with("Install SKSE")
        update.message.reply_text.assert_awaited_once_with("modded response")

    @pytest.mark.asyncio
    async def test_unauthorized_message_ignored(self):
        """An unauthorized text message should be ignored entirely."""
        agent = MagicMock()
        agent.chat = MagicMock(return_value="should not be called")
        bot = _make_bot(agent)
        update = _make_update(UNAUTHORIZED_USER_ID, text="hack")
        context = MagicMock()

        await bot.handle_message(update, context)

        agent.chat.assert_not_called()
        update.message.reply_text.assert_not_awaited()
