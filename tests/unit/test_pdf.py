from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfReader

from collagio.core.model import (
    Background,
    BackgroundKind,
    Canvas,
    PhotoItem,
    Project,
    Rect,
    TextItem,
)
from collagio.errors import ExportError
from collagio.render.export import export_image
from collagio.render.pdf import (
    MARK_LENGTH_MM,
    MARK_OFFSET_MM,
    mm_to_pt,
    pdf_geometry,
    px_to_pt,
)
from collagio.render.renderer import render_project
from tests.helpers.image_compare import ssim


def _mm(points: float) -> float:
    return points / 72 * 25.4


def test_unit_conversion() -> None:
    assert mm_to_pt(25.4) == pytest.approx(72)
    assert px_to_pt(300, 300) == pytest.approx(72)


def test_a4_with_bleed_and_marks() -> None:
    geometry = pdf_geometry(2480, 3508, 300, 3.0, crop_marks=True)
    x0, y0, x1, y1 = geometry.bleed_box
    assert (_mm(x1 - x0), _mm(y1 - y0)) == (
        pytest.approx(216, abs=0.1),
        pytest.approx(303, abs=0.1),
    )
    tx0, ty0, tx1, ty1 = geometry.trim_box
    assert (_mm(tx1 - tx0), _mm(ty1 - ty0)) == (
        pytest.approx(210, abs=0.1),
        pytest.approx(297, abs=0.1),
    )
    width, height = geometry.media_size
    assert (_mm(width), _mm(height)) == (pytest.approx(232, abs=0.1), pytest.approx(319, abs=0.1))
    assert _mm(tx0 - x0) == pytest.approx(3)  # trim sits 3 mm inside the bleed box


def test_without_marks_the_page_is_the_bleed_box() -> None:
    geometry = pdf_geometry(2480, 3508, 300, 3.0, crop_marks=False)
    assert geometry.bleed_box == (0, 0, *geometry.media_size)
    assert geometry.crop_marks() == []


def test_without_bleed_trim_equals_bleed() -> None:
    geometry = pdf_geometry(1000, 800, 100, 0.0, crop_marks=False)
    assert geometry.trim_box == geometry.bleed_box == (0, 0, 720, 576)


def test_crop_marks_align_with_trim_and_stay_outside_bleed() -> None:
    geometry = pdf_geometry(2480, 3508, 300, 3.0, crop_marks=True)
    marks = geometry.crop_marks()
    assert len(marks) == 8
    tx0, ty0, tx1, ty1 = geometry.trim_box
    bx0, by0, bx1, by1 = geometry.bleed_box
    width, height = geometry.media_size
    for x_start, y_start, x_end, y_end in marks:
        if y_start == y_end:  # horizontal: continues a horizontal trim edge
            assert y_start in (ty0, ty1)
            assert max(x_start, x_end) <= bx0 or min(x_start, x_end) >= bx1
        else:
            assert x_start in (tx0, tx1)
            assert max(y_start, y_end) <= by0 or min(y_start, y_end) >= by1
        length = abs(x_end - x_start) + abs(y_end - y_start)
        assert _mm(length) == pytest.approx(MARK_LENGTH_MM)
        assert min(x_start, x_end) >= 0 and max(x_start, x_end) <= width
        assert min(y_start, y_end) >= 0 and max(y_start, y_end) <= height
    gap = min(abs(m[0] - tx0) for m in marks if m[1] == m[3] and min(m[0], m[2]) < tx0)
    assert _mm(gap) == pytest.approx(3 + MARK_OFFSET_MM)


# --- writing PDFs --------------------------------------------------------------------------------


def _loader(_: str) -> Image.Image:
    image = Image.new("RGB", (200, 100), (200, 40, 40))
    image.paste((40, 40, 200), (100, 0, 200, 100))
    return image


def _project() -> Project:
    return Project(
        canvas=Canvas(
            600, 400, dpi=150, background=Background(BackgroundKind.TEXTURE, color="#c0a080")
        ),
        photos=[PhotoItem("a", "a", rect=Rect(50, 50, 300, 200))],
        texts=[TextItem("t", "Hello", 450, 330, size=60)],
    )


def test_pdf_boxes_and_embedded_image(tmp_path: Path) -> None:
    path = export_image(
        _project(), tmp_path / "out.pdf", bleed_mm=3, crop_marks=True, loader=_loader
    )
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    page = reader.pages[0]
    trim = [_mm(float(v)) for v in page.trimbox]
    bleed = [_mm(float(v)) for v in page.bleedbox]
    assert trim[2] - trim[0] == pytest.approx(600 / 150 * 25.4, abs=0.01)
    assert bleed[2] - bleed[0] == pytest.approx(600 / 150 * 25.4 + 6, abs=0.01)
    bleed_px = round(3 / 25.4 * 150)
    assert page.images[0].image.size == (600 + 2 * bleed_px, 400 + 2 * bleed_px)
    assert reader.metadata.title == "out"
    assert "Collagio" in (reader.metadata.creator or "")


def test_pdf_looks_like_the_png(tmp_path: Path) -> None:
    """Rasterise the PDF's trim area and compare it with a PNG export of the same project.

    A smooth background is used: fine textures lose detail in JPEG compression
    and in the PDF renderer's resampling, which would hide geometry errors.
    """
    project = _project()
    project.canvas.background = Background(BackgroundKind.GRADIENT, "#c0a080", "#405060")
    pdf = export_image(project, tmp_path / "out.pdf", quality=98, bleed_mm=3, crop_marks=True,
                       loader=_loader)  # fmt: skip
    expected = render_project(project, loader=_loader)
    page = pdfium.PdfDocument(pdf)[0]
    rendered = page.render(scale=150 / 72).to_pil().convert("RGB")
    trim = PdfReader(pdf).pages[0].trimbox
    scale = 150 / 72
    height = rendered.height
    box = (
        round(float(trim[0]) * scale),
        height - round(float(trim[3]) * scale),
        round(float(trim[2]) * scale),
        height - round(float(trim[1]) * scale),
    )
    cropped = rendered.crop(box).resize(expected.size)
    assert ssim(cropped, expected) > 0.99
    # Crop marks: thin (0.25 pt, anti-aliased) dark lines in the otherwise white corner.
    corner = rendered.crop((0, 0, box[0] - 2, box[1] - 2)).convert("L")
    assert corner.getextrema()[0] < 200


def test_bleed_enlarges_png_and_extends_background(tmp_path: Path) -> None:
    path = export_image(_project(), tmp_path / "out.png", bleed_mm=10, loader=_loader)
    bleed_px = round(10 / 25.4 * 150)
    with Image.open(path) as image:
        assert image.size == (600 + 2 * bleed_px, 400 + 2 * bleed_px)
        # The photo moved inwards by the bleed.
        assert image.getpixel((bleed_px + 60, bleed_px + 60))[:3] == (200, 40, 40)


@pytest.mark.parametrize(
    ("name", "options", "message"),
    [
        ("x.png", {"crop_marks": True}, "crop marks need PDF"),
        ("x.pdf", {"bleed_mm": 25}, "bleed must be between"),
        ("x.pdf", {"bleed_mm": -1}, "bleed must be between"),
    ],
)
def test_export_option_errors(
    tmp_path: Path, name: str, options: dict[str, object], message: str
) -> None:
    with pytest.raises(ExportError, match=message):
        export_image(_project(), tmp_path / name, loader=_loader, **options)  # type: ignore[arg-type]


def test_pdf_unwritable(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="cannot write"):
        export_image(_project(), tmp_path / "missing" / "x.pdf", loader=_loader)
