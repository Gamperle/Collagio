from __future__ import annotations

import pytest

from collagio.core.model import Background, BackgroundKind
from collagio.errors import RenderError
from collagio.render.background import parse_color, render_background


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
