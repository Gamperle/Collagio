"""Helpers shared by the layout generators."""

from __future__ import annotations

import math
from collections.abc import Sequence

from collagio.core.model import Rect
from collagio.errors import LayoutError


def validate_aspects(aspects: Sequence[float]) -> None:
    if any(a <= 0 or not math.isfinite(a) for a in aspects):
        raise LayoutError("photo aspect ratios must be positive")


def content_rect(width: float, height: float, margin: float) -> Rect:
    """The canvas minus its margin on every side."""
    content = Rect(margin, margin, width - 2 * margin, height - 2 * margin)
    if content.width <= 0 or content.height <= 0:
        raise LayoutError(f"margin {margin:g} px is too large for {width}x{height} px")
    return content


def geometric_mean(values: Sequence[float]) -> float:
    return math.exp(sum(math.log(v) for v in values) / len(values))
