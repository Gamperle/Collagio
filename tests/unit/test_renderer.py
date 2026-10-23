from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from collagio.core.model import Canvas, CropBox, PhotoItem, Project, Rect, Shadow, StyleRef
from collagio.errors import RenderError
from collagio.render.renderer import render_project

RED, BLUE, WHITE = (255, 0, 0), (0, 0, 255), (255, 255, 255)


def split_image(_: str) -> Image.Image:
    """Left half red, right half blue (200x100)."""
    image = Image.new("RGB", (200, 100), RED)
    ImageDraw.Draw(image).rectangle((100, 0, 199, 99), fill=BLUE)
    return image


def _project(*items: PhotoItem, style: StyleRef | None = None) -> Project:
    return Project(canvas=Canvas(200, 100), photos=list(items), default_style=style or StyleRef())


def test_background_only() -> None:
    image = render_project(_project(), loader=split_image)
    assert image.size == (200, 100)
    assert image.getcolors() == [(20000, WHITE)]


def test_photo_fills_its_rect() -> None:
    item = PhotoItem("a", "a", rect=Rect(10, 10, 80, 80))  # square cell: crop to centre
    image = render_project(_project(item), loader=split_image)
    assert image.getpixel((5, 50)) == WHITE
    assert image.getpixel((15, 50)) == RED
    assert image.getpixel((85, 50)) == BLUE
    assert image.getpixel((95, 50)) == WHITE


def test_explicit_crop_is_used() -> None:
    item = PhotoItem("a", "a", rect=Rect(0, 0, 100, 100), crop=CropBox(0, 0, 0.5, 1))
    image = render_project(_project(item), loader=split_image)
    assert image.crop((0, 0, 100, 100)).getcolors() == [(10000, RED)]


def test_scale_changes_output_size_and_positions() -> None:
    item = PhotoItem("a", "a", rect=Rect(100, 0, 100, 100), crop=CropBox(0, 0, 0.5, 1))
    image = render_project(_project(item), scale=0.5, loader=split_image)
    assert image.size == (100, 50)
    assert image.getpixel((40, 25)) == WHITE
    assert image.getpixel((60, 25)) == RED


def test_z_order() -> None:
    below = PhotoItem("below", "a", rect=Rect(0, 0, 100, 100), crop=CropBox(0, 0, 0.5, 1), z=0)
    above = PhotoItem("above", "a", rect=Rect(50, 0, 100, 100), crop=CropBox(0.5, 0, 0.5, 1), z=1)
    for photos in ([below, above], [above, below]):  # list order must not matter
        image = render_project(_project(*photos), loader=split_image)
        assert image.getpixel((75, 50)) == BLUE


def test_rotation_keeps_centre_and_expands() -> None:
    item = PhotoItem("a", "a", rect=Rect(60, 10, 80, 80), crop=CropBox(0, 0, 0.5, 1), rotation=45)
    image = render_project(_project(item), loader=split_image)
    assert image.getpixel((100, 50)) == RED  # centre stays put
    assert image.getpixel((100, 3)) == RED  # rotated corner pokes out above the rect
    assert image.getpixel((62, 12)) == WHITE  # original corner is now empty


def test_full_turn_is_not_rotated() -> None:
    a = PhotoItem("a", "a", rect=Rect(10, 10, 80, 80))
    b = PhotoItem("a", "a", rect=Rect(10, 10, 80, 80), rotation=360)
    assert (
        render_project(_project(a), loader=split_image).tobytes()
        == render_project(_project(b), loader=split_image).tobytes()
    )


def test_style_is_applied() -> None:
    item = PhotoItem("a", "a", rect=Rect(0, 0, 100, 100))
    style = StyleRef(
        "plain", {"border_width": 50, "border_color": "#00ff00"}
    )  # 50/1000 * 100 = 5 px
    image = render_project(_project(item, style=style), loader=split_image)
    assert image.getpixel((2, 50)) == (0, 255, 0)
    assert image.getpixel((7, 50)) == RED


def test_per_photo_style_overrides_default() -> None:
    item = PhotoItem(
        "a", "a", rect=Rect(0, 0, 100, 100), style=StyleRef("plain", {"border_width": 0})
    )
    style = StyleRef("plain", {"border_width": 50, "border_color": "#00ff00"})
    image = render_project(_project(item, style=style), loader=split_image)
    assert image.getpixel((2, 50)) == RED


def test_alpha_photos_are_composited() -> None:
    def transparent(_: str) -> Image.Image:
        return Image.new("RGBA", (10, 10), (0, 0, 0, 0))

    item = PhotoItem("a", "a", rect=Rect(0, 0, 100, 100))
    image = render_project(_project(item), loader=transparent)
    assert image.getpixel((50, 50)) == WHITE


