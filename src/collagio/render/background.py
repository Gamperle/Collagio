"""Canvas backgrounds."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageColor

from collagio.core.model import Background, BackgroundKind
from collagio.errors import RenderError


def parse_color(value: str) -> tuple[int, int, int]:
    try:
        rgb = ImageColor.getrgb(value)
    except ValueError as exc:
        raise RenderError(f"invalid colour {value!r}") from exc
    return rgb[0], rgb[1], rgb[2]


def render_background(background: Background, size: tuple[int, int]) -> Image.Image:
    if background.kind is BackgroundKind.SOLID:
        return Image.new("RGB", size, parse_color(background.color))

    width, height = size
    start = np.array(parse_color(background.color), dtype=np.float32)
    end = np.array(parse_color(background.color2), dtype=np.float32)
    angle = math.radians(background.angle)
    dx, dy = math.cos(angle), math.sin(angle)
    xs = np.arange(width, dtype=np.float32)[None, :] * dx
    ys = np.arange(height, dtype=np.float32)[:, None] * dy
    projection = xs + ys
    low, high = float(projection.min()), float(projection.max())
    t = (projection - low) / (high - low) if high > low else np.zeros_like(projection)
    pixels = start + (end - start) * t[..., None]
    return Image.fromarray(np.rint(pixels).astype(np.uint8), mode="RGB")
