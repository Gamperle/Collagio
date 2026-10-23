"""Writing the rendered collage to PNG or JPEG."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from collagio.core.model import Project
from collagio.errors import ExportError
from collagio.imaging.loader import load_image
from collagio.render.renderer import Loader, Progress, render_project


class ExportFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"


_SUFFIXES = {".png": ExportFormat.PNG, ".jpg": ExportFormat.JPEG, ".jpeg": ExportFormat.JPEG}


def format_for_path(path: Path) -> ExportFormat:
    try:
        return _SUFFIXES[path.suffix.lower()]
    except KeyError:
        raise ExportError(
            f"unsupported output format {path.suffix or '(none)'!r}; use .png, .jpg or .jpeg"
        ) from None


def export_image(
    project: Project,
    path: Path,
    *,
    quality: int = 92,
    scale: float = 1.0,
    loader: Loader = load_image,
    progress: Progress | None = None,
) -> Path:
    """Render and save the collage. The format follows the file suffix."""
    fmt = format_for_path(path)
    if not 1 <= quality <= 100:
        raise ExportError(f"JPEG quality must be 1-100, got {quality}")
    image = render_project(project, scale=scale, loader=loader, progress=progress)
    dpi = project.canvas.dpi * scale
    try:
        if fmt is ExportFormat.PNG:
            image.save(path, format="PNG", dpi=(dpi, dpi))
        else:
            # Full chroma resolution for high quality settings: sharper edges.
            subsampling = 0 if quality >= 90 else 2
            image.save(
                path, format="JPEG", quality=quality, subsampling=subsampling, dpi=(dpi, dpi)
            )
    except OSError as exc:
        raise ExportError(f"cannot write {path}: {exc}") from exc
    return path
