"""Persistent configuration for MicWatch."""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "micwatch"
CONFIG_FILE = CONFIG_DIR / "config.json"

MIN_DB = -60.0

APP_NAME = "MicWatch"
METER_NODE_NAME = "MicWatch Meter"

DEFAULTS: dict = {
    # --- appearance ---
    "icon_style": "mic",          # mic | mic_filled | badge | dot | ring | bars
    "color_idle": "#6e7681",      # nothing is recording
    "color_standby": "#e3b341",   # mic open, but below the threshold
    "color_active": "#3fb950",    # mic open and above the threshold
    "animation": "glow",          # see icons.ANIMATIONS
    "animation_speed": 1.0,       # 0.25 .. 3.0
    "animation_fps": 20,
    "shade_by_level": False,      # blend standby -> active colour with the level

    # --- behaviour ---
    "hide_when_idle": False,
    "show_standby": True,         # distinct colour while open but quiet
    "tooltip_show_level": True,

    # --- detection ---
    "threshold_enabled": True,
    "threshold_db": -42.0,        # dBFS, -60 (very sensitive) .. 0
    "meter_source": "auto",       # "auto" = follow the app that is recording
    "hold_ms": 700,               # keep it lit this long after dropping below
    "smoothing": 0.45,            # release smoothing; attack is always fast
    "ignore_corked": True,        # ignore paused streams
    "include_virtual": False,     # count virtual sources (screen-share, loopback)
    "ignore_apps": [],            # lower-case app names to never count
    "poll_ms": 1500,              # safety-net poll on top of pactl events
}


class Config:
    def __init__(self) -> None:
        self._data = dict(DEFAULTS)
        self.load()

    # -- dict-ish access -------------------------------------------------
    def __getitem__(self, key: str):
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value) -> None:
        self._data[key] = value

    def get(self, key: str, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def update(self, values: dict) -> None:
        self._data.update(values)

    def as_dict(self) -> dict:
        return dict(self._data)

    def reset(self) -> None:
        self._data = dict(DEFAULTS)

    # -- persistence -----------------------------------------------------
    def load(self) -> None:
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            raw.pop("threshold", None)  # 1.0 stored a linear threshold; dB replaces it
            for key, value in raw.items():
                if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
                    self._data[key] = value
                elif key in DEFAULTS and isinstance(DEFAULTS[key], float):
                    try:
                        self._data[key] = float(value)
                    except (TypeError, ValueError):
                        pass

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CONFIG_FILE)
