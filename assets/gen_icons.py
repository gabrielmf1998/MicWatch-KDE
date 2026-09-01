"""Renders the application icon (PNG sizes + SVG) from micwatch.icons."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QApplication

from micwatch import icons

COLOR = "#3fb950"
STYLE = "mic_filled"
OUT = Path(__file__).resolve().parent


def main() -> int:
    QApplication([])
    for size in (48, 64, 128, 256, 512):
        pixmap = icons.render_pixmap(STYLE, QColor(COLOR), level=0.25, px=size)
        pixmap.save(str(OUT / f"micwatch-{size}.png"))

    generator = QSvgGenerator()
    generator.setFileName(str(OUT / "micwatch.svg"))
    generator.setSize(QSize(100, 100))
    generator.setViewBox(QRectF(0, 0, 100, 100))
    generator.setTitle("MicWatch")
    generator.setDescription("Microphone in-use tray indicator")
    painter = QPainter(generator)
    painter.setRenderHint(QPainter.Antialiasing, True)
    icons._DRAW[STYLE](painter, QColor(COLOR), 0.25)
    painter.end()
    print("icons written to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
