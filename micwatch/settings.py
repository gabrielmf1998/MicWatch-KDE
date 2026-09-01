"""Settings window: appearance, detection threshold and behaviour."""

from __future__ import annotations

import math
import os
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .config import APP_NAME, DEFAULTS

AUTOSTART_FILE = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "autostart"
    / "micwatch.desktop"
)

PRESETS = [
    ("#3fb950", "Green"),
    ("#e5534b", "Red"),
    ("#e3b341", "Amber"),
    ("#58a6ff", "Blue"),
    ("#bc8cff", "Purple"),
    ("#f778ba", "Pink"),
    ("#2ee6d6", "Teal"),
    ("#ffffff", "White"),
    ("#6e7681", "Grey"),
]


def to_db(value: float) -> float:
    return -96.0 if value <= 0.00002 else 20.0 * math.log10(value)


class LevelBar(QWidget):
    """Live input level with the threshold drawn on top of it."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.level = 0.0
        self.peak = 0.0
        self.threshold = 0.02
        self.active = False
        self.setMinimumHeight(30)
        self._decay = QTimer(self)
        self._decay.timeout.connect(self._fade)
        self._decay.start(80)

    def _fade(self) -> None:
        self.peak = max(self.level, self.peak * 0.94)
        self.update()

    def set_level(self, value: float) -> None:
        self.level = value
        self.peak = max(self.peak, value)
        self.update()

    def set_threshold(self, value: float) -> None:
        self.threshold = value
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(rect, 5, 5)

        scale = 0.35  # full bar == 35% RMS, plenty of headroom for speech
        filled = min(1.0, self.level / scale)
        bar = QRectF(rect)
        bar.setWidth(rect.width() * filled)
        colour = QColor("#3fb950") if self.level >= self.threshold else QColor("#8b949e")
        p.setBrush(colour)
        p.drawRoundedRect(bar, 5, 5)

        peak_x = rect.left() + rect.width() * min(1.0, self.peak / scale)
        p.setBrush(QColor(255, 255, 255, 150))
        p.drawRect(QRectF(peak_x - 1.5, rect.top(), 3, rect.height()))

        thr_x = rect.left() + rect.width() * min(1.0, self.threshold / scale)
        p.setBrush(QColor("#e3b341"))
        p.drawRect(QRectF(thr_x - 1.5, rect.top() - 1, 3, rect.height() + 2))
        p.end()


class IconPreview(QWidget):
    """The three states, drawn exactly like the tray draws them."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.level = 0.0
        self._phase = 0.0
        self.setMinimumHeight(96)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _tick(self) -> None:
        speed = max(0.1, float(self.config["animation_speed"]))
        self._phase = (self._phase + 0.05 * speed * 0.8) % 1.0
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        labels = ["Idle", "Open (quiet)", "In use"]
        keys = ["color_idle", "color_standby", "color_active"]
        size = 56
        step = self.width() / 3
        wave = 0.5 + 0.5 * math.sin(self._phase * 2 * math.pi)
        for i, (label, key) in enumerate(zip(labels, keys)):
            scale, alpha, glow = 1.0, 1.0, 0.0
            level = 0.25
            if i == 2:
                anim = self.config["animation"]
                level = max(0.18, self.level)
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
            elif i == 1:
                alpha = 0.9
                if not self.config["show_standby"]:
                    key = "color_idle"
            pixmap = icons.render_pixmap(
                self.config["icon_style"],
                QColor(self.config[key]),
                level=level,
                scale=scale,
                alpha=alpha,
                glow=glow,
                px=size * 2,
            )
            x = step * i + step / 2 - size / 2
            p.drawPixmap(int(x), 6, size, size, pixmap)
            p.setPen(QColor(150, 150, 150))
            p.drawText(
                QRectF(step * i, size + 12, step, 20), Qt.AlignHCenter | Qt.AlignTop, label
            )
        p.end()


class ColorButton(QPushButton):
    def __init__(self, hexcolor: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 24)
        self.set_color(hexcolor)

    def set_color(self, hexcolor: str) -> None:
        self._color = QColor(hexcolor)
        pixmap = QPixmap(26, 16)
        pixmap.fill(self._color)
        self.setIcon(pixmap)

    def color(self) -> QColor:
        return self._color


