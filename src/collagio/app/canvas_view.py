"""The interactive collage canvas.

Scene coordinates are canvas pixels at full export resolution. Every photo is
one pixmap item showing its preview tile (rendered exactly like the export, at
reduced scale). Interaction works on the project data and commits one undo step
per gesture when the mouse is released:

- click: select (Ctrl: add/remove); drag: move. In grid mode dropping a photo
  onto another one swaps them; anywhere else it snaps back.
- corner handles: resize (aspect ratio kept); round handle: rotate (Shift: 15°).
- Alt+drag: pan the photo inside its frame; Ctrl+wheel: zoom the crop.
- wheel: zoom the view; middle button drag: pan the view.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
    QStyle,
    QWidget,
)

from collagio.app.preview import PreviewRenderer, TileResult, preview_scale, render_key
from collagio.app.qt_image import to_qimage
from collagio.app.strings import error_message
from collagio.core.document import Document
from collagio.core.geometry import (
    Point,
    centre,
    contains,
    pan_crop,
    photo_at,
    resize_from_corner,
    rotate_by_drag,
    to_local,
    to_world,
    zoom_crop,
)
from collagio.core.model import CropBox, LayoutMode, PhotoItem, Project, Rect, TextItem
from collagio.errors import CollagioError
from collagio.imaging.smartcrop import fill_crop
from collagio.layout.scattered import rotated_corners
from collagio.render.renderer import content_aspect, style_unit, text_tile
from collagio.render.text import text_size

ACCENT = QColor("#2f7de1")
TEXT_Z = 100_000  # texts are drawn above all photos
HANDLE_PX = 10  # handle size on screen
ROTATE_HANDLE_PX = 28  # distance of the rotation handle above the top edge, on screen
DRAG_THRESHOLD_PX = 4
ZOOM_STEP = 1.15
CROP_ZOOM_STEP = 1.1
MAX_LISTED_ERRORS = 5  # in the message about photos that cannot be shown
CROP_ZOOM_MERGE_SECONDS = 0.5  # wheel steps closer together are one undo step


def canvas_key(project: Project) -> tuple[int, int]:
    return project.canvas.width, project.canvas.height


class Gesture(Enum):
    NONE = auto()
    PRESS = auto()  # button down, not yet dragged far enough
    MOVE = auto()
    SWAP = auto()
    RESIZE = auto()
    ROTATE = auto()
    PAN_CROP = auto()
    PAN_VIEW = auto()
    MOVE_TEXT = auto()


@dataclass
class _Drag:
    gesture: Gesture = Gesture.NONE
    start: Point = (0.0, 0.0)  # scene position where the button went down
    start_view: QPoint = field(default_factory=QPoint)
    photo_id: str | None = None
    corner: int = 0
    live: dict[str, tuple[Rect, float]] = field(default_factory=dict)  # preview of the result
    swap_target: str | None = None
    live_offset: tuple[float, float] | None = None  # text drag: offset so far
    text_origin: QPointF = field(default_factory=QPointF)  # text item position at the start


class PhotoGraphicsItem(QGraphicsPixmapItem):
    def __init__(self, photo_id: str) -> None:
        super().__init__()
        self.photo_id = photo_id
        self.key: tuple[object, ...] | None = None
        self.tile_offset: tuple[float, float] = (0.0, 0.0)
        self.preview_scale = 1.0
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    def set_tile(self, image: QImage, offset: tuple[float, float], scale: float) -> None:
        self.setPixmap(QPixmap.fromImage(image))
        self.tile_offset = offset
        self.preview_scale = scale
        self.reset_live()

    def place(self, rect: Rect) -> None:
        self.setPos(rect.x + self.tile_offset[0], rect.y + self.tile_offset[1])

    def reset_live(self) -> None:
        self.setRotation(0)
        self.setScale(1 / self.preview_scale)

    def show_live(self, original: Rect, rotation_delta: float, rect: Rect) -> None:
        """Approximate a resize/rotation of the rendered tile until it is re-rendered."""
        ocx, ocy = centre(original)
        origin = QPointF(
            (ocx - original.x - self.tile_offset[0]) * self.preview_scale,
            (ocy - original.y - self.tile_offset[1]) * self.preview_scale,
        )
        self.setTransformOriginPoint(origin)
        self.setScale(rect.width / original.width / self.preview_scale)
        self.setRotation(-rotation_delta)  # Qt rotates clockwise
        ncx, ncy = centre(rect)
        self.setPos(
            original.x + self.tile_offset[0] + ncx - ocx,
            original.y + self.tile_offset[1] + ncy - ocy,
        )


class CanvasView(QGraphicsView):
    selection_changed = Signal(list)  # photo ids
    text_selected = Signal(object)  # text id or None
    files_dropped = Signal(list)  # paths (str)
    error = Signal(str)

    def __init__(
        self, document: Document, renderer: PreviewRenderer, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.document = document
        self.renderer = renderer
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#3b3b3b")))
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self.photo_items: dict[str, PhotoGraphicsItem] = {}
        self.text_items: dict[str, QGraphicsPixmapItem] = {}
        self._text_keys: dict[str, tuple[object, ...]] = {}
        self.selected: list[str] = []
        self.selected_text: str | None = None
        self.auto_fit = True
        self._background = QGraphicsPixmapItem()
        self._background.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._background.setZValue(-1)
        self.scene().addItem(self._background)
        self._background_key: tuple[object, ...] | None = None
        self._background_request = 0
        self._tile_requests: dict[str, int] = {}  # latest request per photo
        self._pending_tiles: set[str] = set()  # photos whose latest tile has not arrived
        self._tile_errors: dict[str, str] = {}  # photo id -> error shown for it
        self._new_tile_errors: list[str] = []  # reported once the pending tiles are in
        self._drag = _Drag()
        self._last_crop_zoom: tuple[str, float] | None = None  # photo id, time

        renderer.tile_ready.connect(self._on_tile)
        renderer.background_ready.connect(self._on_background)

    # --- keeping the scene in sync with the document ---------------------------------------------

    def set_document(self, document: Document) -> None:
        self.document = document
        for item in self.photo_items.values():
            self.scene().removeItem(item)
        self.photo_items.clear()
        self._tile_requests.clear()
        self._pending_tiles.clear()
        self._tile_errors.clear()
        self._new_tile_errors.clear()
        self.selected = []
        self._background_key = None
        self.auto_fit = True
        self.sync()
        self.selection_changed.emit([])

    def sync(self) -> None:
        project = self.document.project
        canvas = project.canvas
        self.scene().setSceneRect(QRectF(0, 0, canvas.width, canvas.height))

        background_key = (canvas.width, canvas.height, canvas.background, project.seed)
        if background_key != self._background_key:
            self._background_key = background_key
            self._background_request = self.renderer.next_request()
            self.renderer.render_background(project, self._background_request)

        current = {p.id for p in project.photos}
        for photo_id in list(self.photo_items):
            if photo_id not in current:
                self.scene().removeItem(self.photo_items.pop(photo_id))
                self._tile_requests.pop(photo_id, None)
                self._pending_tiles.discard(photo_id)
                self._tile_errors.pop(photo_id, None)
        for photo in project.photos:
            item = self.photo_items.get(photo.id)
            if item is None:
                item = PhotoGraphicsItem(photo.id)
                self.photo_items[photo.id] = item
                self.scene().addItem(item)
            item.setZValue(photo.z)
            key = render_key(project, photo)
            if key != item.key and photo.rect is not None:
                item.key = key
                request = self.renderer.next_request()
                self._tile_requests[photo.id] = request
                self._pending_tiles.add(photo.id)
                self.renderer.render_tile(project, photo.id, request)
            if photo.rect is not None:
                item.reset_live()
                item.place(photo.rect)

        self._sync_texts()
        kept = [i for i in self.selected if i in current]
        if kept != self.selected:
            self.selected = kept
            self.selection_changed.emit(list(kept))
        if self.auto_fit:
            self.fit()
        self.viewport().update()

    def _sync_texts(self) -> None:
        project = self.document.project
        scale = preview_scale(project)
        current = {t.id for t in project.texts}
        for text_id in list(self.text_items):
            if text_id not in current:
                self.scene().removeItem(self.text_items.pop(text_id))
                self._text_keys.pop(text_id, None)
        for index, text in enumerate(project.texts):
            item = self.text_items.get(text.id)
            if item is None:
                item = QGraphicsPixmapItem()
                item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                self.text_items[text.id] = item
                self.scene().addItem(item)
            item.setZValue(TEXT_Z + index)
            key = (repr(text), project.shadow, canvas_key(project))
            if key != self._text_keys.get(text.id):
                self._text_keys[text.id] = key
                try:
                    tile, (left, top) = text_tile(project, text, scale)
                except CollagioError as exc:
                    self.error.emit(error_message(exc))
                    continue
                item.setPixmap(QPixmap.fromImage(to_qimage(tile)))
                item.setScale(1 / scale)
                item.setPos(left / scale, top / scale)
        if self.selected_text not in current:
            self.select_text(None)

    def _on_tile(self, result: TileResult) -> None:
        if self._tile_requests.get(result.photo_id) != result.request:
            return  # stale
        self._pending_tiles.discard(result.photo_id)
        item = self.photo_items.get(result.photo_id)
        photo = self._photo(result.photo_id)
        if item is not None and photo is not None and photo.rect is not None:
            scale = preview_scale(self.document.project)
            if result.error is None:
                self._tile_errors.pop(photo.id, None)
                item.set_tile(result.image, result.offset, scale)
            else:
                if self._tile_errors.get(photo.id) != result.error:
                    self._tile_errors[photo.id] = result.error
                    self._new_tile_errors.append(result.error)
                image, offset = self._placeholder(photo.rect, photo.rotation, scale)
                item.set_tile(image, offset, scale)
            item.place(photo.rect)
        if not self._pending_tiles and self._new_tile_errors:
            self._report_tile_errors()

    def _report_tile_errors(self) -> None:
        """One message for all photos that failed since the last report."""
        errors, self._new_tile_errors = self._new_tile_errors, []
        if len(errors) == 1:
            self.error.emit(errors[0])
            return
        shown = errors[:MAX_LISTED_ERRORS]
        if len(errors) > len(shown):
            shown.append("…")
        heading = self.tr("{} photos could not be shown:").format(len(errors))
        self.error.emit("\n".join([heading, *shown]))

    def _placeholder(
        self, rect: Rect, rotation: float, scale: float
    ) -> tuple[QImage, tuple[float, float]]:
        """Grey tile with a warning sign for a photo that cannot be shown."""
        width, height = max(1, round(rect.width * scale)), max(1, round(rect.height * scale))
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("#9a9a9a"))
        icon_size = max(1, min(width, height) // 3)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        painter = QPainter(image)
        painter.drawPixmap(
            (width - icon_size) // 2, (height - icon_size) // 2, icon.pixmap(icon_size)
        )
        painter.end()
        if rotation:
            image = image.transformed(
                QTransform().rotate(-rotation), Qt.TransformationMode.SmoothTransformation
            )
        offset = (
            (rect.width - image.width() / scale) / 2,
            (rect.height - image.height() / scale) / 2,
        )
        return image, offset

    def _on_background(self, request: int, image: QImage) -> None:
        if request != self._background_request:
            return
        self._background.setPixmap(QPixmap.fromImage(image))
        self._background.setScale(1 / preview_scale(self.document.project))

    # --- view ------------------------------------------------------------------------------------

    def fit(self) -> None:
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        self.auto_fit = False
        self.scale(factor, factor)

    def fit_to_window(self) -> None:
        self.auto_fit = True
        self.fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit()

    def _view_scale(self) -> float:
        return self.transform().m11() or 1.0

    # --- selection -------------------------------------------------------------------------------

    def _photo(self, photo_id: str) -> PhotoItem | None:
        return next((p for p in self.document.project.photos if p.id == photo_id), None)

    def select_text(self, text_id: str | None) -> None:
        if text_id != self.selected_text:
            self.selected_text = text_id
            if text_id is not None:
                self.select([])
            self.text_selected.emit(text_id)
            self.viewport().update()

    def _text_frame(self, text: TextItem) -> Rect:
        try:
            width, height = text_size(text, style_unit(self.document.project, 1.0))
        except CollagioError:  # e.g. the font file was deleted: keep the editor usable
            width = height = 2
        return Rect(text.x - width / 2, text.y - height / 2, width, height)

    def _text_at(self, point: Point) -> TextItem | None:
        for text in reversed(self.document.project.texts):
            if text.text.strip() and contains(self._text_frame(text), text.rotation, point):
                return text
        return None

    def select(self, photo_ids: list[str]) -> None:
        if photo_ids and self.selected_text is not None:
            self.select_text(None)
        if photo_ids != self.selected:
            self.selected = list(photo_ids)
            self.selection_changed.emit(list(photo_ids))
            self.viewport().update()

    # --- hit testing -----------------------------------------------------------------------------

    def _handle_positions(self, photo: PhotoItem) -> list[Point]:
        """Four corners and the rotation handle, in scene coordinates."""
        assert photo.rect is not None
        corners = rotated_corners(photo.rect, photo.rotation)
        distance = photo.rect.height / 2 + ROTATE_HANDLE_PX / self._view_scale()
        rotate = to_world((0.0, -distance), centre(photo.rect), photo.rotation)
        return [*corners, rotate]

    def _handle_at(self, point: Point) -> tuple[str, int] | None:
        if len(self.selected) != 1:
            return None
        photo = self._photo(self.selected[0])
        if photo is None or photo.rect is None:
            return None
        reach = HANDLE_PX / self._view_scale()
        for index, (hx, hy) in enumerate(self._handle_positions(photo)):
            if abs(point[0] - hx) <= reach and abs(point[1] - hy) <= reach:
                return photo.id, index
        return None

    # --- mouse -----------------------------------------------------------------------------------

    @staticmethod
    def _point(scene_pos: QPointF) -> Point:
        return scene_pos.x(), scene_pos.y()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = self._point(self.mapToScene(event.position().toPoint()))
        self._drag = _Drag(start=point, start_view=event.position().toPoint())
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag.gesture = Gesture.PAN_VIEW
            self.auto_fit = False
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        text = self._text_at(point)
        if text is not None:
            self.select_text(text.id)
            self._drag.gesture = Gesture.MOVE_TEXT
            self._drag.text_origin = self.text_items[text.id].pos()
            return

        handle = self._handle_at(point)
        if handle is not None:
            self._drag.photo_id, index = handle
            self._drag.gesture = Gesture.ROTATE if index == 4 else Gesture.RESIZE
            self._drag.corner = index
            return

        photo = photo_at(self.document.project.photos, point)
        if photo is None:
            self.select([])
            self.select_text(None)
            return
        self._drag.photo_id = photo.id
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.AltModifier:
            self.select([photo.id])
            self._drag.gesture = Gesture.PAN_CROP
            return
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            toggled = [i for i in self.selected if i != photo.id]
            if photo.id not in self.selected:
                toggled.append(photo.id)
            self.select(toggled)
            self._drag.gesture = Gesture.NONE
            return
        if photo.id not in self.selected:
            self.select([photo.id])
        self._drag.gesture = Gesture.PRESS

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        drag = self._drag
        position = event.position().toPoint()
        point = self._point(self.mapToScene(position))
        if drag.gesture is Gesture.PAN_VIEW:
            delta = position - drag.start_view
            drag.start_view = position
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        if drag.gesture is Gesture.PRESS:
            if (position - drag.start_view).manhattanLength() < DRAG_THRESHOLD_PX:
                return
            grid = self.document.project.layout.mode is LayoutMode.GRID
            drag.gesture = Gesture.SWAP if grid and len(self.selected) == 1 else Gesture.MOVE
        if drag.gesture is Gesture.MOVE_TEXT and self.selected_text is not None:
            text = next(t for t in self.document.project.texts if t.id == self.selected_text)
            frame = self._text_frame(text)
            dx, dy = point[0] - drag.start[0], point[1] - drag.start[1]
            moved = Rect(frame.x + dx, frame.y + dy, frame.width, frame.height)
            drag.live = {text.id: (moved, text.rotation)}
            self.text_items[text.id].setPos(drag.text_origin + QPointF(dx, dy))
            drag.live_offset = (dx, dy)
        elif drag.gesture in (Gesture.MOVE, Gesture.SWAP):
            self._update_move(point)
        elif drag.gesture in (Gesture.RESIZE, Gesture.ROTATE):
            self._update_transform(
                point, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            )
        else:
            super().mouseMoveEvent(event)
            return
        self.viewport().update()

    def _update_move(self, point: Point) -> None:
        drag = self._drag
        dx, dy = point[0] - drag.start[0], point[1] - drag.start[1]
        drag.live.clear()
        for photo_id in self.selected:
            photo = self._photo(photo_id)
            if photo is None or photo.rect is None:
                continue
            moved = Rect(photo.rect.x + dx, photo.rect.y + dy, photo.rect.width, photo.rect.height)
            drag.live[photo_id] = (moved, photo.rotation)
            self.photo_items[photo_id].place(moved)
        if drag.gesture is Gesture.SWAP:
            others = [p for p in self.document.project.photos if p.id != drag.photo_id]
            target = photo_at(others, point)
            drag.swap_target = target.id if target is not None else None

    def _update_transform(self, point: Point, snap: bool) -> None:
        drag = self._drag
        assert drag.photo_id is not None
        photo = self._photo(drag.photo_id)
        if photo is None or photo.rect is None:
            return
        if drag.gesture is Gesture.RESIZE:
            rect = resize_from_corner(photo.rect, photo.rotation, drag.corner, point)
            rotation = photo.rotation
        else:
            rect = photo.rect
            rotation = rotate_by_drag(centre(photo.rect), drag.start, point, photo.rotation, snap)
        drag.live = {photo.id: (rect, rotation)}
        self.photo_items[photo.id].show_live(photo.rect, rotation - photo.rotation, rect)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        drag, self._drag = self._drag, _Drag()
        point = self._point(self.mapToScene(event.position().toPoint()))
        try:
            if drag.gesture is Gesture.MOVE and drag.live:
                self.document.move_photos(drag.live, "Move photo")
            elif drag.gesture is Gesture.SWAP:
                if drag.swap_target is not None and drag.photo_id is not None:
                    self.document.swap_photos(drag.photo_id, drag.swap_target)
                    self.select([drag.photo_id])
            elif drag.gesture in (Gesture.RESIZE, Gesture.ROTATE) and drag.live:
                label = "Resize photo" if drag.gesture is Gesture.RESIZE else "Rotate photo"
                self.document.move_photos(drag.live, label)
            elif drag.gesture is Gesture.PAN_CROP and drag.photo_id is not None:
                self._pan_crop(drag.photo_id, drag.start, point)
            elif drag.gesture is Gesture.MOVE_TEXT and drag.live_offset is not None:
                text_id = self.selected_text
                assert text_id is not None
                text = next(t for t in self.document.project.texts if t.id == text_id)
                dx, dy = drag.live_offset
                self.document.move_text(text_id, text.x + dx, text.y + dy)
            elif drag.gesture is Gesture.PAN_VIEW:
                return
        except CollagioError as exc:
            self.error.emit(error_message(exc))
        self.sync()  # snaps back anything that was not committed

    # --- crop ------------------------------------------------------------------------------------

    def current_crop(self, photo: PhotoItem) -> CropBox:
        """The crop in effect for `photo` (explicit, or the automatic one)."""
        if photo.crop is not None:
            return photo.crop
        width, height = self.document.size_of(photo.path)
        return fill_crop(
            (width, height), content_aspect(self.document.project, photo, width / height)
        )

    def _pan_crop(self, photo_id: str, start: Point, end: Point) -> None:
        photo = self._photo(photo_id)
        if photo is None or photo.rect is None:
            return
        # The drag in the photo's own (rotated) frame.
        origin = centre(photo.rect)
        sx, sy = to_local(start, origin, photo.rotation)
        ex, ey = to_local(end, origin, photo.rotation)
        if math.hypot(ex - sx, ey - sy) < 1e-9:
            return
        crop = self.current_crop(photo)
        moved = pan_crop(crop, (photo.rect.width, photo.rect.height), ex - sx, ey - sy)
        self.document.crop_photo(photo_id, moved)

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120
        if not steps:
            return
        point = self._point(self.mapToScene(event.position().toPoint()))
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            photo = photo_at(self.document.project.photos, point)
            if photo is not None and photo.rect is not None:
                local = to_local(point, centre(photo.rect), photo.rotation)
                anchor = (
                    min(max(local[0] / photo.rect.width + 0.5, 0.0), 1.0),
                    min(max(local[1] / photo.rect.height + 0.5, 0.0), 1.0),
                )
                crop = self.current_crop(photo)
                now = time.monotonic()
                last = self._last_crop_zoom
                merge = (
                    last is not None
                    and last[0] == photo.id
                    and now - last[1] < CROP_ZOOM_MERGE_SECONDS
                )
                self._last_crop_zoom = (photo.id, now)
                try:
                    self.document.crop_photo(
                        photo.id, zoom_crop(crop, CROP_ZOOM_STEP**steps, anchor), merge
                    )
                except CollagioError as exc:
                    self.error.emit(error_message(exc))
                self.sync()
            return
        self.zoom(ZOOM_STEP**steps)

    # --- context menu ----------------------------------------------------------------------------

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        point = self._point(self.mapToScene(event.pos()))
        photo = photo_at(self.document.project.photos, point)
        if photo is None:
            return
        if photo.id not in self.selected:
            self.select([photo.id])
        menu = QMenu(self)
        for text, handler in (
            (self.tr("Bring to front"), lambda: self.document.restack(photo.id, True)),
            (self.tr("Send to back"), lambda: self.document.restack(photo.id, False)),
            (self.tr("Reset crop"), lambda: self.document.crop_photo(photo.id, None)),
            (self.tr("Remove photo"), lambda: self.document.remove_photos(list(self.selected))),
        ):
            action = QAction(text, menu)
            action.triggered.connect(handler)
            menu.addAction(action)
        menu.exec(event.globalPos())
        self.sync()

    # --- drag and drop of files ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit([str(p) for p in paths])
            event.acceptProposedAction()

    # --- selection overlay -----------------------------------------------------------------------

    def drawForeground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        live = self._drag.live
        scale = self._view_scale()
        pen = QPen(ACCENT, 2)
        pen.setCosmetic(True)
        if len(self.selected) > 1:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for photo_id in self.selected:
            photo = self._photo(photo_id)
            if photo is None or photo.rect is None:
                continue
            frame, rotation = live.get(photo_id, (photo.rect, photo.rotation))
            corners = rotated_corners(frame, rotation)
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in corners]))

        if self.selected_text is not None:
            text = next(
                (t for t in self.document.project.texts if t.id == self.selected_text), None
            )
            if text is not None:
                frame, rotation = live.get(text.id, (self._text_frame(text), text.rotation))
                corners = rotated_corners(frame, rotation)
                painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in corners]))

        target = self._drag.swap_target
        if target is not None:
            photo = self._photo(target)
            if photo is not None and photo.rect is not None:
                thick = QPen(ACCENT, 5)
                thick.setCosmetic(True)
                painter.setPen(thick)
                corners = rotated_corners(photo.rect, photo.rotation)
                painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in corners]))

        if len(self.selected) == 1 and self._drag.gesture not in (Gesture.MOVE, Gesture.SWAP):
            photo = self._photo(self.selected[0])
            if photo is None or photo.rect is None:
                return
            frame, rotation = live.get(photo.id, (photo.rect, photo.rotation))
            shown = PhotoItem(photo.id, photo.path, rect=frame, rotation=rotation)
            handles = self._handle_positions(shown)
            size = HANDLE_PX / scale
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor("white")))
            top_mid = to_world((0.0, -frame.height / 2), centre(frame), rotation)
            painter.drawLine(QPointF(*top_mid), QPointF(*handles[4]))
            for hx, hy in handles[:4]:
                painter.drawRect(QRectF(hx - size / 2, hy - size / 2, size, size))
            painter.drawEllipse(QPointF(*handles[4]), size * 0.6, size * 0.6)
