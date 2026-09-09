"""Tray icon, state machine and the glue between detection, level and drawing."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from . import autostart, hotkeys, icons, updates
from .audio import LevelMeter, MicMonitor, set_source_mute, set_stream_mute
from .config import APP_NAME, MIN_DB

IDLE, STANDBY, ACTIVE, MUTED = "idle", "standby", "active", "muted"

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
        self._announce = True
        self.release = None          # set once a check finds a newer release

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

        self.updates = updates.UpdateChecker(self)
        self.updates.checked.connect(self._on_update_checked)

        self.hotkeys = hotkeys.HotkeyListener(self)
        self.hotkeys.activated.connect(self._on_hotkey)
        self.hotkeys.status_changed.connect(self._on_hotkey_status)
        self.hotkey_status = (False, "Not listening: no shortcut configured yet.")
        self.apply_shortcuts()

        self.monitor.start()
        self._refresh_all()
        self.tray.show()

    # -- menu ------------------------------------------------------------
    def _build_menu(self) -> None:
        self.menu = QMenu()
        self._status_action = QAction("Microphone idle", self.menu)
        self._autostart_action = QAction("Start on login", self.menu)
        self._rebuild_menu()
        self.tray.setContextMenu(self.menu)

    def _rebuild_menu(self) -> None:
        """The app list changes as programs start and stop recording."""
        menu = self.menu
        menu.clear()

        self._status_action = QAction(self._status_text(), menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)

        if self.release is not None:
            update_action = QAction(f"Update to {self.release.tag} …", menu)
            update_action.triggered.connect(self.open_update_dialog)
            menu.addAction(update_action)
        menu.addSeparator()

        apps = self.monitor.recording_apps()
        for app in apps:
            streams = self.monitor.streams_of(app)
            action = QAction(f"Mute {app}", menu)
            action.setCheckable(True)
            action.setChecked(bool(streams) and all(s.muted for s in streams))
            action.setToolTip(f"Mute only {app}; other applications keep the microphone")
            action.toggled.connect(lambda checked, a=app: self.set_app_mute(a, checked))
            menu.addAction(action)

        for app in self.config["muted_apps"]:
            if app in apps:
                continue
            action = QAction(f"Unmute {app} (remembered)", menu)
            action.triggered.connect(lambda _=False, a=app: self.set_app_mute(a, False))
            menu.addAction(action)

        if apps or self.config["muted_apps"]:
            menu.addSeparator()

        devices = self.monitor.input_devices(self.config["include_virtual"])
        in_use = {s.source for s in self.monitor.streams}
        default = self.monitor.preferred_source()
        if len(devices) == 1:
            source = devices[0]
            device = QAction(f"Mute {source.description}", menu)
            device.setCheckable(True)
            device.setChecked(source.muted)
            device.setToolTip("Mutes the input device itself, for every application")
            device.toggled.connect(
                lambda checked, n=source.name: self.set_device_mute(n, checked)
            )
            menu.addAction(device)
        elif devices:
            submenu = menu.addMenu("Microphone devices")
            for source in devices:
                marks = []
                if source.name in in_use:
                    marks.append("in use")
                elif source.name == default:
                    marks.append("default")
                label = source.description + (f"  ({', '.join(marks)})" if marks else "")
                action = QAction(f"Mute {label}", submenu)
                action.setCheckable(True)
                action.setChecked(source.muted)
                action.setToolTip(f"Mute {source.description} for every application")
                action.toggled.connect(
                    lambda checked, n=source.name: self.set_device_mute(n, checked)
                )
                submenu.addAction(action)
        menu.addSeparator()

        settings_action = QAction("Settings…", menu)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        self._autostart_action = QAction("Start on login", menu)
        self._autostart_action.setCheckable(True)
        self._autostart_action.setChecked(autostart.is_enabled())
        self._autostart_action.toggled.connect(self._toggle_autostart)
        menu.addAction(self._autostart_action)

        check_action = QAction("Check for updates…", menu)
        check_action.triggered.connect(lambda: self.check_updates())
        menu.addAction(check_action)

        about_action = QAction(f"About {APP_NAME}", menu)
        about_action.triggered.connect(self._about)
        menu.addAction(about_action)
        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

    # -- per-application mute --------------------------------------------
    def set_app_mute(self, app: str, mute: bool) -> None:
        """Mute one application's capture stream; everything else keeps recording."""
        for stream in self.monitor.streams_of(app):
            set_stream_mute(stream.index, mute)
            stream.muted = mute
        remembered = list(self.config["muted_apps"])
        if mute and self.config["remember_mutes"]:
            if app not in remembered:
                remembered.append(app)
        elif not mute and app in remembered:
            remembered.remove(app)
        if remembered != self.config["muted_apps"]:
            self.config["muted_apps"] = remembered
            self.config.save()
        QTimer.singleShot(150, self._after_mute_change)

    def set_device_mute(self, name: str, mute: bool) -> None:
        """Mute one input device, for every application at once."""
        set_source_mute(name or self.monitor.preferred_source(), mute)
        QTimer.singleShot(150, self._after_mute_change)

    def _after_mute_change(self) -> None:
        self.monitor.refresh()
        self._evaluate(force=True)
        self._rebuild_menu()
        if self._settings is not None:
            self._settings.refresh_streams()

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
            f"<b>{APP_NAME} {updates.current_version()}</b><br>"
            "A microphone-in-use tray indicator for PipeWire.<br><br>"
            "It lights up when an application is capturing from a real input device "
            "and the signal is above your threshold, and it can mute one application "
            "without touching the others.<br><br>"
            f'<a href="{updates.RELEASES_URL}">{updates.REPO}</a>',
        )

    # -- updates ---------------------------------------------------------
    # Nothing here ever runs on its own: a check happens only when the user
    # clicks "Check for updates", in the tray menu or in the settings window.
    def check_updates(self, announce: bool = True) -> None:
        self._announce = announce
        self.updates.check()

    def _on_update_checked(self, release, newer: bool) -> None:
        announce, self._announce = self._announce, True
        self.release = release if newer else None
        self._rebuild_menu()
        if self._settings is not None:
            self._settings.show_update_result(release, newer)
        if not announce:
            return
        if release is None:
            QMessageBox.warning(
                None, f"{APP_NAME} — updates", "Could not reach GitHub to check for updates."
            )
        elif newer:
            self.open_update_dialog()
        else:
            QMessageBox.information(
                None,
                f"{APP_NAME} — updates",
                f"You are on the latest version ({updates.current_version()}).",
            )

    def open_update_dialog(self) -> None:
        release = self.release
        if release is None:
            return
        box = QMessageBox()
        box.setWindowTitle(f"{APP_NAME} — update available")
        box.setIcon(QMessageBox.Information)
        box.setText(
            f"<b>MicWatch {release.version}</b> is available."
            f"<br>You are running {updates.current_version()}."
        )
        body = release.body.strip()
        if body:
            box.setDetailedText(body[:2000])
        update_button = box.addButton("Update now", QMessageBox.AcceptRole)
        page_button = box.addButton("Open release page", QMessageBox.ActionRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is update_button:
            self.run_update()
        elif clicked is page_button:
            QDesktopServices.openUrl(QUrl(release.url))

    def run_update(self) -> None:
        if updates.launch_update(self.release):
            return
        QMessageBox.information(
            None,
            f"{APP_NAME} — update",
            "No terminal emulator was found. Run this in a shell:<br><br>"
            f"<code>{updates.INSTALL_COMMAND}</code>",
        )

    # -- signals ---------------------------------------------------------
    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_settings()

    def _on_streams(self, streams) -> None:
        self._remember_apps(streams)
        self._refresh_all()
        self._rebuild_menu()

    # -- the apps that have used the microphone --------------------------
    def _remember_apps(self, streams) -> None:
        """Keep a list of everything that has used the mic, so a shortcut can be
        bound to an app that is not recording right now."""
        known = {entry.get("name"): dict(entry) for entry in self.config["known_apps"]}
        changed = False
        now = time.time()
        for stream in streams:
            entry = known.get(stream.app)
            if entry is None:
                known[stream.app] = {
                    "name": stream.app,
                    "binary": stream.binary,
                    "device": stream.source_desc,
                    "last_seen": now,
                }
                changed = True
            else:
                if entry.get("device") != stream.source_desc:
                    entry["device"] = stream.source_desc
                    changed = True
                entry["last_seen"] = now
        if changed:
            ordered = sorted(known.values(), key=lambda e: e.get("last_seen", 0), reverse=True)
            self.config["known_apps"] = ordered[:40]
            self.config.save()

    def known_apps(self) -> list[dict]:
        """Apps recording now first, then everything seen before."""
        recording = self.monitor.recording_apps()
        seen = {entry.get("name"): entry for entry in self.config["known_apps"]}
        rows = []
        for name in recording:
            entry = seen.pop(name, {"name": name})
            rows.append({**entry, "recording": True})
        for entry in sorted(seen.values(), key=lambda e: e.get("last_seen", 0), reverse=True):
            rows.append({**entry, "recording": False})
        return rows

    # -- global shortcuts ------------------------------------------------
    def apply_shortcuts(self) -> None:
        bindings: dict[str, str] = {}
        for app, combo in (self.config["app_shortcuts"] or {}).items():
            if combo:
                bindings[f"app:{app}"] = combo
        if self.config["shortcut_mute_all"]:
            bindings["all"] = self.config["shortcut_mute_all"]
        if self.config["shortcut_mute_device"]:
            bindings["device"] = self.config["shortcut_mute_device"]
        self.hotkeys.set_bindings(bindings)
        if bindings:
            if not self.hotkeys.isRunning():
                self.hotkeys.start()
        elif self.hotkeys.isRunning():
            # no shortcut left: stop reading the keyboards altogether
            self.hotkeys.stop()
            self._on_hotkey_status(False, "Not listening: no shortcut configured yet.")

    def _on_hotkey_status(self, ok: bool, message: str) -> None:
        self.hotkey_status = (ok, message)
        if self._settings is not None:
            self._settings.show_hotkey_status(ok, message)

    def _app_is_muted(self, app: str) -> bool:
        streams = self.monitor.streams_of(app)
        if streams:
            return all(s.muted for s in streams)
        return app in self.config["muted_apps"]

    def _on_hotkey(self, action: str) -> None:
        if action.startswith("app:"):
            app = action[4:]
            mute = not self._app_is_muted(app)
            self.set_app_mute(app, mute)
            self._hotkey_feedback(f"{app} {'muted' if mute else 'unmuted'}")
        elif action == "all":
            apps = self.monitor.recording_apps() or list(self.config["muted_apps"])
            if not apps:
                self._hotkey_feedback("Nothing is recording")
                return
            mute = not all(self._app_is_muted(a) for a in apps)
            for app in apps:
                self.set_app_mute(app, mute)
            self._hotkey_feedback(("Muted: " if mute else "Unmuted: ") + ", ".join(apps))
        elif action == "device":
            source = self.monitor.preferred_source()
            mute = not self.monitor.source_muted(source)
            self.set_device_mute(source, mute)
            self._hotkey_feedback(f"Microphone device {'muted' if mute else 'unmuted'}")

    def _hotkey_feedback(self, text: str) -> None:
        if self.config["shortcut_feedback"]:
            self.tray.showMessage(APP_NAME, text, self.tray.icon(), 2000)

    def _muted_now(self) -> bool:
        """Muted when everything being counted is silent — per stream or per device."""
        streams = self.monitor.streams
        if streams:
            return all(self.monitor.stream_is_silent(s) for s in streams)
        return self.monitor.source_muted(self.monitor.preferred_source())

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
        if self.monitor.streams and self.config["threshold_enabled"] and not self._muted_now():
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
        elif self._muted_now():
            state = MUTED
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
        if self.state == MUTED:
            return QColor(self.config["color_muted"])
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
        elif self.state == MUTED:
            state = icons.AnimState()
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
                    muted=self.state == MUTED,
                )
            )
        )

    def _status_text(self) -> str:
        joined = ", ".join(self.monitor.recording_apps())
        if self.state == IDLE:
            text = "Microphone idle"
        elif self.state == MUTED:
            text = f"Muted — {joined}"
        elif self.state == STANDBY:
            text = f"Mic open, below threshold — {joined}"
        else:
            text = f"Microphone in use — {joined}"
        if (
            self.config["tooltip_show_level"]
            and self.state != MUTED
            and (self.meter.running or self._preview)
        ):
            text += f"\nLevel: {to_db(self.level):.0f} dB (threshold {float(self.config['threshold_db']):.0f} dB)"
        return text

    def _update_tooltip(self) -> None:
        text = self._status_text()
        self.tray.setToolTip(text)
        self._status_action.setText(text.replace("\n", "  ·  "))

    # -- public ----------------------------------------------------------
    def set_preview(self, enabled: bool) -> None:
        self._preview = enabled
        self._refresh_all()
        self._sync_animation()

    def apply_config(self) -> None:
        self.apply_shortcuts()
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
        self.hotkeys.stop()
        self.meter.stop()
        self.monitor.stop()
        self.tray.hide()
        QApplication.quit()
