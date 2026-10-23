from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from collagio.core.model import TextItem
from collagio.errors import RenderError
from collagio.render.text import load_font, render_text, text_size


def _text(**changes: object) -> TextItem:
    item = TextItem("t1", "Summer 2026", x=100, y=100, size=40)
    for key, value in changes.items():
        setattr(item, key, value)
    return item


def test_size_scales_with_unit() -> None:
    w1, h1 = text_size(_text(), 1.0)
    w2, h2 = text_size(_text(), 2.0)
    assert w2 == pytest.approx(2 * w1, rel=0.1)
    assert h2 == pytest.approx(2 * h1, rel=0.15)
    assert w1 > h1 > 20


def test_multiline_is_taller() -> None:
    assert text_size(_text(text="A\nB"), 1.0)[1] > 1.6 * text_size(_text(text="A"), 1.0)[1]


def test_render_draws_text_in_its_colour() -> None:
    tile = render_text(_text(color="#ff0000"), 1.0)
    width, height = text_size(_text(), 1.0)
    assert tile.width > width and tile.height > height  # with padding
    pixels = np.asarray(tile)
    opaque = pixels[pixels[..., 3] == 255][:, :3]
    assert len(opaque) > 0
    assert (opaque == (255, 0, 0)).all(axis=1).any()
    assert tile.getpixel((0, 0))[3] == 0  # type: ignore[index]


def test_rotation_expands() -> None:
    straight = render_text(_text(), 1.0)
    turned = render_text(_text(rotation=90), 1.0)
    assert turned.size == (straight.height, straight.width)


def test_empty_text() -> None:
    assert render_text(_text(text="   "), 1.0).size == (1, 1)


def test_invalid_colour() -> None:
    with pytest.raises(RenderError, match="invalid colour"):
        render_text(_text(color="nope"), 1.0)


def test_missing_font(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="cannot load font"):
        load_font(str(tmp_path / "missing.ttf"), 20)
    with pytest.raises(RenderError, match="cannot load font"):
        text_size(_text(font=str(tmp_path / "missing.ttf")), 1.0)


def test_builtin_font_minimum_size() -> None:
    assert load_font("", 0) is not None
