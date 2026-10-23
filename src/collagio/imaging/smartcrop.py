"""Choosing which part of a photo fills a frame of a different aspect ratio."""

from __future__ import annotations

from collagio.core.model import CropBox


def fill_crop(
    source_size: tuple[int, int],
    target_aspect: float,
    focus: tuple[float, float] = (0.5, 0.5),
) -> CropBox:
    """Largest crop of `target_aspect` that fits the source, centred on `focus` where possible.

    `focus` is a normalised point (0..1) of the source that should stay as
    central as possible; the crop is clamped to the image bounds.
    """
    if target_aspect <= 0:
        raise ValueError(f"target aspect must be positive, got {target_aspect}")
    width, height = source_size
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid source size {source_size}")

    source_aspect = width / height
    if source_aspect > target_aspect:  # source is wider: crop the sides
        crop_w, crop_h = target_aspect / source_aspect, 1.0
    else:  # source is taller: crop top and bottom
        crop_w, crop_h = 1.0, source_aspect / target_aspect

    x = min(max(focus[0] - crop_w / 2, 0.0), 1.0 - crop_w)
    y = min(max(focus[1] - crop_h / 2, 0.0), 1.0 - crop_h)
    return CropBox(x, y, crop_w, crop_h)


def crop_pixels(crop: CropBox, source_size: tuple[int, int]) -> tuple[float, float, float, float]:
    """Crop box as (left, top, right, bottom) in source pixels."""
    width, height = source_size
    return (
        crop.x * width,
        crop.y * height,
        (crop.x + crop.width) * width,
        (crop.y + crop.height) * height,
    )
