"""Project data model.

Geometry is stored in canvas pixels at full export resolution. Layout spacing
(gap, margin) is stored as a fraction of the canvas short edge so it scales with
the canvas size and DPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1
MIN_PHOTOS = 2
MAX_PHOTOS = 100


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def area(self) -> float:
        return self.width * self.height

    def inflate(self, amount: float) -> Rect:
        """Grow by `amount` on every side (negative shrinks)."""
        return Rect(
            self.x - amount,
            self.y - amount,
            self.width + 2 * amount,
            self.height + 2 * amount,
        )

    def overlaps(self, other: Rect, tolerance: float = 1e-6) -> bool:
        """True if the interiors intersect by more than `tolerance`."""
        return (
            min(self.right, other.right) - max(self.x, other.x) > tolerance
            and min(self.bottom, other.bottom) - max(self.y, other.y) > tolerance
        )


@dataclass
class CropBox:
    """Visible part of the (EXIF-oriented) source photo, normalised to 0..1."""

    x: float
    y: float
    width: float
    height: float


class LayoutMode(StrEnum):
    GRID = "grid"


class PlacementOrder(StrEnum):
    """Which photo goes into which layout cell."""

    SHAPE = "shape"  # match photo and cell aspect ratios: least cropping
    RANDOM = "random"  # shuffled, depends on the seed
    INPUT = "input"  # photo order, starting top-left


class BackgroundKind(StrEnum):
    SOLID = "solid"
    GRADIENT = "gradient"


@dataclass
class Background:
    kind: BackgroundKind = BackgroundKind.SOLID
    color: str = "#ffffff"
    color2: str = "#d9d9d9"
    angle: float = 90.0  # gradient direction in degrees, 0 = left to right, 90 = top to bottom


@dataclass
class Canvas:
    width: int
    height: int
    dpi: int = 300
    background: Background = field(default_factory=Background)

    @property
    def short_edge(self) -> int:
        return min(self.width, self.height)


@dataclass
class StyleRef:
    name: str = "plain"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class LayoutSettings:
    mode: LayoutMode = LayoutMode.GRID
    gap: float = 0.01  # fraction of canvas short edge
    margin: float = 0.02  # fraction of canvas short edge
    size_variation: float = 0.5  # 0 = equal cell sizes, 1 = strong variation
    order: PlacementOrder = PlacementOrder.SHAPE


@dataclass
class PhotoItem:
    id: str
    path: str
    rect: Rect | None = None
    rotation: float = 0.0  # degrees, counter-clockwise
    crop: CropBox | None = None  # None = automatic crop to fill the frame
    style: StyleRef | None = None  # None = project default style
    z: int = 0


@dataclass
class Project:
    canvas: Canvas
    photos: list[PhotoItem] = field(default_factory=list)
    layout: LayoutSettings = field(default_factory=LayoutSettings)
    default_style: StyleRef = field(default_factory=StyleRef)
    seed: int = 0

    def style_for(self, item: PhotoItem) -> StyleRef:
        return item.style if item.style is not None else self.default_style
