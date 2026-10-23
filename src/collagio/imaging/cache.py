"""Thumbnail cache: in-memory LRU in front of an optional on-disk PNG cache.

Entries are keyed by absolute path, modification time, file size and the
requested size, so edited photos are picked up automatically. The disk cache is
kept under a size limit by `prune`, which removes the least recently used files
first (a disk hit refreshes the file's modification time).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

from PIL import Image

from collagio.errors import ImageLoadError
from collagio.imaging.loader import load_image

DEFAULT_DISK_LIMIT = 500 * 1024 * 1024  # bytes
STALE_TEMP_SECONDS = 3600  # leftovers of interrupted writes


def default_cache_dir() -> Path:
    """Per-user cache folder: %LOCALAPPDATA%\\Collagio\\cache or $XDG_CACHE_HOME/collagio."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Collagio" / "cache"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "collagio"


class ThumbnailCache:
    """Safe to share between threads; photos are decoded outside the lock."""

    def __init__(self, directory: Path | None = None, memory_items: int = 256) -> None:
        if memory_items < 1:
            raise ValueError("memory_items must be at least 1")
        self.directory = directory
        self.memory_items = memory_items
        self._memory: OrderedDict[str, Image.Image] = OrderedDict()
        self.memory_hits = 0
        self.disk_hits = 0
        self.misses = 0
        self._lock = threading.Lock()

    @staticmethod
    def key(path: str | Path, max_edge: int) -> str:
        resolved = Path(path).resolve()
        try:
            stat = resolved.stat()
        except OSError as exc:
            raise ImageLoadError("photo not found: {path}", path=path) from exc
        material = f"{resolved}|{stat.st_mtime_ns}|{stat.st_size}|{max_edge}"
        return hashlib.sha256(material.encode()).hexdigest()

    def _disk_path(self, key: str) -> Path | None:
        if self.directory is None:
            return None
        return self.directory / key[:2] / f"{key}.png"

    def _remember(self, key: str, image: Image.Image) -> None:
        self._memory[key] = image
        self._memory.move_to_end(key)
        while len(self._memory) > self.memory_items:
            self._memory.popitem(last=False)

    def get(self, path: str | Path, max_edge: int) -> Image.Image:
        """Upright photo with its longer side at most `max_edge`. Returns a copy."""
        key = self.key(path, max_edge)
        with self._lock:
            if key in self._memory:
                self.memory_hits += 1
                self._memory.move_to_end(key)
                return self._memory[key].copy()

        disk_path = self._disk_path(key)
        if disk_path is not None and disk_path.exists():
            try:
                with Image.open(disk_path) as cached:
                    image = cached.copy()
            except OSError:  # corrupt cache file: fall through and regenerate
                disk_path.unlink(missing_ok=True)
            else:
                with contextlib.suppress(OSError):
                    os.utime(disk_path)  # recently used: pruned last
                with self._lock:
                    self.disk_hits += 1
                    self._remember(key, image)
                return image.copy()

        image = load_image(path, max_edge=max_edge)
        if disk_path is not None:
            disk_path.parent.mkdir(parents=True, exist_ok=True)
            # Unique per thread, so concurrent loads of one photo do not clash.
            temp = disk_path.with_suffix(f".{os.getpid()}-{threading.get_ident()}.tmp")
            image.save(temp, format="PNG")
            os.replace(temp, disk_path)
        with self._lock:
            self.misses += 1
            self._remember(key, image)
        return image.copy()

    def clear_memory(self) -> None:
        with self._lock:
            self._memory.clear()

    def disk_size(self) -> int:
        """Bytes used by the disk cache."""
        return sum(size for _, _, size in self._disk_files())

    def prune(self, max_bytes: int = DEFAULT_DISK_LIMIT) -> int:
        """Delete the least recently used disk entries until at most `max_bytes` remain.

        Leftover temporary files of interrupted writes are deleted too. Returns the
        number of bytes freed.
        """
        if max_bytes < 0:
            raise ValueError("max_bytes must not be negative")
        now = time.time()
        files = [
            (path, used, size)
            for path, used, size in self._disk_files()
            # A recent temporary file may still be written by another thread or instance.
            if path.suffix != ".tmp" or now - used > STALE_TEMP_SECONDS
        ]
        excess = sum(size for _, _, size in files) - max_bytes
        freed = 0
        for path, _, size in sorted(files, key=lambda entry: entry[1]):
            if freed >= excess and path.suffix != ".tmp":
                continue
            try:
                path.unlink()
            except OSError:
                continue
            freed += size
        return freed

    def clear_disk(self) -> int:
        """Delete the whole disk cache; returns the number of bytes freed."""
        return self.prune(0)

    def _disk_files(self) -> list[tuple[Path, float, int]]:
        """Cache files with their last use (modification time) and size."""
        if self.directory is None or not self.directory.is_dir():
            return []
        files = []
        for path in self.directory.glob("*/*"):
            if path.suffix not in (".png", ".tmp"):
                continue
            try:
                stat = path.stat()
            except OSError:  # removed meanwhile
                continue
            files.append((path, stat.st_mtime, stat.st_size))
        return files
