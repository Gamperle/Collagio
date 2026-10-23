"""Exception hierarchy. Everything user-facing derives from CollagioError."""


class CollagioError(Exception):
    """Base class for errors that are reported to the user without a traceback."""


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
