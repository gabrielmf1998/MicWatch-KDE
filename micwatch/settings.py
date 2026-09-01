"""Settings window: appearance, detection threshold and behaviour."""

from __future__ import annotations

import math
import os
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .audio import list_sources
from .config import APP_NAME, MIN_DB

AUTOSTART_FILE = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "autostart"
    / "micwatch.desktop"
)

PRESETS = [
    ("#3fb950", "Green"),
    ("#00e676", "Neon green"),
    ("#e5534b", "Red"),
    ("#ff5c8a", "Hot pink"),
    ("#e3b341", "Amber"),
    ("#ff9800", "Orange"),
    ("#58a6ff", "Blue"),
    ("#2ee6d6", "Teal"),
    ("#bc8cff", "Purple"),
    ("#ffffff", "White"),
    ("#6e7681", "Grey"),
    ("#3a3f46", "Dark grey"),
]


def to_db(value: float) -> float:
    return MIN_DB if value <= 0.000001 else max(MIN_DB, 20.0 * math.log10(value))


def db_fraction(db: float) -> float:
    return max(0.0, min(1.0, (db - MIN_DB) / (0.0 - MIN_DB)))


class LevelBar(QWidget):
    """Live input level on a dB scale, with the threshold drawn on top."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.level = 0.0
        self.peak_db = MIN_DB
        self.threshold_db = -42.0
        self.setMinimumHeight(38)
        self._decay = QTimer(self)
        self._decay.timeout.connect(self._fade)
        self._decay.start(60)

    def _fade(self) -> None:
        self.peak_db = max(to_db(self.level), self.peak_db - 1.2)
        self.update()

    def set_level(self, value: float) -> None:
        self.level = value
        self.peak_db = max(self.peak_db, to_db(value))
        self.update()

    def set_threshold(self, db: float) -> None:
        self.threshold_db = db
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 130))
        p.drawRoundedRect(rect, 5, 5)

        db = to_db(self.level)
        bar = QRectF(rect)
        bar.setWidth(rect.width() * db_fraction(db))
        above = db >= self.threshold_db
        p.setBrush(QColor("#3fb950") if above else QColor("#4c8fd6"))
        p.drawRoundedRect(bar, 5, 5)

        p.setBrush(QColor(255, 255, 255, 170))
        peak_x = rect.left() + rect.width() * db_fraction(self.peak_db)
        p.drawRect(QRectF(peak_x - 1.5, rect.top(), 3, rect.height()))

        thr_x = rect.left() + rect.width() * db_fraction(self.threshold_db)
        p.setBrush(QColor("#e3b341"))
        p.drawRect(QRectF(thr_x - 2, rect.top() - 2, 4, rect.height() + 4))

        p.setPen(QColor(255, 255, 255, 110))
        for mark in (-60, -50, -40, -30, -20, -10):
            x = rect.left() + rect.width() * db_fraction(mark)
            p.drawLine(int(x), int(rect.bottom() - 5), int(x), int(rect.bottom()))
        p.end()


class IconPreview(QWidget):
    """The three states, drawn exactly like the tray draws them."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.level = 0.0
        self._phase = 0.0
        self.setMinimumHeight(100)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def _tick(self) -> None:
        speed = max(0.1, float(self.config["animation_speed"]))
        self._phase = (self._phase + 0.04 * speed * 0.8) % 1.0
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        labels = ["Idle", "Open (quiet)", "In use"]
        keys = ["color_idle", "color_standby", "color_active"]
        size = 58
        step = self.width() / 3
        for i, (label, key) in enumerate(zip(labels, keys)):
            level = 0.30
            if i == 2:
                state = icons.anim_state(
                    self.config["animation"], self._phase, max(0.05, self.level)
                )
                level = max(0.10, self.level)
            elif i == 1:
                state = icons.AnimState(alpha=0.85)
                level = 0.06
                if not self.config["show_standby"]:
                    key = "color_idle"
            else:
                state = icons.AnimState(alpha=0.75)
                level = 0.0
            pixmap = icons.render_pixmap(
                self.config["icon_style"],
                QColor(self.config[key]),
                level=level,
                state=state,
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
        self._calibrating = False
        self._calibration_peak = 0.0
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.resize(560, 720)
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
        layout = QVBoxLayout(page)

        box = QGroupBox("Icon")
        grid = QGridLayout(box)
        grid.setSpacing(4)
        self._style_group = QButtonGroup(self)
        self._style_buttons = {}
        columns = 6
        for i, (key, label) in enumerate(icons.ICON_STYLES):
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(label)
            button.setIconSize(QSize(30, 30))
            button.setChecked(key == self.config["icon_style"])
            button.clicked.connect(lambda _=False, k=key: self._set("icon_style", k))
            self._style_group.addButton(button)
            self._style_buttons[key] = button
            grid.addWidget(button, i // columns, i % columns)
        layout.addWidget(box)
        self._refresh_style_icons()

        form = QFormLayout()
        self.anim_box = QComboBox()
        for key, label in icons.ANIMATIONS:
            self.anim_box.addItem(label, key)
        self.anim_box.setCurrentIndex(max(0, self.anim_box.findData(self.config["animation"])))
        self.anim_box.currentIndexChanged.connect(
            lambda: self._set("animation", self.anim_box.currentData())
        )
        form.addRow("Animation", self.anim_box)

        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.25, 4.0)
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
        layout.addLayout(form)

        colours = QGroupBox("Colours")
        cgrid = QGridLayout(colours)
        self._color_widgets = {}
        rows = [
            ("color_idle", "Idle"),
            ("color_standby", "Open, below threshold"),
            ("color_active", "In use"),
        ]
        for row, (key, label) in enumerate(rows):
            cgrid.addWidget(QLabel(label), row, 0)
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
                lambda _=0, k=key, b=presets: self._preset_picked(k, b)
            )
            cgrid.addWidget(button, row, 1)
            cgrid.addWidget(edit, row, 2)
            cgrid.addWidget(presets, row, 3)
            self._color_widgets[key] = (button, edit, presets)
        layout.addWidget(colours)

        self.shade = QCheckBox("Brighten from “open” to “in use” as the level rises")
        self.shade.setChecked(bool(self.config["shade_by_level"]))
        self.shade.toggled.connect(lambda v: self._set("shade_by_level", bool(v)))
        layout.addWidget(self.shade)
        layout.addStretch(1)
        return page

    def _detection_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.threshold_on = QCheckBox("Only light up above a level threshold")
        self.threshold_on.setChecked(bool(self.config["threshold_enabled"]))
        self.threshold_on.toggled.connect(lambda v: self._set("threshold_enabled", bool(v)))
        layout.addWidget(self.threshold_on)

        hint = QLabel(
            "Off: the icon lights up as soon as an app opens the microphone.\n"
            "On: MicWatch also measures the signal, so it lights up only when sound "
            "actually goes through."
        )
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)

        device_row = QFormLayout()
        self.device = QComboBox()
        self.device.addItem("Follow the app that is recording", "auto")
        for source in list_sources().values():
            if source.real or source.virtual:
                self.device.addItem(source.description, source.name)
        self.device.setCurrentIndex(max(0, self.device.findData(self.config["meter_source"])))
        self.device.currentIndexChanged.connect(
            lambda: self._set("meter_source", self.device.currentData())
        )
        device_row.addRow("Measure", self.device)
        layout.addLayout(device_row)

        self.live = QCheckBox("Live meter (keeps the microphone open while this window is open)")
        self.live.setChecked(True)
        self.live.toggled.connect(lambda v: self.tray.set_preview(bool(v)))
        layout.addWidget(self.live)

        self.bar = LevelBar()
        self.bar.set_threshold(float(self.config["threshold_db"]))
        layout.addWidget(self.bar)

        self.readout = QLabel()
        self.readout.setStyleSheet("color: #8b949e;")
        layout.addWidget(self.readout)

        row = QHBoxLayout()
        self.threshold = QSlider(Qt.Horizontal)
        self.threshold.setRange(int(MIN_DB), 0)
        self.threshold.setValue(int(round(float(self.config["threshold_db"]))))
        self.threshold.valueChanged.connect(self._threshold_moved)
        self.threshold_label = QLabel()
        self.threshold_label.setMinimumWidth(80)
        self.calibrate = QPushButton("Set just above noise")
        self.calibrate.setToolTip(
            "Stay quiet and click: MicWatch listens for 3 seconds and parks the "
            "threshold just above your room noise."
        )
        self.calibrate.clicked.connect(self._calibrate)
        row.addWidget(QLabel("Threshold"))
        row.addWidget(self.threshold, 1)
        row.addWidget(self.threshold_label)
        row.addWidget(self.calibrate)
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
        form.addRow("Release smoothing", self.smooth)
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
    def _refresh_style_icons(self) -> None:
        colour = QColor(self.config["color_active"])
        for key, button in self._style_buttons.items():
            button.setIcon(icons.render_icon(key, colour, level=0.22, px=96))
            button.setChecked(key == self.config["icon_style"])

    def _update_threshold_label(self) -> None:
        db = float(self.config["threshold_db"])
        self.threshold_label.setText(f"{db:.0f} dB")

    def _threshold_moved(self, value: int) -> None:
        self.config["threshold_db"] = float(value)
        self.bar.set_threshold(float(value))
        self._update_threshold_label()
        self._apply()

    def _calibrate(self) -> None:
        if self._calibrating:
            return
        if not self.live.isChecked():
            self.live.setChecked(True)
        self._calibrating = True
        self._calibration_peak = 0.0
        self.calibrate.setEnabled(False)
        self.calibrate.setText("Listening…")
        QTimer.singleShot(3000, self._finish_calibration)

    def _finish_calibration(self) -> None:
        self._calibrating = False
        self.calibrate.setEnabled(True)
        self.calibrate.setText("Set just above noise")
        noise_db = to_db(self._calibration_peak)
        self.threshold.setValue(int(round(min(-6.0, max(MIN_DB + 2, noise_db + 7.0)))))

    def _pick_color(self, key: str) -> None:
        chosen = QColorDialog.getColor(QColor(self.config[key]), self, "Pick a colour")
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
            AUTOSTART_FILE.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                "Comment=Microphone in-use tray indicator\n"
                f"Exec={Path.home() / '.local' / 'bin' / 'micwatch'}\n"
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
        if self._calibrating:
            self._calibration_peak = max(self._calibration_peak, value)
        db = to_db(value)
        state = self.tray.state
        self.readout.setText(
            f"Now: {db:6.1f} dB     peak {self.bar.peak_db:6.1f} dB     state: {state}"
        )

    def _set(self, key: str, value) -> None:
        self.config[key] = value
        if key in ("icon_style", "color_active"):
            self._refresh_style_icons()
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
