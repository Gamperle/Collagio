"""Postage stamp: paper border with a perforated edge and an optional value."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from collagio.errors import StyleError
from collagio.styles.base import Box, Style, StyleContext, register
from collagio.styles.common import ANTIALIAS_RADIUS, font, paper


def hole_count(length_units: float, spacing: float) -> int:
    """Holes along one side: as close to `spacing` apart as fits evenly."""
    return max(1, round(length_units / spacing))


@register
class StampStyle(Style):
    name: ClassVar[str] = "stamp"
    labels: ClassVar[Mapping[str, str]] = {"en": "Postage stamp", "de": "Briefmarke"}
    defaults: ClassVar[Mapping[str, Any]] = {
        "border_width": 16.0,
        "hole_radius": 4.0,
        "hole_spacing": 12.0,
        "paper_color": "#fbf8f0",
        "texture": 0.5,
        "value": "",  # e.g. "60c", printed in the bottom-right corner of the photo
        "text_color": "#2f2f2f",
        "text_size": 18.0,
    }
    ranges: ClassVar[Mapping[str, tuple[float, float]]] = {"texture": (0.0, 1.0)}

    def validate(self, params: Mapping[str, Any]) -> None:
        if params["hole_radius"] * 2 > params["border_width"]:
            raise StyleError("stamp.hole_radius must be at most half of border_width")
        if params["hole_spacing"] <= params["hole_radius"] * 2:
            raise StyleError("stamp.hole_spacing must be larger than the hole diameter")

    def content_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box:
        width, height = size
        border = min(ctx.px(params["border_width"]), (min(width, height) - 1) // 2)
        return border, border, width - 2 * border, height - 2 * border

    def render(
        self,
        content: Image.Image,
        size: tuple[int, int],
        params: Mapping[str, Any],
        ctx: StyleContext,
    ) -> Image.Image:
        width, height = size
        x, y, content_w, content_h = self.content_box(size, params, ctx)
        tile = paper(size, params["paper_color"], params["texture"], ctx)
        tile.alpha_composite(content.convert("RGBA"), (x, y))

        if params["value"]:
            text_px = ctx.px(params["text_size"])
            pad = max(1, text_px // 3)
            ImageDraw.Draw(tile).text(
                (x + content_w - pad, y + content_h - pad),
                params["value"],
                fill=params["text_color"],
                font=font(text_px),
                anchor="rd",
            )

        # Perforation: half circles cut out along every edge.
        radius = params["hole_radius"] * ctx.unit
        holes = Image.new("L", size, 0)
        draw = ImageDraw.Draw(holes)
        for length, positions in (
            (width, lambda t: [(t, 0.0), (t, float(height))]),
            (height, lambda t: [(0.0, t), (float(width), t)]),
        ):
            count = hole_count(length / ctx.unit, params["hole_spacing"])
            for i in range(count):
                for cx, cy in positions((i + 0.5) * length / count):
                    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
        holes = holes.filter(ImageFilter.GaussianBlur(ANTIALIAS_RADIUS))
        tile.putalpha(ImageChops.subtract(tile.getchannel("A"), holes))
        return tile
