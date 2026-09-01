"""Every icon is painted at runtime, so any style/colour/animation combo works."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

ICON_STYLES = [
    ("mic", "Microphone"),
    ("mic_filled", "Microphone (solid)"),
    ("mic_round", "Microphone in a circle"),
    ("badge", "Microphone badge"),
    ("mic_boom", "Headset mic"),
    ("mic_stand", "Studio mic"),
    ("dot", "Dot"),
    ("dot_ring", "Dot with ring"),
    ("led", "LED tile"),
    ("record", "Record"),
    ("ring", "Ring meter"),
    ("ring_dual", "Double ring"),
    ("gauge", "Gauge"),
    ("bars", "Level bars"),
    ("bars_wide", "Level bars (wide)"),
    ("waveform", "Waveform"),
    ("radar", "Signal waves"),
    ("pulse_line", "Heartbeat line"),
]

ANIMATIONS = [
    ("none", "None"),
    ("pulse", "Pulse (scale)"),
    ("breathe", "Breathe (fade)"),
    ("blink", "Blink"),
    ("flash", "Fast strobe"),
    ("glow", "Glow halo"),
    ("ripple", "Ripple rings"),
    ("bounce", "Bounce"),
    ("wobble", "Wobble"),
    ("spin", "Spin"),
    ("heartbeat", "Heartbeat"),
    ("level", "Follow the level"),
    ("level_glow", "Glow with the level"),
    ("rainbow", "Rainbow"),
    ("siren", "Siren (hue sweep)"),
]

_BAR_FACTORS = (0.45, 0.72, 1.0, 0.68, 0.4)
_WIDE_FACTORS = (0.3, 0.55, 0.8, 1.0, 0.78, 0.52, 0.28)


# --------------------------------------------------------------------------
# animation
# --------------------------------------------------------------------------
@dataclass
class AnimState:
    scale: float = 1.0
    alpha: float = 1.0
    glow: float = 0.0
    rotation: float = 0.0
    dy: float = 0.0
    ripple: float = -1.0     # 0..1 while a ring expands, <0 when unused
    hue_shift: float = 0.0


def anim_state(animation: str, phase: float, level: float = 0.0) -> AnimState:
    """Turn (animation, phase 0..1, level 0..1) into drawing parameters."""
    t = phase % 1.0
    wave = 0.5 + 0.5 * math.sin(t * 2 * math.pi)
    loud = min(1.0, level * 8.0)
    st = AnimState()

    if animation == "pulse":
        st.scale = 0.90 + 0.20 * wave
    elif animation == "breathe":
        st.alpha = 0.40 + 0.60 * wave
        st.scale = 0.96 + 0.06 * wave
    elif animation == "blink":
        st.alpha = 1.0 if t < 0.5 else 0.15
    elif animation == "flash":
        st.alpha = 1.0 if (t * 4.0) % 1.0 < 0.5 else 0.12
    elif animation == "glow":
        st.glow = 0.30 + 0.70 * wave
        st.scale = 0.98 + 0.04 * wave
    elif animation == "ripple":
        st.ripple = t
        st.scale = 0.96 + 0.06 * (1.0 - t)
        st.glow = 0.25 * (1.0 - t)
    elif animation == "bounce":
        st.dy = -7.0 * abs(math.sin(t * math.pi))
    elif animation == "wobble":
        st.rotation = 10.0 * math.sin(t * 2 * math.pi)
    elif animation == "spin":
        st.rotation = t * 360.0
    elif animation == "heartbeat":
        if t < 0.16:
            st.scale = 1.0 + 0.20 * math.sin(t / 0.16 * math.pi)
        elif t < 0.34:
            st.scale = 1.0 + 0.12 * math.sin((t - 0.18) / 0.16 * math.pi)
        st.glow = 0.35 * max(0.0, st.scale - 1.0) * 5
    elif animation == "level":
        st.scale = 0.92 + 0.22 * loud
    elif animation == "level_glow":
        st.scale = 0.96 + 0.10 * loud
        st.glow = 0.20 + 0.80 * loud
    elif animation == "rainbow":
        st.hue_shift = t * 360.0
    elif animation == "siren":
        st.hue_shift = 45.0 * math.sin(t * 2 * math.pi)
        st.glow = 0.25 + 0.45 * wave
    return st


def shift_hue(color: QColor, degrees: float) -> QColor:
    if not degrees:
        return color
    h, s, v, a = color.getHsv()
    if h < 0:  # achromatic
        h = 0
        s = max(s, 160)
    return QColor.fromHsv(int((h + degrees) % 360), s, v, a)


def blend(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def _contrast(color: QColor) -> QColor:
    dark = color.lightnessF() > 0.65
    glyph = QColor(24, 26, 30) if dark else QColor(255, 255, 255)
    glyph.setAlphaF(color.alphaF())
    return glyph


# --------------------------------------------------------------------------
# glyphs
# --------------------------------------------------------------------------
def _mic(p: QPainter, c: QColor, filled: bool, weight: float = 9.0, scale: float = 1.0) -> None:
    p.save()
    if scale != 1.0:
        p.translate(50, 50)
        p.scale(scale, scale)
        p.translate(-50, -50)
    pen = QPen(c, weight, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    capsule = QRectF(33, 6, 34, 52)
    path = QPainterPath()
    path.addRoundedRect(capsule, 17, 17)
    if filled:
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPath(path)
    else:
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen)
    p.drawArc(QRectF(19, 28, 62, 56), 180 * 16, 180 * 16)
    p.drawLine(QPointF(50, 84), QPointF(50, 90))
    p.drawLine(QPointF(33, 93), QPointF(67, 93))
    p.restore()


def _mic_round(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(50, 50), 49, 49)
    p.save()
    p.translate(50, 50)
    p.scale(0.68, 0.68)
    p.translate(-50, -50)
    _mic(p, _contrast(c), False, 9.0)
    p.restore()


def _badge(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(2, 2, 96, 96), 28, 28)
    p.save()
    p.translate(50, 50)
    p.scale(0.70, 0.70)
    p.translate(-50, -50)
    _mic(p, _contrast(c), False, 9.0)
    p.restore()


def _mic_boom(p: QPainter, c: QColor, level: float) -> None:
    pen = QPen(c, 10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(11, 8, 78, 68), 20 * 16, 140 * 16)    # headband
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(6, 42, 21, 34), 9, 9)         # ear cup
    p.drawRoundedRect(QRectF(73, 42, 21, 34), 9, 9)
    p.setPen(pen)
    path = QPainterPath(QPointF(83, 74))
    path.quadTo(QPointF(78, 92), QPointF(58, 92))          # boom arm
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    r = 10 + 5 * min(1.0, level * 6)
    p.drawEllipse(QPointF(50, 92), r, r)


def _mic_stand(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(26, 4, 48, 58), 24, 24)       # capsule
    grid = QColor(_contrast(c))
    grid.setAlphaF(c.alphaF() * 0.75)
    p.setPen(QPen(grid, 5, Qt.SolidLine, Qt.RoundCap))
    for y in (20, 32, 44):
        p.drawLine(QPointF(36, y), QPointF(64, y))
    p.setPen(QPen(c, 9, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(50, 62), QPointF(50, 88))
    p.drawLine(QPointF(26, 94), QPointF(74, 94))


def _dot(p: QPainter, c: QColor, level: float, ring: bool = False) -> None:
    radius = 32 + 14 * min(1.0, level * 6.0)
    if ring:
        faint = QColor(c)
        faint.setAlphaF(c.alphaF() * 0.45)
        p.setPen(QPen(faint, 8))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(50, 50), 45, 45)
        radius = min(radius, 32)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(50, 50), radius, radius)


def _led(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    size = 76 + 20 * min(1.0, level * 6.0)
    p.drawRoundedRect(QRectF(50 - size / 2, 50 - size / 2, size, size), 16, 16)


def _record(p: QPainter, c: QColor, level: float) -> None:
    faint = QColor(c)
    faint.setAlphaF(c.alphaF() * 0.40)
    p.setPen(QPen(faint, 9))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(50, 50), 45, 45)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    r = 29 + 7 * min(1.0, level * 6.0)
    p.drawEllipse(QPointF(50, 50), r, r)


def _ring(p: QPainter, c: QColor, level: float, dual: bool = False) -> None:
    box = QRectF(11, 11, 78, 78)
    faint = QColor(c)
    faint.setAlphaF(c.alphaF() * 0.28)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(faint, 12, Qt.SolidLine, Qt.RoundCap))
    p.drawEllipse(box)
    span = int(360 * 16 * max(0.02, min(1.0, level * 5.0)))
    p.setPen(QPen(c, 12, Qt.SolidLine, Qt.RoundCap))
    if dual:
        half = span // 2
        p.drawArc(box, 90 * 16, -half)
        p.drawArc(box, 270 * 16, -half)
    else:
        p.drawArc(box, 90 * 16, -span)


def _gauge(p: QPainter, c: QColor, level: float) -> None:
    box = QRectF(7, 14, 86, 86)
    faint = QColor(c)
    faint.setAlphaF(c.alphaF() * 0.30)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(faint, 13, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(box, 180 * 16, -180 * 16)
    filled = min(1.0, level * 5.0)
    p.setPen(QPen(c, 13, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(box, 180 * 16, int(-180 * 16 * max(0.02, filled)))
    angle = math.pi - math.pi * filled
    p.setPen(QPen(c, 8, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(50, 57), QPointF(50 + 33 * math.cos(angle), 57 - 33 * math.sin(angle)))


def _bars(p: QPainter, c: QColor, level: float, factors=_BAR_FACTORS, width=13.0, gap=6.0) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    total = width * len(factors) + gap * (len(factors) - 1)
    x = 50 - total / 2
    loud = min(1.0, level * 5.0)
    for factor in factors:
        base = 18.0 + 30.0 * factor
        height = max(14.0, min(96.0, base + (96.0 - base) * loud * factor))
        p.drawRoundedRect(QRectF(x, 50 - height / 2, width, height), width / 2, width / 2)
        x += width + gap


def _waveform(p: QPainter, c: QColor, level: float) -> None:
    amp = 8 + 38 * min(1.0, level * 5.0)
    path = QPainterPath(QPointF(5, 50))
    steps = 48
    for i in range(1, steps + 1):
        x = 5 + 90 * i / steps
        y = 50 - amp * math.sin(i / steps * 3.2 * math.pi)
        path.lineTo(QPointF(x, y))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(c, 10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)


def _radar(p: QPainter, c: QColor, level: float) -> None:
    p.setBrush(Qt.NoBrush)
    loud = min(1.0, level * 5.0)
    for i, radius in enumerate((23, 40, 57)):
        arc = QColor(c)
        reach = loud * 3.0
        arc.setAlphaF(c.alphaF() * (1.0 if reach >= i + 1 else max(0.18, reach - i)))
        p.setPen(QPen(arc, 10, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(50 - radius, 74 - radius, radius * 2, radius * 2), 40 * 16, 100 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(50, 80), 10, 10)


def _pulse_line(p: QPainter, c: QColor, level: float) -> None:
    amp = 12 + 34 * min(1.0, level * 5.0)
    path = QPainterPath(QPointF(4, 50))
    path.lineTo(QPointF(28, 50))
    path.lineTo(QPointF(37, 50 - amp))
    path.lineTo(QPointF(46, 50 + amp * 0.8))
    path.lineTo(QPointF(55, 50 - amp * 0.35))
    path.lineTo(QPointF(64, 50))
    path.lineTo(QPointF(96, 50))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(c, 10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)


_DRAW = {
    "mic": lambda p, c, lv: _mic(p, c, False),
    "mic_filled": lambda p, c, lv: _mic(p, c, True),
    "mic_round": _mic_round,
    "badge": _badge,
    "mic_boom": _mic_boom,
    "mic_stand": _mic_stand,
    "dot": lambda p, c, lv: _dot(p, c, lv, False),
    "dot_ring": lambda p, c, lv: _dot(p, c, lv, True),
    "led": _led,
    "record": _record,
    "ring": lambda p, c, lv: _ring(p, c, lv, False),
    "ring_dual": lambda p, c, lv: _ring(p, c, lv, True),
    "gauge": _gauge,
    "bars": lambda p, c, lv: _bars(p, c, lv),
    "bars_wide": lambda p, c, lv: _bars(p, c, lv, _WIDE_FACTORS, 10.0, 4.0),
    "waveform": _waveform,
    "radar": _radar,
    "pulse_line": _pulse_line,
}


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def render_pixmap(
    style: str,
    color: QColor,
    *,
    level: float = 0.0,
    state: AnimState | None = None,
    size: float = 1.0,
    px: int = 128,
) -> QPixmap:
    st = state or AnimState()
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(px / 100.0, px / 100.0)

    paint_color = shift_hue(QColor(color), st.hue_shift)
    paint_color.setAlphaF(max(0.0, min(1.0, st.alpha)))

    if st.glow > 0.01:
        gradient = QRadialGradient(QPointF(50, 50 + st.dy), 52)
        inner = QColor(paint_color)
        inner.setAlphaF(0.55 * st.glow)
        mid = QColor(paint_color)
        mid.setAlphaF(0.22 * st.glow)
        edge = QColor(paint_color)
        edge.setAlphaF(0.0)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(0.55, mid)
        gradient.setColorAt(1.0, edge)
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(50, 50 + st.dy), 50, 50)

    if st.ripple >= 0.0:
        ring = QColor(paint_color)
        ring.setAlphaF(max(0.0, 0.75 * (1.0 - st.ripple)))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ring, 6))
        radius = 26 + 24 * st.ripple
        painter.drawEllipse(QPointF(50, 50 + st.dy), radius, radius)

    painter.translate(50, 50 + st.dy)
    if st.rotation:
        painter.rotate(st.rotation)
    zoom = st.scale * max(0.4, min(1.0, size))
    painter.scale(zoom, zoom)
    painter.translate(-50, -50)

    _DRAW.get(style, _DRAW["mic"])(painter, paint_color, level)
    painter.end()
    return pixmap


def render_icon(style: str, color: QColor, **kwargs) -> QIcon:
    return QIcon(render_pixmap(style, color, **kwargs))
