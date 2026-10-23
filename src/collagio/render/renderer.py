"""Rendering a project to an image at any scale.

Preview and export use the same code path; only `scale` differs. Photos are
drawn in z order: crop to the style's content area, frame with the style,
rotate, composite.
"""

from __future__ import annotations

from collections.abc import Callable

from PIL import Image

from collagio.core.model import PhotoItem, Project
from collagio.core.rng import derive_rng
from collagio.errors import RenderError
from collagio.imaging.loader import load_image
from collagio.imaging.smartcrop import crop_pixels, fill_crop
from collagio.render.background import render_background
from collagio.styles import StyleContext, get_style

Loader = Callable[[str], Image.Image]

STYLE_UNITS_PER_SHORT_EDGE = 1000


def _pixel_box(item: PhotoItem, scale: float) -> tuple[int, int, int, int]:
    """Rect rounded per edge, so neighbouring cells keep exact gaps."""
    if item.rect is None:
        raise RenderError(f"photo {item.id} has no position; generate a layout first")
    left = round(item.rect.x * scale)
    top = round(item.rect.y * scale)
    right = round(item.rect.right * scale)
    bottom = round(item.rect.bottom * scale)
    return left, top, max(1, right - left), max(1, bottom - top)


def render_item(
    project: Project, item: PhotoItem, scale: float, loader: Loader
) -> tuple[Image.Image, tuple[int, int]]:
    """Styled, rotated RGBA tile of one photo and its top-left position on the canvas."""
    left, top, width, height = _pixel_box(item, scale)
    style_ref = project.style_for(item)
    style = get_style(style_ref.name)
    params = style.resolve(style_ref.params)
    ctx = StyleContext(
        unit=project.canvas.short_edge * scale / STYLE_UNITS_PER_SHORT_EDGE,
        rng=derive_rng(project.seed, "style", item.id),
    )

    _, _, content_w, content_h = style.content_box((width, height), params, ctx)
    source = loader(item.path)
    crop = item.crop or fill_crop(source.size, content_w / content_h)
    content = source.resize(
        (content_w, content_h),
        Image.Resampling.LANCZOS,
        box=crop_pixels(crop, source.size),
        reducing_gap=3.0,
    )
    tile = style.render(content, (width, height), params, ctx)

    if item.rotation % 360:
        tile = tile.rotate(item.rotation, Image.Resampling.BICUBIC, expand=True)
        left += (width - tile.width) // 2
        top += (height - tile.height) // 2
    return tile, (left, top)


def render_project(
    project: Project, scale: float = 1.0, loader: Loader = load_image
) -> Image.Image:
    if scale <= 0:
        raise RenderError(f"scale must be positive, got {scale}")
    size = (
        max(1, round(project.canvas.width * scale)),
        max(1, round(project.canvas.height * scale)),
    )
    canvas = render_background(project.canvas.background, size)
    for item in sorted(project.photos, key=lambda p: p.z):
        tile, position = render_item(project, item, scale, loader)
        canvas.paste(tile, position, tile)
    return canvas
