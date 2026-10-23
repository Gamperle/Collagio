"""Render the SVG app icon to PNG sizes and a Windows .ico (run after changing the SVG).

uv run python scripts/build_icons.py
"""

from __future__ import annotations

import io
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "src" / "collagio" / "assets" / "collagio.svg"
OUT = ROOT / "packaging" / "icons"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def render(size: int) -> Image.Image:
    renderer = QSvgRenderer(str(SVG))
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data().data())))


def main() -> None:
    QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    images = {size: render(size) for size in SIZES}
    for size, image in images.items():
        image.save(OUT / f"collagio-{size}.png")
    images[256].save(
        OUT / "collagio.ico", sizes=[(s, s) for s in SIZES if s <= 256], append_images=[]
    )
    print(f"wrote {len(SIZES)} PNGs and collagio.ico to {OUT}")


if __name__ == "__main__":
    main()
