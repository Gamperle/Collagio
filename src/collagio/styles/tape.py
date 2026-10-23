"""Tape and photo corners: a bordered print held by adhesive tape or paper corners."""

from __future__ import annotations

import math
from collections.abc import Mapping
from random import Random
from typing import Any, ClassVar

from PIL import Image, ImageChops

from collagio.styles.base import Box, Style, StyleContext, register
from collagio.styles.common import Point, paper, polygon_mask, rgb

TAPE_ANGLE = 45.0  # degrees across the corner
TAPE_JITTER = 8.0  # random deviation from TAPE_ANGLE
TAPE_SHIFT = 0.15  # tape centre moves this share of its length into the photo
TAPE_END_STEPS = 6  # zigzag points across each torn end of a strip
CORNER_OFFSET = 2.0  # photo corners stick out this far beyond the photo


def _tape_extent(length: float, width: float) -> float:
    """How far a strip reaches beyond the photo corner, horizontally or vertically (worst case)."""
    reach = 0.0
    for angle in (TAPE_ANGLE - TAPE_JITTER, TAPE_ANGLE + TAPE_JITTER):
        a = math.radians(angle)
        reach = max(
            reach,
            length / 2 * math.cos(a) + width / 2 * math.sin(a),
            length / 2 * math.sin(a) + width / 2 * math.cos(a),
        )
    return max(0.0, reach - TAPE_SHIFT * length / math.sqrt(2))


def _strip(centre: Point, angle: float, length: float, width: float, rng: Random) -> list[Point]:
    """Tape strip polygon with zigzag (torn) ends, in style units."""
    a = math.radians(angle)
    along = (math.cos(a), -math.sin(a))
    across = (math.sin(a), math.cos(a))
    points: list[Point] = []
    for end, sign in ((length / 2, 1.0), (-length / 2, -1.0)):
        for step in range(TAPE_END_STEPS + 1):
            t = (step / TAPE_END_STEPS - 0.5) * width * sign
            zigzag = (1 if step % 2 else -1) * rng.uniform(0.3, 1.5)
            d = end + zigzag
            points.append(
                (centre[0] + along[0] * d + across[0] * t, centre[1] + along[1] * d + across[1] * t)
            )
    return points


@register
class TapeStyle(Style):
    name: ClassVar[str] = "tape"
    labels: ClassVar[Mapping[str, str]] = {
        "en": "Tape / photo corners",
        "de": "Klebeband / Fotoecken",
    }
    defaults: ClassVar[Mapping[str, Any]] = {
        "variant": "tape",
        "border_width": 8.0,
        "border_color": "#ffffff",
        "tape_color": "#efe4bd",
        "tape_opacity": 0.75,
        "tape_length": 60.0,
        "tape_width": 20.0,
        "corner_color": "#1e1e1e",
        "corner_size": 34.0,
    }
    choices: ClassVar[Mapping[str, tuple[str, ...]]] = {"variant": ("tape", "corners")}
    ranges: ClassVar[Mapping[str, tuple[float, float]]] = {"tape_opacity": (0.0, 1.0)}

    def _print_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box:
        """The bordered print, leaving room for tape or corners that stick out."""
        width, height = size
        if params["variant"] == "tape":
            reach = _tape_extent(params["tape_length"], params["tape_width"])
            top = side = ctx.px(reach + 1)  # 1 unit of slack for anti-aliasing
            bottom = ctx.px(CORNER_OFFSET)
        else:
            top = side = bottom = ctx.px(CORNER_OFFSET + 1)
        side = min(side, (width - 1) // 2)
        top = min(top, height - 1)
        bottom = min(bottom, height - top - 1)
        return side, top, width - 2 * side, height - top - bottom

    def content_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box:
        x, y, w, h = self._print_box(size, params, ctx)
        border = min(ctx.px(params["border_width"]), (min(w, h) - 1) // 2)
        return x + border, y + border, w - 2 * border, h - 2 * border

    def holders(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> list[list[Point]]:
        """Tape strips or corner triangles in pixels."""
        x, y, w, h = (v / ctx.unit for v in self._print_box(size, params, ctx))
        if params["variant"] == "tape":
            rng = ctx.rng("tape")
            length, width = params["tape_length"], params["tape_width"]
            shift = TAPE_SHIFT * length / math.sqrt(2)
            shapes = [
                _strip(
                    (x + shift, y + shift),
                    TAPE_ANGLE + rng.uniform(-TAPE_JITTER, TAPE_JITTER),
                    length, width, rng,
                ),
                _strip(
                    (x + w - shift, y + shift),
                    -TAPE_ANGLE + rng.uniform(-TAPE_JITTER, TAPE_JITTER),
                    length, width, rng,
                ),
            ]  # fmt: skip
        else:
            c, o = params["corner_size"], CORNER_OFFSET
            shapes = [
                [(x - o, y - o), (x - o + c, y - o), (x - o, y - o + c)],
                [(x + w + o, y - o), (x + w + o, y - o + c), (x + w + o - c, y - o)],
                [(x + w + o, y + h + o), (x + w + o - c, y + h + o), (x + w + o, y + h + o - c)],
                [(x - o, y + h + o), (x - o, y + h + o - c), (x - o + c, y + h + o)],
            ]
        return [[(px * ctx.unit, py * ctx.unit) for px, py in shape] for shape in shapes]

    def render(
        self,
        content: Image.Image,
        size: tuple[int, int],
        params: Mapping[str, Any],
        ctx: StyleContext,
    ) -> Image.Image:
        tile = Image.new("RGBA", size, (0, 0, 0, 0))
        x, y, w, h = self._print_box(size, params, ctx)
        tile.paste(Image.new("RGBA", (w, h), (*rgb(params["border_color"]), 255)), (x, y))
        cx, cy, _, _ = self.content_box(size, params, ctx)
        tile.alpha_composite(content.convert("RGBA"), (cx, cy))

        if params["variant"] == "tape":
            layer = paper(size, params["tape_color"], 0.6, ctx)
            opacity = params["tape_opacity"]
        else:
            layer = Image.new("RGBA", size, (*rgb(params["corner_color"]), 255))
            opacity = 1.0
        mask = Image.new("L", size, 0)
        for shape in self.holders(size, params, ctx):
            mask = ImageChops.lighter(mask, polygon_mask(size, shape))
        layer.putalpha(mask.point(lambda v: round(v * opacity)))
        tile.alpha_composite(layer)
        return tile
