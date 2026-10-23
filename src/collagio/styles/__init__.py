"""Photo styles. Importing this package registers all built-in styles."""

from collagio.styles import plain
from collagio.styles.base import Style, StyleContext, available_styles, get_style

__all__ = ["Style", "StyleContext", "available_styles", "get_style", "plain"]
