from __future__ import annotations

import pytest

from collagio.core.units import (
    Orientation,
    mm_to_px,
    orient,
    parse_size,
    px_to_mm,
)
from collagio.errors import SizeError


def test_a4_at_300_dpi() -> None:
    assert parse_size("A4", 300) == (2480, 3508)


def test_mm_px_round_trip() -> None:
    assert mm_to_px(25.4, 300) == 300
    assert px_to_mm(300, 300) == pytest.approx(25.4)


@pytest.mark.parametrize(
    ("spec", "dpi", "expected"),
    [
        ("a4", 300, (2480, 3508)),
        (" A3 ", 150, (1754, 2480)),
        ("10x15", 300, (1181, 1772)),  # paper preset wins over "10x15 px"
        ("fullhd", 72, (1920, 1080)),
        ("Instagram-Square", 300, (1080, 1080)),
        ("1920x1080", 300, (1920, 1080)),
        ("800 x 600 px", 300, (800, 600)),
        ("640×480", 300, (640, 480)),
        ("100x50mm", 254, (1000, 500)),
        ("100.5x50.4", 300, (100, 50)),
    ],
)
def test_parse_size(spec: str, dpi: int, expected: tuple[int, int]) -> None:
    assert parse_size(spec, dpi) == expected


def test_orientation_is_applied_to_presets() -> None:
    assert parse_size("A4", 300, Orientation.LANDSCAPE) == (3508, 2480)
    assert parse_size("fullhd", 300, Orientation.PORTRAIT) == (1080, 1920)
    assert parse_size("A4", 300, Orientation.PORTRAIT) == (2480, 3508)


@pytest.mark.parametrize(
    ("size", "orientation", "expected"),
    [
        ((10, 20), None, (10, 20)),
        ((10, 20), Orientation.LANDSCAPE, (20, 10)),
        ((20, 10), Orientation.PORTRAIT, (10, 20)),
        ((20, 10), Orientation.LANDSCAPE, (20, 10)),
        ((15, 15), Orientation.PORTRAIT, (15, 15)),
    ],
)
def test_orient(
    size: tuple[int, int], orientation: Orientation | None, expected: tuple[int, int]
) -> None:
    assert orient(size, orientation) == expected


@pytest.mark.parametrize("spec", ["", "A9", "big", "10x", "x10", "-5x10", "10x10cm"])
def test_invalid_specs_are_rejected(spec: str) -> None:
    with pytest.raises(SizeError, match="invalid size"):
        parse_size(spec, 300)


@pytest.mark.parametrize("spec", ["0x100", "100x0", "40000x100"])
def test_out_of_range_sizes_are_rejected(spec: str) -> None:
    with pytest.raises(SizeError, match="outside"):
        parse_size(spec, 300)


def test_non_positive_dpi_is_rejected() -> None:
    with pytest.raises(SizeError, match="DPI"):
        parse_size("A4", 0)
