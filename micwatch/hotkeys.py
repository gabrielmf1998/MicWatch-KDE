"""Global keyboard shortcuts, read straight from the kernel input devices.

A Qt shortcut only fires while the window has focus, which is useless for
muting a microphone mid-call, and KDE's shortcut daemon is not reachable from a
plain Qt process here. So MicWatch reads /dev/input directly: the combination
works in a fullscreen game, on Wayland and on X11 alike.

Nothing is ever grabbed and nothing is logged — the listener only compares each
key press against the combinations you configured.

Two kinds of binding live here. A *shortcut* fires once, when the key goes down.
A *hold* reports the press and the release separately, which is what push-to-talk
needs: the microphone opens while the key is down and closes when you let go.
"""

from __future__ import annotations

import os
import selectors
import threading

from PySide6.QtCore import QThread, Signal

try:  # optional: without it the rest of MicWatch still works
    import evdev
    from evdev import ecodes
except Exception:  # pragma: no cover - depends on the host
    evdev = None
    ecodes = None

MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Meta")
_MODIFIER_NAMES = {
    "Ctrl": ("KEY_LEFTCTRL", "KEY_RIGHTCTRL"),
    "Shift": ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"),
    "Alt": ("KEY_LEFTALT", "KEY_RIGHTALT"),
    "Meta": ("KEY_LEFTMETA", "KEY_RIGHTMETA"),
}

# Qt writes shortcuts like "Ctrl+Shift+B"; these are the spellings it uses for
# keys whose name is not simply the character.
_SPECIAL_NAMES = {
    "Space": "KEY_SPACE", "Return": "KEY_ENTER", "Enter": "KEY_KPENTER",
    "Backspace": "KEY_BACKSPACE", "Esc": "KEY_ESC", "Escape": "KEY_ESC",
    "Tab": "KEY_TAB", "Backtab": "KEY_TAB", "Ins": "KEY_INSERT",
    "Insert": "KEY_INSERT", "Del": "KEY_DELETE", "Delete": "KEY_DELETE",
    "Home": "KEY_HOME", "End": "KEY_END", "PgUp": "KEY_PAGEUP",
    "PgDown": "KEY_PAGEDOWN", "Up": "KEY_UP", "Down": "KEY_DOWN",
    "Left": "KEY_LEFT", "Right": "KEY_RIGHT", "Print": "KEY_SYSRQ",
    "SysReq": "KEY_SYSRQ", "ScrollLock": "KEY_SCROLLLOCK", "Pause": "KEY_PAUSE",
    "Menu": "KEY_COMPOSE", "CapsLock": "KEY_CAPSLOCK", "NumLock": "KEY_NUMLOCK",
    "-": "KEY_MINUS", "=": "KEY_EQUAL", "+": "KEY_EQUAL", "[": "KEY_LEFTBRACE",
    "]": "KEY_RIGHTBRACE", ";": "KEY_SEMICOLON", "'": "KEY_APOSTROPHE",
    ",": "KEY_COMMA", ".": "KEY_DOT", "/": "KEY_SLASH", "\\": "KEY_BACKSLASH",
    "`": "KEY_GRAVE",
}


def _code(name: str) -> int | None:
    return getattr(ecodes, name, None) if ecodes is not None else None


def _modifier_codes() -> dict[str, frozenset[int]]:
    table: dict[str, frozenset[int]] = {}
    for label, names in _MODIFIER_NAMES.items():
        codes = {c for c in (_code(n) for n in names) if c is not None}
        if codes:
            table[label] = frozenset(codes)
    return table


def _trigger_code(key: str) -> int | None:
    """Map one Qt key name to an evdev key code."""
    if ecodes is None or not key:
        return None
    if key in _SPECIAL_NAMES:
        return _code(_SPECIAL_NAMES[key])
    if len(key) == 1:
        char = key.upper()
        if char.isalpha() or char.isdigit():
            return _code(f"KEY_{char}")
        return None
    if key[0] in "Ff" and key[1:].isdigit():
        return _code(f"KEY_F{int(key[1:])}")
    return None


