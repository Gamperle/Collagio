"""Texts shown in the editor that are not written literally in the widget code.

Undo labels come from the core, style parameter names and choices from the
style definitions, texture names from the renderer. They are listed here with
QT_TRANSLATE_NOOP so `pyside6-lupdate` picks them up; `translated()` looks them
up at run time. A test checks that every such string is listed.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from collagio.core.serialize import LEGACY_SUFFIXES, PROJECT_SUFFIX
from collagio.imaging.loader import SUPPORTED_SUFFIXES

COMMANDS = "Commands"
PARAMETERS = "Style parameters"
CHOICES = "Style choices"
TEXTURES = "Textures"

_LISTED = (
    # Undo labels
    QT_TRANSLATE_NOOP("Commands", "Add photos"),
    QT_TRANSLATE_NOOP("Commands", "Add text"),
    QT_TRANSLATE_NOOP("Commands", "Change canvas"),
    QT_TRANSLATE_NOOP("Commands", "Change shadow"),
    QT_TRANSLATE_NOOP("Commands", "Change stacking order"),
    QT_TRANSLATE_NOOP("Commands", "Change style"),
    QT_TRANSLATE_NOOP("Commands", "Crop photo"),
    QT_TRANSLATE_NOOP("Commands", "Edit text"),
    QT_TRANSLATE_NOOP("Commands", "Move photo"),
    QT_TRANSLATE_NOOP("Commands", "Move text"),
    QT_TRANSLATE_NOOP("Commands", "New layout"),
    QT_TRANSLATE_NOOP("Commands", "Remove photos"),
    QT_TRANSLATE_NOOP("Commands", "Remove text"),
    QT_TRANSLATE_NOOP("Commands", "Resize photo"),
    QT_TRANSLATE_NOOP("Commands", "Rotate photo"),
    QT_TRANSLATE_NOOP("Commands", "Swap photos"),
    # Style parameters (shown as the parameter name with "_" replaced and capitalised)
    QT_TRANSLATE_NOOP("Style parameters", "Band"),
    QT_TRANSLATE_NOOP("Style parameters", "Border color"),
    QT_TRANSLATE_NOOP("Style parameters", "Border width"),
    QT_TRANSLATE_NOOP("Style parameters", "Bottom width"),
    QT_TRANSLATE_NOOP("Style parameters", "Caption"),
    QT_TRANSLATE_NOOP("Style parameters", "Caption color"),
    QT_TRANSLATE_NOOP("Style parameters", "Caption size"),
    QT_TRANSLATE_NOOP("Style parameters", "Corner color"),
    QT_TRANSLATE_NOOP("Style parameters", "Corner radius"),
    QT_TRANSLATE_NOOP("Style parameters", "Corner size"),
    QT_TRANSLATE_NOOP("Style parameters", "Fibre width"),
    QT_TRANSLATE_NOOP("Style parameters", "Frame color"),
    QT_TRANSLATE_NOOP("Style parameters", "Hole radius"),
    QT_TRANSLATE_NOOP("Style parameters", "Hole spacing"),
    QT_TRANSLATE_NOOP("Style parameters", "Orientation"),
    QT_TRANSLATE_NOOP("Style parameters", "Paper color"),
    QT_TRANSLATE_NOOP("Style parameters", "Roughness"),
    QT_TRANSLATE_NOOP("Style parameters", "Segment"),
    QT_TRANSLATE_NOOP("Style parameters", "Sides"),
    QT_TRANSLATE_NOOP("Style parameters", "Tape color"),
    QT_TRANSLATE_NOOP("Style parameters", "Tape length"),
    QT_TRANSLATE_NOOP("Style parameters", "Tape opacity"),
    QT_TRANSLATE_NOOP("Style parameters", "Tape width"),
    QT_TRANSLATE_NOOP("Style parameters", "Text color"),
    QT_TRANSLATE_NOOP("Style parameters", "Text size"),
    QT_TRANSLATE_NOOP("Style parameters", "Texture"),
    QT_TRANSLATE_NOOP("Style parameters", "Value"),
    QT_TRANSLATE_NOOP("Style parameters", "Variant"),
    # Style choices
    QT_TRANSLATE_NOOP("Style choices", "auto"),
    QT_TRANSLATE_NOOP("Style choices", "corners"),
    QT_TRANSLATE_NOOP("Style choices", "horizontal"),
    QT_TRANSLATE_NOOP("Style choices", "tape"),
    QT_TRANSLATE_NOOP("Style choices", "vertical"),
    # File dialog filters
    QT_TRANSLATE_NOOP("Files", "Collagio projects"),
    QT_TRANSLATE_NOOP("Files", "Photos"),
    QT_TRANSLATE_NOOP("Files", "PNG image"),
    QT_TRANSLATE_NOOP("Files", "JPEG image"),
    QT_TRANSLATE_NOOP("Files", "PDF for printing"),
    QT_TRANSLATE_NOOP("Files", "Fonts"),
    # Textures (capitalised names)
    QT_TRANSLATE_NOOP("Textures", "Paper"),
    QT_TRANSLATE_NOOP("Textures", "Cork"),
    QT_TRANSLATE_NOOP("Textures", "Wood"),
)


def _filter(name: str, patterns: list[str]) -> str:
    return f"{translated('Files', name)} ({' '.join(patterns)})"


def project_filter() -> str:
    return _filter("Collagio projects", [f"*{s}" for s in (PROJECT_SUFFIX, *LEGACY_SUFFIXES)])


def image_filter() -> str:
    return _filter("Photos", [f"*{s}" for s in sorted(SUPPORTED_SUFFIXES)])


def export_filter() -> str:
    return ";;".join(
        (
            _filter("PNG image", ["*.png"]),
            _filter("JPEG image", ["*.jpg", "*.jpeg"]),
            _filter("PDF for printing", ["*.pdf"]),
        )
    )


def font_filter() -> str:
    return _filter("Fonts", ["*.ttf", "*.otf"])


def translated(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


def command_label(label: str) -> str:
    return translated(COMMANDS, label)


def parameter_label(name: str) -> str:
    return translated(PARAMETERS, name.replace("_", " ").capitalize())


def choice_label(value: str) -> str:
    return translated(CHOICES, value)


def texture_label(name: str) -> str:
    return translated(TEXTURES, name.capitalize())


def listed() -> set[tuple[str, str]]:
    """(context, text) of every string listed above (for tests)."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "QT_TRANSLATE_NOOP":
            context, text = node.args
            assert isinstance(context, ast.Constant)
            assert isinstance(text, ast.Constant)
            found.add((str(context.value), str(text.value)))
    return found