def test_adjacent_cells_have_exact_gap_after_rounding() -> None:
    items = [
        PhotoItem("a", "a", rect=Rect(0.4, 0, 33.3, 100)),
        PhotoItem("b", "a", rect=Rect(43.7, 0, 33.3, 100)),
    ]
    image = render_project(_project(*items), scale=3, loader=split_image)
    row = [image.getpixel((x, 150)) for x in range(image.width)]
    white_run = [x for x in range(1, 240) if row[x] == WHITE and row[x - 1] != WHITE]
    gap_start = white_run[0]
    gap_end = next(x for x in range(gap_start, image.width) if row[x] != WHITE)
    assert gap_end - gap_start == round(43.7 * 3) - round(33.7 * 3)


def test_missing_rect() -> None:
    with pytest.raises(RenderError, match="no position"):
        render_project(_project(PhotoItem("a", "a")), loader=split_image)


@pytest.mark.parametrize("scale", [0, -1])
def test_invalid_scale(scale: float) -> None:
    with pytest.raises(RenderError, match="scale"):
        render_project(_project(), scale=scale)


def test_default_loader_reads_files(sample_photos: list[Path]) -> None:
    item = PhotoItem("a", str(sample_photos[0]), rect=Rect(0, 0, 200, 100))
    image = render_project(_project(item))
    assert image.getpixel((100, 50)) != WHITE


# --- drop shadow ---------------------------------------------------------------------------

BLACK = (0, 0, 0)


def _shadow_project(shadow: Shadow, scale_size: int = 1000) -> Project:
    # Short edge 1000 px -> 1 style unit = 1 px.
    return Project(
        canvas=Canvas(scale_size, scale_size),
        photos=[PhotoItem("a", "a", rect=Rect(100, 100, 200, 200), crop=CropBox(0, 0, 0.5, 1))],
        shadow=shadow,
    )


def test_no_shadow_by_default() -> None:
    image = render_project(_shadow_project(Shadow()), loader=split_image)
    assert image.getpixel((305, 305)) == WHITE


def test_shadow_is_offset_below_right() -> None:
    shadow = Shadow(opacity=1.0, blur=0, offset_x=10, offset_y=20)
    image = render_project(_shadow_project(shadow), loader=split_image)
    assert image.getpixel((305, 200)) == BLACK  # right of the photo
    assert image.getpixel((200, 315)) == BLACK  # below the photo
    assert image.getpixel((95, 200)) == WHITE  # nothing on the left
    assert image.getpixel((200, 95)) == WHITE  # nothing above
    assert image.getpixel((200, 200)) == RED  # photo is on top of its shadow


def test_shadow_opacity_and_colour() -> None:
    shadow = Shadow(opacity=0.5, blur=0, offset_x=10, offset_y=10, color="#0000ff")
    image = render_project(_shadow_project(shadow), loader=split_image)
    assert image.getpixel((305, 200)) == pytest.approx((127, 127, 255), abs=1)


def test_shadow_blur_softens_edges() -> None:
    sharp = render_project(
        _shadow_project(Shadow(opacity=1.0, blur=0, offset_x=0, offset_y=0)), loader=split_image
    )
    soft = render_project(
        _shadow_project(Shadow(opacity=1.0, blur=8, offset_x=0, offset_y=0)), loader=split_image
    )
    assert sharp.getpixel((310, 200)) == WHITE
    assert BLACK < soft.getpixel((310, 200)) < WHITE  # type: ignore[operator]


def test_shadow_scales_with_render_scale() -> None:
    shadow = Shadow(opacity=1.0, blur=0, offset_x=20, offset_y=0)
    half = render_project(_shadow_project(shadow), scale=0.5, loader=split_image)
    # Photo ends at x=150, shadow offset 10 px at half scale.
    assert half.getpixel((155, 100)) == BLACK
    assert half.getpixel((162, 100)) == WHITE


def test_shadow_of_upper_photo_falls_on_lower_photo() -> None:
    project = _shadow_project(Shadow(opacity=1.0, blur=0, offset_x=10, offset_y=0))
    project.photos.append(
        PhotoItem("b", "a", rect=Rect(400, 100, 200, 200), crop=CropBox(0.5, 0, 0.5, 1), z=1)
    )
    project.photos[0].rect = Rect(250, 100, 200, 200)  # under photo b, sticking out left
    image = render_project(project, loader=split_image)
    assert image.getpixel((260, 200)) == RED  # lower photo
    assert image.getpixel((405, 200)) == BLUE  # upper photo
    assert image.getpixel((605, 200)) == BLACK  # upper photo's shadow


@pytest.mark.parametrize(
    ("shadow", "message"),
    [(Shadow(opacity=1.5), "opacity"), (Shadow(opacity=-0.1), "opacity"),
     (Shadow(opacity=0.5, blur=-1), "blur"), (Shadow(opacity=0.5, color="nope"), "colour")],
)  # fmt: skip
def test_invalid_shadow(shadow: Shadow, message: str) -> None:
    with pytest.raises(RenderError, match=message):
        render_project(_shadow_project(shadow), loader=split_image)
