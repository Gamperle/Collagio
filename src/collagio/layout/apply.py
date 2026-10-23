"""Building a project from photos and (re)generating its layout."""

from __future__ import annotations

import math
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
from collagio.core.rng import derive_rng, derive_seed
from collagio.errors import LayoutError
from collagio.imaging.loader import oriented_size
from collagio.layout.grid import GridSettings, grid_layout
from collagio.layout.scattered import Placement, ScatterSettings, scattered_layout
from collagio.styles import StyleContext, get_style
from collagio.styles.base import STYLE_UNITS_PER_SHORT_EDGE

SizeOf = Callable[[str], tuple[int, int]]

_FRAME_ITERATIONS = 6


def check_photo_count(count: int) -> None:
    if not MIN_PHOTOS <= count <= MAX_PHOTOS:
        raise LayoutError(f"a collage needs {MIN_PHOTOS} to {MAX_PHOTOS} photos, got {count}")


def framed_aspect(
    project: Project, item: PhotoItem, photo_aspect: float, tile_area: float
) -> float:
    """Aspect ratio of a tile of about `tile_area` whose style leaves room for a
    photo of `photo_aspect` without cropping."""
    style_ref = project.style_for(item)
    style = get_style(style_ref.name)
    params = style.resolve(style_ref.params)
    ctx = StyleContext(
        unit=project.canvas.short_edge / STYLE_UNITS_PER_SHORT_EDGE,
        seed=derive_seed(project.seed, "style", item.id),
        photo_aspect=photo_aspect,
    )
    a = photo_aspect
    tile_w, tile_h = math.sqrt(tile_area * a), math.sqrt(tile_area / a)
    best_error, best_aspect = math.inf, tile_w / tile_h
    # Borders may depend on the tile size (and frames can switch orientation),
    # so iterate and keep the tile shape whose photo area fits best.
    for _ in range(_FRAME_ITERATIONS):
        size = (max(1, round(tile_w)), max(1, round(tile_h)))
        _, _, box_w, box_h = style.content_box(size, params, ctx)
        error = abs(math.log(box_w / box_h / a))
        if error < best_error:
            best_error, best_aspect = error, tile_w / tile_h
        extra_w, extra_h = size[0] - box_w, size[1] - box_h
        # Photo height h with (a*h + extra_w) * (h + extra_h) = tile_area.
        b = a * extra_h + extra_w
        c = extra_w * extra_h - tile_area
        content_h = max(1.0, (-b + math.sqrt(max(0.0, b * b - 4 * a * c))) / (2 * a))
        tile_w, tile_h = a * content_h + extra_w, content_h + extra_h
    return best_aspect


def apply_layout(project: Project, size_of: SizeOf = oriented_size) -> None:
    """Place every photo according to the project's layout settings and seed.

    Manual changes (position, rotation, crop) are replaced; styles are kept.
    A single photo is allowed here (an editor may hold one while photos are being
    added); finished collages need MIN_PHOTOS, see `build_project`.
    """
    if not 1 <= len(project.photos) <= MAX_PHOTOS:
        check_photo_count(len(project.photos))
    settings = project.layout
    short_edge = project.canvas.short_edge
    # Tiles get the shape of photo plus frame, so styles with wide borders (e.g. a
    # Polaroid's bottom edge) do not force the photo into a different shape.
    nominal_area = project.canvas.width * project.canvas.height / len(project.photos)
    photo_aspects = []
    for item in project.photos:
        width, height = size_of(item.path)
        photo_aspects.append(width / height)
    aspects = [
        framed_aspect(project, item, aspect, nominal_area)
        for item, aspect in zip(project.photos, photo_aspects, strict=True)
    ]

    def tile_aspect(index: int, area: float) -> float:
        return framed_aspect(project, project.photos[index], photo_aspects[index], area)

    rng = derive_rng(project.seed, "layout", settings.mode.value)
    if settings.mode is LayoutMode.GRID:
        rects = grid_layout(
            aspects,
            project.canvas.width,
            project.canvas.height,
            GridSettings(
                gap=settings.gap * short_edge,
                margin=settings.margin * short_edge,
                extra_top=settings.space_top * short_edge,
                extra_bottom=settings.space_bottom * short_edge,
                size_variation=settings.size_variation,
                order=settings.order,
            ),
            rng,
        )
        placements = [Placement(rect, 0.0, z) for z, rect in enumerate(rects)]
    elif settings.mode is LayoutMode.SCATTERED:
        placements = scattered_layout(
            aspects,
            project.canvas.width,
            project.canvas.height,
            ScatterSettings(
                margin=settings.margin * short_edge,
                extra_top=settings.space_top * short_edge,
                extra_bottom=settings.space_bottom * short_edge,
                max_rotation=settings.max_rotation,
                overlap=settings.overlap,
                size_variation=settings.size_variation,
                min_visible=settings.min_visible,
            ),
            rng,
            tile_aspect,
        )
    else:  # pragma: no cover - guarded by the LayoutMode enum
        raise LayoutError(f"unsupported layout mode {settings.mode}")

    for item, placement in zip(project.photos, placements, strict=True):
        item.rect = placement.rect
        item.rotation = placement.rotation
        item.crop = None
        item.z = placement.z


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
