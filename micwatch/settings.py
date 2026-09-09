"""Settings window: appearance, detection threshold and behaviour."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QKeySequenceEdit,
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
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import autostart, hotkeys, icons, updates
from .audio import list_sources, set_stream_volume
from .config import APP_NAME, MIN_DB

PRESETS = [
    ("#3fb950", "Green"),
    ("#00e676", "Neon green"),
    ("#7ee787", "Mint"),
    ("#2ee6d6", "Teal"),
    ("#00e5ff", "Cyan"),
    ("#58a6ff", "Blue"),
    ("#4051ff", "Electric blue"),
    ("#bc8cff", "Purple"),
    ("#d500f9", "Magenta"),
    ("#ff5c8a", "Hot pink"),
    ("#f778ba", "Pink"),
    ("#e5534b", "Red"),
    ("#ff1744", "Crimson"),
    ("#ff9800", "Orange"),
    ("#ff6d00", "Deep orange"),
    ("#e3b341", "Amber"),
    ("#ffe066", "Sun"),
    ("#d4ff00", "Lime"),
    ("#c9d1d9", "Bone"),
    ("#ffffff", "White"),
    ("#8b949e", "Silver"),
    ("#6e7681", "Grey"),
    ("#3a3f46", "Dark grey"),
    ("#161b22", "Ink"),
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
        labels = ["Idle", "Open (quiet)", "In use", "Muted"]
        keys = ["color_idle", "color_standby", "color_active", "color_muted"]
        size = 54
        step = self.width() / 4
        for i, (label, key) in enumerate(zip(labels, keys)):
            level = 0.30
            if i == 3:
                state = icons.AnimState()
                level = 0.20
            elif i == 2:
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
                size=float(self.config["icon_size"]),
                muted=i == 3,
                px=size * 2,
            )
            x = step * i + step / 2 - size / 2
            p.drawPixmap(int(x), 6, size, size, pixmap)
            p.setPen(QColor(150, 150, 150))
            p.drawText(
                QRectF(step * i, size + 12, step, 20), Qt.AlignHCenter | Qt.AlignTop, label
            )
        p.end()


class ShortcutDialog(QDialog):
    """Capture one key combination, the way KDE's shortcut editor does."""

    def __init__(self, current: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Press the combination you want to use:"))
        self.edit = QKeySequenceEdit(QKeySequence(current))
        self.edit.setMaximumSequenceLength(1)
        self.edit.keySequenceChanged.connect(self._validate)
        layout.addWidget(self.edit)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #8b949e;")
        layout.addWidget(self.note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        clear = buttons.addButton("Clear", QDialogButtonBox.ResetRole)
        clear.clicked.connect(self.edit.clear)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok = buttons.button(QDialogButtonBox.Ok)
        self.edit.setFocus()
        self._validate()

    def _validate(self) -> None:
        text = self.value()
        if not text:
            self.note.setText("Empty: the shortcut will be removed.")
            self._ok.setEnabled(True)
            return
        if not hotkeys.is_valid(text):
            self.note.setText(f"“{text}” is not a key MicWatch can listen for.")
            self._ok.setEnabled(False)
            return
        if not hotkeys.has_modifier(text):
            self.note.setText(
                f"“{text}” has no modifier — it will fire whenever you type that key. "
                "Add Ctrl, Alt, Shift or Meta."
            )
        else:
            self.note.setText(f"Shortcut: {text}")
        self._ok.setEnabled(True)

    def value(self) -> str:
        return self.edit.keySequence().toString(QKeySequence.PortableText)


class ShortcutButton(QPushButton):
    """Shows the current combination and opens the capture dialog."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self._value = ""
        self._on_change = None
        self.setMinimumWidth(120)
        self.setMaximumWidth(195)
        self.clicked.connect(self._edit)
        self.set_value("")

    def set_value(self, value: str) -> None:
        self._value = value or ""
        self.setText(self._value or "Set shortcut…")
        self.setToolTip(
            f"Global shortcut for {self._label}" if self._value
            else f"Click to record a global shortcut for {self._label}"
        )

    def value(self) -> str:
        return self._value

    def on_change(self, callback) -> None:
        self._on_change = callback

    def _edit(self) -> None:
        dialog = ShortcutDialog(self._value, f"Shortcut — {self._label}", self)
        if dialog.exec() != QDialog.Accepted:
            return
        value = hotkeys.normalise(dialog.value())
        self.set_value(value)
        if self._on_change is not None:
            self._on_change(value)


class AppRow(QWidget):
    """One application: mute it, ride its capture volume, bind a shortcut."""

    def __init__(self, app: str, tray, parent=None) -> None:
        super().__init__(parent)
        self.app = app
        self.tray = tray
        self._busy = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel(app)
        self.name.setMinimumWidth(120)
        self.status = QLabel("")
        self.status.setStyleSheet("color: #8b949e;")
        self.status.setMinimumWidth(0)
        # let the middle column give way instead of pushing the buttons off-screen
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 150)
        self.volume.setFixedWidth(90)
        self.volume.valueChanged.connect(self._volume_changed)
        self.percent = QLabel()
        self.percent.setMinimumWidth(42)
        self.mute = QCheckBox("Mute")
        self.mute.toggled.connect(self._mute_toggled)
        self.shortcut = ShortcutButton(app)
        self.shortcut.on_change(self._shortcut_changed)
        self.forget = QToolButton()
        self.forget.setText("✕")
        self.forget.setAutoRaise(True)
        self.forget.setToolTip("Forget this application")
        self.forget.clicked.connect(self._forget)

        layout.addWidget(self.name)
        layout.addWidget(self.status, 1)
        layout.addWidget(self.volume)
        layout.addWidget(self.percent)
        layout.addWidget(self.mute)
        layout.addWidget(self.shortcut)
        layout.addWidget(self.forget)

    def update_from(self, entry: dict) -> None:
        self._busy = True
        streams = self.tray.monitor.streams_of(self.app)
        recording = bool(streams)
        if recording:
            volume = max(s.volume for s in streams)
            muted = all(s.muted for s in streams)
            device = ", ".join(dict.fromkeys(s.source_desc for s in streams))
            self.status.setText(f"recording · {device}")
            self.status.setToolTip(device)
            self.volume.setVisible(True)
            self.percent.setVisible(True)
            if not self.volume.isSliderDown():
                self.volume.setValue(volume)
            self.percent.setText(f"{volume}%")
            self.volume.setEnabled(not muted)
        else:
            muted = self.app in self.tray.config["muted_apps"]
            self.volume.setVisible(False)
            self.percent.setVisible(False)
            device = entry.get("device") or ""
            when = entry.get("last_seen")
            ago = _ago(when) if when else "seen before"
            self.status.setText(f"idle · {ago}" + (f" · {device}" if device else ""))
        self.name.setText(("● " if recording else "○ ") + self.app)
        self.mute.setChecked(muted)
        self.mute.setToolTip(
            "Mute this application's microphone" if recording
            else "Keep this application muted; it applies the moment it opens the mic"
        )
        self.forget.setVisible(not recording)
        self.shortcut.set_value(self.tray.config["app_shortcuts"].get(self.app, ""))
        self._busy = False

    def _mute_toggled(self, checked: bool) -> None:
        if not self._busy:
            self.tray.set_app_mute(self.app, checked)

    def _volume_changed(self, value: int) -> None:
        self.percent.setText(f"{value}%")
        if self._busy:
            return
        for stream in self.tray.monitor.streams_of(self.app):
            set_stream_volume(stream.index, value)

    def _shortcut_changed(self, value: str) -> None:
        shortcuts = dict(self.tray.config["app_shortcuts"])
        if value:
            shortcuts[self.app] = value
        else:
            shortcuts.pop(self.app, None)
        self.tray.config["app_shortcuts"] = shortcuts
        self.tray.config.save()
        self.tray.apply_shortcuts()
        window = self.window()
        if hasattr(window, "show_hotkey_status"):
            ok, message = self.tray.hotkey_status
            window.show_hotkey_status(ok, message)

    def _forget(self) -> None:
        config = self.tray.config
        config["known_apps"] = [
            e for e in config["known_apps"] if e.get("name") != self.app
        ]
        config["app_shortcuts"] = {
            k: v for k, v in config["app_shortcuts"].items() if k != self.app
        }
        config["muted_apps"] = [a for a in config["muted_apps"] if a != self.app]
        config.save()
        self.tray.apply_shortcuts()
        window = self.window()
        if hasattr(window, "refresh_streams"):
            window.refresh_streams()


def _ago(when: float) -> str:
    delta = max(0.0, time.time() - float(when))
    if delta < 90:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)} min ago"
    if delta < 86400:
        return f"{int(delta // 3600)} h ago"
    return f"{int(delta // 86400)} d ago"


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
        self.resize(730, 780)
        self.setWindowIcon(
            icons.render_icon(config["icon_style"], QColor(config["color_active"]))
        )

        root = QVBoxLayout(self)
        self.preview = IconPreview(config, self)
        root.addWidget(self.preview)

        tabs = QTabWidget(self)
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._detection_tab(), "Detection")
        tabs.addTab(self._apps_tab(), "Apps && shortcuts")
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
            button.setIconSize(QSize(34, 34))
            button.setChecked(key == self.config["icon_style"])
            button.clicked.connect(lambda _=False, k=key: self._set("icon_style", k))
            self._style_group.addButton(button)
            self._style_buttons[key] = button
            grid.addWidget(button, i // columns, i % columns)
        layout.addWidget(box)
        self._refresh_style_icons()

        form = QFormLayout()

        size_row = QHBoxLayout()
        self.icon_size = QSlider(Qt.Horizontal)
        self.icon_size.setRange(50, 100)
        self.icon_size.setValue(int(round(float(self.config["icon_size"]) * 100)))
        self.icon_size.valueChanged.connect(self._icon_size_moved)
        self.icon_size_label = QLabel(f"{float(self.config['icon_size']) * 100:.0f}%")
        self.icon_size_label.setMinimumWidth(46)
        size_row.addWidget(self.icon_size, 1)
        size_row.addWidget(self.icon_size_label)
        form.addRow("Icon size", size_row)

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
            ("color_muted", "Muted"),
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

        pointer = QLabel(
            "Per-application mute, capture volume and shortcuts live in the "
            "“Apps & shortcuts” tab."
        )
        pointer.setWordWrap(True)
        pointer.setStyleSheet("color: #8b949e;")
        layout.addWidget(pointer)
        layout.addStretch(1)
        return page

    def _apps_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        intro = QLabel(
            "Everything that has used your microphone — browsers included. Mute one "
            "application without touching the others, or give it a global shortcut "
            "that works even inside a fullscreen game."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #8b949e;")
        layout.addWidget(intro)

        head = QHBoxLayout()
        head.addStretch(1)
        self.refresh_button = QPushButton("Refresh apps")
        self.refresh_button.setToolTip(
            "Re-scan the recording applications and input devices right now"
        )
        self.refresh_button.clicked.connect(self._refresh_now)
        head.addWidget(self.refresh_button)
        layout.addLayout(head)

        self.streams_box = QGroupBox("Applications")
        self.streams_layout = QVBoxLayout(self.streams_box)
        self.who = QLabel("Nothing has used the microphone yet.")
        self.who.setWordWrap(True)
        self.who.setStyleSheet("color: #8b949e;")
        self.streams_layout.addWidget(self.who)
        self.streams_layout.addStretch(1)       # rows stay packed at the top

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.streams_box)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll, 1)

        box = QGroupBox("Global shortcuts")
        box_layout = QVBoxLayout(box)
        form = QFormLayout()
        self.sc_all = ShortcutButton("mute everything")
        self.sc_all.set_value(self.config["shortcut_mute_all"])
        self.sc_all.on_change(lambda v: self._set_global_shortcut("shortcut_mute_all", v))
        form.addRow("Mute / unmute every recording app", self.sc_all)
        self.sc_device = ShortcutButton("mute the input device")
        self.sc_device.set_value(self.config["shortcut_mute_device"])
        self.sc_device.on_change(
            lambda v: self._set_global_shortcut("shortcut_mute_device", v)
        )
        form.addRow("Mute / unmute the input device", self.sc_device)
        box_layout.addLayout(form)

        self.feedback = QCheckBox("Show a notification when a shortcut fires")
        self.feedback.setChecked(bool(self.config["shortcut_feedback"]))
        self.feedback.toggled.connect(lambda v: self._set("shortcut_feedback", bool(v)))
        box_layout.addWidget(self.feedback)

        self.hotkey_note = QLabel("")
        self.hotkey_note.setWordWrap(True)
        self.hotkey_note.setStyleSheet("color: #8b949e;")
        box_layout.addWidget(self.hotkey_note)
        layout.addWidget(box)

        self._rows: dict[str, AppRow] = {}
        self._who_timer = QTimer(self)
        self._who_timer.timeout.connect(self.refresh_streams)
        self._who_timer.start(900)
        self.refresh_streams()
        ok, message = self.tray.hotkey_status
        self.show_hotkey_status(ok, message)
        return page

    def _refresh_now(self) -> None:
        """Ask PipeWire again instead of waiting for the next tick."""
        self.tray.monitor.refresh()
        self.refresh_streams()
        self.refresh_button.setText("Refreshed")
        QTimer.singleShot(1200, lambda: self.refresh_button.setText("Refresh apps"))

    def _set_global_shortcut(self, key: str, value: str) -> None:
        self.config[key] = value
        self.config.save()
        self.tray.apply_shortcuts()
        ok, message = self.tray.hotkey_status
        self.show_hotkey_status(ok, message)

    def show_hotkey_status(self, ok: bool, message: str) -> None:
        if not hasattr(self, "hotkey_note"):
            return
        prefix = "Global shortcuts: " if ok else "Global shortcuts unavailable — "
        self.hotkey_note.setText(prefix + message)
        self.hotkey_note.setStyleSheet("color: %s;" % ("#8b949e" if ok else "#e3b341"))

    def _behaviour_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        startup = QGroupBox("Startup")
        startup_layout = QVBoxLayout(startup)
        self.autostart = QCheckBox("Start MicWatch automatically on login")
        self.autostart.setChecked(autostart.is_enabled())
        self.autostart.toggled.connect(self._set_autostart)
        startup_layout.addWidget(self.autostart)
        self.autostart_note = QLabel(autostart.describe())
        self.autostart_note.setWordWrap(True)
        self.autostart_note.setStyleSheet("color: #8b949e;")
        startup_layout.addWidget(self.autostart_note)
        layout.addWidget(startup)

        self.hide_idle = QCheckBox("Hide the icon when nothing is recording")
        self.hide_idle.setChecked(bool(self.config["hide_when_idle"]))
        self.hide_idle.toggled.connect(lambda v: self._set("hide_when_idle", bool(v)))
        layout.addWidget(self.hide_idle)

        self.standby = QCheckBox("Use a separate colour while the mic is open but quiet")
        self.standby.setChecked(bool(self.config["show_standby"]))
        self.standby.toggled.connect(lambda v: self._set("show_standby", bool(v)))
        layout.addWidget(self.standby)

        self.remember = QCheckBox("Remember muted apps and re-mute them automatically")
        self.remember.setChecked(bool(self.config["remember_mutes"]))
        self.remember.toggled.connect(lambda v: self._set("remember_mutes", bool(v)))
        layout.addWidget(self.remember)

        self.tip_level = QCheckBox("Show the level in the tooltip")
        self.tip_level.setChecked(bool(self.config["tooltip_show_level"]))
        self.tip_level.toggled.connect(lambda v: self._set("tooltip_show_level", bool(v)))
        layout.addWidget(self.tip_level)

        form = QFormLayout()
        self.poll = QSpinBox()
        self.poll.setRange(400, 10000)
        self.poll.setSingleStep(100)
        self.poll.setSuffix(" ms")
        self.poll.setValue(int(self.config["poll_ms"]))
        self.poll.valueChanged.connect(lambda v: self._set("poll_ms", int(v)))
        form.addRow("Stream re-check interval", self.poll)
        layout.addLayout(form)

        box = QGroupBox("Updates")
        box_layout = QVBoxLayout(box)

        top = QHBoxLayout()
        self.version_label = QLabel(f"Installed version: <b>{updates.current_version()}</b>")
        self.check_button = QPushButton("Check for updates")
        self.check_button.clicked.connect(self._check_updates)
        top.addWidget(self.version_label, 1)
        top.addWidget(self.check_button)
        box_layout.addLayout(top)

        self.update_status = QLabel("")
        self.update_status.setWordWrap(True)
        self.update_status.setStyleSheet("color: #8b949e;")
        box_layout.addWidget(self.update_status)

        actions = QHBoxLayout()
        self.update_button = QPushButton("Update now")
        self.update_button.clicked.connect(self.tray.run_update)
        self.update_button.setVisible(False)
        self.release_button = QPushButton("Open release page")
        self.release_button.clicked.connect(self._open_release)
        self.release_button.setVisible(False)
        actions.addWidget(self.update_button)
        actions.addWidget(self.release_button)
        actions.addStretch(1)
        box_layout.addLayout(actions)

        hint = QLabel(
            "MicWatch never checks on its own — it only asks GitHub when you press "
            "the button."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        box_layout.addWidget(hint)
        layout.addWidget(box)

        note = QLabel(
            "KDE ships its own microphone indicator. To avoid two icons, turn it off in\n"
            "System Settings → Quick Settings → System Tray → Entries → Microphone."
        )
        note.setStyleSheet("color: #8b949e;")
        layout.addWidget(note)
        layout.addStretch(1)
        if self.tray.release is not None:
            self.show_update_result(self.tray.release, True)
        return page

    # -- helpers ---------------------------------------------------------
    def _refresh_style_icons(self) -> None:
        colour = QColor(self.config["color_active"])
        size = float(self.config["icon_size"])
        for key, button in self._style_buttons.items():
            button.setIcon(icons.render_icon(key, colour, level=0.14, size=size, px=96))
            button.setChecked(key == self.config["icon_style"])
        if hasattr(self, "icon_size_label"):  # the grid is built before the slider
            self.icon_size_label.setText(f"{size * 100:.0f}%")

    def _icon_size_moved(self, value: int) -> None:
        self.config["icon_size"] = value / 100.0
        self._refresh_style_icons()
        self._apply()

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
        result = autostart.set_enabled(enabled)
        self.autostart_note.setText(autostart.describe())
        if result != enabled:
            self.autostart.setChecked(result)
        self.tray.sync_autostart_action()

    def refresh_streams(self) -> None:
        """One row per application, recording ones first, live."""
        entries = self.tray.known_apps()
        names = [e["name"] for e in entries]
        for app in list(self._rows):
            if app not in names:
                row = self._rows.pop(app)
                self.streams_layout.removeWidget(row)
                row.deleteLater()
        for position, entry in enumerate(entries):
            app = entry["name"]
            row = self._rows.get(app)
            if row is None:
                row = AppRow(app, self.tray, self.streams_box)
                self._rows[app] = row
            self.streams_layout.insertWidget(position, row)
            row.update_from(entry)
        self.who.setVisible(not entries)

    def _check_updates(self) -> None:
        self.check_button.setEnabled(False)
        self.check_button.setText("Checking…")
        self.update_status.setText("Asking GitHub for the latest release…")
        self.tray.check_updates(announce=False)

    def show_update_result(self, release, newer: bool) -> None:
        """Called by the tray when a check finishes."""
        self.check_button.setEnabled(True)
        self.check_button.setText("Check for updates")
        if release is None:
            self.update_status.setText("Could not reach GitHub. Check your connection.")
            self.update_button.setVisible(False)
            self.release_button.setVisible(False)
            return
        self._release = release
        self.release_button.setVisible(True)
        if newer:
            self.update_status.setText(
                f"<b>{release.name}</b> is available — you are on "
                f"{updates.current_version()}. “Update now” opens a terminal running the "
                "installer for your distro."
            )
            self.update_button.setVisible(True)
        else:
            self.update_status.setText(
                f"You are on the latest version ({updates.current_version()})."
            )
            self.update_button.setVisible(False)

    def _open_release(self) -> None:
        release = getattr(self, "_release", None)
        QDesktopServices.openUrl(QUrl(release.url if release else updates.RELEASES_URL))

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
        if key in ("icon_style", "color_active", "icon_size"):
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
