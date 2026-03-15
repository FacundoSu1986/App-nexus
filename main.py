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

import sv_ttk

from src.gui.main_window import MainWindow


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


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("App-nexus starting.")
    app = MainWindow()

    sv_ttk.set_theme("dark")

    app.mainloop()
    logger.info("App-nexus exiting.")


if __name__ == "__main__":
    main()
