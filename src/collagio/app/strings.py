"""Texts shown in the editor that are not written literally in the widget code.

Undo labels and error messages come from the core, style parameter names and
choices from the style definitions, texture names from the renderer. They are listed here with
QT_TRANSLATE_NOOP so `pyside6-lupdate` picks them up; `translated()` looks them
up at run time. A test checks that every such string is listed.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from collagio.core.serialize import LEGACY_SUFFIXES, PROJECT_SUFFIX
from collagio.errors import CollagioError
from collagio.imaging.loader import SUPPORTED_SUFFIXES

COMMANDS = "Commands"
PARAMETERS = "Style parameters"
CHOICES = "Style choices"
TEXTURES = "Textures"
ERRORS = "Errors"

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
    # Error messages from the core (templates, see CollagioError)
    QT_TRANSLATE_NOOP("Errors", "DPI must be positive, got {dpi}"),
    QT_TRANSLATE_NOOP("Errors", "JPEG quality must be 1-100, got {quality}"),
    QT_TRANSLATE_NOOP("Errors", "a collage can have at most {maximum} photos ({total} requested)"),
    QT_TRANSLATE_NOOP("Errors", "a collage needs {minimum} to {maximum} photos, got {count}"),
    QT_TRANSLATE_NOOP("Errors", "background dim must be between 0 and 1, got {dim}"),
    QT_TRANSLATE_NOOP("Errors", "bleed must be between 0 and {maximum:g} mm, got {bleed:g}"),
    QT_TRANSLATE_NOOP("Errors", "bleed must not be negative, got {bleed}"),
    QT_TRANSLATE_NOOP("Errors", "cannot decode photo {path}: {error}"),
    QT_TRANSLATE_NOOP(
        "Errors",
        "cannot fit {count} photos with a {gap:g} px gap into {width:g}x{height:g} px",
    ),
    QT_TRANSLATE_NOOP("Errors", "cannot load font {path}: {error}"),
    QT_TRANSLATE_NOOP("Errors", "cannot read photo {path}: {error}"),
    QT_TRANSLATE_NOOP("Errors", "cannot swap photo {photo_id!r} with itself"),
    QT_TRANSLATE_NOOP("Errors", "cannot write {path}: {error}"),
    QT_TRANSLATE_NOOP("Errors", "canvas size {width}x{height} px is outside 1..{maximum} px"),
    QT_TRANSLATE_NOOP("Errors", "crop marks need PDF output (.pdf)"),
    QT_TRANSLATE_NOOP("Errors", "crop was not applied"),
    QT_TRANSLATE_NOOP("Errors", "invalid colour {value!r}"),
    QT_TRANSLATE_NOOP("Errors", "invalid project file: {error!r}"),
    QT_TRANSLATE_NOOP("Errors", "invalid schema_version {version!r}"),
    QT_TRANSLATE_NOOP(
        "Errors",
        "invalid size {spec!r}; use WIDTHxHEIGHT, WIDTHxHEIGHTmm or one of: {presets}",
    ),
    QT_TRANSLATE_NOOP("Errors", "margin {margin:g} px is too large for {width}x{height} px"),
    QT_TRANSLATE_NOOP(
        "Errors",
        "margin {margin:g} px plus free space is too large for {width}x{height} px",
    ),
    QT_TRANSLATE_NOOP("Errors", "move was not applied"),
    QT_TRANSLATE_NOOP("Errors", "no file name given"),
    QT_TRANSLATE_NOOP("Errors", "no photo chosen for the photo background"),
    QT_TRANSLATE_NOOP("Errors", "no photo with id {photo_id!r}"),
    QT_TRANSLATE_NOOP("Errors", "no text with id {text_id!r}"),
    QT_TRANSLATE_NOOP("Errors", "not a Collagio project file"),
    QT_TRANSLATE_NOOP("Errors", "not a folder: {folder}"),
    QT_TRANSLATE_NOOP("Errors", "photo aspect ratios must be positive"),
    QT_TRANSLATE_NOOP("Errors", "photo backgrounds need a photo loader"),
    QT_TRANSLATE_NOOP("Errors", "photo not found: {path}"),
    QT_TRANSLATE_NOOP("Errors", "photo {photo_id} has no position; generate a layout first"),
    QT_TRANSLATE_NOOP(
        "Errors",
        "project was saved by a newer Collagio (schema {version}, supported {supported})",
    ),
    QT_TRANSLATE_NOOP("Errors", "scale must be positive, got {scale}"),
    QT_TRANSLATE_NOOP("Errors", "shadow blur must not be negative, got {blur}"),
    QT_TRANSLATE_NOOP("Errors", "shadow opacity must be between 0 and 1, got {opacity}"),
    QT_TRANSLATE_NOOP("Errors", "stacking change was not applied"),
    QT_TRANSLATE_NOOP("Errors", "stamp.hole_radius must be at most half of border_width"),
    QT_TRANSLATE_NOOP("Errors", "stamp.hole_spacing must be larger than the hole diameter"),
    QT_TRANSLATE_NOOP("Errors", "style change was not applied"),
    QT_TRANSLATE_NOOP("Errors", "style {name!r} is already registered"),
    QT_TRANSLATE_NOOP("Errors", "swap was not applied"),
    QT_TRANSLATE_NOOP("Errors", "torn.sides must be 'all' or a list of {sides}, got {value!r}"),
    QT_TRANSLATE_NOOP("Errors", "unknown parameter(s) for style {style!r}: {names}"),
    QT_TRANSLATE_NOOP("Errors", "unknown style {name!r}; available: {available}"),
    QT_TRANSLATE_NOOP("Errors", "unknown text field {name!r}"),
    QT_TRANSLATE_NOOP("Errors", "unknown texture {name!r}; available: {available}"),
    QT_TRANSLATE_NOOP("Errors", "unsupported layout mode {mode}"),
    QT_TRANSLATE_NOOP(
        "Errors",
        "unsupported output format {suffix!r}; use .png, .jpg, .jpeg or .pdf",
    ),
    QT_TRANSLATE_NOOP("Errors", "{label!r} was not applied"),
    QT_TRANSLATE_NOOP("Errors", "{path}: not valid JSON ({error})"),
    QT_TRANSLATE_NOOP("Errors", "{style}.{key} must be a number, got {value!r}"),
    QT_TRANSLATE_NOOP(
        "Errors",
        "{style}.{key} must be between {low:g} and {high:g}, got {value!r}",
    ),
    QT_TRANSLATE_NOOP("Errors", "{style}.{key} must be one of {choices}, got {value!r}"),
    QT_TRANSLATE_NOOP("Errors", "{style}.{key} must be text, got {value!r}"),
    QT_TRANSLATE_NOOP("Errors", "{style}.{key} must not be negative, got {value!r}"),
    QT_TRANSLATE_NOOP("Errors", "{style}.{key}: invalid colour {value!r}"),
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


def error_message(error: BaseException) -> str:
    """The error in the interface language; core errors are translated by template."""
    if not isinstance(error, CollagioError):
        return str(error)
    text = translated(ERRORS, error.template)
    if not error.params:
        return text
    try:
        return text.format(**error.params)
    except (KeyError, IndexError, ValueError):  # a broken translation: show the English text
        return str(error)


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
