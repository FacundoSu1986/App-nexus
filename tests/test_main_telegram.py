"""Tests for the Telegram bot integration in main.py."""

import os
import sys
from unittest.mock import MagicMock, patch

# Stub out modules that require a display server so main.py can be imported
# in headless CI environments.
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("tkinter.ttk", MagicMock())
sys.modules.setdefault("sv_ttk", MagicMock())

from main import _TelegramChatAgent  # noqa: E402


class TestTelegramChatAgent:
    """Tests for the adapter that bridges local_agent.chat → bot interface."""

    def test_chat_delegates_to_local_agent(self):
        """The adapter should call local_agent.chat and return the reply."""
        db = MagicMock()
        agent = _TelegramChatAgent(db)

        with patch("main.local_agent") as mock_module:
            mock_module.chat.return_value = ("hello world", [{"role": "assistant"}])
            result = agent.chat("hi")

        mock_module.chat.assert_called_once_with("hi", db, history=None)
        assert result == "hello world"

    def test_chat_preserves_history_across_calls(self):
        """History returned by the first call should be passed to the next."""
        db = MagicMock()
        agent = _TelegramChatAgent(db)

        history_1 = [{"role": "system"}, {"role": "user"}, {"role": "assistant"}]
        history_2 = history_1 + [{"role": "user"}, {"role": "assistant"}]

        with patch("main.local_agent") as mock_module:
            mock_module.chat.side_effect = [
                ("first", history_1),
                ("second", history_2),
            ]
            agent.chat("one")
            agent.chat("two")

        # Second call should receive the history returned by the first call
        assert mock_module.chat.call_args_list[1][1]["history"] == history_1


class TestMainTelegramIntegration:
    """Smoke-test that main() wires the Telegram bot correctly."""

    @patch.dict("os.environ", {"TELEGRAM_TOKEN": "real-token"})
    @patch("main.MainWindow")
    @patch("main.sv_ttk")
    @patch("main.DovhaTelegramBot")
    @patch("main.DatabaseManager")
    @patch("main.local_agent")
    @patch("main.threading.Thread")
    def test_bot_started_in_daemon_thread(
        self, mock_thread_cls, mock_la, mock_db_cls, mock_bot_cls,
        mock_sv, mock_mw,
    ):
        """main() should create a daemon thread for the bot and start it."""
        import main as main_mod

        mock_db_inst = MagicMock()
        mock_db_cls.return_value = mock_db_inst

        mock_bot_inst = MagicMock()
        mock_bot_cls.return_value = mock_bot_inst

        mock_thread_inst = MagicMock()
        mock_thread_cls.return_value = mock_thread_inst

        main_mod.main()

        # DatabaseManager created and connected
        mock_db_cls.assert_called_once()
        mock_db_inst.connect.assert_called_once()

        # DovhaTelegramBot instantiated with correct args
        mock_bot_cls.assert_called_once()
        call_kwargs = mock_bot_cls.call_args[1]
        assert "bot_token" in call_kwargs
        assert "allowed_user_id" in call_kwargs
        assert "agent" in call_kwargs

        # Daemon thread created and started
        mock_thread_cls.assert_called_once_with(
            target=mock_bot_inst.start_polling, daemon=True,
        )
        mock_thread_inst.start.assert_called_once()

        # GUI mainloop still called
        mock_mw.return_value.mainloop.assert_called_once()

    @patch.dict("os.environ", {}, clear=False)
    @patch("main.MainWindow")
    @patch("main.sv_ttk")
    @patch("main.DovhaTelegramBot")
    @patch("main.threading.Thread")
    def test_bot_skipped_when_token_is_placeholder(
        self, mock_thread_cls, mock_bot_cls, mock_sv, mock_mw,
    ):
        """When TELEGRAM_TOKEN is not set, the bot should not start."""
        import main as main_mod

        # Ensure the placeholder fallback is used
        os.environ.pop("TELEGRAM_TOKEN", None)

        main_mod.main()

        mock_bot_cls.assert_not_called()
        mock_thread_cls.assert_not_called()
        # GUI should still work
        mock_mw.return_value.mainloop.assert_called_once()
