"""Checks that the synthetic test photos really cover the cases later tests rely on."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageOps

from tests.fixtures.generate import (
    EXIF_ORIENTATION_TAG,
    LARGE_SPEC,
    STANDARD_SPECS,
    PhotoSpec,
    generate,
)


def test_all_standard_photos_are_created(sample_photos: list[Path]) -> None:
    assert [p.name for p in sample_photos] == [s.name for s in STANDARD_SPECS]
    assert all(p.stat().st_size > 0 for p in sample_photos)


@pytest.mark.parametrize("spec", STANDARD_SPECS, ids=lambda s: s.name)
def test_photo_has_declared_format_and_size(sample_photos: list[Path], spec: PhotoSpec) -> None:
    path = next(p for p in sample_photos if p.name == spec.name)
    with Image.open(path) as image:
        assert image.format == spec.fmt
        assert image.size == spec.size


def test_exif_rotated_photo_displays_as_portrait(sample_photos: list[Path]) -> None:
    path = next(p for p in sample_photos if "exif_rotated" in p.name)
    with Image.open(path) as image:
        assert image.getexif()[EXIF_ORIENTATION_TAG] == 6
        assert image.width > image.height
        upright = ImageOps.exif_transpose(image).convert("RGB")
        assert upright.height > upright.width
        # The orientation marker ends up top-left only if the tag is honoured.
        assert upright.getpixel((2, 2)) == pytest.approx((0, 0, 0), abs=20)
        assert upright.getpixel((upright.width - 3, 2)) != pytest.approx((0, 0, 0), abs=20)


def test_alpha_photo_has_transparent_corners(sample_photos: list[Path]) -> None:
    path = next(p for p in sample_photos if "alpha" in p.name)
    with Image.open(path) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((image.width // 2, image.height // 2))[3] == 255


def test_photos_are_distinguishable(sample_photos: list[Path]) -> None:
    centres = set()
    for path in sample_photos:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            centres.add(rgb.getpixel((rgb.width // 4, rgb.height // 4)))
    assert len(centres) == len(sample_photos)


def test_generate_is_deterministic(tmp_path: Path) -> None:
    first = generate(tmp_path / "a")
    second = generate(tmp_path / "b")
    for a, b in zip(first, second, strict=True):
        assert a.read_bytes() == b.read_bytes()


@pytest.mark.slow
def test_large_photo(large_photo: Path) -> None:
    assert large_photo.name == LARGE_SPEC.name
    with Image.open(large_photo) as image:
        assert image.size == (6000, 4000)