def split(text: str) -> tuple[list[str], str]:
    """'Ctrl+Shift+B' -> (['Ctrl', 'Shift'], 'B'); handles a bare '+' key."""
    text = (text or "").strip()
    if not text:
        return [], ""
    parts = text.split("+")
    if parts[-1] == "":            # trailing '+' means the key itself is '+'
        parts = parts[:-1]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        parts.append("+")
    modifiers = [p for p in parts[:-1] if p]
    return modifiers, parts[-1]


def normalise(text: str) -> str:
    modifiers, key = split(text)
    known = [m for m in MODIFIER_ORDER if m in modifiers]
    return "+".join([*known, key]) if key else ""


def parse(text: str) -> tuple[frozenset[str], int] | None:
    """Turn a shortcut string into (modifier names, evdev key code)."""
    modifiers, key = split(text)
    code = _trigger_code(key)
    if code is None:
        return None
    known = {m for m in modifiers if m in _MODIFIER_NAMES}
    if len(known) != len(modifiers):
        return None
    return frozenset(known), code


def is_valid(text: str) -> bool:
    return parse(text) is not None


def has_modifier(text: str) -> bool:
    modifiers, _ = split(text)
    return bool(modifiers)


def keyboards(wanted: frozenset = frozenset()) -> list:
    """Every readable input device that can emit the keys we care about.

    A normal keyboard is the common case, but gaming keyboards put their macro
    and media keys on a second device that has no KEY_A at all, and a push-to-talk
    key has to work wherever it physically lives — so any device that can emit a
    key we were asked to watch is opened too.
    """
    if evdev is None:
        return []
    found = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        try:
            keys = set(device.capabilities().get(ecodes.EV_KEY, []))
        except OSError:
            device.close()
            continue
        typing = ecodes.KEY_A in keys and ecodes.KEY_LEFTSHIFT in keys
        if typing or (wanted and keys & wanted):
            found.append(device)
        else:
            device.close()
    return found


def availability() -> tuple[bool, str]:
    """Can we listen at all, and what should the user be told?"""
    if evdev is None:
        return False, (
            "Global shortcuts need the python3-evdev package "
            "(Fedora: sudo dnf install python3-evdev)."
        )
    devices = keyboards()
    count = len(devices)
    for device in devices:
        device.close()
    if not count:
        return False, (
            "No readable keyboard in /dev/input. Add your user to the 'input' group "
            "(sudo usermod -aG input $USER) and log back in."
        )
    return True, f"Listening on {count} keyboard{'s' if count != 1 else ''}."


