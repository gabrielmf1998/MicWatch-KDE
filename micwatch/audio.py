"""PipeWire / PulseAudio glue: who is recording, and how loud it is."""

from __future__ import annotations

import array
import json
import math
import subprocess
import threading
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .config import METER_NODE_NAME

METER_RATE = 16000
METER_BLOCK = 480          # 30 ms of mono audio
_REAL_SOURCE_CLASSES = {"Audio/Source"}
_VIRTUAL_SOURCE_CLASSES = {"Audio/Source/Virtual"}


@dataclass
class StreamInfo:
    index: int
    app: str
    node_name: str
    binary: str
    pid: str
    source: str
    source_desc: str
    corked: bool
    virtual: bool


@dataclass
class SourceInfo:
    index: int
    name: str
    description: str
    real: bool
    virtual: bool


def _run(args: list[str]) -> str:
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if out.returncode == 0 else ""


def default_source() -> str:
    return _run(["pactl", "get-default-source"]).strip()


def list_sources() -> dict[int, SourceInfo]:
    raw = _run(["pactl", "-f", "json", "list", "sources"])
    sources: dict[int, SourceInfo] = {}
    try:
        entries = json.loads(raw) if raw else []
    except ValueError:
        entries = []
    for entry in entries:
        props = entry.get("properties") or {}
        media_class = props.get("media.class", "")
        monitor_of = entry.get("monitor_source") or ""
        real = media_class in _REAL_SOURCE_CLASSES and not monitor_of
        virtual = media_class in _VIRTUAL_SOURCE_CLASSES
        sources[entry.get("index", -1)] = SourceInfo(
            index=entry.get("index", -1),
            name=entry.get("name", ""),
            description=entry.get("description", "") or entry.get("name", ""),
            real=real,
            virtual=virtual,
        )
    return sources


def list_streams() -> tuple[list[StreamInfo], dict[int, SourceInfo]]:
    sources = list_sources()
    raw = _run(["pactl", "-f", "json", "list", "source-outputs"])
    try:
        entries = json.loads(raw) if raw else []
    except ValueError:
        entries = []

    streams: list[StreamInfo] = []
    for entry in entries:
        props = entry.get("properties") or {}
        src = sources.get(entry.get("source", -1))
        if src is None or (not src.real and not src.virtual):
            continue  # monitor of a sink: that is loopback, not a microphone
        app = (
            props.get("application.name")
            or props.get("node.name")
            or props.get("application.process.binary")
            or "Unknown"
        )
        streams.append(
            StreamInfo(
                index=entry.get("index", -1),
                app=app,
                node_name=props.get("node.name", ""),
                binary=props.get("application.process.binary", ""),
                pid=props.get("application.process.id", ""),
                source=src.name,
                source_desc=src.description,
                corked=bool(entry.get("corked", False)),
                virtual=src.virtual,
            )
        )
    return streams, sources


class MicMonitor(QObject):
    """Watches recording streams and reports the ones that count."""

    changed = Signal(list)  # list[StreamInfo]

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.streams: list[StreamInfo] = []
        self.sources: dict[int, SourceInfo] = {}

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self.refresh)

        self._poll = QTimer(self)
        self._poll.timeout.connect(self.refresh)

        self._subscribe = QProcess(self)
        self._subscribe.readyReadStandardOutput.connect(self._on_events)
        self._subscribe.finished.connect(self._restart_subscribe)

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self._poll.start(max(400, int(self.config["poll_ms"])))
        self._subscribe.start("pactl", ["subscribe"])
        self.refresh()

    def stop(self) -> None:
        self._poll.stop()
        self._subscribe.finished.disconnect(self._restart_subscribe)
        self._subscribe.kill()
        self._subscribe.waitForFinished(500)

    def apply_config(self) -> None:
        self._poll.setInterval(max(400, int(self.config["poll_ms"])))
        self.refresh()

    # -- internals -------------------------------------------------------
    def _on_events(self) -> None:
        data = bytes(self._subscribe.readAllStandardOutput()).decode("utf-8", "replace")
        if "source-output" in data or "'source'" in data or "server" in data:
            self._debounce.start()

    def _restart_subscribe(self) -> None:
        QTimer.singleShot(2000, lambda: self._subscribe.start("pactl", ["subscribe"]))

    def _counts(self, stream: StreamInfo) -> bool:
        if METER_NODE_NAME in (stream.app, stream.node_name):
            return False  # our own level meter
        if stream.virtual and not self.config["include_virtual"]:
            return False
        if stream.corked and self.config["ignore_corked"]:
            return False
        ignored = [a.strip().lower() for a in self.config["ignore_apps"] if a.strip()]
        name = stream.app.lower()
        binary = (stream.binary or "").lower()
        return not any(i == name or i == binary or i in name for i in ignored)

    def refresh(self) -> None:
        streams, sources = list_streams()
        self.sources = sources
        counted = [s for s in streams if self._counts(s)]
        if counted != self.streams:
            self.streams = counted
            self.changed.emit(counted)

    def preferred_source(self) -> str:
        for stream in self.streams:
            if not stream.virtual and stream.source:
                return stream.source
        for stream in self.streams:
            if stream.source:
                return stream.source
        return default_source()


class LevelMeter(QObject):
    """Reads the microphone through pw-cat and reports an RMS level (0..1)."""

    level = Signal(float)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._target = ""

    @property
    def running(self) -> bool:
        return self._proc is not None

    @property
    def target(self) -> str:
        return self._target

    def start(self, target: str) -> None:
        if self._proc is not None:
            if target == self._target:
                return
            self.stop()
        if not target:
            target = default_source()
        if not target:
            self.failed.emit("no input device")
            return
        args = [
            "pw-cat", "-r", "-a",
            "--target", target,
            "--rate", str(METER_RATE),
            "--channels", "1",
            "--format", "s16",
            "--latency", "30ms",
            "-P",
            '{ node.name = "%s" application.name = "%s" node.description = "%s" '
            'media.role = Communication }'
            % (METER_NODE_NAME, METER_NODE_NAME, "MicWatch level meter"),
            "-",
        ]
        try:
            self._proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
            )
        except OSError as exc:
            self._proc = None
            self.failed.emit(str(exc))
            return
        self._target = target
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc, self._proc = self._proc, None
        self._target = ""
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except (OSError, subprocess.SubprocessError):
                try:
                    proc.kill()
                except OSError:
                    pass
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)
        self.level.emit(0.0)

    def _reader(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        nbytes = METER_BLOCK * 2
        samples = array.array("h")
        while not self._stop.is_set():
            try:
                chunk = proc.stdout.read(nbytes)
            except (OSError, ValueError):
                break
            if not chunk or len(chunk) < nbytes:
                break
            del samples[:]
            samples.frombytes(chunk)
            total = 0
            for value in samples:
                total += value * value
            rms = math.sqrt(total / len(samples)) / 32768.0
            self.level.emit(min(1.0, rms))
        if not self._stop.is_set():
            self.failed.emit("capture stopped")
