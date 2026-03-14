"""
App-nexus — Skyrim Mod Compatibility Manager
Entry point.

Run directly with Python:
    python main.py

Or build to a standalone .exe with PyInstaller:
    pyinstaller build/app_nexus.spec
"""

from src.gui.main_window import MainWindow


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
