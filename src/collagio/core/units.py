"""Physical units, paper and pixel presets, and canvas size parsing."""

from __future__ import annotations

import re
from enum import StrEnum

from collagio.errors import SizeError

MM_PER_INCH = 25.4
MAX_CANVAS_PX = 30_000

# Portrait orientation (width <= height).
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A5": (148.0, 210.0),
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "10x15": (100.0, 150.0),
    "13x18": (130.0, 180.0),
    "20x30": (200.0, 300.0),
}

PIXEL_PRESETS: dict[str, tuple[int, int]] = {
    "instagram-square": (1080, 1080),
    "instagram-portrait": (1080, 1350),
    "fullhd": (1920, 1080),
    "4k": (3840, 2160),
}

_SIZE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*[x\u00d7]\s*(\d+(?:\.\d+)?)\s*(px|mm)?\s*$",
    re.IGNORECASE,
)


class Orientation(StrEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


def mm_to_px(mm: float, dpi: float) -> int:
    return round(mm / MM_PER_INCH * dpi)


def px_to_mm(px: float, dpi: float) -> float:
    return px / dpi * MM_PER_INCH


def orient(size: tuple[int, int], orientation: Orientation | None) -> tuple[int, int]:
    """Swap width and height if needed to match the orientation (None keeps the size)."""
    width, height = size
    if orientation is Orientation.PORTRAIT and width > height:
        return height, width
    if orientation is Orientation.LANDSCAPE and height > width:
        return height, width
    return size


def _lookup_preset(spec: str, dpi: float) -> tuple[int, int] | None:
    key = spec.strip()
    for name, (w_mm, h_mm) in PAPER_SIZES_MM.items():
        if name.lower() == key.lower():
            return mm_to_px(w_mm, dpi), mm_to_px(h_mm, dpi)
    return PIXEL_PRESETS.get(key.lower())


def parse_size(spec: str, dpi: float, orientation: Orientation | None = None) -> tuple[int, int]:
    """Parse a canvas size into pixels.

    Accepts paper presets ("A4", "10x15"), pixel presets ("fullhd"),
    "WIDTHxHEIGHT" in pixels (optionally suffixed "px") or "WIDTHxHEIGHTmm".
    """
    if dpi <= 0:
        raise SizeError(f"DPI must be positive, got {dpi}")
    size = _lookup_preset(spec, dpi)
    if size is None:
        match = _SIZE_RE.match(spec)
        if match is None:
            presets = ", ".join([*PAPER_SIZES_MM, *PIXEL_PRESETS])
            raise SizeError(
                f"invalid size {spec!r}; use WIDTHxHEIGHT, WIDTHxHEIGHTmm or one of: {presets}"
            )
        width, height = float(match[1]), float(match[2])
        if (match[3] or "px").lower() == "mm":
            size = mm_to_px(width, dpi), mm_to_px(height, dpi)
        else:
            size = round(width), round(height)
    width, height = orient(size, orientation)
    if not (0 < width <= MAX_CANVAS_PX and 0 < height <= MAX_CANVAS_PX):
        raise SizeError(f"canvas size {width}x{height} px is outside 1..{MAX_CANVAS_PX} px")
    return width, height
