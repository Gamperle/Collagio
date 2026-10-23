"""Plain style: the photo with an optional border and rounded corners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from PIL import Image, ImageChops, ImageDraw

from collagio.styles.base import Box, Style, StyleContext, register


@register
class PlainStyle(Style):
    name: ClassVar[str] = "plain"
    labels: ClassVar[Mapping[str, str]] = {"en": "Plain", "de": "Schlicht"}
    defaults: ClassVar[Mapping[str, Any]] = {
        "border_width": 0.0,
        "border_color": "#ffffff",
        "corner_radius": 0.0,
    }

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
        x, y, _, _ = self.content_box(size, params, ctx)
        fill = params["border_color"] if x > 0 else (0, 0, 0, 0)
        tile = Image.new("RGBA", size, fill)
        tile.paste(content.convert("RGBA"), (x, y))

        radius = ctx.px(params["corner_radius"])
        if radius > 0:
            mask = Image.new("L", size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255
            )
            tile.putalpha(ImageChops.multiply(tile.getchannel("A"), mask))
        return tile
