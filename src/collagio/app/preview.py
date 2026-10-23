"""Background rendering of photo previews for the editor.

Each photo is rendered exactly as in the export, at a reduced scale, in a
worker thread. Results carry a request number so stale results (the photo was
changed again meanwhile) are dropped.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from collagio.app.qt_image import to_qimage
from collagio.core.model import PhotoItem, Project
from collagio.errors import CollagioError
from collagio.imaging.cache import ThumbnailCache
from collagio.render.background import render_background
from collagio.render.renderer import render_photo
from collagio.styles.base import STYLE_UNITS_PER_SHORT_EDGE

PREVIEW_LONG_EDGE = 2000  # preview canvas size in pixels (longer side)
SOURCE_LONG_EDGE = 2000  # photos are decoded at most this large for previews
ICON_EDGE = 160


def preview_scale(project: Project) -> float:
    longest = max(project.canvas.width, project.canvas.height)
    return min(1.0, PREVIEW_LONG_EDGE / longest)


def render_key(project: Project, item: PhotoItem) -> tuple[object, ...]:
    """Everything that changes how a photo looks, but not where it is."""
    rect = item.rect
    size = None if rect is None else (round(rect.width, 3), round(rect.height, 3))
    return (
        item.path,
        size,
        round(item.rotation, 4),
        item.crop,
        repr(project.style_for(item)),
        project.shadow,
        project.canvas.width,
        project.canvas.height,
        project.seed,
    )


@dataclass(frozen=True)
class TileResult:
    request: int
    photo_id: str
    image: QImage
    offset: tuple[float, float]  # canvas position of the image minus the photo's rect origin
    error: str | None = None


class _Signals(QObject):
    tile = Signal(object)  # TileResult
    background = Signal(int, QImage)
    icon = Signal(str, QImage)


class _Job(QRunnable):
    def __init__(self, work: Callable[[], None]) -> None:
        super().__init__()
        self._work = work

    def run(self) -> None:
        self._work()


class PreviewRenderer(QObject):
    """Renders tiles, backgrounds and list icons on a thread pool."""

    tile_ready = Signal(object)  # TileResult
    background_ready = Signal(int, QImage)
    icon_ready = Signal(str, QImage)

    def __init__(self, cache: ThumbnailCache, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.pool = QThreadPool(self)
        self._signals = _Signals()
        self._signals.tile.connect(self.tile_ready)
        self._signals.background.connect(self.background_ready)
        self._signals.icon.connect(self.icon_ready)
        self._request = 0

    def _load(self, path: str) -> Image.Image:
        return self.cache.get(path, SOURCE_LONG_EDGE)

    def next_request(self) -> int:
        self._request += 1
        return self._request

    def render_tile(self, project: Project, photo_id: str, request: int) -> None:
        snapshot = copy.deepcopy(project)
        item = next(p for p in snapshot.photos if p.id == photo_id)
        scale = preview_scale(snapshot)

        def work() -> None:
            try:
                tile, (left, top) = render_photo(snapshot, item, scale, self._load)
            except (CollagioError, OSError) as exc:
                self._signals.tile.emit(TileResult(request, photo_id, QImage(), (0, 0), str(exc)))
                return
            assert item.rect is not None  # render_photo checked it
            offset = (left / scale - item.rect.x, top / scale - item.rect.y)
            self._signals.tile.emit(TileResult(request, photo_id, to_qimage(tile), offset))

        self.pool.start(_Job(work))

    def render_background(self, project: Project, request: int) -> None:
        background = copy.deepcopy(project.canvas.background)
        scale = preview_scale(project)
        unit = project.canvas.short_edge * scale / STYLE_UNITS_PER_SHORT_EDGE
        seed = project.seed
        size = (
            max(1, round(project.canvas.width * scale)),
            max(1, round(project.canvas.height * scale)),
        )

        def work() -> None:
            try:
                image = render_background(background, size, unit=unit, seed=seed, loader=self._load)
            except (CollagioError, OSError):
                image = Image.new("RGB", size, "white")
            self._signals.background.emit(request, to_qimage(image))

        self.pool.start(_Job(work))

    def render_icon(self, path: str) -> None:
        def work() -> None:
            try:
                image = self.cache.get(path, ICON_EDGE)
            except (CollagioError, OSError):
                image = Image.new("RGB", (ICON_EDGE, ICON_EDGE), "#999999")
            self._signals.icon.emit(path, to_qimage(image))

        self.pool.start(_Job(work))

    def prune_cache(self) -> None:
        """Keep the thumbnail disk cache under its size limit, in the background."""

        def work() -> None:
            self.cache.prune()

        self.pool.start(_Job(work))

    def wait(self) -> None:
        """Block until all queued work is done (for tests and shutdown)."""
        self.pool.waitForDone()
