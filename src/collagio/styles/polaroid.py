"""Polaroid: instant-photo frame with a wide bottom edge and an optional caption."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from PIL import Image, ImageDraw

from collagio.styles.base import Box, Style, StyleContext, register
from collagio.styles.common import font, paper


@register
class PolaroidStyle(Style):
    name: ClassVar[str] = "polaroid"
    labels: ClassVar[Mapping[str, str]] = {"en": "Polaroid", "de": "Sofortbild"}
    defaults: ClassVar[Mapping[str, Any]] = {
        "border_width": 26.0,  # top, left and right
        "bottom_width": 90.0,
        "frame_color": "#fbfaf5",
        "texture": 0.3,
        "caption": "",
        "caption_color": "#2b2b2b",
        "caption_size": 32.0,
    }
    ranges: ClassVar[Mapping[str, tuple[float, float]]] = {"texture": (0.0, 1.0)}

    def _borders(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> tuple[int, int]:
        """Side and bottom border in pixels, scaled down together if the tile is too small."""
        width, height = size
        side, bottom = params["border_width"] * ctx.unit, params["bottom_width"] * ctx.unit
        fit = min(
            1.0,
            (width - 1) / (2 * side) if side else 1.0,
            (height - 1) / (side + bottom) if side + bottom else 1.0,
        )
        return int(side * fit), int(bottom * fit)

    def content_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box:
        side, bottom = self._borders(size, params, ctx)
        return side, side, size[0] - 2 * side, size[1] - side - bottom

    def render(
        self,
        content: Image.Image,
        size: tuple[int, int],
        params: Mapping[str, Any],
        ctx: StyleContext,
    ) -> Image.Image:
        width, height = size
        side, bottom = self._borders(size, params, ctx)
        tile = paper(size, params["frame_color"], params["texture"], ctx)
        tile.alpha_composite(content.convert("RGBA"), (side, side))
        if params["caption"] and bottom > 0:
            text_px = min(ctx.px(params["caption_size"]), int(bottom * 0.6))
            ImageDraw.Draw(tile).text(
                (width / 2, height - bottom / 2),
                params["caption"],
                fill=params["caption_color"],
                font=font(text_px),
                anchor="mm",
            )
        return tile
