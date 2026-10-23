from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from collagio.core.model import Canvas, PhotoItem, Project, Rect
from collagio.errors import ExportError
from collagio.render.export import ExportFormat, export_image, format_for_path


def _loader(_: str) -> Image.Image:
    return Image.new("RGB", (50, 50), (10, 120, 200))


def _project() -> Project:
    return Project(
        canvas=Canvas(200, 100, dpi=150),
        photos=[PhotoItem("a", "a", rect=Rect(10, 10, 80, 80))],
    )


@pytest.mark.parametrize(
    ("name", "fmt"),
    [("a.png", ExportFormat.PNG), ("b.PNG", ExportFormat.PNG), ("c.jpg", ExportFormat.JPEG),
     ("d.jpeg", ExportFormat.JPEG), ("e.JPG", ExportFormat.JPEG)],
)  # fmt: skip
def test_format_for_path(name: str, fmt: ExportFormat) -> None:
    assert format_for_path(Path(name)) is fmt


@pytest.mark.parametrize("name", ["a.gif", "b.tiff", "noext"])
def test_unsupported_format(name: str) -> None:
    with pytest.raises(ExportError, match="unsupported output format"):
        format_for_path(Path(name))


def test_png_export(tmp_path: Path) -> None:
    path = export_image(_project(), tmp_path / "out.png", loader=_loader)
    with Image.open(path) as image:
        assert image.format == "PNG"
        assert image.size == (200, 100)
        # PNG stores pixels per metre, so the DPI comes back slightly rounded.
        assert image.info["dpi"] == pytest.approx((150, 150), abs=0.05)
        assert image.getpixel((50, 50)) == (10, 120, 200)


def test_jpeg_export(tmp_path: Path) -> None:
    path = export_image(_project(), tmp_path / "out.jpg", quality=95, loader=_loader)
    with Image.open(path) as image:
        assert image.format == "JPEG"
        assert image.size == (200, 100)
        assert image.info["dpi"] == (150, 150)
        assert image.getpixel((50, 50)) == pytest.approx((10, 120, 200), abs=3)


def test_jpeg_quality_affects_size(tmp_path: Path) -> None:
    def noisy(_: str) -> Image.Image:
        return Image.effect_noise((200, 200), 80).convert("RGB")

    low = export_image(_project(), tmp_path / "low.jpg", quality=20, loader=noisy)
    high = export_image(_project(), tmp_path / "high.jpg", quality=95, loader=noisy)
    assert low.stat().st_size < high.stat().st_size


def test_scale_adjusts_size_and_dpi(tmp_path: Path) -> None:
    path = export_image(_project(), tmp_path / "half.png", scale=0.5, loader=_loader)
    with Image.open(path) as image:
        assert image.size == (100, 50)
        assert image.info["dpi"] == pytest.approx((75, 75), abs=0.05)


@pytest.mark.parametrize("quality", [0, 101])
def test_invalid_quality(tmp_path: Path, quality: int) -> None:
    with pytest.raises(ExportError, match="quality"):
        export_image(_project(), tmp_path / "x.jpg", quality=quality, loader=_loader)


def test_unwritable_destination(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="cannot write"):
        export_image(_project(), tmp_path / "missing-dir" / "x.png", loader=_loader)
