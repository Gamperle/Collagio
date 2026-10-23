from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from collagio.core.model import Canvas, CropBox, LayoutSettings, Rect, StyleRef
from collagio.errors import LayoutError
from collagio.layout import apply as apply_module
from collagio.layout.apply import apply_layout, build_project

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
