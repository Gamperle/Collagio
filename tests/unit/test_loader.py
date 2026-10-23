from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from collagio.errors import ImageLoadError
from collagio.imaging.loader import (
    EXIF_ORIENTATION_TAG,
    find_images,
    is_supported,
    load_image,
    oriented_size,
)
from tests.fixtures.generate import STANDARD_SPECS, PhotoSpec


def _photo(photos: list[Path], fragment: str) -> Path:
    return next(p for p in photos if fragment in p.name)


def _is_black(pixel: tuple[int, ...]) -> bool:
    return max(pixel[:3]) < 40


def test_find_images_lists_supported_files_sorted(tmp_path: Path) -> None:
    for name in ["b.JPG", "a.png", "C.webp", "notes.txt", "raw.cr2"]:
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "hidden.jpg").write_bytes(b"")
    (tmp_path / "folder.jpg").mkdir()
    assert [p.name for p in find_images(tmp_path)] == ["a.png", "b.JPG", "C.webp"]


def test_find_images_rejects_non_folder(tmp_path: Path) -> None:
    with pytest.raises(ImageLoadError, match="not a folder"):
        find_images(tmp_path / "missing")


@pytest.mark.parametrize(
    ("name", "supported"),
    [("a.jpg", True), ("b.JPEG", True), ("c.Png", True), ("d.webp", True), ("e.tif", True),
     ("f.tiff", True), ("g.gif", False), ("h.txt", False), ("noext", False)],
)  # fmt: skip
def test_is_supported(name: str, supported: bool) -> None:
    assert is_supported(Path(name)) is supported


@pytest.mark.parametrize("spec", STANDARD_SPECS, ids=lambda s: s.name)
def test_oriented_size_and_load_agree(sample_photos: list[Path], spec: PhotoSpec) -> None:
    path = _photo(sample_photos, spec.name)
    image = load_image(path)
    assert oriented_size(path) == image.size
    assert image.mode in ("RGB", "RGBA")


def test_exif_orientation_is_applied(sample_photos: list[Path]) -> None:
    path = _photo(sample_photos, "exif_rotated")
    with Image.open(path) as raw:
        assert raw.size == (600, 400)
        assert raw.getexif()[EXIF_ORIENTATION_TAG] == 6
    image = load_image(path)
    assert image.size == (400, 600)
    assert _is_black(image.getpixel((2, 2)))  # orientation marker is top-left
    assert not _is_black(image.getpixel((image.width - 3, 2)))


def test_alpha_is_preserved(sample_photos: list[Path]) -> None:
    image = load_image(_photo(sample_photos, "alpha"))
    assert image.mode == "RGBA"
    assert image.getpixel((0, 0))[3] == 0


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("L", "RGB"), ("CMYK", "RGB"), ("LA", "RGBA"), ("P", "RGB"), ("RGBA", "RGBA")],
)
def test_modes_are_normalised(tmp_path: Path, mode: str, expected: str) -> None:
    path = tmp_path / f"{mode}.{'jpg' if mode == 'CMYK' else 'png'}"
    Image.new(mode, (20, 10)).save(path)
    assert load_image(path).mode == expected


def test_palette_with_transparency_keeps_alpha(tmp_path: Path) -> None:
    path = tmp_path / "p.png"
    image = Image.new("P", (10, 10), 0)
    image.save(path, transparency=0)
    assert load_image(path).mode == "RGBA"


def test_max_edge_downscales_keeping_aspect(sample_photos: list[Path]) -> None:
    image = load_image(_photo(sample_photos, "02_portrait"), max_edge=150)
    assert image.size == (100, 150)


def test_max_edge_larger_than_photo_keeps_size(sample_photos: list[Path]) -> None:
    assert load_image(_photo(sample_photos, "03_square"), max_edge=5000).size == (500, 500)


def test_max_edge_with_exif_rotation(sample_photos: list[Path]) -> None:
    image = load_image(_photo(sample_photos, "exif_rotated"), max_edge=120)
    assert image.size == (80, 120)
    assert _is_black(image.getpixel((1, 1)))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ImageLoadError, match="not found"):
        load_image(tmp_path / "missing.jpg")
    with pytest.raises(ImageLoadError, match="not found"):
        oriented_size(tmp_path / "missing.jpg")


def test_not_an_image(tmp_path: Path) -> None:
    path = tmp_path / "fake.jpg"
    path.write_text("definitely not a jpeg")
    with pytest.raises(ImageLoadError, match="cannot read"):
        load_image(path)


def test_truncated_image(sample_photos: list[Path], tmp_path: Path) -> None:
    data = _photo(sample_photos, "01_landscape").read_bytes()
    path = tmp_path / "truncated.jpg"
    path.write_bytes(data[: len(data) // 3])
    with pytest.raises(ImageLoadError, match="cannot decode"):
        load_image(path)
