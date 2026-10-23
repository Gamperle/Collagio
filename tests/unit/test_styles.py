from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from collagio.errors import StyleError
from collagio.styles import StyleContext, available_styles, get_style
from collagio.styles.base import register
from collagio.styles.plain import PlainStyle
from tests.helpers.image_compare import ssim

ALL_STYLES = available_styles()


def _ctx(unit: float = 1.0, seed: int = 0) -> StyleContext:
    return StyleContext(unit=unit, seed=seed)


def _render(
    name: str, size: tuple[int, int], params: dict[str, Any], unit: float = 1.0, seed: int = 0
) -> Image.Image:
    style = get_style(name)
    resolved = style.resolve(params)
    _, _, w, h = style.content_box(size, resolved, _ctx(unit, seed))
    content = Image.new("RGB", (w, h), (200, 30, 40))
    return style.render(content, size, resolved, _ctx(unit, seed))


# --- registry -------------------------------------------------------------


def test_plain_is_registered() -> None:
    assert "plain" in ALL_STYLES
    assert isinstance(get_style("plain"), PlainStyle)


def test_unknown_style() -> None:
    with pytest.raises(StyleError, match=r"unknown style 'nope'; available: .*plain"):
        get_style("nope")


def test_duplicate_registration_is_rejected() -> None:
    with pytest.raises(StyleError, match="already registered"):
        register(PlainStyle)


# --- contract every style must fulfil (new styles are covered automatically) ---


@pytest.mark.parametrize("name", ALL_STYLES)
def test_style_has_labels_in_both_languages(name: str) -> None:
    labels = get_style(name).labels
    assert labels.get("en") and labels.get("de")


@pytest.mark.parametrize("name", ALL_STYLES)
@pytest.mark.parametrize("size", [(1, 1), (2, 7), (300, 200), (200, 300)])
def test_style_output_contract(name: str, size: tuple[int, int]) -> None:
    style = get_style(name)
    params = style.resolve({})
    x, y, w, h = style.content_box(size, params, _ctx(5.0))
    assert w >= 1 and h >= 1
    assert x >= 0 and x + w <= size[0] and y >= 0 and y + h <= size[1]
    tile = style.render(Image.new("RGB", (w, h), "red"), size, params, _ctx(5.0))
    assert tile.mode == "RGBA"
    assert tile.size == size


@pytest.mark.parametrize("name", ALL_STYLES)
def test_style_is_deterministic(name: str) -> None:
    a = _render(name, (240, 160), {}, unit=2.0, seed=9)
    b = _render(name, (240, 160), {}, unit=2.0, seed=9)
    assert a.tobytes() == b.tobytes()


@pytest.mark.parametrize("name", ALL_STYLES)
def test_style_is_scale_invariant(name: str) -> None:
    """A 4x render downsampled must look like the 1x render (details scale with `unit`)."""
    small = _render(name, (150, 100), {}, unit=1.0)
    large = _render(name, (600, 400), {}, unit=4.0)
    downsampled = large.resize(small.size, Image.Resampling.LANCZOS)
    background = Image.new("RGBA", small.size, "white")
    assert (
        ssim(
            Image.alpha_composite(background, small), Image.alpha_composite(background, downsampled)
        )
        >= 0.95
    )


@pytest.mark.slow
@pytest.mark.parametrize("name", ALL_STYLES)
def test_style_handles_large_tiles(name: str) -> None:
    assert _render(name, (6000, 4000), {}, unit=4.0).size == (6000, 4000)


# --- parameter validation ----------------------------------------------------


def test_resolve_fills_defaults() -> None:
    assert get_style("plain").resolve({"border_width": 4}) == {
        "border_width": 4,
        "border_color": "#ffffff",
        "corner_radius": 0.0,
    }


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"shadow": 1}, "unknown parameter"),
        ({"border_width": -1}, "must not be negative"),
        ({"border_width": "wide"}, "must be a number"),
        ({"border_width": True}, "must be a number"),
        ({"border_color": "not-a-colour"}, "invalid colour"),
        ({"border_color": 123}, "must be text"),
    ],
)
def test_resolve_rejects_invalid_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(StyleError, match=message):
        get_style("plain").resolve(params)


@pytest.mark.parametrize("color", ["#abc", "#aabbcc", "red", "rgb(1, 2, 3)"])
def test_resolve_accepts_colour_formats(color: str) -> None:
    assert get_style("plain").resolve({"border_color": color})["border_color"] == color


# --- plain style ------------------------------------------------------------------


def test_plain_without_border_is_just_the_photo() -> None:
    tile = _render("plain", (100, 60), {})
    assert tile.getpixel((0, 0)) == (200, 30, 40, 255)
    assert tile.getpixel((99, 59)) == (200, 30, 40, 255)


def test_plain_border_scales_with_unit() -> None:
    style = get_style("plain")
    params = style.resolve({"border_width": 5})
    assert style.content_box((100, 80), params, _ctx(1.0)) == (5, 5, 90, 70)
    assert style.content_box((100, 80), params, _ctx(2.0)) == (10, 10, 80, 60)


def test_plain_border_colour_and_content() -> None:
    tile = _render("plain", (100, 80), {"border_width": 10, "border_color": "#00ff00"})
    assert tile.getpixel((5, 40)) == (0, 255, 0, 255)
    assert tile.getpixel((95, 40)) == (0, 255, 0, 255)
    assert tile.getpixel((50, 40)) == (200, 30, 40, 255)
    assert tile.getpixel((10, 10)) == (200, 30, 40, 255)


def test_plain_border_is_clamped_for_tiny_tiles() -> None:
    style = get_style("plain")
    box = style.content_box((6, 4), style.resolve({"border_width": 50}), _ctx())
    assert box == (1, 1, 4, 2)


def test_plain_rounded_corners_are_transparent() -> None:
    tile = _render("plain", (100, 80), {"corner_radius": 20})
    assert tile.getpixel((0, 0))[3] == 0
    assert tile.getpixel((99, 79))[3] == 0
    assert tile.getpixel((50, 0))[3] == 255
    assert tile.getpixel((50, 40))[3] == 255


def test_plain_keeps_content_transparency() -> None:
    style = get_style("plain")
    params = style.resolve({"border_width": 4})
    content = Image.new("RGBA", (92, 72), (0, 0, 0, 0))
    tile = style.render(content, (100, 80), params, _ctx())
    assert tile.getpixel((50, 40))[3] == 0
    assert tile.getpixel((1, 1)) == (255, 255, 255, 255)
