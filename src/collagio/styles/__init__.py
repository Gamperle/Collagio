"""Photo styles. Importing this package registers all built-in styles."""

from collagio.styles import cutout, filmstrip, plain, polaroid, stamp, tape, torn
from collagio.styles.base import Style, StyleContext, available_styles, get_style

__all__ = [
    "Style",
    "StyleContext",
    "available_styles",
    "cutout",
    "filmstrip",
    "get_style",
    "plain",
    "polaroid",
    "stamp",
    "tape",
    "torn",
]
