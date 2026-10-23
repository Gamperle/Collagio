"""Scissor cut-out: a paper border cut by hand in short, slightly crooked lines."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from PIL import Image, ImageChops

from collagio.styles.base import Box, Style, StyleContext, register
from collagio.styles.common import Point, paper, polygon_mask


@register
class CutoutStyle(Style):
    name: ClassVar[str] = "cutout"
    labels: ClassVar[Mapping[str, str]] = {"en": "Scissor cut-out", "de": "Ausgeschnitten"}
    defaults: ClassVar[Mapping[str, Any]] = {
        "border_width": 8.0,  # 0 = the photo itself is cut
        "roughness": 2.5,  # how far the cut wanders from a straight line
        "segment": 40.0,  # typical length of one straight scissor cut
        "paper_color": "#ffffff",
        "texture": 0.2,
    }
    ranges: ClassVar[Mapping[str, tuple[float, float]]] = {
        "texture": (0.0, 1.0),
        "segment": (5.0, 1000.0),
    }

    def _inset(self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext) -> int:
        inset = ctx.px(params["border_width"])
        if inset > 0:  # keep the photo clear of the wandering cut line
            inset += ctx.px(2 * params["roughness"])
        return min(inset, (min(size) - 1) // 2)

    def content_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box:
        inset = self._inset(size, params, ctx)
        return inset, inset, size[0] - 2 * inset, size[1] - 2 * inset

    def outline(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> list[Point]:
        """Cut line in pixels: straight segments with jittered ends.

        Every point lies between the tile edge and 2 x roughness inside it.
        """
        rng = ctx.rng("cut")
        rough = float(params["roughness"])
        width_u, height_u = size[0] / ctx.unit, size[1] / ctx.unit

        def jitter() -> float:
            return rough + rng.uniform(-rough, rough)

        corners = [
            (jitter(), jitter()),
            (width_u - jitter(), jitter()),
            (width_u - jitter(), height_u - jitter()),
            (jitter(), height_u - jitter()),
        ]
        points: list[Point] = []
        for index, (start, end) in enumerate(zip(corners, corners[1:] + corners[:1], strict=True)):
            points.append(start)
            length = abs(end[0] - start[0]) + abs(end[1] - start[1])
            position = rng.uniform(0.5, 1.5) * params["segment"]
            while position < length - 0.5 * params["segment"]:
                t = position / length
                x = start[0] + (end[0] - start[0]) * t
                y = start[1] + (end[1] - start[1]) * t
                offset = rng.uniform(-rough, rough)
                if index % 2 == 0:  # top and bottom sides: wander vertically
                    y = (rough if index == 0 else height_u - rough) + offset
                else:
                    x = (width_u - rough if index == 1 else rough) + offset
                points.append((x, y))
                position += rng.uniform(0.5, 1.5) * params["segment"]
        return [(x * ctx.unit, y * ctx.unit) for x, y in points]

    def render(
        self,
        content: Image.Image,
        size: tuple[int, int],
        params: Mapping[str, Any],
        ctx: StyleContext,
    ) -> Image.Image:
        x, y, _, _ = self.content_box(size, params, ctx)
        tile = paper(size, params["paper_color"], params["texture"], ctx)
        tile.alpha_composite(content.convert("RGBA"), (x, y))
        mask = polygon_mask(size, self.outline(size, params, ctx))
        tile.putalpha(ImageChops.multiply(tile.getchannel("A"), mask))
        return tile
