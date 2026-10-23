"""Helpers shared by the layout generators."""

from __future__ import annotations

import math
from collections.abc import Sequence

from collagio.core.model import Rect
from collagio.errors import LayoutError


def validate_aspects(aspects: Sequence[float]) -> None:
    if any(a <= 0 or not math.isfinite(a) for a in aspects):
        raise LayoutError("photo aspect ratios must be positive")


def content_rect(
    width: float, height: float, margin: float, extra_top: float = 0.0, extra_bottom: float = 0.0
) -> Rect:
    """The canvas minus its margin on every side and extra space at top and bottom
    (e.g. room for a title)."""
    top, bottom = margin + extra_top, margin + extra_bottom
    content = Rect(margin, top, width - 2 * margin, height - top - bottom)
    if content.width <= 0 or content.height <= 0:
        size = {"margin": margin, "width": width, "height": height}
        if extra_top or extra_bottom:
            raise LayoutError(
                "margin {margin:g} px plus free space is too large for {width}x{height} px", **size
            )
        raise LayoutError("margin {margin:g} px is too large for {width}x{height} px", **size)
    return content


def geometric_mean(values: Sequence[float]) -> float:
    return math.exp(sum(math.log(v) for v in values) / len(values))
