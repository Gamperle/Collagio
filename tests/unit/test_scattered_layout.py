"""Tests for the scattered (rotated, overlapping) layout."""

from __future__ import annotations

import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely import Polygon
from shapely.ops import unary_union

from collagio.core.model import Rect
from collagio.errors import LayoutError
from collagio.layout import scattered
from collagio.layout.scattered import (
    Placement,
    ScatterSettings,
    rotated_corners,
    rotated_extent,
    scattered_layout,
    visibility,
)

MIXED = [1.5, 0.67, 1.0, 1.33, 0.75, 1.78, 0.56, 1.5, 0.67, 1.2]


def reference_visibility(placements: list[Placement]) -> list[float]:
    """Independent computation: one growing union, from the top of the stack down."""
    result = [0.0] * len(placements)
    covered = Polygon()
    for index in sorted(range(len(placements)), key=lambda i: -placements[i].z):
        polygon = Polygon(rotated_corners(placements[index].rect, placements[index].rotation))
        result[index] = polygon.difference(covered).area / polygon.area
        covered = unary_union([covered, polygon])
    return result


def total_photo_area(placements: list[Placement]) -> float:
    return sum(p.rect.area for p in placements)


# --- geometry helpers ----------------------------------------------------------------------------


def test_rotated_corners_without_rotation() -> None:
    assert rotated_corners(Rect(10, 20, 40, 20), 0) == [(10, 20), (50, 20), (50, 40), (10, 40)]


def test_rotation_is_counter_clockwise_on_screen() -> None:
    corners = rotated_corners(Rect(-1, -1, 2, 2), 90)
    # The top-left corner moves to the bottom-left (screen y points down).
    assert corners[0] == pytest.approx((-1, 1))
    assert corners[1] == pytest.approx((-1, -1))


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [(0, (40, 20)), (90, (20, 40)), (-90, (20, 40)), (180, (40, 20)),
     (45, (60 / math.sqrt(2), 60 / math.sqrt(2)))],
)  # fmt: skip
def test_rotated_extent(rotation: float, expected: tuple[float, float]) -> None:
    assert rotated_extent(40, 20, rotation) == pytest.approx(expected)


def test_visibility_respects_stacking() -> None:
    below = Placement(Rect(0, 0, 10, 10), 0, z=0)
    above = Placement(Rect(5, 0, 10, 10), 0, z=1)
    apart = Placement(Rect(100, 100, 10, 10), 0, z=2)
    assert visibility([below, above, apart]) == pytest.approx([0.5, 1.0, 1.0])
    assert visibility([Placement(below.rect, 0, 1), Placement(above.rect, 0, 0)]) == (
        pytest.approx([1.0, 0.5])
    )


def test_visibility_with_full_cover() -> None:
    small = Placement(Rect(2, 2, 4, 4), 0, z=0)
    large = Placement(Rect(0, 0, 10, 10), 0, z=1)
    assert visibility([small, large]) == pytest.approx([0.0, 1.0])


# --- properties ----------------------------------------------------------------------------------


@settings(deadline=None, max_examples=60)
@given(
    aspects=st.lists(st.floats(0.4, 2.5), min_size=2, max_size=100),
    width=st.integers(800, 4000),
    height=st.integers(800, 4000),
    margin=st.floats(0, 60),
    max_rotation=st.floats(0, 45),
    overlap=st.floats(0, 1),
    variation=st.floats(0, 1),
    min_visible=st.floats(0, 0.9),
    seed=st.integers(0, 2**32),
)
def test_layout_properties(
    aspects: list[float],
    width: int,
    height: int,
    margin: float,
    max_rotation: float,
    overlap: float,
    variation: float,
    min_visible: float,
    seed: int,
) -> None:
    s = ScatterSettings(
        margin=margin,
        max_rotation=max_rotation,
        overlap=overlap,
        size_variation=variation,
        min_visible=min_visible,
    )
    placements = scattered_layout(aspects, width, height, s, random.Random(seed))
    tol = 1e-6 * max(width, height)

    assert len(placements) == len(aspects)
    # Stacking order is a permutation.
    assert sorted(p.z for p in placements) == list(range(len(aspects)))
    for placement, aspect in zip(placements, aspects, strict=True):
        # Rotation within limits, photo keeps its aspect ratio.
        assert abs(placement.rotation) <= max_rotation + 1e-9
        assert placement.rect.aspect == pytest.approx(aspect, rel=1e-9)
        # The rotated photo lies completely inside the canvas minus margins.
        for x, y in rotated_corners(placement.rect, placement.rotation):
            assert margin - tol <= x <= width - margin + tol
            assert margin - tol <= y <= height - margin + tol
    # Every photo is visible enough (checked with an independent computation).
    assert min(reference_visibility(placements)) >= min_visible - 1e-9


@settings(deadline=None, max_examples=25)
@given(aspects=st.lists(st.floats(0.4, 2.5), min_size=2, max_size=40), seed=st.integers(0, 2**32))
def test_same_seed_same_layout(aspects: list[float], seed: int) -> None:
    s = ScatterSettings(margin=20)
    assert scattered_layout(aspects, 2480, 3508, s, random.Random(seed)) == scattered_layout(
        aspects, 2480, 3508, s, random.Random(seed)
    )


