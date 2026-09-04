"""Every icon is painted at runtime, so any style/colour/animation combo works."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
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
    ("mic_hex", "Microphone hexagon"),
    ("diamond", "Diamond"),
    ("pill", "Pill meter"),
    ("eye", "Watching eye"),
    ("tower", "Radio tower"),
    ("bubble", "Speech bubble"),
    ("radial_bars", "Radial bars"),
    ("pie", "Pie meter"),
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
    ("crazy_rainbow", "Crazy rainbow"),
    ("glitch", "Glitch"),
    ("hard_glitch", "Hard glitch"),
    ("neon", "Neon flicker"),
    ("jelly", "Jelly (squash)"),
    ("shake", "Shake"),
    ("swing", "Swing"),
    ("zoom", "Zoom in/out"),
    ("orbit", "Orbit"),
    ("vhs", "VHS tracking"),
]

_BAR_FACTORS = (0.45, 0.72, 1.0, 0.68, 0.4)
_WIDE_FACTORS = (0.3, 0.55, 0.8, 1.0, 0.78, 0.52, 0.28)


# --------------------------------------------------------------------------
# animation
# --------------------------------------------------------------------------
@dataclass
class AnimState:
    scale: float = 1.0
    scale_x: float = 1.0     # non-uniform, for squash and stretch
    scale_y: float = 1.0
    alpha: float = 1.0
    glow: float = 0.0
    rotation: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    ripple: float = -1.0     # 0..1 while a ring expands, <0 when unused
    hue_shift: float = 0.0
    glitch: float = 0.0      # 0..1 amount of RGB split and slice tearing
    phase: float = 0.0


def _noise(seed: float) -> float:
    """Deterministic 0..1 pseudo-random, so a phase always glitches the same way."""
    value = math.sin(seed * 127.1) * 43758.5453
    return value - math.floor(value)


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
    elif animation == "crazy_rainbow":
        st.hue_shift = (t * 3.0 % 1.0) * 360.0
        st.scale = 0.90 + 0.18 * (0.5 + 0.5 * math.sin(t * 6 * math.pi))
        st.rotation = 14.0 * math.sin(t * 4 * math.pi)
        st.glow = 0.35 + 0.5 * wave
    elif animation == "glitch":
        st.glitch = 0.45 + 0.55 * _noise(t * 7.0)
        st.dx = (_noise(t * 13.0) - 0.5) * 5.0
        st.hue_shift = 22.0 * (_noise(t * 3.0) - 0.5)
    elif animation == "hard_glitch":
        st.glitch = 1.0
        st.dx = (_noise(t * 23.0) - 0.5) * 12.0
        st.dy = (_noise(t * 29.0) - 0.5) * 6.0
        st.hue_shift = 90.0 * (_noise(t * 5.0) - 0.5)
        st.alpha = 0.65 + 0.35 * _noise(t * 17.0)
        st.scale = 0.94 + 0.12 * _noise(t * 11.0)
    elif animation == "neon":
        flicker = _noise(t * 19.0)
        st.alpha = 0.35 if flicker > 0.86 else 1.0
        st.glow = 0.25 + 0.75 * (0.0 if flicker > 0.86 else 0.6 + 0.4 * wave)
    elif animation == "jelly":
        squash = 0.16 * math.sin(t * 4 * math.pi)
        st.scale_x = 1.0 + squash
        st.scale_y = 1.0 - squash
        st.dy = -4.0 * abs(math.sin(t * 2 * math.pi))
    elif animation == "shake":
        st.dx = (_noise(t * 41.0) - 0.5) * 9.0
        st.dy = (_noise(t * 37.0) - 0.5) * 9.0
    elif animation == "swing":
        st.rotation = 18.0 * math.sin(t * 2 * math.pi) ** 3
        st.dy = -2.0 * abs(math.sin(t * 2 * math.pi))
    elif animation == "zoom":
        st.scale = 0.72 + 0.42 * wave
    elif animation == "orbit":
        st.dx = 7.0 * math.cos(t * 2 * math.pi)
        st.dy = 7.0 * math.sin(t * 2 * math.pi)
    elif animation == "vhs":
        st.glitch = 0.30
        st.dy = (_noise(t * 3.0) - 0.5) * 10.0
        st.alpha = 0.8 + 0.2 * wave
        st.hue_shift = 12.0 * math.sin(t * 8 * math.pi)
    st.phase = t
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


def _polygon(cx: float, cy: float, radius: float, sides: int, rotation: float = 0.0):
    from PySide6.QtGui import QPolygonF

    points = []
    for i in range(sides):
        angle = rotation + i * 2 * math.pi / sides
        points.append(QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return QPolygonF(points)


def _mic_hex(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPolygon(_polygon(50, 50, 50, 6, -math.pi / 2))
    p.save()
    p.translate(50, 50)
    p.scale(0.60, 0.60)
    p.translate(-50, -50)
    _mic(p, _contrast(c), False, 9.0)
    p.restore()


def _diamond(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    radius = 38 + 12 * min(1.0, level * 6.0)
    p.drawPolygon(_polygon(50, 50, radius, 4, -math.pi / 2))


def _pill(p: QPainter, c: QColor, level: float) -> None:
    track = QColor(c)
    track.setAlphaF(c.alphaF() * 0.28)
    box = QRectF(4, 34, 92, 32)
    p.setPen(Qt.NoPen)
    p.setBrush(track)
    p.drawRoundedRect(box, 16, 16)
    filled = QRectF(box)
    filled.setWidth(max(20.0, box.width() * min(1.0, level * 5.0)))
    p.setBrush(c)
    p.drawRoundedRect(filled, 16, 16)


def _eye(p: QPainter, c: QColor, level: float) -> None:
    path = QPainterPath(QPointF(4, 50))
    path.quadTo(QPointF(50, 4), QPointF(96, 50))
    path.quadTo(QPointF(50, 96), QPointF(4, 50))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(c, 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(50, 50), 14 + 8 * min(1.0, level * 6.0), 14 + 8 * min(1.0, level * 6.0))


def _tower(p: QPainter, c: QColor, level: float) -> None:
    loud = min(1.0, level * 5.0)
    p.setBrush(Qt.NoBrush)
    for i, radius in enumerate((17, 30)):
        arc = QColor(c)
        arc.setAlphaF(c.alphaF() * (1.0 if loud * 2.0 >= i + 1 else max(0.2, loud * 2.0 - i)))
        p.setPen(QPen(arc, 8, Qt.SolidLine, Qt.RoundCap))
        box = QRectF(50 - radius, 30 - radius, radius * 2, radius * 2)
        p.drawArc(box, 25 * 16, 60 * 16)
        p.drawArc(box, 95 * 16, 60 * 16)
    p.setPen(QPen(c, 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(QPointF(50, 22), QPointF(50, 36))          # mast
    p.drawLine(QPointF(32, 94), QPointF(46, 40))          # legs
    p.drawLine(QPointF(68, 94), QPointF(54, 40))
    p.setPen(QPen(c, 7, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(41, 62), QPointF(59, 62))          # cross braces
    p.drawLine(QPointF(36, 80), QPointF(64, 80))


def _bubble(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(4, 12, 92, 62), 22, 22)
    tail = QPainterPath(QPointF(30, 70))
    tail.lineTo(QPointF(30, 96))
    tail.lineTo(QPointF(56, 70))
    tail.closeSubpath()
    p.drawPath(tail)
    dot = _contrast(c)
    p.setBrush(dot)
    loud = min(1.0, level * 5.0)
    for i, x in enumerate((30, 50, 70)):
        radius = 5 + 4 * loud * (0.6 + 0.4 * ((i + 1) % 3) / 2)
        p.drawEllipse(QPointF(x, 43), radius, radius)


def _radial_bars(p: QPainter, c: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    loud = min(1.0, level * 5.0)
    count = 12
    for i in range(count):
        angle = i * 2 * math.pi / count
        factor = 0.45 + 0.55 * abs(math.sin(i * 1.7))
        length = 14 + 26 * loud * factor + 6 * factor
        inner, outer = 16.0, 16.0 + length
        p.save()
        p.translate(50, 50)
        p.rotate(math.degrees(angle))
        p.drawRoundedRect(QRectF(inner, -4.5, outer - inner, 9), 4.5, 4.5)
        p.restore()


def _pie(p: QPainter, c: QColor, level: float) -> None:
    box = QRectF(6, 6, 88, 88)
    faint = QColor(c)
    faint.setAlphaF(c.alphaF() * 0.25)
    p.setPen(Qt.NoPen)
    p.setBrush(faint)
    p.drawEllipse(box)
    p.setBrush(c)
    span = int(360 * 16 * max(0.04, min(1.0, level * 5.0)))
    p.drawPie(box, 90 * 16, -span)


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
    "mic_hex": _mic_hex,
    "diamond": _diamond,
    "pill": _pill,
    "eye": _eye,
    "tower": _tower,
    "bubble": _bubble,
    "radial_bars": _radial_bars,
    "pie": _pie,
}


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def _draw_glyph(
    painter: QPainter,
    style: str,
    colour: QColor,
    level: float,
    st: AnimState,
    zoom: float,
    dx: float,
    dy: float,
) -> None:
    painter.save()
    painter.translate(50 + dx, 50 + dy)
    if st.rotation:
        painter.rotate(st.rotation)
    painter.scale(zoom * st.scale_x, zoom * st.scale_y)
    painter.translate(-50, -50)
    _DRAW.get(style, _DRAW["mic"])(painter, colour, level)
    painter.restore()


def _tear(pixmap: QPixmap, st: AnimState, px: int) -> QPixmap:
    """Slice the finished icon into bands and shove them sideways."""
    torn = QPixmap(px, px)
    torn.fill(Qt.transparent)
    painter = QPainter(torn)
    painter.drawPixmap(0, 0, pixmap)
    for i in range(2 + int(st.glitch * 2)):
        pick = _noise(st.phase * 31.0 + i * 7.13)
        size = _noise(st.phase * 17.0 + i * 3.77)
        height = max(2, int(px * (0.05 + 0.11 * size)))
        top = int(pick * max(1, px - height))
        shift = int((size - 0.5) * px * 0.26 * st.glitch)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(QRect(0, top, px, height), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(
            QRect(shift, top, px, height), pixmap, QRect(0, top, px, height)
        )
    painter.end()
    return torn


def render_pixmap(
    style: str,
    color: QColor,
    *,
    level: float = 0.0,
    state: AnimState | None = None,
    size: float = 1.0,
    muted: bool = False,
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
    centre = QPointF(50 + st.dx, 50 + st.dy)

    if st.glow > 0.01:
        gradient = QRadialGradient(centre, 52)
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
        painter.drawEllipse(centre, 50, 50)

    if st.ripple >= 0.0:
        ring = QColor(paint_color)
        ring.setAlphaF(max(0.0, 0.75 * (1.0 - st.ripple)))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ring, 6))
        painter.drawEllipse(centre, 26 + 24 * st.ripple, 26 + 24 * st.ripple)

    zoom = st.scale * max(0.4, min(1.0, size))

    if st.glitch > 0.01:
        # chromatic aberration: two tinted ghosts either side of the glyph
        for offset, tint in (
            (-5.0 * st.glitch, QColor(255, 45, 120)),
            (5.0 * st.glitch, QColor(45, 230, 255)),
        ):
            ghost = QColor(tint)
            ghost.setAlphaF(0.55 * max(0.35, st.alpha))
            _draw_glyph(painter, style, ghost, level, st, zoom, st.dx + offset, st.dy)

    _draw_glyph(painter, style, paint_color, level, st, zoom, st.dx, st.dy)

    if muted:
        # carve a gap out of the glyph first, so the slash reads at 22 px
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.setPen(QPen(QColor(0, 0, 0), 20, Qt.SolidLine, Qt.FlatCap))
        painter.drawLine(QPointF(12, 12), QPointF(88, 88))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(QPen(paint_color, 11, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(14, 14), QPointF(86, 86))

    painter.end()

    if st.glitch > 0.01:
        pixmap = _tear(pixmap, st, px)
    return pixmap


def render_icon(style: str, color: QColor, **kwargs) -> QIcon:
    return QIcon(render_pixmap(style, color, **kwargs))
