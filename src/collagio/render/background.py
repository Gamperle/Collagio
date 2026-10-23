"""Canvas backgrounds: solid, gradient, generated textures and a blurred photo.

Textures are generated procedurally (no stock images, so no licensing questions)
from seeded noise sized in style units, so a preview and a full-size export of
the same project look alike.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageColor, ImageFilter

from collagio.core.model import Background, BackgroundKind
from collagio.core.rng import derive_seed
from collagio.errors import RenderError
from collagio.imaging.smartcrop import crop_pixels, fill_crop

Loader = Callable[[str], Image.Image]

# Texture name -> suggested base colour.
TEXTURES: dict[str, str] = {
    "paper": "#f2ede3",
    "cork": "#b8875a",
    "wood": "#9c6b3e",
}
BLUR_WORK_RADIUS = 8.0  # photo backgrounds are blurred at a size where the radius is ~this


def parse_color(value: str) -> tuple[int, int, int]:
    try:
        rgb = ImageColor.getrgb(value)
    except ValueError as exc:
        raise RenderError(f"invalid colour {value!r}") from exc
    return rgb[0], rgb[1], rgb[2]


def _noise(
    size: tuple[int, int], cell: tuple[float, float], unit: float, rng: np.random.Generator
) -> NDArray[np.float32]:
    """Smooth noise (about mean 0, deviation 1) with features of `cell` style units."""
    width, height = size
    grid = (
        max(2, math.ceil(width / (cell[0] * unit)) + 1),
        max(2, math.ceil(height / (cell[1] * unit)) + 1),
    )
    values = rng.normal(0.0, 1.0, (grid[1], grid[0])).astype(np.float32)
    smooth = Image.fromarray(values, mode="F").resize(size, Image.Resampling.BICUBIC)
    return np.asarray(smooth, dtype=np.float32)


def _shade(base: tuple[int, int, int], brightness: NDArray[np.float32]) -> Image.Image:
    """Base colour with per-pixel brightness offsets (in 0..255 levels)."""
    pixels = np.asarray(base, dtype=np.float32)[None, None, :] + brightness[..., None]
    return Image.fromarray(np.clip(np.rint(pixels), 0, 255).astype(np.uint8), mode="RGB")


def _texture(
    name: str, base: tuple[int, int, int], size: tuple[int, int], unit: float, seed: int
) -> Image.Image:
    rng = np.random.default_rng(derive_seed(seed, "background", name))
    if name == "paper":
        brightness = 3.0 * _noise(size, (2, 2), unit, rng) + 5.0 * _noise(size, (40, 40), unit, rng)
    elif name == "cork":
        fine = _noise(size, (1.5, 1.5), unit, rng)
        brightness = 18.0 * _noise(size, (10, 10), unit, rng) + 16.0 * fine
        brightness -= 55.0 * np.clip(fine - 1.3, 0.0, None)  # dark speckles
    elif name == "wood":
        height = size[1]
        warp = _noise(size, (300, 60), unit, rng)
        ys = np.arange(height, dtype=np.float32)[:, None] / unit
        grain = np.sin((ys + 25.0 * warp) * (2 * math.pi / 14.0))
        streaks = _noise(size, (120, 1.5), unit, rng)  # long, thin pores along the grain
        brightness = 16.0 * grain + 7.0 * streaks + 8.0 * _noise(size, (200, 40), unit, rng)
    else:
        raise RenderError(f"unknown texture {name!r}; available: {', '.join(TEXTURES)}")
    return _shade(base, brightness.astype(np.float32))


def _photo(
    background: Background, size: tuple[int, int], unit: float, loader: Loader | None
) -> Image.Image:
    if not background.photo:
        raise RenderError("no photo chosen for the photo background")
    if loader is None:
        raise RenderError("photo backgrounds need a photo loader")
    if not 0.0 <= background.dim <= 1.0:
        raise RenderError(f"background dim must be between 0 and 1, got {background.dim}")
    source = loader(background.photo).convert("RGB")
    radius = max(0.0, background.blur * unit)
    # Blur at reduced size (much faster for large radii), then scale up.
    shrink = max(1.0, radius / BLUR_WORK_RADIUS)
    work = (max(1, round(size[0] / shrink)), max(1, round(size[1] / shrink)))
    crop = fill_crop(source.size, size[0] / size[1])
    image = source.resize(work, Image.Resampling.LANCZOS, box=crop_pixels(crop, source.size))
    if radius > 0:
        image = image.filter(ImageFilter.GaussianBlur(radius / shrink))
    image = image.resize(size, Image.Resampling.BICUBIC)
    if background.dim > 0:
        image = Image.blend(image, Image.new("RGB", size, "black"), background.dim)
    return image


def render_background(
    background: Background,
    size: tuple[int, int],
    *,
    unit: float = 1.0,
    seed: int = 0,
    loader: Loader | None = None,
) -> Image.Image:
    """The background as an RGB image. `unit` is pixels per style unit."""
    if background.kind is BackgroundKind.SOLID:
        return Image.new("RGB", size, parse_color(background.color))
    if background.kind is BackgroundKind.TEXTURE:
        return _texture(background.texture, parse_color(background.color), size, unit, seed)
    if background.kind is BackgroundKind.PHOTO:
        return _photo(background, size, unit, loader)

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
