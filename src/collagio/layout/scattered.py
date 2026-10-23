"""Scattered layout: rotated, overlapping photos.

Each photo gets a seeded rotation, a size from its share of the total photo
area (`overlap` controls how much area is handed out relative to the canvas)
and a position chosen by best-candidate sampling: of several random centres,
the one farthest from the photos already placed wins. A short relaxation then
pushes crowded photos apart, which spreads them evenly without looking like a
grid. Stacking order is shuffled.

Every photo must stay at least `min_visible` visible. Visibility is computed
exactly with polygon geometry; if no candidate layout satisfies it, photos are
shrunk and placed again. As a last resort they go on a jittered grid with no
overlap at all, so the guarantee always holds.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from random import Random

import numpy as np
from shapely import Polygon, STRtree
from shapely.ops import unary_union

from collagio.core.model import Rect
from collagio.layout.common import content_rect, geometric_mean, validate_aspects

_CENTRE_CANDIDATES = 12  # random centres tried per photo
_ATTEMPTS = 6  # shrink steps before falling back to the jittered grid
_SHRINK = 0.8  # area factor per shrink step
_GRID_FILL = 0.9  # share of a fallback grid cell a rotated photo may use
_RELAX_STEPS = 40  # repulsion iterations after the initial placement
_RESTACK_ROUNDS = 8  # rounds of lifting covered photos to the top
# Total photo area relative to the canvas for overlap 0 and 1. With half of
# every photo visible, about 1.5x the canvas area is the realistic maximum.
_COVERAGE_MIN, _COVERAGE_MAX = 0.6, 1.5


@dataclass(frozen=True)
class ScatterSettings:
    margin: float = 0.0  # pixels
    max_rotation: float = 12.0  # degrees, photos get a rotation in [-max, +max]
    overlap: float = 0.5  # 0 = photos barely touch, 1 = heavy overlap
    size_variation: float = 0.5
    min_visible: float = 0.5  # share of each photo that must stay uncovered
    candidates: int = 4  # layouts tried per shrink step


# Tile aspect ratio for photo `index` when its tile has `area` square pixels.
TileAspect = Callable[[int, float], float]


@dataclass(frozen=True)
class Placement:
    rect: Rect  # unrotated frame; the photo is rotated about its centre
    rotation: float  # degrees, counter-clockwise
    z: int


def rotated_corners(rect: Rect, rotation: float) -> list[tuple[float, float]]:
    """Corners of `rect` rotated counter-clockwise (as seen on screen) about its centre."""
    cx, cy = rect.x + rect.width / 2, rect.y + rect.height / 2
    cos, sin = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    corners = []
    for dx, dy in (
        (-rect.width / 2, -rect.height / 2),
        (rect.width / 2, -rect.height / 2),
        (rect.width / 2, rect.height / 2),
        (-rect.width / 2, rect.height / 2),
    ):
        # Screen y points down, so a counter-clockwise turn subtracts the sine term from y.
        corners.append((cx + dx * cos + dy * sin, cy - dx * sin + dy * cos))
    return corners


def rotated_extent(width: float, height: float, rotation: float) -> tuple[float, float]:
    """Width and height of the axis-aligned bounding box of a rotated rectangle."""
    cos, sin = abs(math.cos(math.radians(rotation))), abs(math.sin(math.radians(rotation)))
    return width * cos + height * sin, width * sin + height * cos


def visibility(placements: Sequence[Placement]) -> list[float]:
    """Uncovered share of each photo, taking stacking order into account."""
    polygons = [Polygon(rotated_corners(p.rect, p.rotation)) for p in placements]
    tree = STRtree(polygons)
    result = []
    for index, polygon in enumerate(polygons):
        above = [
            polygons[other]
            for other in tree.query(polygon, predicate="intersects")
            if placements[other].z > placements[index].z
        ]
        if not above:
            result.append(1.0)
            continue
        result.append(polygon.difference(unary_union(above)).area / polygon.area)
    return result


def _scatter(
    aspects: Sequence[float],
    weights: Sequence[float],
    rotations: Sequence[float],
    z_order: Sequence[int],
    content: Rect,
    coverage: float,
    rng: Random,
    tile_aspect: TileAspect | None,
) -> list[Placement]:
    total_area = content.area * coverage
    weight_sum = sum(weights)
    sizes: list[tuple[float, float]] = []
    for index, (aspect, weight, rotation) in enumerate(
        zip(aspects, weights, rotations, strict=True)
    ):
        area = total_area * weight / weight_sum
        if tile_aspect is not None:
            aspect = tile_aspect(index, area)
        width, height = math.sqrt(area * aspect), math.sqrt(area / aspect)
        extent_w, extent_h = rotated_extent(width, height, rotation)
        fit = min(1.0, content.width / extent_w, content.height / extent_h)
        sizes.append((width * fit, height * fit))

    radii = [math.sqrt(w * h) / 2 for w, h in sizes]
    centres: list[tuple[float, float]] = [(0.0, 0.0)] * len(aspects)
    placed: list[int] = []
    for index in sorted(range(len(aspects)), key=lambda i: -radii[i]):
        extent_w, extent_h = rotated_extent(*sizes[index], rotations[index])
        x_low, x_high = content.x + extent_w / 2, content.right - extent_w / 2
        y_low, y_high = content.y + extent_h / 2, content.bottom - extent_h / 2
        best, best_score = (0.0, 0.0), -math.inf
        for _ in range(_CENTRE_CANDIDATES if placed else 1):
            candidate = (
                rng.uniform(x_low, max(x_low, x_high)),
                rng.uniform(y_low, max(y_low, y_high)),
            )
            score = min(
                (
                    math.dist(candidate, centres[other]) / (radii[index] + radii[other])
                    for other in placed
                ),
                default=0.0,
            )
            if score > best_score:
                best, best_score = candidate, score
        centres[index] = best
        placed.append(index)

    bounds = []
    for (w, h), rotation in zip(sizes, rotations, strict=True):
        extent_w, extent_h = rotated_extent(w, h, rotation)
        bounds.append(
            (
                content.x + extent_w / 2,
                content.y + extent_h / 2,
                max(content.x + extent_w / 2, content.right - extent_w / 2),
                max(content.y + extent_h / 2, content.bottom - extent_h / 2),
            )
        )
    centres = _relax(centres, radii, bounds)

    return [
        Placement(Rect(cx - w / 2, cy - h / 2, w, h), rotation, z)
        for (cx, cy), (w, h), rotation, z in zip(centres, sizes, rotations, z_order, strict=True)
    ]


def _restack(placements: list[Placement], min_visible: float) -> list[Placement]:
    """Lift photos that are covered too much to the top of the stack.

    All such photos are lifted together, the worst one highest. Lifting can
    cover other photos, so this repeats a few rounds and may not fully succeed.
    """
    for _ in range(_RESTACK_ROUNDS):
        shares = visibility(placements)
        covered = [i for i, share in enumerate(shares) if share < min_visible]
        if not covered:
            break
        top = max(p.z for p in placements)
        for rank, index in enumerate(sorted(covered, key=lambda i: -shares[i]), start=1):
            placements[index] = Placement(
                placements[index].rect, placements[index].rotation, top + rank
            )
    ranks = sorted(range(len(placements)), key=lambda i: placements[i].z)
    for z, index in enumerate(ranks):
        placements[index] = Placement(placements[index].rect, placements[index].rotation, z)
    return placements


def _relax(
    centres: Sequence[tuple[float, float]],
    radii: Sequence[float],
    bounds: Sequence[tuple[float, float, float, float]],
) -> list[tuple[float, float]]:
    """Push apart photos whose circles (of `radii`) overlap, staying within `bounds`.

    `bounds` holds (x_min, y_min, x_max, y_max) per centre. When the photos
    cannot all fit without overlap, the pushes balance out into an even spread.
    """
    position = np.array(centres, dtype=np.float64)
    radius = np.array(radii, dtype=np.float64)
    limits = np.array(bounds, dtype=np.float64)
    wanted = radius[:, None] + radius[None, :]
    for _ in range(_RELAX_STEPS):
        delta = position[:, None, :] - position[None, :, :]
        distance = np.hypot(delta[..., 0], delta[..., 1])
        np.fill_diagonal(distance, np.inf)
        push = np.clip(wanted - distance, 0.0, None) / 2
        if not push.any():
            break
        direction = delta / np.where(distance > 0, distance, np.inf)[..., None]
        position += 0.5 * (direction * push[..., None]).sum(axis=1)
        position = np.clip(position, limits[:, :2], limits[:, 2:])
    return [(float(x), float(y)) for x, y in position]


def _jittered_grid(
    aspects: Sequence[float],
    rotations: Sequence[float],
    z_order: Sequence[int],
    content: Rect,
    rng: Random,
) -> list[Placement]:
    """No-overlap fallback: one photo per grid cell, rotated and slightly offset."""
    count = len(aspects)
    target = geometric_mean(aspects)

    def mismatch(cols: int) -> float:
        rows = math.ceil(count / cols)
        return abs(math.log((content.width / cols) / (content.height / rows) / target))

    cols = min(range(1, count + 1), key=mismatch)
    rows = math.ceil(count / cols)
    cell_w, cell_h = content.width / cols, content.height / rows
    cells = list(range(rows * cols))
    rng.shuffle(cells)

    placements = []
    for aspect, rotation, z, cell in zip(aspects, rotations, z_order, cells, strict=False):
        extent_w, extent_h = rotated_extent(aspect, 1.0, rotation)
        scale = _GRID_FILL * min(cell_w / extent_w, cell_h / extent_h)
        width, height = aspect * scale, scale
        slack_x = (cell_w - extent_w * scale) / 2
        slack_y = (cell_h - extent_h * scale) / 2
        row, col = divmod(cell, cols)
        cx = content.x + (col + 0.5) * cell_w + rng.uniform(-slack_x, slack_x)
        cy = content.y + (row + 0.5) * cell_h + rng.uniform(-slack_y, slack_y)
        placements.append(
            Placement(Rect(cx - width / 2, cy - height / 2, width, height), rotation, z)
        )
    return placements


def scattered_layout(
    aspects: Sequence[float],
    width: float,
    height: float,
    settings: ScatterSettings,
    rng: Random,
    tile_aspect: TileAspect | None = None,
) -> list[Placement]:
    """One rotated placement per photo (in input order) inside the canvas minus margins.

    `aspects` are the tiles' aspect ratios. If `tile_aspect` is given, it refines
    them once a tile's size is known (frames whose borders do not scale).
    """
    if not aspects:
        return []
    validate_aspects(aspects)
    content = content_rect(width, height, settings.margin)

    count = len(aspects)
    rotations = [rng.uniform(-settings.max_rotation, settings.max_rotation) for _ in aspects]
    variation = settings.size_variation
    weights = [rng.uniform(1 - 0.5 * variation, 1 + variation) for _ in aspects]
    z_order = list(range(count))
    rng.shuffle(z_order)

    coverage = _COVERAGE_MIN + (_COVERAGE_MAX - _COVERAGE_MIN) * settings.overlap
    for _ in range(_ATTEMPTS):
        for _ in range(max(1, settings.candidates)):
            placements = _scatter(
                aspects, weights, rotations, z_order, content, coverage, rng, tile_aspect
            )
            placements = _restack(placements, settings.min_visible)
            if min(visibility(placements)) >= settings.min_visible:
                return placements
        coverage *= _SHRINK
    return _jittered_grid(aspects, rotations, z_order, content, rng)
