"""Exception hierarchy. Everything user-facing derives from CollagioError."""

from __future__ import annotations


class CollagioError(Exception):
    """Base class for errors that are reported to the user without a traceback.

    The message is an English template with `str.format` fields, filled from the
    keyword arguments: `ImageLoadError("photo not found: {path}", path=path)`.
    `str(error)` is the English message (command line); the editor translates
    `template`, which stays the same for every occurrence, and fills in `params`.
    """

    def __init__(self, template: str, /, **params: object) -> None:
        self.template = template
        self.params = params
        super().__init__(template.format(**params) if params else template)


class SizeError(CollagioError):
    """A canvas size specification could not be parsed or is out of range."""


class ProjectFormatError(CollagioError):
    """A project file is malformed or has an unsupported schema version."""


class ImageLoadError(CollagioError):
    """A photo could not be found or decoded."""


class LayoutError(CollagioError):
    """A layout cannot be generated with the given photos and settings."""


class StyleError(CollagioError):
    """Unknown style or invalid style parameters."""


class RenderError(CollagioError):
    """The project cannot be rendered (e.g. photos without a position)."""


class ExportError(CollagioError):
    """The output file cannot be written in the requested format."""


class EditError(CollagioError):
    """An edit refers to photos that do not exist or cannot be applied."""
