"""Building a project from photos and (re)generating its layout."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from collagio.core.model import (
    MAX_PHOTOS,
    MIN_PHOTOS,
    Canvas,
    LayoutMode,
    LayoutSettings,
    PhotoItem,
    Project,
    StyleRef,
)
from collagio.core.rng import derive_rng
from collagio.errors import LayoutError
from collagio.imaging.loader import oriented_size
from collagio.layout.grid import GridSettings, grid_layout

SizeOf = Callable[[str], tuple[int, int]]


def check_photo_count(count: int) -> None:
    if not MIN_PHOTOS <= count <= MAX_PHOTOS:
        raise LayoutError(f"a collage needs {MIN_PHOTOS} to {MAX_PHOTOS} photos, got {count}")


def apply_layout(project: Project, size_of: SizeOf = oriented_size) -> None:
    """Place every photo according to the project's layout settings and seed.

    Manual changes (position, rotation, crop) are replaced; styles are kept.
    """
    check_photo_count(len(project.photos))
    settings = project.layout
    short_edge = project.canvas.short_edge
    aspects = []
    for item in project.photos:
        width, height = size_of(item.path)
        aspects.append(width / height)

    if settings.mode is LayoutMode.GRID:
        rects = grid_layout(
            aspects,
            project.canvas.width,
            project.canvas.height,
            GridSettings(
                gap=settings.gap * short_edge,
                margin=settings.margin * short_edge,
                size_variation=settings.size_variation,
                order=settings.order,
            ),
            derive_rng(project.seed, "layout", settings.mode.value),
        )
    else:  # pragma: no cover - guarded by the LayoutMode enum
        raise LayoutError(f"unsupported layout mode {settings.mode}")

    for z, (item, rect) in enumerate(zip(project.photos, rects, strict=True)):
        item.rect = rect
        item.rotation = 0.0
        item.crop = None
        item.z = z


def build_project(
    paths: Sequence[str | Path],
    canvas: Canvas,
    layout: LayoutSettings | None = None,
    default_style: StyleRef | None = None,
    seed: int = 0,
    size_of: SizeOf = oriented_size,
) -> Project:
    check_photo_count(len(paths))
    project = Project(
        canvas=canvas,
        photos=[PhotoItem(id=f"p{i:03d}", path=str(p)) for i, p in enumerate(paths, start=1)],
        layout=layout if layout is not None else LayoutSettings(),
        default_style=default_style if default_style is not None else StyleRef(),
        seed=seed,
    )
    apply_layout(project, size_of)
    return project
