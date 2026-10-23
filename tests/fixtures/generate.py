"""Generate synthetic test photos.

Each photo is a coloured gradient with its index drawn on it, so layout and
crop mistakes are visible in golden images. Generated instead of committed to
keep the repository small and the content licence-free.

Usage: python tests/fixtures/generate.py <output-dir> [--large]
"""

from __future__ import annotations

import argparse
import colorsys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

EXIF_ORIENTATION_TAG = 0x0112


@dataclass(frozen=True)
class PhotoSpec:
    name: str
    size: tuple[int, int]
    fmt: str
    exif_orientation: int | None = None
    alpha: bool = False


STANDARD_SPECS: tuple[PhotoSpec, ...] = (
    PhotoSpec("01_landscape_3x2.jpg", (600, 400), "JPEG"),
    PhotoSpec("02_portrait_2x3.jpg", (400, 600), "JPEG"),
    PhotoSpec("03_square.png", (500, 500), "PNG"),
    PhotoSpec("04_wide_16x9.webp", (640, 360), "WEBP"),
    PhotoSpec("05_tall_9x16.jpg", (360, 640), "JPEG"),
    PhotoSpec("06_landscape_4x3.tiff", (640, 480), "TIFF"),
    # Stored landscape, EXIF says "rotate 90° CW" -> displays as portrait.
    PhotoSpec("07_exif_rotated.jpg", (600, 400), "JPEG", exif_orientation=6),
    PhotoSpec("08_alpha.png", (500, 400), "PNG", alpha=True),
)

LARGE_SPEC = PhotoSpec("99_large_6000x4000.jpg", (6000, 4000), "JPEG")


def _gradient(size: tuple[int, int], hue: float) -> Image.Image:
    width, height = size
    xs = np.linspace(0.0, 1.0, width)[None, :]
    ys = np.linspace(0.0, 1.0, height)[:, None]
    light = np.array(colorsys.hsv_to_rgb(hue, 0.35, 1.0)) * 255
    dark = np.array(colorsys.hsv_to_rgb((hue + 0.15) % 1.0, 0.9, 0.55)) * 255
    t = ((xs + ys) / 2.0)[..., None]
    pixels = light * (1 - t) + dark * t
    return Image.fromarray(pixels.astype(np.uint8), mode="RGB")


def render_photo(spec: PhotoSpec, index: int) -> Image.Image:
    image = _gradient(spec.size, hue=(index * 0.13) % 1.0)
    draw = ImageDraw.Draw(image)
    width, height = spec.size
    font = ImageFont.load_default(size=max(12, min(width, height) // 3))
    draw.text((width / 2, height / 2), str(index), fill="white", font=font, anchor="mm")
    # Marker in the top-left corner to verify orientation and cropping.
    marker = max(4, min(width, height) // 10)
    draw.rectangle((0, 0, marker, marker), fill="black")
    if spec.alpha:
        mask = Image.new("L", spec.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, width - 1, height - 1), fill=255)
        image.putalpha(mask)
    return image


def write_photo(spec: PhotoSpec, index: int, directory: Path) -> Path:
    path = directory / spec.name
    image = render_photo(spec, index)
    save_kwargs: dict[str, object] = {}
    if spec.exif_orientation is not None:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION_TAG] = spec.exif_orientation
        save_kwargs["exif"] = exif
    if spec.fmt == "JPEG":
        save_kwargs["quality"] = 92
    image.save(path, format=spec.fmt, **save_kwargs)
    return path


def generate(directory: Path, *, large: bool = False) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    specs = [*STANDARD_SPECS, LARGE_SPEC] if large else list(STANDARD_SPECS)
    return [write_photo(spec, index, directory) for index, spec in enumerate(specs, start=1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    parser.add_argument("--large", action="store_true", help="also create a 6000x4000 photo")
    args = parser.parse_args()
    for path in generate(args.output, large=args.large):
        print(path)


if __name__ == "__main__":
    main()
