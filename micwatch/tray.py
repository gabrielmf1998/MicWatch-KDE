"""Tray icon, state machine and the glue between detection, level and drawing."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from . import icons
from .audio import LevelMeter, MicMonitor
from .config import APP_NAME

IDLE, STANDBY, ACTIVE = "idle", "standby", "active"


class MicWatchTray(QObject):
    level_changed = Signal(float)     # smoothed level, for the settings meter
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

        about_action = QAction(f"About {APP_NAME}", menu)
        about_action.triggered.connect(self._about)
        menu.addAction(about_action)
        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.menu = menu
        self.tray.setContextMenu(menu)

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

    def _on_level(self, value: float) -> None:
        smoothing = max(0.0, min(0.95, float(self.config["smoothing"])))
        self.level = self.level * smoothing + value * (1.0 - smoothing)
        if self.level >= float(self.config["threshold"]):
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
            above = self.level >= float(self.config["threshold"])
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
        reactive = self.state in (ACTIVE, STANDBY) and self.config["icon_style"] in (
            "bars", "ring", "dot"
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
            threshold = max(0.001, float(self.config["threshold"]))
            ratio = min(1.0, (self.level - threshold) / max(0.02, threshold * 4))
            return icons.blend(standby, active, max(0.35, ratio))
        return active

    def _paint(self) -> None:
        if self.config["hide_when_idle"] and self.state == IDLE:
            if self.tray.isVisible():
                self.tray.hide()
            return
        if not self.tray.isVisible():
            self.tray.show()

        scale, alpha, glow = 1.0, 1.0, 0.0
        if self.state == ACTIVE:
            anim = self.config["animation"]
            wave = 0.5 + 0.5 * math.sin(self._phase * 2 * math.pi)
            if anim == "pulse":
                scale = 0.92 + 0.14 * wave
            elif anim == "blink":
                alpha = 1.0 if self._phase < 0.5 else 0.2
            elif anim == "glow":
                glow = 0.35 + 0.65 * wave
            elif anim == "level":
                boost = min(1.0, self.level * 6.0)
                scale = 0.94 + 0.16 * boost
                glow = 0.25 + 0.6 * boost
        elif self.state == STANDBY:
            alpha = 0.9

        pixmap = icons.render_pixmap(
            self.config["icon_style"],
            self._colors(),
            level=self.level if self.config["threshold_enabled"] or self._preview else 0.35,
            scale=scale,
            alpha=alpha,
            glow=glow,
        )
        self.tray.setIcon(QIcon(pixmap))

    def _update_tooltip(self) -> None:
        streams = self.monitor.streams
        names: list[str] = []
        for stream in streams:
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
            text += f"\nLevel: {self.level * 100:5.1f}%"
        self.tray.setToolTip(text)
        self._status_action.setText(text.replace("\n", "  ·  "))

    # -- public ----------------------------------------------------------
    def set_preview(self, enabled: bool) -> None:
        self._preview = enabled
        self._refresh_all()

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
