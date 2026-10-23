from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from collagio.core.model import CropBox
from collagio.imaging.smartcrop import crop_pixels, fill_crop


def test_wider_source_is_cropped_at_the_sides() -> None:
    crop = fill_crop((600, 300), 1.0)
    assert crop == CropBox(pytest.approx(0.25), 0.0, pytest.approx(0.5), 1.0)


def test_taller_source_is_cropped_top_and_bottom() -> None:
    crop = fill_crop((300, 600), 1.0)
    assert crop == CropBox(0.0, pytest.approx(0.25), 1.0, pytest.approx(0.5))


def test_matching_aspect_keeps_everything() -> None:
    assert fill_crop((400, 300), 4 / 3) == CropBox(0.0, 0.0, 1.0, 1.0)


def test_focus_shifts_crop_and_is_clamped() -> None:
    assert fill_crop((600, 300), 1.0, focus=(0.4, 0.5)).x == pytest.approx(0.15)
    assert fill_crop((600, 300), 1.0, focus=(0.0, 0.5)).x == 0.0
    assert fill_crop((600, 300), 1.0, focus=(1.0, 0.5)).x == pytest.approx(0.5)


@given(
    width=st.integers(1, 10_000),
    height=st.integers(1, 10_000),
    aspect=st.floats(0.05, 20),
    fx=st.floats(0, 1),
    fy=st.floats(0, 1),
)
def test_crop_properties(width: int, height: int, aspect: float, fx: float, fy: float) -> None:
    crop = fill_crop((width, height), aspect, focus=(fx, fy))
    # Inside the image ...
    assert crop.x >= -1e-9 and crop.x + crop.width <= 1 + 1e-9
    assert crop.y >= -1e-9 and crop.y + crop.height <= 1 + 1e-9
    # ... has the requested aspect in pixels ...
    left, top, right, bottom = crop_pixels(crop, (width, height))
    assert (right - left) / (bottom - top) == pytest.approx(aspect, rel=1e-9)
    # ... and is as large as possible (touches both edges in one dimension).
    assert crop.width == 1.0 or crop.height == 1.0


def test_crop_pixels() -> None:
    assert crop_pixels(CropBox(0.25, 0.1, 0.5, 0.8), (400, 200)) == (100, 20, 300, 180)


@pytest.mark.parametrize(
    ("size", "aspect"), [((0, 10), 1.0), ((10, -1), 1.0), ((10, 10), 0.0), ((10, 10), -2.0)]
)
def test_invalid_input(size: tuple[int, int], aspect: float) -> None:
    with pytest.raises(ValueError, match=r"must be positive|invalid source size"):
        fill_crop(size, aspect)