class SettingsWindow(QWidget):
    def __init__(self, config, tray) -> None:
        super().__init__()
        self.config = config
        self.tray = tray
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.resize(520, 620)
        self.setWindowIcon(
            icons.render_icon(config["icon_style"], QColor(config["color_active"]))
        )

        root = QVBoxLayout(self)
        self.preview = IconPreview(config, self)
        root.addWidget(self.preview)

        tabs = QTabWidget(self)
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._detection_tab(), "Detection")
        tabs.addTab(self._behaviour_tab(), "Behaviour")
        root.addWidget(tabs, 1)

        buttons = QHBoxLayout()
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(close)
        root.addLayout(buttons)

        tray.level_changed.connect(self._on_level)

    # -- tabs ------------------------------------------------------------
    def _appearance_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.style_box = QComboBox()
        for key, label in icons.ICON_STYLES:
            self.style_box.addItem(label, key)
        self.style_box.setCurrentIndex(
            max(0, self.style_box.findData(self.config["icon_style"]))
        )
        self.style_box.currentIndexChanged.connect(
            lambda: self._set("icon_style", self.style_box.currentData())
        )
        form.addRow("Icon style", self.style_box)

        self.anim_box = QComboBox()
        for key, label in icons.ANIMATIONS:
            self.anim_box.addItem(label, key)
        self.anim_box.setCurrentIndex(
            max(0, self.anim_box.findData(self.config["animation"]))
        )
        self.anim_box.currentIndexChanged.connect(
            lambda: self._set("animation", self.anim_box.currentData())
        )
        form.addRow("Animation", self.anim_box)

        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.25, 3.0)
        self.speed.setSingleStep(0.25)
        self.speed.setValue(float(self.config["animation_speed"]))
        self.speed.valueChanged.connect(lambda v: self._set("animation_speed", float(v)))
        form.addRow("Animation speed", self.speed)

        self.fps = QSpinBox()
        self.fps.setRange(4, 30)
        self.fps.setSuffix(" fps")
        self.fps.setValue(int(self.config["animation_fps"]))
        self.fps.valueChanged.connect(lambda v: self._set("animation_fps", int(v)))
        form.addRow("Refresh rate", self.fps)

        colours = QGroupBox("Colours")
        grid = QGridLayout(colours)
        self._color_widgets = {}
        rows = [
            ("color_idle", "Idle"),
            ("color_standby", "Open, below threshold"),
            ("color_active", "In use"),
        ]
        for row, (key, label) in enumerate(rows):
            grid.addWidget(QLabel(label), row, 0)
            button = ColorButton(self.config[key])
            edit = QLineEdit(self.config[key])
            edit.setMaximumWidth(90)
            presets = QComboBox()
            presets.addItem("Presets…", "")
            for hexcolor, name in PRESETS:
                presets.addItem(f"{name}  {hexcolor}", hexcolor)
            button.clicked.connect(lambda _=False, k=key: self._pick_color(k))
            edit.editingFinished.connect(lambda k=key: self._hex_entered(k))
            presets.currentIndexChanged.connect(
                lambda _=0, k=key, box=presets: self._preset_picked(k, box)
            )
            grid.addWidget(button, row, 1)
            grid.addWidget(edit, row, 2)
            grid.addWidget(presets, row, 3)
            self._color_widgets[key] = (button, edit, presets)
        form.addRow(colours)

        self.shade = QCheckBox("Brighten from “open” to “in use” as the level rises")
        self.shade.setChecked(bool(self.config["shade_by_level"]))
        self.shade.toggled.connect(lambda v: self._set("shade_by_level", bool(v)))
        form.addRow(self.shade)
        return page

    def _detection_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.threshold_on = QCheckBox("Only light up above a level threshold")
        self.threshold_on.setChecked(bool(self.config["threshold_enabled"]))
        self.threshold_on.toggled.connect(self._threshold_toggled)
        layout.addWidget(self.threshold_on)

        hint = QLabel(
            "With this off, the icon lights up as soon as an app opens the microphone.\n"
            "With it on, MicWatch also measures the signal, so the icon only lights up\n"
            "when sound actually goes through."
        )
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)

        self.live = QCheckBox("Live meter (keeps the microphone open while this window is open)")
        self.live.setChecked(True)
        self.live.toggled.connect(lambda v: self.tray.set_preview(bool(v)))
        layout.addWidget(self.live)

        self.bar = LevelBar()
        self.bar.set_threshold(float(self.config["threshold"]))
        layout.addWidget(self.bar)

        row = QHBoxLayout()
        self.threshold = QSlider(Qt.Horizontal)
        self.threshold.setRange(0, 1000)
        self.threshold.setValue(self._to_slider(float(self.config["threshold"])))
        self.threshold.valueChanged.connect(self._threshold_moved)
        self.threshold_label = QLabel()
        self.threshold_label.setMinimumWidth(130)
        calibrate = QPushButton("Set just above noise")
        calibrate.setToolTip("Stay quiet, then click: the threshold lands above the room noise.")
        calibrate.clicked.connect(self._calibrate)
        row.addWidget(QLabel("Threshold"))
        row.addWidget(self.threshold, 1)
        row.addWidget(self.threshold_label)
        row.addWidget(calibrate)
        layout.addLayout(row)
        self._update_threshold_label()

        form = QFormLayout()
        self.hold = QSpinBox()
        self.hold.setRange(0, 5000)
        self.hold.setSingleStep(100)
        self.hold.setSuffix(" ms")
        self.hold.setValue(int(self.config["hold_ms"]))
        self.hold.valueChanged.connect(lambda v: self._set("hold_ms", int(v)))
        form.addRow("Stay lit after speech", self.hold)

        self.smooth = QDoubleSpinBox()
        self.smooth.setRange(0.0, 0.9)
        self.smooth.setSingleStep(0.05)
        self.smooth.setValue(float(self.config["smoothing"]))
        self.smooth.valueChanged.connect(lambda v: self._set("smoothing", float(v)))
        form.addRow("Smoothing", self.smooth)
        layout.addLayout(form)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        self.corked = QCheckBox("Ignore paused (corked) streams")
        self.corked.setChecked(bool(self.config["ignore_corked"]))
        self.corked.toggled.connect(lambda v: self._set("ignore_corked", bool(v)))
        layout.addWidget(self.corked)

        self.virtual = QCheckBox("Count virtual sources (screen share, loopback)")
        self.virtual.setChecked(bool(self.config["include_virtual"]))
        self.virtual.toggled.connect(lambda v: self._set("include_virtual", bool(v)))
        layout.addWidget(self.virtual)

        ignore_row = QFormLayout()
        self.ignore = QLineEdit(", ".join(self.config["ignore_apps"]))
        self.ignore.setPlaceholderText("e.g. obs, easyeffects")
        self.ignore.editingFinished.connect(self._ignore_changed)
        ignore_row.addRow("Ignore apps", self.ignore)
        layout.addLayout(ignore_row)

        self.who = QLabel()
        self.who.setWordWrap(True)
        self.who.setStyleSheet("color: #8b949e;")
        layout.addWidget(self.who)
        layout.addStretch(1)

        self._who_timer = QTimer(self)
        self._who_timer.timeout.connect(self._update_who)
        self._who_timer.start(700)
        self._update_who()
        return page

    def _behaviour_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.hide_idle = QCheckBox("Hide the icon when nothing is recording")
        self.hide_idle.setChecked(bool(self.config["hide_when_idle"]))
        self.hide_idle.toggled.connect(lambda v: self._set("hide_when_idle", bool(v)))
        layout.addWidget(self.hide_idle)

        self.standby = QCheckBox("Use a separate colour while the mic is open but quiet")
        self.standby.setChecked(bool(self.config["show_standby"]))
        self.standby.toggled.connect(lambda v: self._set("show_standby", bool(v)))
        layout.addWidget(self.standby)

        self.tip_level = QCheckBox("Show the level in the tooltip")
        self.tip_level.setChecked(bool(self.config["tooltip_show_level"]))
        self.tip_level.toggled.connect(lambda v: self._set("tooltip_show_level", bool(v)))
        layout.addWidget(self.tip_level)

        self.autostart = QCheckBox("Start automatically on login")
        self.autostart.setChecked(AUTOSTART_FILE.exists())
        self.autostart.toggled.connect(self._set_autostart)
        layout.addWidget(self.autostart)

        form = QFormLayout()
        self.poll = QSpinBox()
        self.poll.setRange(400, 10000)
        self.poll.setSingleStep(100)
        self.poll.setSuffix(" ms")
        self.poll.setValue(int(self.config["poll_ms"]))
        self.poll.valueChanged.connect(lambda v: self._set("poll_ms", int(v)))
        form.addRow("Stream re-check interval", self.poll)
        layout.addLayout(form)

        note = QLabel(
            "KDE ships its own microphone indicator. To avoid two icons, turn it off in\n"
            "System Settings → Quick Settings → System Tray → Entries → Microphone."
        )
        note.setStyleSheet("color: #8b949e;")
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _to_slider(value: float) -> int:
        return int(round(math.sqrt(max(0.0, value) / 0.5) * 1000))

    @staticmethod
    def _from_slider(value: int) -> float:
        return (value / 1000.0) ** 2 * 0.5

    def _update_threshold_label(self) -> None:
        value = float(self.config["threshold"])
        self.threshold_label.setText(f"{value * 100:.2f}%  ({to_db(value):.1f} dB)")

    def _threshold_moved(self, value: int) -> None:
        threshold = self._from_slider(value)
        self.config["threshold"] = threshold
        self.bar.set_threshold(threshold)
        self._update_threshold_label()
        self._apply()

    def _threshold_toggled(self, enabled: bool) -> None:
        self._set("threshold_enabled", bool(enabled))

    def _calibrate(self) -> None:
        floor = max(self.bar.peak, self.bar.level)
        threshold = max(0.004, min(0.4, floor * 1.8 + 0.003))
        self.threshold.setValue(self._to_slider(threshold))

    def _pick_color(self, key: str) -> None:
        chosen = QColorDialog.getColor(
            QColor(self.config[key]), self, "Pick a colour", QColorDialog.ShowAlphaChannel
        )
        if chosen.isValid():
            self._set_color(key, chosen.name())

    def _hex_entered(self, key: str) -> None:
        _, edit, _ = self._color_widgets[key]
        colour = QColor(edit.text().strip())
        if colour.isValid():
            self._set_color(key, colour.name())
        else:
            edit.setText(self.config[key])

    def _preset_picked(self, key: str, box: QComboBox) -> None:
        value = box.currentData()
        if value:
            self._set_color(key, value)
            box.setCurrentIndex(0)

    def _set_color(self, key: str, hexcolor: str) -> None:
        button, edit, _ = self._color_widgets[key]
        button.set_color(hexcolor)
        edit.setText(hexcolor)
        self._set(key, hexcolor)

    def _ignore_changed(self) -> None:
        parts = [p.strip() for p in self.ignore.text().split(",") if p.strip()]
        self._set("ignore_apps", parts)

    def _set_autostart(self, enabled: bool) -> None:
        if enabled:
            AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
            exec_path = Path.home() / ".local" / "bin" / "micwatch"
            AUTOSTART_FILE.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                "Comment=Microphone in-use tray indicator\n"
                f"Exec={exec_path}\n"
                "Icon=audio-input-microphone\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        else:
            AUTOSTART_FILE.unlink(missing_ok=True)

    def _update_who(self) -> None:
        streams = self.tray.monitor.streams
        if not streams:
            self.who.setText("Nothing is recording right now.")
            return
        lines = [
            f"• {s.app}" + (f" (pid {s.pid})" if s.pid else "") + f" → {s.source_desc}"
            for s in streams
        ]
        self.who.setText("Recording now:\n" + "\n".join(lines))

    def _on_level(self, value: float) -> None:
        self.bar.set_level(value)
        self.preview.level = value

    def _set(self, key: str, value) -> None:
        self.config[key] = value
        self._apply()

    def _apply(self) -> None:
        self.config.save()
        self.tray.apply_config()
        self.preview.update()

    def _reset(self) -> None:
        self.config.reset()
        self.config.save()
        self.tray.apply_config()
        self.close()
        self.tray._settings = None
        self.tray.open_settings()

    # -- window ----------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.live.isChecked():
            self.tray.set_preview(True)

    def closeEvent(self, event) -> None:
        self.tray.set_preview(False)
        self.config.save()
        super().closeEvent(event)
