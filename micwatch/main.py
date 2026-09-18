"""Entry point."""

from __future__ import annotations

import signal
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .config import APP_NAME, Config
from .tray import MicWatchTray


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("micwatch")
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(str(Path(tempfile.gettempdir()) / f"micwatch-{Path.home().name}.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        print("MicWatch is already running.", file=sys.stderr)
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "No system tray is available on this session.")
        return 1

    config = Config()
    tray = MicWatchTray(config)

    if "--settings" in argv:
        QTimer.singleShot(200, tray.open_settings)

    # Quitting has to run tray.quit(): push-to-talk holds the microphone muted,
    # and a session logout or `systemctl stop` sends SIGTERM, not SIGINT — without
    # this the microphone would be left dead with nothing running to open it.
    for _sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(_sig, lambda *_: tray.quit())
        except (OSError, ValueError, AttributeError):
            pass
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)  # let Python handle signals

    return app.exec()
