"""Conversion between Pillow images and Qt images."""

from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QImage


def to_qimage(image: Image.Image) -> QImage:
    """A QImage that owns a copy of the pixels (safe to create in worker threads)."""
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return qimage.copy()  # detach from the Python buffer
