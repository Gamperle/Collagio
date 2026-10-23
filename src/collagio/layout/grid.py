"""Grid layout with mixed cell sizes.

The content area is split recursively in two (a guillotine partition), so the
result always has exactly one cell per photo, no holes and the same gap between
all neighbours. Each photo gets a random weight; a split divides the area in
proportion to the weights on each side, which yields the mix of large and small
cells. Several seeded candidates are generated and the one whose cell aspect
ratios best match the photos (least cropping, no slivers) wins.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import accumulate
from random import Random

from collagio.core.model import PlacementOrder, Rect
from collagio.errors import LayoutError
from collagio.layout.common import content_rect, geometric_mean, validate_aspects

# Extra weight drawn per photo, scaled by size_variation: most photos stay
# small, some get double or quadruple area.
_WEIGHT_CHOICES = (0.0, 0.0, 0.0, 1.0, 3.0)
# A split is chosen among positions that put 30-70 % of the weight on one side.
_BALANCE = (0.3, 0.7)
# Cells whose short side is below this fraction of an average cell are penalised.
_MIN_SIDE_FRACTION = 0.35


@dataclass(frozen=True)
class GridSettings:
    gap: float = 0.0  # pixels
    margin: float = 0.0  # pixels
    extra_top: float = 0.0  # pixels, kept free above the photos (e.g. for a title)
    extra_bottom: float = 0.0  # pixels, kept free below the photos
    size_variation: float = 0.5
    order: PlacementOrder = PlacementOrder.SHAPE
    candidates: int = 16


def _region_cost(rect: Rect, photo_count: int, target_aspect: float) -> float:
    """How badly a region's shape fits `photo_count` photos of `target_aspect`.

    A single photo should match exactly; a region holding m photos can absorb up
    to a factor of m in aspect ratio by further splitting.
    """
    if rect.width <= 0 or rect.height <= 0:
        return math.inf
    mismatch = abs(math.log(rect.aspect / target_aspect))
    if photo_count == 1:
        return mismatch
    return max(0.0, mismatch - math.log(photo_count))


def _split_rect(rect: Rect, fraction: float, gap: float, vertical: bool) -> tuple[Rect, Rect]:
    if vertical:  # cut with a vertical line: children side by side
        available = rect.width - gap
        first_w = available * fraction
        return (
            Rect(rect.x, rect.y, first_w, rect.height),
            Rect(rect.x + first_w + gap, rect.y, available - first_w, rect.height),
        )
    available = rect.height - gap
    first_h = available * fraction
    return (
        Rect(rect.x, rect.y, rect.width, first_h),
        Rect(rect.x, rect.y + first_h + gap, rect.width, available - first_h),
    )


def _partition(
    rect: Rect, weights: Sequence[float], gap: float, target_aspect: float, rng: Random
) -> list[Rect]:
    count = len(weights)
    if count == 1:
        return [rect]
    total = sum(weights)
    fractions = [c / total for c in accumulate(weights[:-1])]
    balanced = [k for k, f in enumerate(fractions, start=1) if _BALANCE[0] <= f <= _BALANCE[1]]
    if not balanced:
        balanced = [min(range(1, count), key=lambda k: abs(fractions[k - 1] - 0.5))]
    k = rng.choice(balanced)
    fraction = fractions[k - 1]

    def cost(vertical: bool) -> float:
        first, second = _split_rect(rect, fraction, gap, vertical)
        return _region_cost(first, k, target_aspect) + _region_cost(
            second, count - k, target_aspect
        )

    vertical_cost, horizontal_cost = cost(True), cost(False)
    if math.isclose(vertical_cost, horizontal_cost):
        vertical = rng.random() < 0.5
    else:
        vertical = vertical_cost < horizontal_cost
    first, second = _split_rect(rect, fraction, gap, vertical)
    return _partition(first, weights[:k], gap, target_aspect, rng) + _partition(
        second, weights[k:], gap, target_aspect, rng
    )


def _assign(
    cells: Sequence[Rect], aspects: Sequence[float], order: PlacementOrder, rng: Random
) -> list[Rect]:
    """Decide which photo goes into which cell.

    SHAPE gives the widest cell to the widest photo, and so on (least cropping).
    INPUT fills cells in partition order, which reads from the top-left.
    RANDOM shuffles; candidate scoring still prefers shuffles that crop less.
    """
    if order is PlacementOrder.INPUT:
        return list(cells)
    if order is PlacementOrder.RANDOM:
        shuffled = list(cells)
        rng.shuffle(shuffled)
        return shuffled
    cell_order = sorted(range(len(cells)), key=lambda i: cells[i].aspect)
    photo_order = sorted(range(len(aspects)), key=lambda i: aspects[i])
    result: list[Rect] = [cells[0]] * len(cells)
    for cell_index, photo_index in zip(cell_order, photo_order, strict=True):
        result[photo_index] = cells[cell_index]
    return result


def _score(rects: Sequence[Rect], aspects: Sequence[float], content: Rect) -> float:
    crop_loss = (
        sum(abs(math.log(r.aspect / a)) * r.area for r, a in zip(rects, aspects, strict=True))
        / content.area
    )
    reference_side = math.sqrt(content.area / len(rects)) * _MIN_SIDE_FRACTION
    sliver_penalty = sum(max(0.0, 1.0 - min(r.width, r.height) / reference_side) for r in rects)
    return crop_loss + sliver_penalty


def grid_layout(
    aspects: Sequence[float],
    width: float,
    height: float,
    settings: GridSettings,
    rng: Random,
) -> list[Rect]:
    """One cell per photo (in input order) covering the canvas minus margins."""
    if not aspects:
        return []
    validate_aspects(aspects)
    content = content_rect(
        width, height, settings.margin, settings.extra_top, settings.extra_bottom
    )
    target_aspect = geometric_mean(aspects)
    best: list[Rect] | None = None
    best_score = math.inf
    for _ in range(max(1, settings.candidates)):
        weights = [1.0 + settings.size_variation * rng.choice(_WEIGHT_CHOICES) for _ in aspects]
        cells = _partition(content, weights, settings.gap, target_aspect, rng)
        if min(min(c.width, c.height) for c in cells) < 1.0:
            continue
        rects = _assign(cells, aspects, settings.order, rng)
        score = _score(rects, aspects, content)
        if score < best_score:
            best, best_score = rects, score
    if best is None:
        raise LayoutError(
            f"cannot fit {len(aspects)} photos with a {settings.gap:g} px gap "
            f"into {width:g}x{height:g} px"
        )
    return best