def test_different_seeds_give_different_layouts() -> None:
    layouts = {
        tuple(
            p.rect.x
            for p in scattered_layout(MIXED, 2480, 3508, ScatterSettings(), random.Random(seed))
        )
        for seed in range(5)
    }
    assert len(layouts) == 5


# --- settings ------------------------------------------------------------------------------------


def test_zero_rotation() -> None:
    s = ScatterSettings(max_rotation=0)
    assert all(p.rotation == 0 for p in scattered_layout(MIXED, 2000, 1500, s, random.Random(1)))


def test_rotations_use_the_range() -> None:
    s = ScatterSettings(max_rotation=20)
    rotations = [
        p.rotation for seed in range(5)
        for p in scattered_layout(MIXED, 2000, 1500, s, random.Random(seed))
    ]  # fmt: skip
    assert min(rotations) < -10
    assert max(rotations) > 10


def test_more_overlap_means_larger_photos() -> None:
    def area(overlap: float) -> float:
        s = ScatterSettings(overlap=overlap, min_visible=0.3)
        return sum(
            total_photo_area(scattered_layout(MIXED, 2000, 1500, s, random.Random(seed)))
            for seed in range(5)
        )

    assert area(0.0) < area(0.5) < area(1.0)


def test_no_overlap_setting_keeps_photos_mostly_apart() -> None:
    s = ScatterSettings(overlap=0.0, min_visible=0.0)
    for seed in range(5):
        shares = visibility(scattered_layout(MIXED, 2000, 1500, s, random.Random(seed)))
        assert sum(shares) / len(shares) > 0.9


def test_zero_variation_gives_equal_areas() -> None:
    s = ScatterSettings(size_variation=0.0, min_visible=0.0)
    areas = [p.rect.area for p in scattered_layout(MIXED, 2000, 1500, s, random.Random(2))]
    assert max(areas) / min(areas) == pytest.approx(1.0)


def test_variation_gives_mixed_sizes() -> None:
    s = ScatterSettings(size_variation=1.0, min_visible=0.0)
    areas = [p.rect.area for p in scattered_layout(MIXED, 2000, 1500, s, random.Random(2))]
    assert max(areas) / min(areas) > 1.5


def test_photos_are_spread_over_the_canvas() -> None:
    """Every quarter of the canvas contains photo centres (no clumping)."""
    placements = scattered_layout([1.5] * 20, 2000, 2000, ScatterSettings(), random.Random(4))
    quadrants = {
        (p.rect.x + p.rect.width / 2 > 1000, p.rect.y + p.rect.height / 2 > 1000)
        for p in placements
    }
    assert len(quadrants) == 4


def test_huge_photo_is_scaled_to_fit() -> None:
    """Extreme aspect ratios still fit inside the canvas when rotated."""
    s = ScatterSettings(overlap=1.0, max_rotation=45, min_visible=0.0)
    for placement in scattered_layout([20.0, 0.05], 1000, 1000, s, random.Random(0)):
        for x, y in rotated_corners(placement.rect, placement.rotation):
            assert -1e-6 <= x <= 1000 + 1e-6
            assert -1e-6 <= y <= 1000 + 1e-6


# --- fallback ------------------------------------------------------------------------------------


def test_fallback_grid_has_no_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scattered, "_ATTEMPTS", 0)
    s = ScatterSettings(margin=30, max_rotation=30, min_visible=1.0)
    for count in (2, 7, 30, 100):
        placements = scattered_layout(([1.5, 0.67] * 50)[:count], 2480, 3508, s, random.Random(3))
        assert len(placements) == count
        assert min(reference_visibility(placements)) == pytest.approx(1.0)
        for p in placements:
            for x, y in rotated_corners(p.rect, p.rotation):
                assert 30 - 1e-6 <= x <= 2450 + 1e-6
                assert 30 - 1e-6 <= y <= 3478 + 1e-6


def test_unreachable_visibility_falls_back_to_grid() -> None:
    """Full visibility with heavy overlap is impossible for random placement."""
    s = ScatterSettings(overlap=1.0, min_visible=1.0)
    placements = scattered_layout([1.5] * 30, 2000, 1500, s, random.Random(0))
    assert min(reference_visibility(placements)) == pytest.approx(1.0)


# --- errors --------------------------------------------------------------------------------------


def test_empty_input() -> None:
    assert scattered_layout([], 100, 100, ScatterSettings(), random.Random(0)) == []


def test_invalid_aspects() -> None:
    with pytest.raises(LayoutError, match="aspect"):
        scattered_layout([1.0, -1.0], 100, 100, ScatterSettings(), random.Random(0))


def test_margin_too_large() -> None:
    with pytest.raises(LayoutError, match="margin"):
        scattered_layout([1.0, 1.0], 100, 100, ScatterSettings(margin=60), random.Random(0))
