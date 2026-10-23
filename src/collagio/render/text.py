"""Text items (titles, captions) drawn on top of the collage."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from collagio.core.model import TextItem
from collagio.errors import RenderError
from collagio.render.background import parse_color

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def load_font(path: str, size_px: int) -> Font:
    """`path` to a TrueType/OpenType font, or "" for the built-in font."""
    size_px = max(1, size_px)
    if not path:
        return ImageFont.load_default(size=size_px)
    try:
        return ImageFont.truetype(path, size_px)
    except OSError as exc:
        raise RenderError(f"cannot load font {path}: {exc}") from exc


def text_size(item: TextItem, unit: float) -> tuple[int, int]:
    """Width and height of the unrotated text block in pixels."""
    font = load_font(item.font, round(item.size * unit))
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = probe.multiline_textbbox(
        (0, 0), item.text, font=font, anchor="mm", align="center"
    )
    return max(1, round(right - left)), max(1, round(bottom - top))


def render_text(item: TextItem, unit: float) -> Image.Image:
    """The text as an RGBA image, rotated, centred on its own middle."""
    if not item.text.strip():
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    color = parse_color(item.color)
    font = load_font(item.font, round(item.size * unit))
    width, height = text_size(item, unit)
    pad = max(2, round(item.size * unit * 0.2))
    tile = Image.new("RGBA", (width + 2 * pad, height + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(tile).multiline_text(
        (tile.width / 2, tile.height / 2),
        item.text,
        fill=color,
        font=font,
        anchor="mm",
        align="center",
    )
    if item.rotation % 360:
        tile = tile.rotate(item.rotation, Image.Resampling.BICUBIC, expand=True)
    return tile
