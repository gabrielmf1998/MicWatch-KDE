"""XDG autostart entry: start MicWatch with the session."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from .config import APP_NAME

AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "micwatch.desktop"
LAUNCHER = Path.home() / ".local" / "bin" / "micwatch"


def exec_command() -> str:
    """How to relaunch this exact installation."""
    if LAUNCHER.is_file() and os.access(LAUNCHER, os.X_OK):
        return str(LAUNCHER)
    root = Path(__file__).resolve().parent.parent
    return "env %s %s -m micwatch" % (
        shlex.quote(f"PYTHONPATH={root}"),
        shlex.quote(sys.executable),
    )


def is_enabled() -> bool:
    if not AUTOSTART_FILE.is_file():
        return False
    try:
        text = AUTOSTART_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "Hidden" and value.strip().lower() == "true":
            return False
        if key.strip() == "X-GNOME-Autostart-enabled" and value.strip().lower() == "false":
            return False
    return True


def set_enabled(enabled: bool) -> bool:
    """Write or remove the autostart entry. Returns the resulting state."""
    if enabled:
        try:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FILE.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                "GenericName=Microphone Indicator\n"
                "Comment=Tray indicator that lights up when the microphone is in use\n"
                f"Exec={exec_command()}\n"
                "Icon=audio-input-microphone\n"
                "Terminal=false\n"
                "NoDisplay=false\n"
                "Hidden=false\n"
                "X-GNOME-Autostart-enabled=true\n"
                "X-KDE-autostart-after=panel\n"
                "StartupNotify=false\n",
                encoding="utf-8",
            )
        except OSError:
            return is_enabled()
    else:
        try:
            AUTOSTART_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    return is_enabled()


def describe() -> str:
    if is_enabled():
        return f"Enabled — {AUTOSTART_FILE}"
    return "Disabled — MicWatch will not start with the session"
