"""Project data model.

Geometry is stored in canvas pixels at full export resolution. Layout spacing
(gap, margin) is stored as a fraction of the canvas short edge so it scales with
the canvas size and DPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 2
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
    SCATTERED = "scattered"


class PlacementOrder(StrEnum):
    """Which photo goes into which layout cell."""

    SHAPE = "shape"  # match photo and cell aspect ratios: least cropping
    RANDOM = "random"  # shuffled, depends on the seed
    INPUT = "input"  # photo order, starting top-left


class BackgroundKind(StrEnum):
    SOLID = "solid"
    GRADIENT = "gradient"
    TEXTURE = "texture"
    PHOTO = "photo"


@dataclass
class Background:
    kind: BackgroundKind = BackgroundKind.SOLID
    color: str = "#ffffff"  # solid colour, gradient start, or texture base colour
    color2: str = "#d9d9d9"
    angle: float = 90.0  # gradient direction in degrees, 0 = left to right, 90 = top to bottom
    texture: str = "paper"  # see render.background.TEXTURES
    photo: str = ""  # photo path for kind PHOTO
    blur: float = 25.0  # photo background blur radius, style units
    dim: float = 0.25  # photo background: 0 = unchanged, 1 = black


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
    order: PlacementOrder = PlacementOrder.SHAPE  # grid only
    max_rotation: float = 12.0  # scattered only: degrees, rotation in [-max, +max]
    overlap: float = 0.5  # scattered only: 0 = photos barely touch, 1 = heavy overlap
    min_visible: float = 0.5  # scattered only: share of each photo that stays uncovered
    space_top: float = 0.0  # extra free space above the photos, fraction of short edge
    space_bottom: float = 0.0  # extra free space below the photos, fraction of short edge


@dataclass
class Shadow:
    """Drop shadow under every photo. Sizes are in style units (1/1000 of the short edge)."""

    opacity: float = 0.0  # 0 = no shadow
    blur: float = 6.0
    offset_x: float = 3.0
    offset_y: float = 5.0
    color: str = "#000000"


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
class TextItem:
    """A title or caption placed on the canvas, drawn above the photos."""

    id: str
    text: str
    x: float  # centre, canvas pixels
    y: float
    size: float = 60.0  # letter height in style units (1/1000 of the short edge)
    color: str = "#222222"
    rotation: float = 0.0  # degrees, counter-clockwise
    font: str = ""  # path to a TrueType/OpenType font; "" = built-in font
    shadow: bool = False  # drop shadow behind the text (project shadow, or a soft default)


@dataclass
class Project:
    canvas: Canvas
    photos: list[PhotoItem] = field(default_factory=list)
    layout: LayoutSettings = field(default_factory=LayoutSettings)
    default_style: StyleRef = field(default_factory=StyleRef)
    shadow: Shadow = field(default_factory=Shadow)
    texts: list[TextItem] = field(default_factory=list)
    seed: int = 0

    def style_for(self, item: PhotoItem) -> StyleRef:
        return item.style if item.style is not None else self.default_style
