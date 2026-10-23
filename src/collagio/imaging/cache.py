"""Thumbnail cache: in-memory LRU in front of an optional on-disk PNG cache.

Entries are keyed by absolute path, modification time, file size and the
requested size, so edited photos are picked up automatically.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections import OrderedDict
from pathlib import Path

from PIL import Image

from collagio.imaging.loader import load_image


def default_cache_dir() -> Path:
    """Per-user cache folder: %LOCALAPPDATA%\\Collagio\\cache or $XDG_CACHE_HOME/collagio."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Collagio" / "cache"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "collagio"


class ThumbnailCache:
    def __init__(self, directory: Path | None = None, memory_items: int = 256) -> None:
        if memory_items < 1:
            raise ValueError("memory_items must be at least 1")
        self.directory = directory
        self.memory_items = memory_items
        self._memory: OrderedDict[str, Image.Image] = OrderedDict()
        self.memory_hits = 0
        self.disk_hits = 0
        self.misses = 0

    @staticmethod
    def key(path: str | Path, max_edge: int) -> str:
        resolved = Path(path).resolve()
        stat = resolved.stat()
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
                self.disk_hits += 1
                self._remember(key, image)
                return image.copy()

        self.misses += 1
        image = load_image(path, max_edge=max_edge)
        if disk_path is not None:
            disk_path.parent.mkdir(parents=True, exist_ok=True)
            temp = disk_path.with_suffix(".tmp")
            image.save(temp, format="PNG")
            os.replace(temp, disk_path)
        self._remember(key, image)
        return image.copy()

    def clear_memory(self) -> None:
        self._memory.clear()
