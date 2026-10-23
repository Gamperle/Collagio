"""Film strip: a dark frame with sprocket holes along the two long edges.

Proportions follow the tile, like a real negative: the sprocket bands take a
share of the tile's short side, the holes are cut out (transparent).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from collagio.styles.base import Box, Style, StyleContext, register
from collagio.styles.common import ANTIALIAS_RADIUS, rgb

SIDE_SHARE = 0.03  # frame divider at the short ends, share of the long side
HOLE_HEIGHT = 0.42  # sprocket hole height, share of the band
HOLE_ASPECT = 1.35  # sprocket hole width / height
HOLE_PITCH = 1.9  # distance between hole starts, in hole widths


@register
class FilmstripStyle(Style):
    name: ClassVar[str] = "filmstrip"
    labels: ClassVar[Mapping[str, str]] = {"en": "Film strip", "de": "Filmstreifen"}
    defaults: ClassVar[Mapping[str, Any]] = {
        "orientation": "auto",
        "frame_color": "#161514",
        "band": 0.14,  # sprocket band, share of the tile's short side
    }
    ranges: ClassVar[Mapping[str, tuple[float, float]]] = {"band": (0.05, 0.3)}
    choices: ClassVar[Mapping[str, tuple[str, ...]]] = {
        "orientation": ("auto", "horizontal", "vertical")
    }

    @staticmethod
    def _bands(size: tuple[int, int], params: Mapping[str, Any]) -> tuple[bool, int, int]:
        """(horizontal strip?, band thickness, end divider) in pixels.

        With orientation "auto" the strip runs along the tile's longer side. Nearly
        square photos then get cropped somewhat, because the bands make a square
        photo's tile tall when horizontal and wide when vertical; set the
        orientation explicitly for an exact fit.
        """
        width, height = size
        if params["orientation"] == "auto":
            horizontal = width >= height
        else:
            horizontal = params["orientation"] == "horizontal"
        across, along = (height, width) if horizontal else (width, height)
        band = min(round(across * params["band"]), (across - 1) // 2)
        divider = min(round(along * SIDE_SHARE), (along - 1) // 2)
        return horizontal, band, divider

    def content_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box:
        width, height = size
        horizontal, band, divider = self._bands(size, params)
        if horizontal:
            return divider, band, width - 2 * divider, height - 2 * band
        return band, divider, width - 2 * band, height - 2 * divider

    def holes(
        self, size: tuple[int, int], params: Mapping[str, Any]
    ) -> list[tuple[float, float, float, float]]:
        """Sprocket hole rectangles (left, top, right, bottom) in pixels."""
        width, height = size
        horizontal, band, _ = self._bands(size, params)
        long = width if horizontal else height
        hole_h = band * HOLE_HEIGHT
        hole_w = hole_h * HOLE_ASPECT
        pitch = hole_w * HOLE_PITCH
        if hole_h < 1 or pitch <= 0:
            return []
        count = max(1, int(long // pitch))
        start = (long - (count - 1) * pitch - hole_w) / 2
        result = []
        for i in range(count):
            a = start + i * pitch
            for band_start in (0.0, (height if horizontal else width) - band):
                b = band_start + (band - hole_h) / 2
                if horizontal:
                    result.append((a, b, a + hole_w, b + hole_h))
                else:
                    result.append((b, a, b + hole_h, a + hole_w))
        return result

    def render(
        self,
        content: Image.Image,
        size: tuple[int, int],
        params: Mapping[str, Any],
        ctx: StyleContext,
    ) -> Image.Image:
        tile = Image.new("RGBA", size, (*rgb(params["frame_color"]), 255))
        x, y, _, _ = self.content_box(size, params, ctx)
        tile.alpha_composite(content.convert("RGBA"), (x, y))
        cutouts = Image.new("L", size, 0)
        draw = ImageDraw.Draw(cutouts)
        for left, top, right, bottom in self.holes(size, params):
            radius = (bottom - top if right - left > bottom - top else right - left) * 0.2
            draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=255)
        cutouts = cutouts.filter(ImageFilter.GaussianBlur(ANTIALIAS_RADIUS))
        tile.putalpha(ImageChops.subtract(tile.getchannel("A"), cutouts))
        return tile
