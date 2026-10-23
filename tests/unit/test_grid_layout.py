"""Property-based tests for the mixed-size grid layout."""

from __future__ import annotations

import itertools
import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from collagio.core.model import PlacementOrder, Rect
from collagio.errors import LayoutError
from collagio.layout.grid import GridSettings, grid_layout

aspect_lists = st.lists(st.floats(0.4, 2.5), min_size=2, max_size=100)


def _check_tiling(rects: list[Rect], width: float, height: float, s: GridSettings) -> None:
    content = Rect(s.margin, s.margin, width - 2 * s.margin, height - 2 * s.margin)
    tol = 1e-6 * max(width, height)

    # Every cell lies inside the content area.
    for r in rects:
        assert r.width > 0 and r.height > 0
        assert r.x >= content.x - tol and r.y >= content.y - tol
        assert r.right <= content.right + tol and r.bottom <= content.bottom + tol

    # Cells grown by half a gap neither overlap ...
    grown = [r.inflate(s.gap / 2) for r in rects]
    for a, b in itertools.combinations(grown, 2):
        assert not a.overlaps(b, tolerance=tol)

    # ... nor leave holes: together they exactly cover the grown content area.
    covered = sum(g.area for g in grown)
    assert covered == pytest.approx(content.inflate(s.gap / 2).area, rel=1e-9)


@settings(deadline=None, max_examples=150)
@given(
    aspects=aspect_lists,
    width=st.integers(800, 4000),
    height=st.integers(800, 4000),
    gap=st.floats(0, 8),
    margin=st.floats(0, 50),
    variation=st.floats(0, 1),
    order=st.sampled_from(PlacementOrder),
    seed=st.integers(0, 2**32),
)
def test_layout_is_an_exact_tiling(
    aspects: list[float],
    width: int,
    height: int,
    gap: float,
    margin: float,
    variation: float,
    order: PlacementOrder,
    seed: int,
) -> None:
    s = GridSettings(gap=gap, margin=margin, size_variation=variation, order=order)
    rects = grid_layout(aspects, width, height, s, random.Random(seed))
    assert len(rects) == len(aspects)
    _check_tiling(rects, width, height, s)


@settings(deadline=None, max_examples=50)
@given(aspects=aspect_lists, seed=st.integers(0, 2**32))
def test_same_seed_same_layout(aspects: list[float], seed: int) -> None:
    s = GridSettings(gap=6, margin=10)
    first = grid_layout(aspects, 2480, 3508, s, random.Random(seed))
    second = grid_layout(aspects, 2480, 3508, s, random.Random(seed))
    assert first == second


