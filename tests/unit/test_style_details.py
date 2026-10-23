"""Behaviour specific to each style (the shared contract is in test_styles.py)."""

from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from collagio.errors import StyleError
from collagio.styles import StyleContext, get_style
from collagio.styles.cutout import CutoutStyle
from collagio.styles.filmstrip import FilmstripStyle
from collagio.styles.stamp import hole_count
from collagio.styles.tape import TapeStyle
from collagio.styles.torn import TornStyle, parse_sides

RED = (200, 30, 40)


def ctx(unit: float = 1.0, seed: int = 0) -> StyleContext:
    return StyleContext(unit=unit, seed=seed)


def render(
    name: str, size: tuple[int, int], params: dict[str, Any] | None = None, unit: float = 1.0
) -> Image.Image:
    style = get_style(name)
    resolved = style.resolve(params or {})
    _, _, w, h = style.content_box(size, resolved, ctx(unit))
    return style.render(Image.new("RGB", (w, h), RED), size, resolved, ctx(unit))


def alpha(tile: Image.Image, x: int, y: int) -> int:
    return int(tile.getpixel((x, y))[3])  # type: ignore[index]


def transparent_runs(values: list[int]) -> int:
    runs, inside = 0, False
    for value in values:
        if value < 128 and not inside:
            runs += 1
        inside = value < 128
    return runs


# --- postage stamp -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("length", "spacing", "expected"), [(300, 12, 25), (5, 12, 1), (130, 12, 11)]
)
def test_hole_count(length: float, spacing: float, expected: int) -> None:
    assert hole_count(length, spacing) == expected


def test_stamp_perforation() -> None:
    tile = render("stamp", (300, 240))
    top = [alpha(tile, x, 0) for x in range(300)]
    left = [alpha(tile, 0, y) for y in range(240)]
    assert transparent_runs(top) == hole_count(300, 12)
    assert transparent_runs(left) == hole_count(240, 12)
    spacing = 300 / hole_count(300, 12)
    assert alpha(tile, round(spacing / 2), 0) == 0  # hole centre
    assert alpha(tile, round(spacing), 1) > 240  # paper between holes (anti-aliased)
    assert alpha(tile, round(spacing / 2), 7) > 240  # holes do not reach the photo


def test_stamp_photo_and_border() -> None:
    tile = render("stamp", (300, 240), {"texture": 0})
    assert tile.getpixel((150, 120)) == (*RED, 255)
    assert tile.getpixel((150, 10)) == (0xFB, 0xF8, 0xF0, 255)


def test_stamp_value_is_printed_bottom_right() -> None:
    plain = render("stamp", (300, 240), {"texture": 0})
    valued = render("stamp", (300, 240), {"texture": 0, "value": "60c"})
    differs = [
        (x, y) for x in range(0, 300, 2) for y in range(0, 240, 2)
        if plain.getpixel((x, y)) != valued.getpixel((x, y))
    ]  # fmt: skip
    assert differs
    assert min(x for x, _ in differs) > 150
    assert min(y for _, y in differs) > 120


@pytest.mark.parametrize(
    ("params", "message"),
    [({"hole_radius": 9}, "at most half"), ({"hole_spacing": 7}, "larger than the hole")],
)
def test_stamp_validation(params: dict[str, Any], message: str) -> None:
    with pytest.raises(StyleError, match=message):
        get_style("stamp").resolve(params)


# --- scissor cut-out -----------------------------------------------------------------------------


def test_cutout_outline_stays_near_the_edge() -> None:
    style = CutoutStyle()
    params = style.resolve({"roughness": 3})
    points = style.outline((400, 300), params, ctx())
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    assert min(xs) >= 0 and max(xs) <= 400
    assert min(ys) >= 0 and max(ys) <= 300
    # Every point is within 2 x roughness of one of the edges.
    for x, y in points:
        assert min(x, y, 400 - x, 300 - y) <= 6 + 1e-9
    # Not a straight line: points on the top edge vary in height.
    top = [y for x, y in points if y < 10]
    assert max(top) - min(top) > 0.5
    assert len(points) > 8


