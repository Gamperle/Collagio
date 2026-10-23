from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from collagio.core.model import (
    Canvas,
    CropBox,
    LayoutMode,
    LayoutSettings,
    Project,
    Rect,
    StyleRef,
)
from collagio.errors import LayoutError
from collagio.layout import apply as apply_module
from collagio.layout.apply import apply_layout, build_project, framed_aspect
from collagio.styles import StyleContext, get_style

SIZES = {"land.jpg": (600, 400), "port.jpg": (400, 600), "square.jpg": (500, 500)}


def size_of(path: str) -> tuple[int, int]:
    return SIZES[Path(path).name]


def test_build_project_places_all_photos() -> None:
    project = build_project(list(SIZES), Canvas(2000, 1500), seed=7, size_of=size_of)
    assert [p.id for p in project.photos] == ["p001", "p002", "p003"]
    assert all(p.rect is not None for p in project.photos)
    assert [p.z for p in project.photos] == [0, 1, 2]
    assert project.seed == 7
    assert project.layout == LayoutSettings()
    assert project.default_style == StyleRef()


def test_gap_and_margin_are_relative_to_short_edge() -> None:
    layout = LayoutSettings(gap=0.02, margin=0.05, size_variation=0)
    project = build_project(list(SIZES), Canvas(2000, 1000), layout=layout, seed=1, size_of=size_of)
    rects = [p.rect for p in project.photos]
    assert all(r is not None for r in rects)
    left = min(r.x for r in rects if r is not None)
    top = min(r.y for r in rects if r is not None)
    assert (left, top) == (pytest.approx(50), pytest.approx(50))


def test_custom_style_is_kept() -> None:
    style = StyleRef("plain", {"border_width": 5})
    project = build_project(list(SIZES), Canvas(800, 600), default_style=style, size_of=size_of)
    assert project.default_style == style


def test_relayout_resets_manual_edits_but_keeps_styles() -> None:
    project = build_project(list(SIZES), Canvas(2000, 1500), seed=3, size_of=size_of)
    original = [p.rect for p in project.photos]
    item = project.photos[0]
    item.rect = Rect(0, 0, 1, 1)
    item.rotation = 12
    item.crop = CropBox(0, 0, 0.5, 0.5)
    item.style = StyleRef("plain", {"border_width": 2})
    apply_layout(project, size_of)
    assert [p.rect for p in project.photos] == original
    assert (item.rotation, item.crop) == (0.0, None)
    assert item.style == StyleRef("plain", {"border_width": 2})


def test_seed_controls_the_layout() -> None:
    names = list(SIZES) * 3
    a = build_project(names, Canvas(2000, 1500), seed=1, size_of=size_of)
    b = build_project(names, Canvas(2000, 1500), seed=1, size_of=size_of)
    c = build_project(names, Canvas(2000, 1500), seed=2, size_of=size_of)
    assert [p.rect for p in a.photos] == [p.rect for p in b.photos]
    assert [p.rect for p in a.photos] != [p.rect for p in c.photos]


@pytest.mark.parametrize("count", [0, 1, 101])
def test_photo_count_limits(count: int) -> None:
    with pytest.raises(LayoutError, match="2 to 100 photos"):
        build_project(["land.jpg"] * count, Canvas(2000, 1500), size_of=size_of)


def test_real_files_use_exif_oriented_size(
    sample_photos: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[float]] = []
    real_grid_layout = apply_module.grid_layout

    def spy(aspects: list[float], *args: Any) -> list[Rect]:
        seen.append(list(aspects))
        return real_grid_layout(aspects, *args)

    monkeypatch.setattr(apply_module, "grid_layout", spy)
    exif = next(p for p in sample_photos if "exif_rotated" in p.name)
    land = next(p for p in sample_photos if "01_landscape" in p.name)
    build_project([exif, land], Canvas(1000, 1000), seed=0)
    assert seen == [[pytest.approx(400 / 600), pytest.approx(600 / 400)]]


def test_scattered_mode_sets_rotation_and_stacking() -> None:
    layout = LayoutSettings(mode=LayoutMode.SCATTERED, max_rotation=20, overlap=0.6)
    names = list(SIZES) * 4
    project = build_project(names, Canvas(2000, 1500), layout=layout, seed=5, size_of=size_of)
    assert sorted(p.z for p in project.photos) == list(range(len(names)))
    assert any(p.rotation != 0 for p in project.photos)
    assert all(abs(p.rotation) <= 20 for p in project.photos)
    for item in project.photos:
        assert item.rect is not None
        assert item.rect.aspect == pytest.approx(size_of(item.path)[0] / size_of(item.path)[1])