@pytest.mark.parametrize("count", [4, 7, 20, 100])
def test_different_seeds_give_different_layouts(count: int) -> None:
    aspects = [1.5, 0.67, 1.0, 1.33] * (count // 4) + [1.5] * (count % 4)
    s = GridSettings(gap=6, margin=10)
    layouts = set()
    for seed in range(5):
        rects = grid_layout(aspects, 2480, 3508, s, random.Random(seed))
        layouts.add(tuple((round(r.x), round(r.y)) for r in rects))
    assert len(layouts) > 1


def test_zero_variation_gives_similar_cell_areas() -> None:
    aspects = [1.5] * 16
    rects = grid_layout(aspects, 3000, 2000, GridSettings(size_variation=0), random.Random(1))
    areas = [r.area for r in rects]
    assert max(areas) / min(areas) == pytest.approx(1.0, rel=1e-6)


def test_variation_gives_mixed_cell_sizes() -> None:
    aspects = [1.5] * 16
    rects = grid_layout(aspects, 3000, 2000, GridSettings(size_variation=1), random.Random(1))
    areas = [r.area for r in rects]
    assert max(areas) / min(areas) > 1.5


def test_cells_follow_photo_orientation() -> None:
    """Portrait photos should mostly get portrait cells and vice versa."""
    aspects = [1.5, 0.67] * 6
    rects = grid_layout(aspects, 3000, 2000, GridSettings(gap=10), random.Random(3))
    matches = sum((r.aspect > 1) == (a > 1) for r, a in zip(rects, aspects, strict=True))
    assert matches >= 10


def test_cropping_is_limited_for_typical_photos() -> None:
    aspects = [1.5, 0.67, 1.33, 1.0, 1.5, 1.5, 0.75]
    rects = grid_layout(aspects, 2480, 3508, GridSettings(gap=20, margin=40), random.Random(0))
    for rect, aspect in zip(rects, aspects, strict=True):
        # At most a factor of 2 between cell and photo shape.
        assert abs(math.log(rect.aspect / aspect)) < math.log(2)


def test_no_slivers_with_many_photos() -> None:
    rects = grid_layout([1.5] * 100, 2480, 3508, GridSettings(gap=8), random.Random(5))
    average_side = math.sqrt(2480 * 3508 / 100)
    assert min(min(r.width, r.height) for r in rects) > 0.25 * average_side


def test_single_photo_fills_content_area() -> None:
    (rect,) = grid_layout([1.5], 300, 200, GridSettings(margin=10), random.Random(0))
    assert rect == Rect(10, 10, 280, 180)


def test_empty_input() -> None:
    assert grid_layout([], 100, 100, GridSettings(), random.Random(0)) == []


@pytest.mark.parametrize("aspects", [[1.0, 0.0], [1.0, -2.0], [math.inf, 1.0], [math.nan, 1.0]])
def test_invalid_aspects(aspects: list[float]) -> None:
    with pytest.raises(LayoutError, match="aspect"):
        grid_layout(aspects, 100, 100, GridSettings(), random.Random(0))


def test_margin_too_large() -> None:
    with pytest.raises(LayoutError, match="margin"):
        grid_layout([1.0, 1.0], 100, 100, GridSettings(margin=50), random.Random(0))


def test_gap_too_large() -> None:
    with pytest.raises(LayoutError, match="cannot fit 100 photos"):
        grid_layout([1.0] * 100, 200, 200, GridSettings(gap=30), random.Random(0))


MIXED = [1.5, 0.67, 1.0, 1.33, 0.75, 1.78, 0.56, 1.5, 0.67, 1.2]


def _assignment(order: PlacementOrder, seed: int) -> tuple[tuple[int, int], ...]:
    s = GridSettings(gap=6, margin=10, order=order)
    rects = grid_layout(MIXED, 2480, 3508, s, random.Random(seed))
    return tuple((round(r.x), round(r.y)) for r in rects)


def test_input_order_reads_from_top_left() -> None:
    s = GridSettings(gap=6, margin=10, order=PlacementOrder.INPUT)
    for seed in range(10):
        rects = grid_layout(MIXED, 2480, 3508, s, random.Random(seed))
        assert (rects[0].x, rects[0].y) == (10, 10)
        # The last photo ends at the bottom-right corner.
        assert rects[-1].right == pytest.approx(2470)
        assert rects[-1].bottom == pytest.approx(3498)


def test_random_order_places_photos_differently_per_seed() -> None:
    """Even with the same cell structure, random order moves the first photo around."""
    first_positions = {_assignment(PlacementOrder.RANDOM, seed)[0] for seed in range(10)}
    assert len(first_positions) > 3


def test_shape_order_crops_least() -> None:
    def crop_loss(order: PlacementOrder) -> float:
        s = GridSettings(gap=6, margin=10, order=order)
        total = 0.0
        for seed in range(10):
            rects = grid_layout(MIXED, 2480, 3508, s, random.Random(seed))
            total += sum(abs(math.log(r.aspect / a)) for r, a in zip(rects, MIXED, strict=True))
        return total

    assert crop_loss(PlacementOrder.SHAPE) < crop_loss(PlacementOrder.RANDOM)
    assert crop_loss(PlacementOrder.SHAPE) < crop_loss(PlacementOrder.INPUT)


def test_shape_order_is_the_default() -> None:
    assert GridSettings().order is PlacementOrder.SHAPE