def test_cutout_cuts_outside_the_line() -> None:
    tile = render("cutout", (400, 300), {"texture": 0})
    assert alpha(tile, 200, 150) == 255
    assert tile.getpixel((200, 150))[:3] == RED  # type: ignore[index]
    assert tile.getpixel((200, 9))[:3] == (255, 255, 255)  # type: ignore[index]
    assert sum(alpha(tile, x, 0) for x in range(400)) < 400 * 255 * 0.6


def test_cutout_without_border_cuts_the_photo() -> None:
    style = CutoutStyle()
    assert style.content_box((400, 300), style.resolve({"border_width": 0}), ctx()) == (
        0,
        0,
        400,
        300,
    )
    with_border = style.content_box((400, 300), style.resolve({}), ctx())
    assert with_border[0] == 8 + 5  # border + 2 x roughness (rounded)


def test_cutout_differs_per_seed() -> None:
    style = CutoutStyle()
    params = style.resolve({})
    assert style.outline((400, 300), params, ctx(seed=1)) != style.outline(
        (400, 300), params, ctx(seed=2)
    )


# --- torn paper ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("all", {"top", "right", "bottom", "left"}), ("top", {"top"}),
     ("top, bottom", {"top", "bottom"}), ("left,left", {"left"})],
)  # fmt: skip
def test_parse_sides(value: str, expected: set[str]) -> None:
    assert parse_sides(value) == expected


@pytest.mark.parametrize("value", ["", "middle", "top,center", ","])
def test_invalid_sides(value: str) -> None:
    with pytest.raises(StyleError, match=r"torn\.sides"):
        get_style("torn").resolve({"sides": value})


def test_torn_outline_depths() -> None:
    style = TornStyle()
    params = style.resolve({"roughness": 8, "fibre_width": 4})
    outer, inner = style.outlines((400, 300), params, ctx())
    for x, y in outer:
        assert 0 <= min(x, y, 400 - x, 300 - y) <= 16 + 1e-9
    for x, y in inner:
        assert 0 <= min(x, y, 400 - x, 300 - y) <= 16 + 6 + 1e-9
    top = [y for x, y in outer if 20 < x < 380 and y < 50]
    assert max(top) - min(top) > 4  # ragged, not straight


def test_torn_has_paper_band_between_tear_and_photo() -> None:
    tile = render("torn", (400, 300), {"texture": 0, "sides": "top", "fibre_width": 6})
    column = [tile.getpixel((200, y)) for y in range(40)]
    paper_rows = [y for y, p in enumerate(column) if p == (0xFD, 0xFC, 0xF7, 255)]
    photo_rows = [y for y, p in enumerate(column) if p == (*RED, 255)]
    assert paper_rows
    assert photo_rows
    assert max(paper_rows) < min(photo_rows)


def test_torn_only_selected_sides() -> None:
    tile = render("torn", (400, 300), {"sides": "top"})
    assert alpha(tile, 200, 0) == 0  # torn top
    assert alpha(tile, 0, 150) == 255  # straight left
    assert alpha(tile, 399, 150) == 255  # straight right
    assert alpha(tile, 200, 299) == 255  # straight bottom


def test_torn_corners_do_not_poke_out() -> None:
    for seed in range(10):
        style = TornStyle()
        params = style.resolve({})
        tile = style.render(Image.new("RGB", (300, 200), RED), (300, 200), params, ctx(seed=seed))
        for x, y in ((0, 0), (299, 0), (0, 199), (299, 199)):
            assert alpha(tile, x, y) == 0


# --- polaroid ------------------------------------------------------------------------------------


def test_polaroid_frame_proportions() -> None:
    style = get_style("polaroid")
    box = style.content_box((400, 500), style.resolve({}), ctx())
    assert box == (26, 26, 400 - 52, 500 - 26 - 90)


