from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from collagio.core.model import Background, BackgroundKind
from collagio.errors import RenderError
from collagio.imaging.loader import load_image
from collagio.render.background import TEXTURES, parse_color, render_background
from tests.helpers.image_compare import ssim


def test_solid() -> None:
    image = render_background(Background(color="#336699"), (20, 10))
    assert image.mode == "RGB"
    assert image.size == (20, 10)
    assert image.getcolors() == [(200, (0x33, 0x66, 0x99))]


@pytest.mark.parametrize(
    ("angle", "start_px", "end_px"),
    [
        (90.0, (5, 0), (5, 99)),  # top to bottom
        (0.0, (0, 50), (99, 50)),  # left to right
        (180.0, (99, 50), (0, 50)),  # right to left
        (45.0, (0, 0), (99, 99)),  # diagonal
    ],
)
def test_gradient_direction(
    angle: float, start_px: tuple[int, int], end_px: tuple[int, int]
) -> None:
    bg = Background(BackgroundKind.GRADIENT, "#000000", "#ffffff", angle)
    image = render_background(bg, (100, 100))
    assert image.getpixel(start_px) == (0, 0, 0)
    assert image.getpixel(end_px) == (255, 255, 255)


def test_gradient_is_monotonic() -> None:
    bg = Background(BackgroundKind.GRADIENT, "#000000", "#ffffff", 90.0)
    image = render_background(bg, (3, 50))
    values = [image.getpixel((1, y))[0] for y in range(50)]  # type: ignore[index]
    assert values == sorted(values)


def test_gradient_on_single_pixel() -> None:
    bg = Background(BackgroundKind.GRADIENT, "#102030", "#ffffff")
    assert render_background(bg, (1, 1)).getpixel((0, 0)) == (0x10, 0x20, 0x30)


def test_parse_color() -> None:
    assert parse_color("red") == (255, 0, 0)
    assert parse_color("#11223344") == (0x11, 0x22, 0x33)


def test_invalid_colour() -> None:
    with pytest.raises(RenderError, match="invalid colour"):
        render_background(Background(color="blurple"), (2, 2))


# --- textures and photo backgrounds --------------------------------------------------------------


@pytest.mark.parametrize("name", list(TEXTURES))
def test_texture_renders_deterministically(name: str) -> None:
    bg = Background(BackgroundKind.TEXTURE, color=TEXTURES[name], texture=name)
    a = render_background(bg, (200, 150), unit=1.0, seed=3)
    b = render_background(bg, (200, 150), unit=1.0, seed=3)
    c = render_background(bg, (200, 150), unit=1.0, seed=4)
    assert a.mode == "RGB"
    assert a.size == (200, 150)
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != c.tobytes()
    pixels = np.asarray(a, dtype=np.float32)
    assert pixels.std() > 1.0  # it is a texture, not a flat colour
    base = np.asarray(Image.new("RGB", (1, 1), TEXTURES[name]), dtype=np.float32)[0, 0]
    assert np.abs(pixels.reshape(-1, 3).mean(axis=0) - base).max() < 25  # keeps its colour


@pytest.mark.parametrize("name", list(TEXTURES))
def test_texture_is_scale_invariant(name: str) -> None:
    bg = Background(BackgroundKind.TEXTURE, color=TEXTURES[name], texture=name)
    small = render_background(bg, (200, 150), unit=1.0, seed=1)
    large = render_background(bg, (800, 600), unit=4.0, seed=1)
    assert ssim(small, large.resize(small.size, Image.Resampling.LANCZOS)) > 0.6


def test_texture_follows_the_base_colour() -> None:
    dark = render_background(Background(BackgroundKind.TEXTURE, color="#202020"), (50, 50))
    light = render_background(Background(BackgroundKind.TEXTURE, color="#e0e0e0"), (50, 50))
    assert np.asarray(dark).mean() < 60 < 200 < np.asarray(light).mean()


def test_unknown_texture() -> None:
    with pytest.raises(RenderError, match="unknown texture 'marble'"):
        render_background(Background(BackgroundKind.TEXTURE, texture="marble"), (10, 10))


def _stripes(_: str) -> Image.Image:
    image = Image.new("RGB", (400, 200), "white")
    for x in range(0, 400, 20):
        image.paste((0, 0, 0), (x, 0, x + 10, 200))
    return image


def test_photo_background_fills_blurs_and_dims() -> None:
    sharp = render_background(
        Background(BackgroundKind.PHOTO, photo="x", blur=0, dim=0), (300, 300), loader=_stripes
    )
    blurred = render_background(
        Background(BackgroundKind.PHOTO, photo="x", blur=20, dim=0), (300, 300), loader=_stripes
    )
    dark = render_background(
        Background(BackgroundKind.PHOTO, photo="x", blur=0, dim=1), (300, 300), loader=_stripes
    )
    assert sharp.size == (300, 300)
    assert np.asarray(sharp).std() > 100  # crisp stripes
    assert np.asarray(blurred).std() < 0.3 * np.asarray(sharp).std()
    assert dark.getextrema() == ((0, 0), (0, 0), (0, 0))


def test_photo_background_blur_scales_with_unit() -> None:
    bg = Background(BackgroundKind.PHOTO, photo="x", blur=10, dim=0)
    small = render_background(bg, (150, 150), unit=1.0, loader=_stripes)
    large = render_background(bg, (600, 600), unit=4.0, loader=_stripes)
    assert ssim(small, large.resize(small.size, Image.Resampling.LANCZOS)) > 0.9


def test_photo_background_real_file(sample_photos: list[Path]) -> None:
    """The sample photo's black corner marker is crisp without blur and smeared with it."""

    def corner(blur: float) -> int:
        bg = Background(BackgroundKind.PHOTO, photo=str(sample_photos[0]), blur=blur, dim=0)
        image = render_background(bg, (240, 160), loader=load_image)
        assert image.size == (240, 160)
        return int(image.convert("L").getpixel((3, 3)))  # type: ignore[arg-type]

    sharp, blurred = corner(0), corner(10)
    assert sharp < 30
    assert blurred > sharp + 25


@pytest.mark.parametrize(
    ("background", "loader", "message"),
    [
        (Background(BackgroundKind.PHOTO), _stripes, "no photo chosen"),
        (Background(BackgroundKind.PHOTO, photo="x"), None, "need a photo loader"),
        (Background(BackgroundKind.PHOTO, photo="x", dim=2), _stripes, "dim must be between"),
    ],
)
def test_photo_background_errors(background: Background, loader: object, message: str) -> None:
    with pytest.raises(RenderError, match=message):
        render_background(background, (10, 10), loader=loader)  # type: ignore[arg-type]
