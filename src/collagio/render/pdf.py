"""Print-ready PDF: one page with the collage, optional bleed and crop marks.

Page layout (all in PDF points, origin bottom-left):

    +-- MediaBox -----------------------------+
    |  crop marks (slug, only with marks)      |
    |   +-- BleedBox ----------------------+   |
    |   |  bleed (background extends here)  |   |
    |   |   +-- TrimBox (final size) ---+   |   |
    |   |   |                            |   |   |

The image covers the BleedBox. Crop marks sit outside the bleed, aligned with
the trim edges, so they are cut off together with the bleed.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from collagio import __version__
from collagio.core.units import MM_PER_INCH

PT_PER_INCH = 72.0
MARK_OFFSET_MM = 2.0  # gap between the bleed edge and a crop mark
MARK_LENGTH_MM = 5.0
MARK_MARGIN_MM = 1.0  # space between a mark and the page edge
MARK_WIDTH_PT = 0.25

Box = tuple[float, float, float, float]  # x0, y0, x1, y1
Line = tuple[float, float, float, float]


def mm_to_pt(mm: float) -> float:
    return mm / MM_PER_INCH * PT_PER_INCH


def px_to_pt(px: float, dpi: float) -> float:
    return px / dpi * PT_PER_INCH


@dataclass(frozen=True)
class PdfGeometry:
    trim_width: float  # points
    trim_height: float
    bleed: float
    slug: float  # room for crop marks outside the bleed (0 without marks)

    @property
    def media_size(self) -> tuple[float, float]:
        margin = 2 * (self.bleed + self.slug)
        return self.trim_width + margin, self.trim_height + margin

    @property
    def trim_box(self) -> Box:
        inset = self.bleed + self.slug
        return inset, inset, inset + self.trim_width, inset + self.trim_height

    @property
    def bleed_box(self) -> Box:
        width, height = self.media_size
        return self.slug, self.slug, width - self.slug, height - self.slug

    def crop_marks(self) -> list[Line]:
        """Two short lines per corner, continuing the trim edges outside the bleed."""
        if self.slug <= 0:
            return []
        x0, y0, x1, y1 = self.trim_box
        start = self.bleed + mm_to_pt(MARK_OFFSET_MM)
        end = start + mm_to_pt(MARK_LENGTH_MM)
        lines: list[Line] = []
        for x, sx in ((x0, -1), (x1, 1)):
            for y, sy in ((y0, -1), (y1, 1)):
                lines.append((x + sx * start, y, x + sx * end, y))  # horizontal
                lines.append((x, y + sy * start, x, y + sy * end))  # vertical
        return lines


def pdf_geometry(
    width_px: int, height_px: int, dpi: float, bleed_mm: float, crop_marks: bool
) -> PdfGeometry:
    slug = mm_to_pt(MARK_OFFSET_MM + MARK_LENGTH_MM + MARK_MARGIN_MM) if crop_marks else 0.0
    return PdfGeometry(
        trim_width=px_to_pt(width_px, dpi),
        trim_height=px_to_pt(height_px, dpi),
        bleed=mm_to_pt(bleed_mm),
        slug=slug,
    )


def write_pdf(
    image: Image.Image,
    geometry: PdfGeometry,
    path: Path,
    *,
    quality: int = 95,
    title: str = "Collage",
) -> None:
    """`image` must cover the BleedBox (trim size plus bleed on every side)."""
    pdf = Canvas(str(path), pagesize=geometry.media_size, pageCompression=1)
    pdf.setTitle(title)
    pdf.setCreator(f"Collagio {__version__}")
    pdf.setTrimBox(geometry.trim_box)
    pdf.setBleedBox(geometry.bleed_box)

    # Embed as JPEG: reportlab passes it through unchanged (DCTDecode).
    encoded = io.BytesIO()
    image.convert("RGB").save(encoded, format="JPEG", quality=quality, subsampling=0)
    encoded.seek(0)
    x0, y0, x1, y1 = geometry.bleed_box
    pdf.drawImage(ImageReader(encoded), x0, y0, width=x1 - x0, height=y1 - y0)

    pdf.setLineWidth(MARK_WIDTH_PT)
    pdf.setStrokeColorRGB(0, 0, 0)
    for line in geometry.crop_marks():
        pdf.line(*line)
    pdf.showPage()
    pdf.save()
