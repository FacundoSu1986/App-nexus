"""
App-nexus — Skyrim Mod Compatibility Manager
Entry point.

Run directly with Python:
    python main.py

Or build to a standalone .exe with PyInstaller:
    pyinstaller build/app_nexus.spec
"""

import logging
import os
import sys
import threading

import sv_ttk

from src.ai import local_agent
from src.database.manager import DatabaseManager
from src.gui.main_window import MainWindow
from src.telegram.bot import DovhaTelegramBot


def _setup_logging() -> None:
    """Configure application-wide logging to file and console."""
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    log_dir = os.path.join(app_data, "AppNexus", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app_nexus.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


class _TelegramChatAgent:
    """Wrap the module-level :func:`local_agent.chat` so it exposes the
    ``.chat(text) -> str`` interface expected by :class:`DovhaTelegramBot`."""

    def __init__(self, db):
        self._db = db
        self._history = None

    def chat(self, message: str) -> str:
        reply, self._history = local_agent.chat(
            message, self._db, history=self._history,
        )
        return reply


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("App-nexus starting.")
    app = MainWindow()

    sv_ttk.set_theme("dark")

    # -- Telegram bot --------------------------------------------------
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_ACA")
    ALLOWED_USER_ID = int(
        os.environ.get("TELEGRAM_ALLOWED_USER_ID", "123456789")
    )

    if TELEGRAM_TOKEN != "TU_TOKEN_ACA":
        db = DatabaseManager()
        db.connect()
        bot_agent = _TelegramChatAgent(db)
        telegram_bot = DovhaTelegramBot(
            bot_token=TELEGRAM_TOKEN,
            allowed_user_id=ALLOWED_USER_ID,
            agent=bot_agent,
        )

        bot_thread = threading.Thread(
            target=telegram_bot.start_polling, daemon=True,
        )
        bot_thread.start()
        logger.info("Telegram bot thread started.")
    else:
        logger.info(
            "Telegram bot disabled — set TELEGRAM_TOKEN env var to enable."
        )

    app.mainloop()
    logger.info("App-nexus exiting.")


if __name__ == "__main__":
    main()
