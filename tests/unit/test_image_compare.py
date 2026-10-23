from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from tests.helpers.image_compare import compare_images, ssim, write_diff_image


def _pattern(size: tuple[int, int] = (64, 48)) -> Image.Image:
    image = Image.new("RGB", size, "navy")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 30, 30), fill="orange")
    draw.ellipse((34, 10, 60, 40), fill="white")
    return image


def _shift_levels(image: Image.Image, delta: int) -> Image.Image:
    pixels = np.asarray(image, dtype=np.int16) + delta
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), mode=image.mode)


def test_identical_images_pass_with_perfect_ssim() -> None:
    image = _pattern()
    result = compare_images(image, image.copy())
    assert result.passed
    assert result.max_diff == 0
    assert result.ssim == pytest.approx(1.0)


def test_small_level_shift_is_tolerated() -> None:
    image = _pattern()
    result = compare_images(_shift_levels(image, 2), image)
    assert result.passed
    assert result.max_diff == 2


def test_large_level_shift_fails() -> None:
    image = _pattern()
    result = compare_images(_shift_levels(image, 40), image)
    assert not result.passed
    assert result.max_diff == 40


def test_structural_change_fails_and_lowers_ssim() -> None:
    expected = _pattern()
    actual = expected.copy()
    ImageDraw.Draw(actual).rectangle((0, 0, 20, 47), fill="red")
    result = compare_images(actual, expected)
    assert not result.passed
    assert result.ssim < 0.9


def test_size_mismatch_fails_without_error() -> None:
    result = compare_images(_pattern((64, 48)), _pattern((48, 64)))
    assert not result.passed
    assert not result.size_match
    assert result.describe() == "image sizes differ"


def test_describe_reports_metrics() -> None:
    image = _pattern()
    assert "SSIM=1.00000" in compare_images(image, image).describe()


def test_mode_differences_are_normalised() -> None:
    image = _pattern()
    assert compare_images(image.convert("RGBA"), image).passed


def test_ssim_rejects_different_sizes() -> None:
    with pytest.raises(ValueError, match="sizes differ"):
        ssim(_pattern((10, 10)), _pattern((12, 10)))


def test_ssim_handles_images_smaller_than_window() -> None:
    tiny = Image.new("RGB", (3, 3), "gray")
    assert ssim(tiny, tiny.copy()) == pytest.approx(1.0)


def test_write_diff_image_creates_side_by_side_sheet(tmp_path: Path) -> None:
    expected = _pattern()
    actual = _shift_levels(expected, 30)
    out = tmp_path / "nested" / "diff.png"
    write_diff_image(actual, expected, out)
    with Image.open(out) as sheet:
        assert sheet.size == (expected.width * 3, expected.height)
        # Third panel shows the amplified difference: uniform shift -> bright.
        assert sheet.getpixel((expected.width * 2 + 5, 5))[0] == 240
