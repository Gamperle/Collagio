"""Geometry for interactive editing: resizing, rotating and panning photos.

Pure functions in canvas coordinates (pixels, y pointing down, rotations in
degrees counter-clockwise as seen on screen), so they are testable without a GUI.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from collagio.core.model import CropBox, PhotoItem, Rect

Point = tuple[float, float]

MIN_SIZE = 8.0  # smallest photo edge in canvas pixels when resizing
MIN_CROP = 0.05  # smallest visible share of a photo when zooming the crop
SNAP_DEGREES = 15.0


def centre(rect: Rect) -> Point:
    return rect.x + rect.width / 2, rect.y + rect.height / 2


def to_local(point: Point, origin: Point, rotation: float) -> Point:
    """`point` in the frame of a rectangle centred at `origin` rotated by `rotation`."""
    cos, sin = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    wx, wy = point[0] - origin[0], point[1] - origin[1]
    return wx * cos - wy * sin, wx * sin + wy * cos


def to_world(local: Point, origin: Point, rotation: float) -> Point:
    cos, sin = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    dx, dy = local
    return origin[0] + dx * cos + dy * sin, origin[1] - dx * sin + dy * cos


def resize_from_corner(rect: Rect, rotation: float, corner: int, pointer: Point) -> Rect:
    """Resize by dragging `corner` (0 top-left, 1 top-right, 2 bottom-right, 3 bottom-left
    in the photo's own frame) to `pointer`, keeping the aspect ratio and the opposite
    corner in place."""
    signs = ((-1, -1), (1, -1), (1, 1), (-1, 1))[corner]
    half_w, half_h = rect.width / 2, rect.height / 2
    dragged = (signs[0] * half_w, signs[1] * half_h)
    fixed = (-dragged[0], -dragged[1])
    old_centre = centre(rect)
    local = to_local(pointer, old_centre, rotation)

    diagonal = (dragged[0] - fixed[0], dragged[1] - fixed[1])
    reach = (local[0] - fixed[0], local[1] - fixed[1])
    scale = (reach[0] * diagonal[0] + reach[1] * diagonal[1]) / (
        diagonal[0] ** 2 + diagonal[1] ** 2
    )
    scale = max(scale, MIN_SIZE / min(rect.width, rect.height))
    width, height = rect.width * scale, rect.height * scale
    new_centre_local = (fixed[0] + diagonal[0] * scale / 2, fixed[1] + diagonal[1] * scale / 2)
    cx, cy = to_world(new_centre_local, old_centre, rotation)
    return Rect(cx - width / 2, cy - height / 2, width, height)


def screen_angle(origin: Point, point: Point) -> float:
    """Direction from `origin` to `point` in degrees, counter-clockwise on screen."""
    return math.degrees(math.atan2(-(point[1] - origin[1]), point[0] - origin[0]))


def normalise_angle(angle: float) -> float:
    """Angle in (-180, 180]."""
    angle = math.fmod(angle, 360.0)
    if angle <= -180.0:
        angle += 360.0
    elif angle > 180.0:
        angle -= 360.0
    return angle


def rotate_by_drag(
    origin: Point, start: Point, pointer: Point, start_rotation: float, snap: bool = False
) -> float:
    """Rotation after dragging from `start` to `pointer` around `origin`."""
    angle = start_rotation + screen_angle(origin, pointer) - screen_angle(origin, start)
    if snap:
        angle = round(angle / SNAP_DEGREES) * SNAP_DEGREES
    return normalise_angle(angle)


def pan_crop(crop: CropBox, frame_size: tuple[float, float], dx: float, dy: float) -> CropBox:
    """Crop after dragging the photo content by (dx, dy) frame pixels inside its frame."""
    width, height = frame_size
    x = crop.x - dx / width * crop.width
    y = crop.y - dy / height * crop.height
    return CropBox(
        min(max(x, 0.0), 1.0 - crop.width),
        min(max(y, 0.0), 1.0 - crop.height),
        crop.width,
        crop.height,
    )


def zoom_crop(crop: CropBox, factor: float, anchor: Point = (0.5, 0.5)) -> CropBox:
    """Zoom into (`factor` > 1) or out of the crop, keeping its shape.

    `anchor` is the point of the frame (0..1) that stays in place.
    """
    if factor <= 0:
        raise ValueError(f"zoom factor must be positive, got {factor}")
    largest = min(1.0 / crop.width, 1.0 / crop.height)  # crop may grow at most this much
    smallest = MIN_CROP / min(crop.width, crop.height)
    scale = min(max(1.0 / factor, smallest), largest)
    width, height = crop.width * scale, crop.height * scale
    focus_x = crop.x + anchor[0] * crop.width
    focus_y = crop.y + anchor[1] * crop.height
    x = focus_x - anchor[0] * width
    y = focus_y - anchor[1] * height
    return CropBox(
        min(max(x, 0.0), 1.0 - width),
        min(max(y, 0.0), 1.0 - height),
        width,
        height,
    )


def contains(rect: Rect, rotation: float, point: Point) -> bool:
    """True if `point` lies on the rotated rectangle."""
    x, y = to_local(point, centre(rect), rotation)
    return abs(x) <= rect.width / 2 and abs(y) <= rect.height / 2


def photo_at(photos: Sequence[PhotoItem], point: Point) -> PhotoItem | None:
    """The topmost photo under `point`."""
    for item in sorted(photos, key=lambda p: -p.z):
        if item.rect is not None and contains(item.rect, item.rotation, point):
            return item
    return None
