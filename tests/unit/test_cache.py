from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from PIL import Image

from collagio.errors import ImageLoadError
from collagio.imaging import cache as cache_module
from collagio.imaging.cache import ThumbnailCache, default_cache_dir


@pytest.fixture
def photo(sample_photos: list[Path], tmp_path: Path) -> Path:
    """A private copy, so tests may modify it."""
    source = sample_photos[0]
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    return target


def test_memory_hit_after_first_load(photo: Path) -> None:
    cache = ThumbnailCache()
    first = cache.get(photo, 100)
    second = cache.get(photo, 100)
    assert max(first.size) == 100
    assert first.tobytes() == second.tobytes()
    assert (cache.misses, cache.memory_hits, cache.disk_hits) == (1, 1, 0)


def test_returned_images_are_copies(photo: Path) -> None:
    cache = ThumbnailCache()
    cache.get(photo, 50).paste((255, 0, 0), (0, 0, 50, 50))
    assert cache.get(photo, 50).getpixel((25, 25)) != (255, 0, 0)


def test_different_sizes_are_cached_separately(photo: Path) -> None:
    cache = ThumbnailCache()
    assert max(cache.get(photo, 64).size) == 64
    assert max(cache.get(photo, 128).size) == 128
    assert cache.misses == 2


def test_disk_cache_survives_new_instance(photo: Path, tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    expected = ThumbnailCache(directory).get(photo, 80)
    fresh = ThumbnailCache(directory)
    image = fresh.get(photo, 80)
    assert (fresh.misses, fresh.disk_hits) == (0, 1)
    assert image.tobytes() == expected.tobytes()
    assert len(list(directory.rglob("*.png"))) == 1
    assert not list(directory.rglob("*.tmp"))


def test_modified_photo_is_reloaded(photo: Path) -> None:
    cache = ThumbnailCache()
    cache.get(photo, 64)
    Image.new("RGB", (300, 100), "red").save(photo, format="JPEG")
    stat = photo.stat()
    os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    image = cache.get(photo, 64)
    assert image.size == (64, 21)
    assert cache.misses == 2


def test_lru_eviction(sample_photos: list[Path]) -> None:
    cache = ThumbnailCache(memory_items=2)
    a, b, c = sample_photos[:3]
    cache.get(a, 32)
    cache.get(b, 32)
    cache.get(a, 32)  # a is now most recently used
    cache.get(c, 32)  # evicts b
    cache.get(a, 32)
    assert cache.memory_hits == 2
    cache.get(b, 32)
    assert cache.misses == 4


def test_clear_memory(photo: Path) -> None:
    cache = ThumbnailCache()
    cache.get(photo, 32)
    cache.clear_memory()
    cache.get(photo, 32)
    assert cache.misses == 2


def test_corrupt_disk_entry_is_regenerated(photo: Path, tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    ThumbnailCache(directory).get(photo, 40)
    (entry,) = directory.rglob("*.png")
    entry.write_bytes(b"garbage")
    fresh = ThumbnailCache(directory)
    assert max(fresh.get(photo, 40).size) == 40
    assert (fresh.misses, fresh.disk_hits) == (1, 0)


def _fill(directory: Path, sizes: dict[str, int]) -> dict[str, Path]:
    """Cache files of the given sizes, the first one least recently used."""
    files = {}
    for age, (name, size) in enumerate(reversed(sizes.items())):
        path = directory / name[:2] / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        used = time.time() - 100 * (age + 1)
        os.utime(path, (used, used))
        files[name] = path
    return files


def test_prune_removes_least_recently_used_first(tmp_path: Path) -> None:
    cache = ThumbnailCache(tmp_path)
    files = _fill(tmp_path, {"aa1": 400, "bb2": 300, "cc3": 200, "dd4": 100})
    assert cache.disk_size() == 1000
    assert cache.prune(max_bytes=350) == 700
    assert {name for name, path in files.items() if path.exists()} == {"cc3", "dd4"}
    assert cache.disk_size() == 300
    assert cache.prune(max_bytes=350) == 0


def test_disk_hit_counts_as_recent_use(photo: Path, tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    ThumbnailCache(directory).get(photo, 40)
    (used,) = directory.rglob("*.png")
    os.utime(used, (1, 1))
    _fill(directory, {"ff1": 10})
    cache = ThumbnailCache(directory)
    cache.get(photo, 40)
    assert cache.disk_hits == 1
    cache.prune(max_bytes=used.stat().st_size)
    assert used.exists()
    assert len(list(directory.rglob("*.png"))) == 1


def test_prune_removes_stale_temp_files_only(tmp_path: Path) -> None:
    (tmp_path / "ab").mkdir()
    stale = tmp_path / "ab" / "ab1.123-4.tmp"
    fresh = tmp_path / "ab" / "ab2.123-5.tmp"
    for path in (stale, fresh):
        path.write_bytes(b"x")
    old = time.time() - 2 * cache_module.STALE_TEMP_SECONDS
    os.utime(stale, (old, old))
    ThumbnailCache(tmp_path).prune()
    assert not stale.exists()
    assert fresh.exists()


def test_clear_disk_and_cache_without_directory(photo: Path, tmp_path: Path) -> None:
    cache = ThumbnailCache(tmp_path / "cache")
    assert cache.disk_size() == 0  # not created yet
    cache.get(photo, 40)
    size = cache.disk_size()
    assert size > 0
    assert cache.clear_disk() == size
    assert cache.disk_size() == 0
    assert ThumbnailCache().prune() == 0
    with pytest.raises(ValueError, match="negative"):
        cache.prune(-1)


def test_memory_items_must_be_positive() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        ThumbnailCache(memory_items=0)


def test_default_cache_dir_linux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cache_module.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert default_cache_dir() == tmp_path / "collagio"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert default_cache_dir() == Path.home() / ".cache" / "collagio"


def test_default_cache_dir_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cache_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_cache_dir() == tmp_path / "Collagio" / "cache"
    monkeypatch.delenv("LOCALAPPDATA")
    assert default_cache_dir() == Path.home() / "AppData" / "Local" / "Collagio" / "cache"


def test_missing_photo_raises_image_load_error(tmp_path: Path) -> None:
    with pytest.raises(ImageLoadError, match="photo not found"):
        ThumbnailCache().get(tmp_path / "gone.jpg", 64)
