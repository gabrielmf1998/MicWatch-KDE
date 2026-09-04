"""Check GitHub for a newer release, and hand the user a one-click upgrade."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from . import __version__

REPO = "gabrielmf1998/MicWatch-KDE"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
INSTALL_URL = f"https://raw.githubusercontent.com/{REPO}/main/install-online.sh"
INSTALL_COMMAND = f"curl -fsSL {INSTALL_URL} | sh"

TERMINALS = [
    ("konsole", ["-e"]),
    ("gnome-terminal", ["--"]),
    ("kgx", ["--"]),
    ("xfce4-terminal", ["-x"]),
    ("kitty", []),
    ("alacritty", ["-e"]),
    ("foot", []),
    ("x-terminal-emulator", ["-e"]),
    ("xterm", ["-e"]),
]


@dataclass
class Release:
    tag: str
    name: str
    url: str
    body: str
    appimage_url: str = ""

    @property
    def version(self) -> str:
        return self.tag.lstrip("vV")


def parse_version(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in text.lstrip("vV").split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def current_version() -> str:
    return __version__


def is_newer(candidate: str, installed: str) -> bool:
    return parse_version(candidate) > parse_version(installed)


def running_as_appimage() -> str:
    return os.environ.get("APPIMAGE", "")


def fetch_latest(timeout: float = 8.0) -> Release | None:
    request = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"MicWatch/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if not isinstance(data, dict) or not data.get("tag_name"):
        return None
    appimage = ""
    for asset in data.get("assets") or []:
        name = asset.get("name", "")
        if name.endswith(".AppImage"):
            appimage = asset.get("browser_download_url", "")
    return Release(
        tag=str(data["tag_name"]),
        name=str(data.get("name") or data["tag_name"]),
        url=str(data.get("html_url") or RELEASES_URL),
        body=str(data.get("body") or ""),
        appimage_url=appimage,
    )


def terminal_command(script: str) -> list[str] | None:
    """Wrap a shell script in whatever terminal emulator this desktop has."""
    for name, flags in TERMINALS:
        path = shutil.which(name)
        if path:
            return [path, *flags, "sh", "-c", script]
    return None


def update_script(release: Release | None = None) -> str:
    """The shell MicWatch runs to upgrade itself."""
    appimage = running_as_appimage()
    if appimage and release and release.appimage_url:
        return (
            f'set -e; echo "Updating {os.path.basename(appimage)}…"; '
            f'tmp="$(mktemp)"; curl -fL --progress-bar "{release.appimage_url}" -o "$tmp"; '
            f'chmod +x "$tmp"; mv "$tmp" "{appimage}"; '
            'echo; echo "Done. Start MicWatch again."; '
            'printf "Press Enter to close… "; read _'
        )
    return (
        f'{INSTALL_COMMAND}; status=$?; echo; '
        '[ $status -eq 0 ] && echo "Done. Restart MicWatch to run the new version." '
        '|| echo "Update failed (exit $status)."; '
        'printf "Press Enter to close… "; read _'
    )


def launch_update(release: Release | None = None) -> bool:
    """Open a terminal running the upgrade, so the user can type their password."""
    command = terminal_command(update_script(release))
    if command is None:
        return False
    try:
        subprocess.Popen(command, start_new_session=True)
    except OSError:
        return False
    return True


class _Worker(QThread):
    done = Signal(object)

    def run(self) -> None:  # noqa: D102
        self.done.emit(fetch_latest())


class UpdateChecker(QObject):
    """Fetches the latest release off the GUI thread."""

    checked = Signal(object, bool)   # (Release | None, is_newer)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: _Worker | None = None

    @property
    def busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def check(self) -> None:
        if self.busy:
            return
        self._worker = _Worker(self)
        self._worker.done.connect(self._finished)
        self._worker.start()

    def _finished(self, release) -> None:
        newer = bool(release) and is_newer(release.tag, current_version())
        self.checked.emit(release, newer)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
