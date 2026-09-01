"""Every icon is painted at runtime, so any colour or style combination works."""

from __future__ import annotations

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
    ("mic", "Microphone (outline)"),
    ("mic_filled", "Microphone (solid)"),
    ("badge", "Microphone on badge"),
    ("dot", "Dot"),
    ("ring", "Ring meter"),
    ("bars", "Level bars"),
]

ANIMATIONS = [
    ("none", "None"),
    ("pulse", "Pulse (scale)"),
    ("blink", "Blink"),
    ("glow", "Glow halo"),
    ("level", "Follow the level"),
]

_BAR_FACTORS = (0.45, 0.72, 1.0, 0.68, 0.4)


def blend(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def _mic_path(rect: QRectF) -> QPainterPath:
    """Capsule of a classic microphone inside the given rect."""
    path = QPainterPath()
    path.addRoundedRect(rect, rect.width() / 2, rect.width() / 2)
    return path


def _draw_mic(p: QPainter, color: QColor, filled: bool, weight: float = 8.0) -> None:
    pen = QPen(color, weight, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    capsule = QRectF(37, 12, 26, 44)
    if filled:
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(_mic_path(capsule))
    else:
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(_mic_path(capsule))
    p.setBrush(Qt.NoBrush)
    p.setPen(pen)
    p.drawArc(QRectF(27, 34, 46, 44), 180 * 16, 180 * 16)
    p.drawLine(QPointF(50, 78), QPointF(50, 88))
    p.drawLine(QPointF(36, 88), QPointF(64, 88))


def _draw_bars(p: QPainter, color: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    width, gap = 12.0, 6.0
    total = width * 5 + gap * 4
    x = 50 - total / 2
    loud = min(1.0, level * 1.6)
    for factor in _BAR_FACTORS:
        base = 14.0 + 24.0 * factor
        height = base + (84.0 - base) * loud * factor
        height = max(12.0, min(88.0, height))
        y = 50 - height / 2
        p.drawRoundedRect(QRectF(x, y, width, height), width / 2, width / 2)
        x += width + gap


def _draw_ring(p: QPainter, color: QColor, level: float) -> None:
    box = QRectF(16, 16, 68, 68)
    faint = QColor(color)
    faint.setAlphaF(color.alphaF() * 0.28)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(faint, 10, Qt.SolidLine, Qt.RoundCap))
    p.drawEllipse(box)
    span = int(360 * 16 * max(0.02, min(1.0, level * 1.6)))
    p.setPen(QPen(color, 10, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(box, 90 * 16, -span)


def _draw_dot(p: QPainter, color: QColor, level: float) -> None:
    radius = 22 + 12 * min(1.0, level * 1.8)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(50, 50), radius, radius)


def _draw_badge(p: QPainter, color: QColor, level: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(8, 8, 84, 84), 24, 24)
    glyph = QColor(255, 255, 255, round(255 * color.alphaF()))
    if color.lightnessF() > 0.72:
        glyph = QColor(20, 22, 26, round(255 * color.alphaF()))
    p.save()
    p.translate(50, 50)
    p.scale(0.66, 0.66)
    p.translate(-50, -50)
    _draw_mic(p, glyph, False, 8.0)
    p.restore()


def render_pixmap(
    style: str,
    color: QColor,
    *,
    level: float = 0.0,
    scale: float = 1.0,
    alpha: float = 1.0,
    glow: float = 0.0,
    px: int = 128,
) -> QPixmap:
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(px / 100.0, px / 100.0)

    paint_color = QColor(color)
    paint_color.setAlphaF(max(0.0, min(1.0, alpha)))

    if glow > 0.01:
        gradient = QRadialGradient(QPointF(50, 50), 52)
        inner = QColor(color)
        inner.setAlphaF(0.55 * glow)
        mid = QColor(color)
        mid.setAlphaF(0.22 * glow)
        edge = QColor(color)
        edge.setAlphaF(0.0)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(0.55, mid)
        gradient.setColorAt(1.0, edge)
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(50, 50), 50, 50)

    painter.translate(50, 50)
    painter.scale(scale, scale)
    painter.translate(-50, -50)

    if style == "mic_filled":
        _draw_mic(painter, paint_color, True)
    elif style == "badge":
        _draw_badge(painter, paint_color, level)
    elif style == "dot":
        _draw_dot(painter, paint_color, level)
    elif style == "ring":
        _draw_ring(painter, paint_color, level)
    elif style == "bars":
        _draw_bars(painter, paint_color, level)
    else:
        _draw_mic(painter, paint_color, False)

    painter.end()
    return pixmap


def render_icon(style: str, color: QColor, **kwargs) -> QIcon:
    return QIcon(render_pixmap(style, color, **kwargs))
