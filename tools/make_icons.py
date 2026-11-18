#!/usr/bin/env python3
"""Draw Phonotype's icon set into src/phonotype/assets/.

phonotype-0.png      idle: a still waveform (also the application icon)
phonotype-1…9.png    activity frames: the same five bars as a travelling wave

    QT_QPA_PLATFORM=offscreen python tools/make_icons.py
"""
import math
import sys
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter

SIZE = 256
BARS = 5
IDLE = [0.34, 0.62, 1.0, 0.62, 0.34]
OUT = Path(__file__).resolve().parents[1] / "src" / "phonotype" / "assets"


def draw(heights, bar_color: str) -> QImage:
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    # tile
    p.setBrush(QColor("#23262d"))
    p.drawRoundedRect(QRectF(8, 8, SIZE - 16, SIZE - 16), 56, 56)
    # bars
    p.setBrush(QColor(bar_color))
    bar_w, gap, max_h = 26.0, 14.0, 150.0
    total = BARS * bar_w + (BARS - 1) * gap
    x = (SIZE - total) / 2
    for h in heights:
        bh = max(bar_w, max_h * h)
        p.drawRoundedRect(QRectF(x, (SIZE - bh) / 2, bar_w, bh), bar_w / 2, bar_w / 2)
        x += bar_w + gap
    p.end()
    return img


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841  (QPainter needs it)
    OUT.mkdir(parents=True, exist_ok=True)
    draw(IDLE, "#e9ecf1").save(str(OUT / "phonotype-0.png"))
    for frame in range(1, 10):
        phase = 2 * math.pi * (frame - 1) / 9
        heights = [0.25 + 0.75 * (0.5 + 0.5 * math.sin(phase - i * 1.1)) for i in range(BARS)]
        draw(heights, "#ff8a1f").save(str(OUT / f"phonotype-{frame}.png"))
    print(f"wrote 10 icons to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