def test_scattered_margin_is_relative_to_short_edge() -> None:
    layout = LayoutSettings(mode=LayoutMode.SCATTERED, margin=0.1, max_rotation=0)
    project = build_project(list(SIZES), Canvas(2000, 1000), layout=layout, size_of=size_of)
    for item in project.photos:
        assert item.rect is not None
        assert item.rect.x >= 100 - 1e-6
        assert item.rect.right <= 1900 + 1e-6


def test_switching_mode_resets_rotation() -> None:
    names = list(SIZES) * 2
    project = build_project(
        names,
        Canvas(2000, 1500),
        layout=LayoutSettings(mode=LayoutMode.SCATTERED, max_rotation=30),
        size_of=size_of,
    )
    project.layout.mode = LayoutMode.GRID
    apply_layout(project, size_of)
    assert all(p.rotation == 0 for p in project.photos)
    assert [p.z for p in project.photos] == list(range(len(names)))


# --- tiles shaped for photo + frame --------------------------------------------------------------


def _project_with(style: StyleRef, mode: LayoutMode = LayoutMode.SCATTERED) -> Project:
    names = list(SIZES) * 2
    return build_project(
        names,
        Canvas(3000, 2000),
        layout=LayoutSettings(mode=mode, max_rotation=0),
        default_style=style,
        seed=4,
        size_of=size_of,
    )


def test_framed_aspect_without_frame_is_the_photo_aspect() -> None:
    project = _project_with(StyleRef())
    assert framed_aspect(project, project.photos[0], 1.5, 500_000) == pytest.approx(1.5)


def test_polaroid_tiles_are_taller_than_the_photo() -> None:
    project = _project_with(StyleRef("polaroid"))
    assert framed_aspect(project, project.photos[0], 1.5, 500_000) < 1.4


@pytest.mark.parametrize(
    ("style", "params", "names"),
    [
        ("polaroid", {}, None),
        ("stamp", {}, None),
        ("tape", {}, None),
        ("cutout", {}, None),
        # Automatic film orientation follows the photo, so square photos fit too.
        ("filmstrip", {}, ["land.jpg", "port.jpg", "square.jpg"]),
        ("filmstrip", {"orientation": "horizontal"}, ["square.jpg", "land.jpg"]),
        ("filmstrip", {"orientation": "vertical"}, ["square.jpg", "port.jpg"]),
    ],
)
def test_scattered_photos_fit_their_frames(
    style: str, params: dict[str, Any], names: list[str] | None
) -> None:
    """The style's photo area has (nearly) the photo's shape: little cropping."""
    project = build_project(
        (names or list(SIZES)) * 2,
        Canvas(3000, 2000),
        layout=LayoutSettings(mode=LayoutMode.SCATTERED, max_rotation=0),
        default_style=StyleRef(style, params),
        seed=4,
        size_of=size_of,
    )
    get = get_style(style)
    for item in project.photos:
        assert item.rect is not None
        size = (round(item.rect.width), round(item.rect.height))
        photo_w, photo_h = size_of(item.path)
        # Canvas short edge 2000 -> 2 px per unit.
        ctx = StyleContext(unit=2.0, seed=0, photo_aspect=photo_w / photo_h)
        _, _, w, h = get.content_box(size, get.resolve(params), ctx)
        assert w / h == pytest.approx(photo_w / photo_h, rel=0.03)


def test_per_photo_styles_shape_their_own_tiles() -> None:
    project = _project_with(StyleRef())
    project.photos[0].style = StyleRef("polaroid")
    apply_layout(project, size_of)
    first, second = project.photos[0].rect, project.photos[3].rect  # both land.jpg
    assert first is not None and second is not None
    assert first.aspect < second.aspect


@pytest.mark.parametrize("mode", list(LayoutMode))
def test_space_above_and_below_is_kept_free(mode: LayoutMode) -> None:
    layout = LayoutSettings(mode=mode, margin=0.0, space_top=0.1, space_bottom=0.2, max_rotation=0)
    project = build_project(list(SIZES) * 2, Canvas(2000, 1000), layout=layout, size_of=size_of)
    for item in project.photos:
        assert item.rect is not None
        assert item.rect.y >= 100 - 1e-6
        assert item.rect.bottom <= 1000 - 200 + 1e-6


def test_too_much_space_is_reported() -> None:
    layout = LayoutSettings(margin=0.1, space_top=0.5, space_bottom=0.4)
    with pytest.raises(LayoutError, match="plus free space is too large"):
        build_project(list(SIZES), Canvas(2000, 1000), layout=layout, size_of=size_of)
