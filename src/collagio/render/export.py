"""Writing the rendered collage to PNG, JPEG or a print-ready PDF."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from collagio.core.model import Project
from collagio.core.units import mm_to_px
from collagio.errors import ExportError
from collagio.imaging.loader import load_image
from collagio.render.pdf import pdf_geometry, write_pdf
from collagio.render.renderer import Loader, Progress, render_project


class ExportFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    PDF = "pdf"


_SUFFIXES = {
    ".png": ExportFormat.PNG,
    ".jpg": ExportFormat.JPEG,
    ".jpeg": ExportFormat.JPEG,
    ".pdf": ExportFormat.PDF,
}
MAX_BLEED_MM = 20.0


def format_for_path(path: Path) -> ExportFormat:
    try:
        return _SUFFIXES[path.suffix.lower()]
    except KeyError:
        raise ExportError(
            "unsupported output format {suffix!r}; use .png, .jpg, .jpeg or .pdf",
            suffix=path.suffix or "(none)",
        ) from None


def export_image(
    project: Project,
    path: Path,
    *,
    quality: int = 92,
    scale: float = 1.0,
    loader: Loader = load_image,
    progress: Progress | None = None,
    bleed_mm: float = 0.0,
    crop_marks: bool = False,
) -> Path:
    """Render and save the collage. The format follows the file suffix.

    `bleed_mm` extends the image on every side (background only). Crop marks
    are only available for PDF, where they are drawn outside the bleed.
    """
    fmt = format_for_path(path)
    if not 1 <= quality <= 100:
        raise ExportError("JPEG quality must be 1-100, got {quality}", quality=quality)
    if not 0 <= bleed_mm <= MAX_BLEED_MM:
        raise ExportError(
            "bleed must be between 0 and {maximum:g} mm, got {bleed:g}",
            maximum=MAX_BLEED_MM,
            bleed=bleed_mm,
        )
    if crop_marks and fmt is not ExportFormat.PDF:
        raise ExportError("crop marks need PDF output (.pdf)")

    dpi = project.canvas.dpi * scale
    bleed_px = mm_to_px(bleed_mm, project.canvas.dpi)  # canvas pixels at full scale
    image = render_project(project, scale=scale, loader=loader, progress=progress, bleed=bleed_px)
    try:
        if fmt is ExportFormat.PNG:
            image.save(path, format="PNG", dpi=(dpi, dpi))
        elif fmt is ExportFormat.JPEG:
            # Full chroma resolution for high quality settings: sharper edges.
            subsampling = 0 if quality >= 90 else 2
            image.save(
                path, format="JPEG", quality=quality, subsampling=subsampling, dpi=(dpi, dpi)
            )
        else:
            geometry = pdf_geometry(
                round(project.canvas.width * scale),
                round(project.canvas.height * scale),
                dpi,
                bleed_mm,
                crop_marks,
            )
            write_pdf(image, geometry, path, quality=quality, title=path.stem)
    except OSError as exc:
        raise ExportError("cannot write {path}: {error}", path=path, error=exc) from exc
    return path
