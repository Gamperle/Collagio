"""Tolerant image comparison for golden-image tests.

Rendering can differ by a few levels between platforms and Pillow builds, so
images are compared by maximum per-channel difference and by SSIM instead of
byte equality. On failure a diff image is written for inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

DEFAULT_MAX_DIFF = 2
DEFAULT_MIN_SSIM = 0.99

_SSIM_WINDOW = 7
_SSIM_C1 = (0.01 * 255) ** 2
_SSIM_C2 = (0.03 * 255) ** 2


@dataclass(frozen=True)
class CompareResult:
    max_diff: int
    ssim: float
    size_match: bool
    passed: bool

    def describe(self) -> str:
        if not self.size_match:
            return "image sizes differ"
        return f"max channel diff={self.max_diff}, SSIM={self.ssim:.5f}"


def _to_rgba_array(image: Image.Image) -> NDArray[np.float64]:
    return np.asarray(image.convert("RGBA"), dtype=np.float64)


def _box_mean(values: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Mean over every `window`x`window` box (valid region only), via summed-area table."""
    padded = np.pad(values, ((1, 0), (1, 0)))
    sat = padded.cumsum(axis=0).cumsum(axis=1)
    total = (
        sat[window:, window:]
        - sat[:-window, window:]
        - sat[window:, :-window]
        + sat[:-window, :-window]
    )
    result: NDArray[np.float64] = total / (window * window)
    return result


def ssim(a: Image.Image, b: Image.Image) -> float:
    """Mean structural similarity of the luminance channels of two equally sized images."""
    if a.size != b.size:
        raise ValueError(f"image sizes differ: {a.size} != {b.size}")
    x = np.asarray(a.convert("L"), dtype=np.float64)
    y = np.asarray(b.convert("L"), dtype=np.float64)
    window = min(_SSIM_WINDOW, *x.shape)

    mu_x = _box_mean(x, window)
    mu_y = _box_mean(y, window)
    var_x = _box_mean(x * x, window) - mu_x**2
    var_y = _box_mean(y * y, window) - mu_y**2
    cov = _box_mean(x * y, window) - mu_x * mu_y

    numerator = (2 * mu_x * mu_y + _SSIM_C1) * (2 * cov + _SSIM_C2)
    denominator = (mu_x**2 + mu_y**2 + _SSIM_C1) * (var_x + var_y + _SSIM_C2)
    return float(np.mean(numerator / denominator))


def compare_images(
    actual: Image.Image,
    expected: Image.Image,
    max_diff: int = DEFAULT_MAX_DIFF,
    min_ssim: float = DEFAULT_MIN_SSIM,
) -> CompareResult:
    if actual.size != expected.size:
        return CompareResult(max_diff=255, ssim=0.0, size_match=False, passed=False)
    diff = int(np.abs(_to_rgba_array(actual) - _to_rgba_array(expected)).max())
    score = ssim(actual, expected)
    return CompareResult(
        max_diff=diff,
        ssim=score,
        size_match=True,
        passed=diff <= max_diff and score >= min_ssim,
    )


def write_diff_image(actual: Image.Image, expected: Image.Image, path: Path) -> None:
    """Write expected | actual | amplified difference side by side."""
    width, height = expected.size
    actual = actual.convert("RGBA").resize(expected.size)
    expected = expected.convert("RGBA")
    delta = np.abs(_to_rgba_array(actual) - _to_rgba_array(expected))[..., :3].max(axis=2)
    heat = Image.fromarray(np.clip(delta * 8, 0, 255).astype(np.uint8), mode="L")

    sheet = Image.new("RGBA", (width * 3, height), "white")
    sheet.paste(expected, (0, 0))
    sheet.paste(actual, (width, 0))
    sheet.paste(heat.convert("RGBA"), (width * 2, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
