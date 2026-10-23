"""Drawing helpers shared by the styles."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from collagio.styles.base import StyleContext

Point = tuple[float, float]

ANTIALIAS_RADIUS = 0.6  # pixels; softens polygon edges drawn without anti-aliasing
NOISE_CELL_UNITS = 2.0  # size of one paper texture noise cell
TEXTURE_LEVELS = 10.0  # brightness variation at texture = 1
PROFILE_STEP_UNITS = 1.5  # spacing of points along a random edge


def rgb(color: str) -> tuple[int, int, int]:
    value = ImageColor.getrgb(color)
    return value[0], value[1], value[2]


def paper(size: tuple[int, int], color: str, texture: float, ctx: StyleContext) -> Image.Image:
    """Opaque paper of `color` with soft, scale-independent brightness noise."""
    width, height = size
    base = Image.new("RGBA", size, (*rgb(color), 255))
    if texture <= 0:
        return base
    cells = (
        max(2, math.ceil(width / (NOISE_CELL_UNITS * ctx.unit)) + 1),
        max(2, math.ceil(height / (NOISE_CELL_UNITS * ctx.unit)) + 1),
    )
    noise = ctx.numpy_rng("paper").normal(0.0, 1.0, (cells[1], cells[0]))
    levels = np.clip(128 + noise * 40, 0, 255).astype(np.uint8)
    smooth = Image.fromarray(levels, mode="L").resize(size, Image.Resampling.BICUBIC)
    offset = (np.asarray(smooth, dtype=np.float32) - 128) / 40 * TEXTURE_LEVELS * texture
    pixels = np.asarray(base, dtype=np.float32).copy()
    pixels[..., :3] += offset[..., None]
    return Image.fromarray(np.clip(np.rint(pixels), 0, 255).astype(np.uint8), mode="RGBA")


def polygon_mask(size: tuple[int, int], points: Sequence[Point]) -> Image.Image:
    """Filled polygon as an anti-aliased L mask."""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(list(points), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(ANTIALIAS_RADIUS))


def fractal_profile(
    length: float, amplitude: float, rng: np.random.Generator, roughness: float = 0.6
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Random 1-D edge profile by midpoint displacement.

    Returns positions 0..`length` (about every PROFILE_STEP_UNITS) and values
    in [-amplitude, amplitude]. Everything is in style units, so the profile
    does not depend on the render scale.
    """
    levels = max(1, math.ceil(math.log2(max(length / PROFILE_STEP_UNITS, 2.0))))
    count = 2**levels
    values = np.zeros(count + 1)
    values[0], values[-1] = rng.uniform(-1.0, 1.0, 2)
    scale, span = 1.0, count
    while span > 1:
        half = span // 2
        middle = (values[0:count:span] + values[span : count + 1 : span]) / 2
        values[half:count:span] = middle + rng.uniform(-scale, scale, len(middle))
        scale *= roughness
        span = half
    peak = float(np.abs(values).max())
    if peak > 0:
        values *= amplitude / peak
    return np.linspace(0.0, length, count + 1), values


def font(size_px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=max(1, size_px))