class HotkeyListener(QThread):
    """Watches every keyboard for the configured combinations."""

    activated = Signal(str)          # action id, on the key going down
    hold_changed = Signal(str, bool)  # action id, True on press and False on release
    status_changed = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bindings: dict[str, tuple[frozenset[str], int]] = {}
        self._holds: dict[str, tuple[frozenset[str], int]] = {}
        self._down: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake_r, self._wake_w = os.pipe()
        self._modifiers = _modifier_codes()

    # -- control ---------------------------------------------------------
    def set_bindings(self, mapping: dict[str, str]) -> None:
        """mapping: {action id: 'Ctrl+Alt+M'}"""
        parsed: dict[str, tuple[frozenset[str], int]] = {}
        for action, text in mapping.items():
            combo = parse(text)
            if combo is not None:
                parsed[action] = combo
        with self._lock:
            self._bindings = parsed
        self._wake()

    def set_holds(self, mapping: dict[str, str]) -> None:
        """Bindings whose press and release are both reported (push-to-talk)."""
        parsed: dict[str, tuple[frozenset[str], int]] = {}
        for action, text in mapping.items():
            combo = parse(text)
            if combo is not None:
                parsed[action] = combo
        with self._lock:
            self._holds = parsed
            stale = [a for a in self._down if a not in parsed]
            self._down -= set(stale)
        for action in stale:      # a binding that vanished counts as released
            self.hold_changed.emit(action, False)
        self._wake()

    def _wanted_codes(self) -> frozenset:
        """Every key code we were asked to watch, for picking input devices."""
        with self._lock:
            combos = list(self._bindings.values()) + list(self._holds.values())
        return frozenset(code for _, code in combos)

    @property
    def has_work(self) -> bool:
        with self._lock:
            return bool(self._bindings or self._holds)

    def release_all(self) -> None:
        """Fail-safe: we can no longer see the keyboard, so nothing is held.

        Called whenever the device set is rebuilt or the thread stops — without
        it a key released behind our back would leave push-to-talk stuck open.
        """
        with self._lock:
            actions = list(self._down)
            self._down.clear()
        for action in actions:
            self.hold_changed.emit(action, False)

    def stop(self) -> None:
        self._stop.set()
        self._wake()
        self.wait(1500)
        self.release_all()

    def _wake(self) -> None:
        try:
            os.write(self._wake_w, b"1")
        except OSError:
            pass

    # -- loop ------------------------------------------------------------
    def run(self) -> None:  # noqa: D102
        self._stop.clear()
        try:                                   # drop anything left in the pipe
            os.set_blocking(self._wake_r, False)
            while os.read(self._wake_r, 256):
                pass
        except (OSError, BlockingIOError):
            pass
        finally:
            os.set_blocking(self._wake_r, True)
        ok, message = availability()
        self.status_changed.emit(ok, message)
        if not ok:
            return

        while not self._stop.is_set():
            devices = keyboards(self._wanted_codes())
            if not devices:
                self.status_changed.emit(False, "No readable keyboard in /dev/input.")
                if self._stop.wait(5):
                    break
                continue
            # Compare against every device node, not just the keyboards we
            # opened: list_devices() lists mice and everything else too, so
            # comparing it with our filtered set was never equal — the loop
            # rebuilt itself on every pass and lost `held` with it, which is why
            # a combination like Ctrl+B could never fire.
            all_paths = set(evdev.list_devices()) if evdev is not None else set()
            selector = selectors.DefaultSelector()
            selector.register(self._wake_r, selectors.EVENT_READ, None)
            for device in devices:
                selector.register(device, selectors.EVENT_READ, device)
            held: set[int] = set()
            stale = False
            try:
                while not self._stop.is_set():
                    for key, _ in selector.select(timeout=1):
                        device = key.data
                        if device is None:
                            try:
                                os.read(self._wake_r, 64)
                            except OSError:
                                pass
                            continue
                        try:
                            events = list(device.read())
                        except OSError:
                            selector.unregister(device)
                            stale = True      # lost a keyboard: start over
                            continue
                        self._handle(events, held)
                    if stale:
                        break
                    if evdev is not None and set(evdev.list_devices()) != all_paths:
                        break  # a device came or went: rebuild the selector
            finally:
                selector.close()
                for device in devices:
                    try:
                        device.close()
                    except OSError:
                        pass
                self.release_all()   # we stop seeing key-ups from here on

    def _handle(self, events, held: set[int]) -> None:
        for event in events:
            if ecodes is None or event.type != ecodes.EV_KEY:
                continue
            if event.value == 0:
                held.discard(event.code)
                self._release_code(event.code)
                continue
            if event.value != 1:      # 2 == auto-repeat: it is already down
                continue
            held.add(event.code)
            active = {
                name for name, codes in self._modifiers.items() if held & codes
            }
            with self._lock:
                bindings = dict(self._bindings)
                holds = dict(self._holds)
            for action, (modifiers, trigger) in bindings.items():
                if event.code == trigger and active == modifiers:
                    self.activated.emit(action)
            # A hold only needs its modifiers to be present, not to be the only
            # ones down: you may well be holding Shift to run while you talk.
            for action, (modifiers, trigger) in holds.items():
                if event.code == trigger and modifiers <= active:
                    self._press(action)

    def _press(self, action: str) -> None:
        with self._lock:
            if action in self._down:
                return
            self._down.add(action)
        self.hold_changed.emit(action, True)

    def _release_code(self, code: int) -> None:
        """A key came up: release every hold triggered by it, whatever modifiers
        are still down — you may let go of Ctrl before the talk key itself."""
        with self._lock:
            actions = [
                a for a, (_, trigger) in self._holds.items()
                if trigger == code and a in self._down
            ]
            self._down -= set(actions)
        for action in actions:
            self.hold_changed.emit(action, False)
