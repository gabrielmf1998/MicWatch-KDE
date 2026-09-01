"""Tray icon, state machine and the glue between detection, level and drawing."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from . import autostart, icons
from .audio import LevelMeter, MicMonitor
from .config import APP_NAME, MIN_DB

IDLE, STANDBY, ACTIVE = "idle", "standby", "active"

# styles whose drawing reacts to the level, so they need repainting as it moves
REACTIVE_STYLES = {
    "dot", "dot_ring", "led", "record", "ring", "ring_dual", "gauge",
    "bars", "bars_wide", "waveform", "radar", "pulse_line", "mic_boom",
}


def to_db(level: float) -> float:
    return MIN_DB if level <= 0.000001 else max(MIN_DB, 20.0 * math.log10(level))


class MicWatchTray(QObject):
    level_changed = Signal(float)     # smoothed linear level, for the settings meter
    state_changed = Signal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.state = IDLE
        self.level = 0.0
        self._phase = 0.0
        self._last_tick = time.monotonic()
        self._last_above = 0.0
        self._preview = False
        self._settings = None

        self.monitor = MicMonitor(config, self)
        self.monitor.changed.connect(self._on_streams)
        self.meter = LevelMeter(self)
        self.meter.level.connect(self._on_level)
        self.meter.failed.connect(self._on_meter_failed)

        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self._on_activated)
        self._build_menu()

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)

        self.monitor.start()
        self._refresh_all()
        self.tray.show()

    # -- menu ------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = QMenu()
        self._status_action = QAction("Microphone idle", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        menu.addSeparator()

        settings_action = QAction("Settings…", menu)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        self._autostart_action = QAction("Start on login", menu)
        self._autostart_action.setCheckable(True)
        self._autostart_action.setChecked(autostart.is_enabled())
        self._autostart_action.toggled.connect(self._toggle_autostart)
        menu.addAction(self._autostart_action)

        about_action = QAction(f"About {APP_NAME}", menu)
        about_action.triggered.connect(self._about)
        menu.addAction(about_action)
        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.menu = menu
        self.tray.setContextMenu(menu)

    def _toggle_autostart(self, enabled: bool) -> None:
        result = autostart.set_enabled(enabled)
        if result != enabled:
            self.sync_autostart_action()
        window = self._settings
        if window is not None and hasattr(window, "autostart"):
            window.autostart.blockSignals(True)
            window.autostart.setChecked(result)
            window.autostart.blockSignals(False)
            window.autostart_note.setText(autostart.describe())

    def sync_autostart_action(self) -> None:
        enabled = autostart.is_enabled()
        if self._autostart_action.isChecked() != enabled:
            self._autostart_action.blockSignals(True)
            self._autostart_action.setChecked(enabled)
            self._autostart_action.blockSignals(False)

    def _about(self) -> None:
        QMessageBox.information(
            None,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>A microphone-in-use tray indicator for PipeWire.<br><br>"
            "It lights up when an application is capturing from a real input device "
            "and the signal is above your threshold.",
        )

    # -- signals ---------------------------------------------------------
    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_settings()

    def _on_streams(self, streams) -> None:
        self._refresh_all()

    def _on_meter_failed(self, reason: str) -> None:
        """The capture died (device unplugged, PipeWire restart): drop it and retry."""
        self.meter.stop()
        self.level = 0.0
        self.level_changed.emit(0.0)
        self._evaluate(force=True)
        if self._wanted_meter_target():
            QTimer.singleShot(1200, self._refresh_all)

    def _on_level(self, value: float) -> None:
        # fast attack, configurable release: the icon reacts the instant you speak
        if value > self.level:
            self.level = self.level * 0.25 + value * 0.75
        else:
            release = max(0.0, min(0.95, float(self.config["smoothing"])))
            self.level = self.level * release + value * (1.0 - release)
        if to_db(self.level) >= float(self.config["threshold_db"]):
            self._last_above = time.monotonic()
        self.level_changed.emit(self.level)
        self._evaluate()

    # -- state -----------------------------------------------------------
    def _wanted_meter_target(self) -> str | None:
        if self._preview:
            return self.monitor.preferred_source()
        if self.monitor.streams and self.config["threshold_enabled"]:
            return self.monitor.preferred_source()
        return None

    def _refresh_all(self) -> None:
        target = self._wanted_meter_target()
        if target:
            self.meter.start(target)
        elif self.meter.running:
            self.meter.stop()
            self.level = 0.0
            self.level_changed.emit(0.0)
        self._evaluate(force=True)

    def _evaluate(self, force: bool = False) -> None:
        streams = self.monitor.streams
        if not streams:
            state = IDLE
        elif not self.config["threshold_enabled"]:
            state = ACTIVE
        else:
            hold = max(0.0, float(self.config["hold_ms"]) / 1000.0)
            above = to_db(self.level) >= float(self.config["threshold_db"])
            state = ACTIVE if above or (time.monotonic() - self._last_above) <= hold else STANDBY

        changed = state != self.state
        self.state = state
        if changed:
            self.state_changed.emit(state)
            self._sync_animation()
        self._update_tooltip()
        if changed or force or not self._anim.isActive():
            self._paint()

    def _sync_animation(self) -> None:
        animated = self.state == ACTIVE and self.config["animation"] != "none"
        reactive = (
            self.state in (ACTIVE, STANDBY)
            and self.config["icon_style"] in REACTIVE_STYLES
            and (self.config["threshold_enabled"] or self._preview)
        )
        shading = (
            self.state == ACTIVE
            and self.config["shade_by_level"]
            and self.config["threshold_enabled"]
        )
        if animated or reactive or shading:
            fps = max(4, min(30, int(self.config["animation_fps"])))
            self._last_tick = time.monotonic()
            self._anim.start(int(1000 / fps))
        else:
            self._anim.stop()
            self._phase = 0.0

    def _tick(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        speed = max(0.1, float(self.config["animation_speed"]))
        self._phase = (self._phase + dt * speed * 0.8) % 1.0
        self._evaluate()
        self._paint()

    # -- painting --------------------------------------------------------
    def _colors(self) -> QColor:
        idle = QColor(self.config["color_idle"])
        standby = QColor(self.config["color_standby"])
        active = QColor(self.config["color_active"])
        if self.state == IDLE:
            return idle
        if self.state == STANDBY:
            return standby if self.config["show_standby"] else idle
        if self.config["shade_by_level"] and self.config["threshold_enabled"]:
            headroom = max(3.0, abs(float(self.config["threshold_db"])) * 0.5)
            over = to_db(self.level) - float(self.config["threshold_db"])
            return icons.blend(standby, active, max(0.35, min(1.0, over / headroom)))
        return active

    def _paint(self) -> None:
        if self.config["hide_when_idle"] and self.state == IDLE:
            if self.tray.isVisible():
                self.tray.hide()
            return
        if not self.tray.isVisible():
            self.tray.show()

        if self.state == ACTIVE:
            state = icons.anim_state(self.config["animation"], self._phase, self.level)
        elif self.state == STANDBY:
            state = icons.AnimState(alpha=0.85)
        else:
            state = icons.AnimState(alpha=0.75)

        metering = self.meter.running or self._preview
        self.tray.setIcon(
            QIcon(
                icons.render_pixmap(
                    self.config["icon_style"],
                    self._colors(),
                    level=self.level if metering else (0.28 if self.state == ACTIVE else 0.0),
                    state=state,
                    size=float(self.config["icon_size"]),
                )
            )
        )

    def _update_tooltip(self) -> None:
        names: list[str] = []
        for stream in self.monitor.streams:
            if stream.app not in names:
                names.append(stream.app)
        joined = ", ".join(names)
        if self.state == IDLE:
            text = "Microphone idle"
        elif self.state == STANDBY:
            text = f"Mic open, below threshold — {joined}"
        else:
            text = f"Microphone in use — {joined}"
        if self.config["tooltip_show_level"] and (self.meter.running or self._preview):
            text += f"\nLevel: {to_db(self.level):.0f} dB (threshold {float(self.config['threshold_db']):.0f} dB)"
        self.tray.setToolTip(text)
        self._status_action.setText(text.replace("\n", "  ·  "))

    # -- public ----------------------------------------------------------
    def set_preview(self, enabled: bool) -> None:
        self._preview = enabled
        self._refresh_all()
        self._sync_animation()

    def apply_config(self) -> None:
        self.monitor.apply_config()
        self._refresh_all()
        self._sync_animation()
        self._paint()

    def open_settings(self) -> None:
        from .settings import SettingsWindow

        if self._settings is None:
            self._settings = SettingsWindow(self.config, self)
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        self._anim.stop()
        self.meter.stop()
        self.monitor.stop()
        self.tray.hide()
        QApplication.quit()
