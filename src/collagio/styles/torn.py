"""Torn paper: ragged edges with a band of white paper fibres along the tear."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageChops

from collagio.errors import StyleError
from collagio.styles.base import Box, Style, StyleContext, register
from collagio.styles.common import Point, fractal_profile, paper, polygon_mask

SIDES = ("top", "right", "bottom", "left")


def parse_sides(value: str) -> frozenset[str]:
    """Sides to tear: "all", or a comma-separated subset of top, right, bottom, left."""
    if value.strip() == "all":
        return frozenset(SIDES)
    sides = frozenset(part.strip() for part in value.split(",") if part.strip())
    if not sides or not sides <= set(SIDES):
        raise StyleError(
            "torn.sides must be 'all' or a list of {sides}, got {value!r}",
            sides=", ".join(SIDES),
            value=value,
        )
    return sides


def _outline(
    profiles: Mapping[str, tuple[NDArray[np.float64], ...]],
    which: int,
    width: float,
    height: float,
) -> list[Point]:
    """Closed outline from per-side depth profiles (top/bottom run left to right and
    right to left, right/left top to bottom and bottom to top).

    Corners sit where two neighbouring edges meet; points of a side beyond its
    corners are dropped, so nothing pokes out at the corners.
    """
    top, right = profiles["top"][which], profiles["right"][which]
    bottom, left = profiles["bottom"][which], profiles["left"][which]
    top_left = (float(left[-1]), float(top[0]))
    top_right = (width - float(right[0]), float(top[-1]))
    bottom_right = (width - float(right[-1]), height - float(bottom[0]))
    bottom_left = (float(left[0]), height - float(bottom[-1]))

    def side(name: str) -> list[Point]:
        positions, depths = profiles[name][0], profiles[name][which]
        points: list[Point] = []
        for t, d in zip(positions, depths, strict=True):
            if name == "top" and top_left[0] < t < top_right[0]:
                points.append((t, d))
            elif name == "right" and top_right[1] < t < bottom_right[1]:
                points.append((width - d, t))
            elif name == "bottom" and bottom_left[0] < width - t < bottom_right[0]:
                points.append((width - t, height - d))
            elif name == "left" and top_left[1] < height - t < bottom_left[1]:
                points.append((d, height - t))
        return points

    return [
        top_left, *side("top"),
        top_right, *side("right"),
        bottom_right, *side("bottom"),
        bottom_left, *side("left"),
    ]  # fmt: skip


@register
class TornStyle(Style):
    name: ClassVar[str] = "torn"
    labels: ClassVar[Mapping[str, str]] = {"en": "Torn paper", "de": "Abgerissen"}
    defaults: ClassVar[Mapping[str, Any]] = {
        "sides": "all",
        "roughness": 10.0,  # amplitude of the tear
        "fibre_width": 4.0,  # width of the white paper band along the tear
        "paper_color": "#fdfcf7",
        "texture": 0.4,
    }
    ranges: ClassVar[Mapping[str, tuple[float, float]]] = {"texture": (0.0, 1.0)}

    def validate(self, params: Mapping[str, Any]) -> None:
        parse_sides(params["sides"])

    def content_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box:
        return 0, 0, size[0], size[1]  # the tear cuts into the photo itself

    def outlines(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> tuple[list[Point], list[Point]]:
        """Paper edge and photo edge in pixels.

        On torn sides the paper edge lies up to 2 x roughness inside the tile and
        the photo edge up to 2 x roughness + 1.5 x fibre width.
        """
        sides = parse_sides(params["sides"])
        rough, fibre = params["roughness"], params["fibre_width"]
        width_u, height_u = size[0] / ctx.unit, size[1] / ctx.unit
        profiles: dict[str, tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]]
        profiles = {}
        for side in SIDES:
            length = width_u if side in ("top", "bottom") else height_u
            if side in sides:
                rng = ctx.numpy_rng(f"tear-{side}")
                positions, tear = fractal_profile(length, rough, rng)
                _, band = fractal_profile(length, fibre / 2, rng)
                depth_outer = rough + tear
                profiles[side] = (positions, depth_outer, depth_outer + fibre + band)
            else:
                flat = np.zeros(2)
                profiles[side] = (np.array([0.0, length]), flat, flat)
        outer = _outline(profiles, 1, width_u, height_u)
        inner = _outline(profiles, 2, width_u, height_u)
        return (
            [(x * ctx.unit, y * ctx.unit) for x, y in outer],
            [(x * ctx.unit, y * ctx.unit) for x, y in inner],
        )

    def render(
        self,
        content: Image.Image,
        size: tuple[int, int],
        params: Mapping[str, Any],
        ctx: StyleContext,
    ) -> Image.Image:
        outer, inner = self.outlines(size, params, ctx)
        tile = paper(size, params["paper_color"], params["texture"], ctx)
        tile.putalpha(polygon_mask(size, outer))
        photo = content.convert("RGBA")
        photo.putalpha(ImageChops.multiply(photo.getchannel("A"), polygon_mask(size, inner)))
        tile.alpha_composite(photo)
        return tile
