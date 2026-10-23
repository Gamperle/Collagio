"""Rendering a project to an image at any scale.

Preview and export use the same code path; only `scale` differs. Photos are
drawn in z order: crop to the style's content area, frame with the style,
rotate, add the drop shadow, composite. Each photo's shadow is drawn right
under that photo, so it falls onto the photos below it.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PIL import Image, ImageFilter

from collagio.core.model import PhotoItem, Project, Shadow, TextItem
from collagio.core.rng import derive_seed
from collagio.errors import RenderError
from collagio.imaging.loader import load_image
from collagio.imaging.smartcrop import crop_pixels, fill_crop
from collagio.render.background import parse_color, render_background
from collagio.render.text import render_text
from collagio.styles import StyleContext, get_style
from collagio.styles.base import STYLE_UNITS_PER_SHORT_EDGE

Loader = Callable[[str], Image.Image]
Progress = Callable[[int, int], None]


TEXT_SHADOW = Shadow(opacity=0.6, blur=4.0, offset_x=2.0, offset_y=3.0)  # if shadows are off


class RenderCancelledError(Exception):
    """Raised by a progress callback to stop rendering."""


def _pixel_box(item: PhotoItem, scale: float) -> tuple[int, int, int, int]:
    """Rect rounded per edge, so neighbouring cells keep exact gaps."""
    if item.rect is None:
        raise RenderError(f"photo {item.id} has no position; generate a layout first")
    left = round(item.rect.x * scale)
    top = round(item.rect.y * scale)
    right = round(item.rect.right * scale)
    bottom = round(item.rect.bottom * scale)
    return left, top, max(1, right - left), max(1, bottom - top)


def style_unit(project: Project, scale: float) -> float:
    """Pixels per style unit at the given render scale."""
    return project.canvas.short_edge * scale / STYLE_UNITS_PER_SHORT_EDGE


def add_shadow(
    tile: Image.Image, shadow: Shadow, unit: float
) -> tuple[Image.Image, tuple[int, int]]:
    """The tile on top of its drop shadow, and the shift of the tile's top-left corner.

    The result is larger than the tile so the blurred, offset shadow fits.
    """
    if not 0.0 <= shadow.opacity <= 1.0:
        raise RenderError(f"shadow opacity must be between 0 and 1, got {shadow.opacity}")
    if shadow.opacity == 0.0:
        return tile, (0, 0)
    if shadow.blur < 0:
        raise RenderError(f"shadow blur must not be negative, got {shadow.blur}")
    color = parse_color(shadow.color)
    blur = shadow.blur * unit
    offset_x, offset_y = round(shadow.offset_x * unit), round(shadow.offset_y * unit)
    pad = math.ceil(3 * blur) + max(abs(offset_x), abs(offset_y))

    size = (tile.width + 2 * pad, tile.height + 2 * pad)
    mask = Image.new("L", size, 0)
    alpha = tile.getchannel("A").point(lambda a: round(a * shadow.opacity))
    mask.paste(alpha, (pad + offset_x, pad + offset_y))
    if blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    result = Image.new("RGBA", size, (*color, 0))
    result.putalpha(mask)
    result.alpha_composite(tile, (pad, pad))
    return result, (-pad, -pad)


def content_aspect(project: Project, item: PhotoItem) -> float:
    """Aspect ratio of the area the photo's style leaves for the photo itself."""
    _, _, width, height = _pixel_box(item, 1.0)
    style_ref = project.style_for(item)
    style = get_style(style_ref.name)
    ctx = StyleContext(
        unit=style_unit(project, 1.0), seed=derive_seed(project.seed, "style", item.id)
    )
    _, _, content_w, content_h = style.content_box(
        (width, height), style.resolve(style_ref.params), ctx
    )
    return content_w / content_h


def render_item(
    project: Project, item: PhotoItem, scale: float, loader: Loader
) -> tuple[Image.Image, tuple[int, int]]:
    """Styled, rotated RGBA tile of one photo and its top-left position on the canvas."""
    left, top, width, height = _pixel_box(item, scale)
    style_ref = project.style_for(item)
    style = get_style(style_ref.name)
    params = style.resolve(style_ref.params)
    ctx = StyleContext(
        unit=style_unit(project, scale),
        seed=derive_seed(project.seed, "style", item.id),
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


def render_photo(
    project: Project, item: PhotoItem, scale: float, loader: Loader
) -> tuple[Image.Image, tuple[int, int]]:
    """One photo exactly as it appears in the collage (styled, rotated, with shadow)
    and the canvas position of the image's top-left corner."""
    tile, (left, top) = render_item(project, item, scale, loader)
    tile, (shift_x, shift_y) = add_shadow(tile, project.shadow, style_unit(project, scale))
    return tile, (left + shift_x, top + shift_y)


def text_tile(
    project: Project, item: TextItem, scale: float
) -> tuple[Image.Image, tuple[int, int]]:
    """A text item as drawn on the collage, and the position of its top-left corner."""
    unit = style_unit(project, scale)
    tile = render_text(item, unit)
    left = round(item.x * scale) - tile.width // 2
    top = round(item.y * scale) - tile.height // 2
    if item.shadow:
        shadow = project.shadow if project.shadow.opacity > 0 else TEXT_SHADOW
        tile, (shift_x, shift_y) = add_shadow(tile, shadow, unit)
        left, top = left + shift_x, top + shift_y
    return tile, (left, top)


def render_texts(project: Project, canvas: Image.Image, scale: float, offset: int = 0) -> None:
    """Draw the project's text items onto `canvas` (`offset`: bleed in pixels)."""
    for item in project.texts:
        tile, (left, top) = text_tile(project, item, scale)
        canvas.paste(tile, (left + offset, top + offset), tile)


def render_project(
    project: Project,
    scale: float = 1.0,
    loader: Loader = load_image,
    progress: Progress | None = None,
    bleed: float = 0.0,
) -> Image.Image:
    """The whole collage. `progress(done, total)` is called after each photo; it
    may raise (e.g. RenderCancelledError) to stop rendering.

    `bleed` (canvas pixels) extends the image on every side; the background
    fills it and everything else moves inwards by the same amount.
    """
    if scale <= 0:
        raise RenderError(f"scale must be positive, got {scale}")
    if bleed < 0:
        raise RenderError(f"bleed must not be negative, got {bleed}")
    offset = round(bleed * scale)
    size = (
        max(1, round(project.canvas.width * scale)) + 2 * offset,
        max(1, round(project.canvas.height * scale)) + 2 * offset,
    )
    canvas = render_background(
        project.canvas.background,
        size,
        unit=style_unit(project, scale),
        seed=project.seed,
        loader=loader,
    )
    total = len(project.photos)
    if progress is not None:
        progress(0, total)
    for done, item in enumerate(sorted(project.photos, key=lambda p: p.z), start=1):
        tile, (left, top) = render_photo(project, item, scale, loader)
        canvas.paste(tile, (left + offset, top + offset), tile)
        if progress is not None:
            progress(done, total)
    render_texts(project, canvas, scale, offset)
    return canvas