def test_polaroid_borders_shrink_for_small_tiles() -> None:
    style = get_style("polaroid")
    x, y, w, h = style.content_box((60, 60), style.resolve({}), ctx())
    assert w >= 1 and h >= 1
    assert 60 - y - h > x  # bottom still wider than the sides


def test_polaroid_caption() -> None:
    plain = render("polaroid", (400, 500), {"texture": 0})
    captioned = render("polaroid", (400, 500), {"texture": 0, "caption": "Hello"})
    assert plain.crop((0, 0, 400, 410)).tobytes() == captioned.crop((0, 0, 400, 410)).tobytes()
    assert plain.crop((0, 410, 400, 500)).tobytes() != captioned.crop((0, 410, 400, 500)).tobytes()


# --- tape and photo corners ----------------------------------------------------------------------


def test_tape_leaves_room_above_the_print() -> None:
    style = TapeStyle()
    x, y, _, h = style.content_box((400, 300), style.resolve({"border_width": 0}), ctx())
    assert x > 15 and y > 15
    assert 300 - (y + h) < 5  # little room needed at the bottom


def test_tape_is_semi_transparent_over_the_corner() -> None:
    style = TapeStyle()
    params = style.resolve({"tape_opacity": 0.5})
    tile = render("tape", (400, 300), {"tape_opacity": 0.5})
    strips = style.holders((400, 300), params, ctx())
    assert len(strips) == 2
    cx = sum(p[0] for p in strips[0]) / len(strips[0])
    cy = sum(p[1] for p in strips[0]) / len(strips[0])
    pixel = tile.getpixel((round(cx), round(cy)))
    assert pixel[:3] != (*RED,)  # tape tints the photo
    assert pixel[0] > RED[0] or pixel[1] > RED[1]  # type: ignore[index]


def test_photo_corners_cover_the_corners() -> None:
    style = TapeStyle()
    params = style.resolve({"variant": "corners", "border_width": 0})
    x, y, w, h = style.content_box((400, 300), params, ctx())
    tile = render("tape", (400, 300), {"variant": "corners", "border_width": 0})
    assert len(style.holders((400, 300), params, ctx())) == 4
    for px, py in ((x + 3, y + 3), (x + w - 4, y + 3), (x + 3, y + h - 4), (x + w - 4, y + h - 4)):
        assert tile.getpixel((px, py)) == (0x1E, 0x1E, 0x1E, 255)
    assert tile.getpixel((x + w // 2, y + h // 2)) == (*RED, 255)


@pytest.mark.parametrize(
    ("params", "message"),
    [({"variant": "glue"}, "must be one of tape, corners"),
     ({"tape_opacity": 1.5}, "between 0 and 1")],
)  # fmt: skip
def test_tape_validation(params: dict[str, Any], message: str) -> None:
    with pytest.raises(StyleError, match=message):
        get_style("tape").resolve(params)


# --- film strip ----------------------------------------------------------------------------------


@pytest.mark.parametrize(("size", "horizontal"), [((400, 300), True), ((300, 400), False)])
def test_filmstrip_orientation(size: tuple[int, int], horizontal: bool) -> None:
    style = FilmstripStyle()
    params = style.resolve({})
    x, y, _, _ = style.content_box(size, params, ctx())
    if horizontal:
        assert y == round(300 * 0.14) and x < y
    else:
        assert x == round(300 * 0.14) and y < x
    holes = style.holes(size, params)
    assert len(holes) % 2 == 0 and len(holes) >= 4
    tile = render("filmstrip", size)
    for left, top, right, bottom in holes:
        assert alpha(tile, round((left + right) / 2), round((top + bottom) / 2)) == 0


def test_filmstrip_band_range() -> None:
    with pytest.raises(StyleError, match=r"between 0\.05 and 0\.3"):
        get_style("filmstrip").resolve({"band": 0.5})


def test_filmstrip_tiny_tile_has_no_holes() -> None:
    style = FilmstripStyle()
    assert style.holes((10, 6), style.resolve({})) == []
