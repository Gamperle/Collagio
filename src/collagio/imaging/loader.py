"""Opening photos: format support, EXIF orientation and fast downscaled loading."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from collagio.errors import ImageLoadError

EXIF_ORIENTATION_TAG = 0x0112
# EXIF orientations 5-8 include a 90° rotation, so width and height swap.
_TRANSPOSED_ORIENTATIONS = frozenset({5, 6, 7, 8})

SUPPORTED_SUFFIXES: set[str] = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

try:  # Optional HEIC/HEIF support.
    from pillow_heif import register_heif_opener  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on optional package
    pass
else:  # pragma: no cover - depends on optional package
    register_heif_opener()
    SUPPORTED_SUFFIXES |= {".heic", ".heif"}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def find_images(folder: Path) -> list[Path]:
    """Supported photos directly inside `folder`, sorted by file name."""
    if not folder.is_dir():
        raise ImageLoadError(f"not a folder: {folder}")
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and is_supported(p)),
        key=lambda p: p.name.lower(),
    )


def _open(path: str | Path) -> Image.Image:
    try:
        return Image.open(path)
    except FileNotFoundError as exc:
        raise ImageLoadError(f"photo not found: {path}") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError(f"cannot read photo {path}: {exc}") from exc


def oriented_size(path: str | Path) -> tuple[int, int]:
    """Displayed (EXIF-corrected) size without decoding the pixel data."""
    with _open(path) as image:
        width, height = image.size
        if image.getexif().get(EXIF_ORIENTATION_TAG) in _TRANSPOSED_ORIENTATIONS:
            return height, width
        return width, height


def _normalise_mode(image: Image.Image) -> Image.Image:
    if image.mode in ("RGB", "RGBA"):
        return image
    has_alpha = image.mode in ("LA", "PA") or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def load_image(path: str | Path, max_edge: int | None = None) -> Image.Image:
    """Load a photo upright, as RGB or RGBA.

    With `max_edge` the result is downscaled so its longer side is at most
    `max_edge`; JPEGs are then decoded at reduced size, which is much faster.
    """
    with _open(path) as image:
        try:
            if max_edge is not None and image.format == "JPEG":
                image.draft("RGB", (max_edge, max_edge))
            upright = ImageOps.exif_transpose(image)
            upright.load()
        except OSError as exc:
            raise ImageLoadError(f"cannot decode photo {path}: {exc}") from exc
    upright = _normalise_mode(upright)
    if max_edge is not None and max(upright.size) > max_edge:
        upright.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return upright
