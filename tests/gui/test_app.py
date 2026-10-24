"""Editor tests: real widgets in Qt's offscreen mode, driven by simulated input."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDropEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from collagio import __version__
from collagio.app import main as gui_main
from collagio.app.main import build_window
from collagio.app.main_window import (
    ExportOptions,
    ExportOptionsDialog,
    MainWindow,
    expand_paths,
)
from collagio.app.strings import export_filter
from collagio.app.workers import ExportJob
from collagio.core.document import Document, autosave_name
from collagio.core.geometry import centre, photo_at
from collagio.core.model import LayoutMode, LayoutSettings, PhotoItem, Rect, StyleRef
from collagio.core.serialize import load_project, save_project
from collagio.imaging.cache import DEFAULT_DISK_LIMIT, ThumbnailCache
from collagio.layout.scattered import rotated_corners
from tests.gui.conftest import click, drag, settle, view_point


def _photo(window: MainWindow, photo_id: str) -> PhotoItem:
    return next(p for p in window.document.project.photos if p.id == photo_id)


def _rect(window: MainWindow, photo_id: str) -> Rect:
    rect = _photo(window, photo_id).rect
    assert rect is not None
    return rect


def _scattered(window: MainWindow, qtbot: QtBot) -> None:
    window.document.relayout(LayoutSettings(mode=LayoutMode.SCATTERED, max_rotation=0), seed=3)
    settle(window, qtbot)


def _visible_point(window: MainWindow, photo_id: str) -> tuple[float, float]:
    """A point where `photo_id` is the topmost photo."""
    rect = _rect(window, photo_id)
    for fx in (0.5, 0.3, 0.7, 0.2, 0.8):
        for fy in (0.5, 0.3, 0.7, 0.2, 0.8):
            point = (rect.x + rect.width * fx, rect.y + rect.height * fy)
            top = photo_at(window.document.project.photos, point)
            if top is not None and top.id == photo_id:
                return point
    raise AssertionError(f"{photo_id} is hidden")


# --- startup and photos --------------------------------------------------------------------------


def test_empty_window(window: MainWindow) -> None:
    assert window.windowTitle() == "Untitled – Collagio"
    assert not window.export_action.isEnabled()
    assert not window.undo_action.isEnabled()
    assert window.photo_list.list.count() == 0


def test_add_folder_shows_photos_and_previews(loaded: MainWindow) -> None:
    assert loaded.photo_list.list.count() == 8
    assert loaded.windowTitle() == "Untitled* – Collagio"
    assert len(loaded.canvas.photo_items) == 8
    assert all(not item.pixmap().isNull() for item in loaded.canvas.photo_items.values())
    assert loaded.undo_action.text() == "&Undo Add photos"
    assert loaded.export_action.isEnabled()


def test_preview_tiles_sit_on_their_photos(loaded: MainWindow) -> None:
    for photo in loaded.document.project.photos:
        item = loaded.canvas.photo_items[photo.id]
        bounds = item.sceneBoundingRect()
        rect = photo.rect
        assert rect is not None
        assert bounds.center().x() == pytest.approx(rect.x + rect.width / 2, abs=3)
        assert bounds.center().y() == pytest.approx(rect.y + rect.height / 2, abs=3)


def test_list_icons_arrive(loaded: MainWindow, qtbot: QtBot) -> None:
    settle(loaded, qtbot)
    item = loaded.photo_list.list.item(0)
    assert not item.icon().isNull()


def test_list_icon_follows_changes_on_disk(
    window: MainWindow, qtbot: QtBot, tmp_path: Path
) -> None:
    photo = tmp_path / "edited.png"
    Image.new("RGB", (60, 40), "#ff0000").save(photo)
    window.add_photos([str(photo)])
    settle(window, qtbot)

    def icon_colour() -> QColor:
        icon = window.photo_list.list.item(0).icon()
        return icon.pixmap(16, 16).toImage().pixelColor(8, 8)

    assert icon_colour().red() > 200
    Image.new("RGB", (60, 40), "#0000ff").save(photo)
    stat = photo.stat()
    os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    window.photo_list.show_project(window.document.project, [])
    settle(window, qtbot)
    assert icon_colour().blue() > 200


def test_clear_thumbnail_cache(loaded: MainWindow) -> None:
    cache = loaded.renderer.cache
    assert cache.disk_size() > 0
    loaded.clear_cache_action.trigger()
    assert cache.disk_size() == 0
    assert "MB" in loaded.statusBar().currentMessage()


def test_cache_is_pruned_on_start(
    make_window: Callable[[], MainWindow], monkeypatch: pytest.MonkeyPatch
) -> None:
    limits: list[int] = []

    def prune(self: ThumbnailCache, max_bytes: int = DEFAULT_DISK_LIMIT) -> int:
        limits.append(max_bytes)
        return 0

    monkeypatch.setattr(ThumbnailCache, "prune", prune)
    make_window().renderer.wait()
    assert limits == [DEFAULT_DISK_LIMIT]


def test_missing_photos_are_reported_once(
    window: MainWindow,
    qtbot: QtBot,
    sample_photos: list[Path],
    tmp_path: Path,
    errors: list[str],
) -> None:
    folder = tmp_path / "photos"
    folder.mkdir()
    copies = []
    for photo in sample_photos[:6]:
        copies.append(folder / photo.name)
        copies[-1].write_bytes(photo.read_bytes())
    window.add_photos([str(p) for p in copies])
    settle(window, qtbot)
    project = tmp_path / "moved.collagio"
    window.document.save(project)
    for photo in copies[:4]:
        photo.unlink()

    assert window.open_file(project)
    settle(window, qtbot)
    assert len(errors) == 1
    assert errors[0].startswith("4 photos could not be shown:")
    assert errors[0].count("\n") == 4
    for photo in window.document.project.photos:
        assert not window.canvas.photo_items[photo.id].pixmap().isNull()  # placeholder

    window.document.move_photo(  # a missing photo already reported: no new message
        "p001", window.document.project.photos[0].rect, 10.0, "Rotate photo"
    )
    settle(window, qtbot)
    assert len(errors) == 1


def test_one_missing_photo_shows_its_message(
    window: MainWindow, qtbot: QtBot, tmp_path: Path, errors: list[str]
) -> None:
    photos = [tmp_path / "a.png", tmp_path / "b.png"]
    for photo in photos:
        Image.new("RGB", (60, 40), "#336699").save(photo)
    window.add_photos([str(p) for p in photos])
    settle(window, qtbot)
    photos[0].unlink()
    rect = window.document.project.photos[0].rect
    assert rect is not None
    window.document.move_photo("p001", rect, 10.0, "Rotate photo")
    settle(window, qtbot)
    assert len(errors) == 1
    assert "a.png" in errors[0]


def test_expand_paths(sample_photos: list[Path], tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("x")
    paths = expand_paths(
        [str(sample_photos[0].parent), str(sample_photos[0]), str(tmp_path / "notes.txt")]
    )
    assert len(paths) == 9


def test_adding_nothing_usable_reports(
    window: MainWindow, tmp_path: Path, errors: list[str]
) -> None:
    (tmp_path / "notes.txt").write_text("x")
    window.add_photos([str(tmp_path / "notes.txt")])
    assert errors == ["No supported photos found."]


def test_drop_files_on_canvas(window: MainWindow, sample_photos: list[Path], qtbot: QtBot) -> None:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in sample_photos[:3]])
    event = QDropEvent(
        QPointF(100, 100), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    window.canvas.dropEvent(event)
    assert len(window.document.project.photos) == 3


def test_remove_selected(loaded: MainWindow) -> None:
    loaded.canvas.select(["p001", "p002"])
    loaded.remove_action.trigger()
    assert [p.id for p in loaded.document.project.photos][:2] == ["p003", "p004"]
    assert loaded.photo_list.list.count() == 6
    assert loaded.canvas.selected == []


# --- selection -----------------------------------------------------------------------------------


def test_click_selects_and_syncs_list(loaded: MainWindow) -> None:
    point = _visible_point(loaded, "p003")
    click(loaded, *point)
    assert loaded.canvas.selected == ["p003"]
    assert loaded.photo_list.selected_ids() == ["p003"]
    assert loaded.style_panel.target_selected.isChecked()
    click(loaded, -50, -50)  # outside the canvas
    assert loaded.canvas.selected == []


def test_ctrl_click_toggles(loaded: MainWindow) -> None:
    click(loaded, *_visible_point(loaded, "p001"))
    click(loaded, *_visible_point(loaded, "p002"), Qt.KeyboardModifier.ControlModifier)
    assert sorted(loaded.canvas.selected) == ["p001", "p002"]
    click(loaded, *_visible_point(loaded, "p001"), Qt.KeyboardModifier.ControlModifier)
    assert loaded.canvas.selected == ["p002"]


def test_list_selection_selects_on_canvas(loaded: MainWindow) -> None:
    loaded.photo_list.list.item(4).setSelected(True)
    assert loaded.canvas.selected == ["p005"]
    assert loaded.remove_action.isEnabled()


def test_select_all(loaded: MainWindow) -> None:
    loaded.select_all_action.trigger()
    assert len(loaded.canvas.selected) == 8


# --- moving, swapping, resizing, rotating --------------------------------------------------------


def test_drag_moves_in_scattered_mode_and_undo(loaded: MainWindow, qtbot: QtBot) -> None:
    _scattered(loaded, qtbot)
    before = _rect(loaded, "p004")
    start = _visible_point(loaded, "p004")
    drag(loaded, start, (start[0] + 150, start[1] + 80))
    after = _rect(loaded, "p004")
    assert (after.x - before.x, after.y - before.y) == (
        pytest.approx(150, abs=6),
        pytest.approx(80, abs=6),
    )
    assert loaded.undo_action.text() == "&Undo Move photo"
    loaded.undo_action.trigger()
    assert _rect(loaded, "p004") == before


def test_small_click_does_not_move(loaded: MainWindow, qtbot: QtBot) -> None:
    _scattered(loaded, qtbot)
    before = _rect(loaded, "p002")
    start = _visible_point(loaded, "p002")
    drag(loaded, start, (start[0] + 0.5, start[1]), steps=1)
    assert _rect(loaded, "p002") == before


def test_grid_drag_swaps_photos(loaded: MainWindow) -> None:
    first, second = _rect(loaded, "p001"), _rect(loaded, "p002")
    drag(loaded, _visible_point(loaded, "p001"), _visible_point(loaded, "p002"))
    assert _rect(loaded, "p001") == second
    assert _rect(loaded, "p002") == first
    assert loaded.undo_action.text() == "&Undo Swap photos"


def test_grid_drag_to_empty_space_snaps_back(loaded: MainWindow) -> None:
    before = _rect(loaded, "p001")
    drag(loaded, _visible_point(loaded, "p001"), (-200, -200))
    assert _rect(loaded, "p001") == before
    assert loaded.undo_action.text() == "&Undo Add photos"


def test_resize_with_corner_handle(loaded: MainWindow, qtbot: QtBot) -> None:
    _scattered(loaded, qtbot)
    loaded.canvas.select(["p002"])
    photo = _photo(loaded, "p002")
    original = _rect(loaded, "p002")  # the command replaces photo.rect
    corner = rotated_corners(original, photo.rotation)[2]  # bottom-right
    drag(loaded, corner, (corner[0] + 120, corner[1] + 120 / original.aspect))
    resized = _rect(loaded, "p002")
    assert resized.width == pytest.approx(original.width + 120, abs=8)
    assert resized.aspect == pytest.approx(original.aspect)
    assert (resized.x, resized.y) == pytest.approx((original.x, original.y))  # top-left fixed
    assert loaded.undo_action.text() == "&Undo Resize photo"


def _drawn_rect(window: MainWindow, photo_id: str) -> tuple[float, float, float, float]:
    bounds = window.canvas.photo_items[photo_id].sceneBoundingRect()
    return bounds.x(), bounds.y(), bounds.width(), bounds.height()


def test_tile_stays_on_its_photo_after_resize(loaded: MainWindow, qtbot: QtBot) -> None:
    """The live preview of a resize must not leave the tile shifted (grid, no rotation)."""
    loaded.canvas.select(["p002"])
    original = _rect(loaded, "p002")
    corner = (original.right, original.bottom)
    drag(loaded, corner, (corner[0] - 60, corner[1] - 60 / original.aspect))
    settle(loaded, qtbot)
    for photo_id in ("p002", "p001"):
        rect = _rect(loaded, photo_id)
        expected = (rect.x, rect.y, rect.width, rect.height)
        assert _drawn_rect(loaded, photo_id) == pytest.approx(expected, abs=2)
    loaded.undo_action.trigger()
    settle(loaded, qtbot)
    rect = _rect(loaded, "p002")
    assert _drawn_rect(loaded, "p002") == pytest.approx(
        (rect.x, rect.y, rect.width, rect.height), abs=2
    )


def test_edge_handle_changes_the_frame_shape_and_crops(loaded: MainWindow, qtbot: QtBot) -> None:
    loaded.canvas.select(["p001"])
    original = _rect(loaded, "p001")
    right_middle = (original.right, original.y + original.height / 2)
    start = QPointF(view_point(loaded, *right_middle))
    end = QPointF(view_point(loaded, right_middle[0] - original.width / 3, right_middle[1]))
    viewport = loaded.canvas.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start.toPoint())
    for step in range(1, 6):
        QTest.mouseMove(viewport, (start + (end - start) * step / 5).toPoint())

    def preview_has_new_width() -> bool:
        # One live render at a time: earlier frames may arrive first.
        loaded.renderer.wait()
        live = loaded.canvas.photo_items["p001"].sceneBoundingRect()
        return live.width() == pytest.approx(original.width * 2 / 3, rel=0.05)

    qtbot.waitUntil(preview_has_new_width, timeout=10_000)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end.toPoint())
    settle(loaded, qtbot)
    resized = _rect(loaded, "p001")
    assert resized.width == pytest.approx(original.width * 2 / 3, rel=0.05)
    assert resized.height == pytest.approx(original.height)
    assert (resized.x, resized.y) == pytest.approx((original.x, original.y))
    assert _drawn_rect(loaded, "p001") == pytest.approx(
        (resized.x, resized.y, resized.width, resized.height), abs=2
    )  # cropped to the new frame, not stretched
    assert loaded.undo_action.text() == "&Undo Resize photo"


def test_shift_corner_resizes_freely(loaded: MainWindow, qtbot: QtBot) -> None:
    loaded.canvas.select(["p002"])
    original = _rect(loaded, "p002")
    shift = Qt.KeyboardModifier.ShiftModifier
    viewport = loaded.canvas.viewport()
    start = view_point(loaded, original.right, original.bottom)
    end = view_point(loaded, original.right - 40, original.bottom - original.height / 2)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, shift, start)
    for step in range(1, 6):  # QTest.mouseMove cannot hold Shift
        position = QPointF(start + (end - start) * (step / 5))
        move = QMouseEvent(
            QEvent.Type.MouseMove, position, viewport.mapToGlobal(position),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, shift,
        )  # fmt: skip
        QApplication.sendEvent(viewport, move)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, shift, end)
    resized = _rect(loaded, "p002")
    assert resized.width == pytest.approx(original.width - 40, abs=3)
    assert resized.height == pytest.approx(original.height / 2, abs=3)
    assert resized.aspect != pytest.approx(original.aspect, rel=0.05)


def test_rotate_with_handle(loaded: MainWindow, qtbot: QtBot) -> None:
    _scattered(loaded, qtbot)
    loaded.canvas.select(["p003"])
    photo = _photo(loaded, "p003")
    assert photo.rect is not None
    handle = loaded.canvas._handle_positions(photo)[4]
    middle = centre(photo.rect)
    distance = middle[1] - handle[1]
    drag(loaded, handle, (middle[0] - distance, middle[1]))  # quarter turn to the left
    assert _photo(loaded, "p003").rotation == pytest.approx(90, abs=3)
    assert loaded.undo_action.text() == "&Undo Rotate photo"


def test_alt_drag_pans_the_crop(loaded: MainWindow) -> None:
    # p001 is landscape 3:2; find a cell where it gets cropped at the sides.
    photo = _photo(loaded, "p001")
    assert photo.crop is None
    start = _visible_point(loaded, "p001")
    drag(loaded, start, (start[0] + 40, start[1] + 40), Qt.KeyboardModifier.AltModifier)
    crop = _photo(loaded, "p001").crop
    assert crop is not None
    assert loaded.undo_action.text() == "&Undo Crop photo"


def test_ctrl_wheel_zooms_crop_and_reset(loaded: MainWindow) -> None:
    point = _visible_point(loaded, "p003")
    position = QPointF(view_point(loaded, *point))
    event = QWheelEvent(
        position, QPointF(loaded.canvas.viewport().mapToGlobal(position.toPoint())),
        QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False,
    )  # fmt: skip
    QApplication.sendEvent(loaded.canvas.viewport(), event)
    crop = _photo(loaded, "p003").crop
    assert crop is not None
    assert max(crop.width, crop.height) < 1.0
    loaded.canvas.select(["p003"])
    loaded.reset_crop_action.trigger()
    assert _photo(loaded, "p003").crop is None


def test_continuous_ctrl_wheel_zoom_is_one_undo_step(loaded: MainWindow) -> None:
    point = _visible_point(loaded, "p003")
    position = QPointF(view_point(loaded, *point))
    for _ in range(5):
        event = QWheelEvent(
            position, QPointF(loaded.canvas.viewport().mapToGlobal(position.toPoint())),
            QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False,
        )  # fmt: skip
        QApplication.sendEvent(loaded.canvas.viewport(), event)
    assert _photo(loaded, "p003").crop is not None
    loaded.undo_action.trigger()
    assert _photo(loaded, "p003").crop is None


def test_wheel_zooms_view_and_fit(loaded: MainWindow) -> None:
    before = loaded.canvas.transform().m11()
    loaded.zoom_in_action.trigger()
    assert loaded.canvas.transform().m11() == pytest.approx(before * 1.25)
    assert not loaded.canvas.auto_fit
    loaded.fit_action.trigger()
    assert loaded.canvas.transform().m11() == pytest.approx(before)


def test_restack_actions(loaded: MainWindow) -> None:
    loaded.canvas.select(["p001"])
    loaded.front_action.trigger()
    assert _photo(loaded, "p001").z == 7
    loaded.back_action.trigger()
    assert _photo(loaded, "p001").z == 0
    assert loaded.canvas.photo_items["p001"].zValue() == 0


# --- panels --------------------------------------------------------------------------------------


def test_layout_panel_rows_follow_mode(loaded: MainWindow) -> None:
    panel = loaded.layout_panel
    assert panel._form.isRowVisible(panel.order)
    assert not panel._form.isRowVisible(panel.overlap)
    panel.mode.setCurrentIndex(panel.mode.findData(LayoutMode.SCATTERED))
    assert not panel._form.isRowVisible(panel.order)
    assert panel._form.isRowVisible(panel.overlap)


def test_layout_panel_apply_and_shuffle(loaded: MainWindow) -> None:
    panel = loaded.layout_panel
    panel.mode.setCurrentIndex(panel.mode.findData(LayoutMode.SCATTERED))
    panel.rotation.setValue(20)
    panel.apply_button.click()
    layout = loaded.document.project.layout
    assert (layout.mode, layout.max_rotation) == (LayoutMode.SCATTERED, 20)
    seed = loaded.document.project.seed
    panel.shuffle_button.click()
    assert loaded.document.project.seed != seed or loaded.undo_action.text() == "&Undo New layout"


def test_apply_layout_asks_only_when_manual_edits_would_be_lost(loaded: MainWindow) -> None:
    panel = loaded.layout_panel
    answers: list[tuple[bool, bool]] = []
    asked: list[int] = []

    def ask() -> tuple[bool, bool]:
        asked.append(1)
        return answers.pop(0)

    panel.ask_replace = ask  # type: ignore[method-assign]
    panel.apply_button.click()  # automatic layout: nothing to lose
    assert asked == []
    assert loaded.undo_action.text() == "&Undo New layout"

    photo = _photo(loaded, "p001")
    assert photo.rect is not None
    loaded.document.move_photo("p001", photo.rect, 15.0, "Rotate photo")
    seed = panel.seed.value()
    answers.append((False, False))
    panel.shuffle_button.click()  # cancelled: nothing changes
    assert asked == [1]
    assert _photo(loaded, "p001").rotation == 15.0
    assert panel.seed.value() == seed
    assert loaded.undo_action.text() == "&Undo Rotate photo"

    answers.append((True, True))
    panel.apply_button.click()  # replaced, and don't ask again
    assert _photo(loaded, "p001").rotation == 0.0
    loaded.document.move_photo("p001", photo.rect, 15.0, "Rotate photo")
    panel.apply_button.click()
    assert asked == [1, 1]
    assert _photo(loaded, "p001").rotation == 0.0


def test_replace_question_dialog(loaded: MainWindow) -> None:
    def answer() -> None:
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        box.checkBox().setChecked(True)
        box.button(QMessageBox.StandardButton.Yes).click()

    QTimer.singleShot(0, answer)
    assert loaded.layout_panel.ask_replace() == (True, True)


def test_layout_panel_reports_errors(loaded: MainWindow, errors: list[str]) -> None:
    loaded.layout_panel.margin.setValue(50)
    loaded.layout_panel.apply_button.click()
    assert errors
    assert "margin" in errors[0]


def test_style_panel_default_style(loaded: MainWindow) -> None:
    panel = loaded.style_panel
    panel.style_combo.setCurrentIndex(panel.style_combo.findData("polaroid"))
    assert panel.form is not None
    caption = panel.form.fields["caption"]
    caption.setText("Hello")  # type: ignore[attr-defined]
    panel.apply_button.click()
    assert loaded.document.project.default_style == StyleRef("polaroid", {"caption": "Hello"})


def test_style_panel_selected_photos_and_reset(loaded: MainWindow) -> None:
    loaded.canvas.select(["p002"])
    panel = loaded.style_panel
    assert panel.target_selected.isChecked()
    panel.style_combo.setCurrentIndex(panel.style_combo.findData("stamp"))
    panel.apply_button.click()
    assert _photo(loaded, "p002").style == StyleRef("stamp")
    assert _photo(loaded, "p001").style is None
    assert not panel.reset_button.isHidden()
    panel.reset_button.click()
    assert _photo(loaded, "p002").style is None


def test_style_form_values_only_store_changes(loaded: MainWindow) -> None:
    panel = loaded.style_panel
    panel.style_combo.setCurrentIndex(panel.style_combo.findData("tape"))
    assert panel.form is not None
    assert panel.form.values() == {}
    panel.form.set_values({"variant": "corners", "tape_opacity": 0.5, "border_color": "#000000"})
    assert panel.form.values() == {
        "variant": "corners",
        "tape_opacity": 0.5,
        "border_color": "#000000",
    }


def test_shadow_settings(loaded: MainWindow) -> None:
    panel = loaded.style_panel
    panel.shadow_opacity.setValue(0.6)
    panel.shadow_blur.setValue(12)
    panel.shadow_button.click()
    shadow = loaded.document.project.shadow
    assert (shadow.opacity, shadow.blur) == (0.6, 12)


def test_canvas_panel_preset(loaded: MainWindow) -> None:
    panel = loaded.canvas_panel
    assert panel.preset.currentData() == "A4"
    panel.preset.setCurrentIndex(panel.preset.findData("fullhd"))
    assert (panel.width_spin.value(), panel.height_spin.value()) == (1080, 1920)
    panel.orientation.setCurrentIndex(1)  # landscape
    assert (panel.width_spin.value(), panel.height_spin.value()) == (1920, 1080)
    panel.apply_button.click()
    canvas = loaded.document.project.canvas
    assert (canvas.width, canvas.height) == (1920, 1080)
    assert all(p.rect is not None and p.rect.right <= 1920 for p in loaded.document.project.photos)


def test_canvas_panel_custom_size_and_gradient(loaded: MainWindow) -> None:
    panel = loaded.canvas_panel
    panel.preset.setCurrentIndex(panel.preset.findData("custom"))
    assert panel.width_spin.isEnabled()
    panel.width_spin.setValue(1234)
    panel.height_spin.setValue(999)
    panel.background_kind.setCurrentIndex(1)
    assert panel.color2.isEnabled()
    panel.color.set_color("#112233")
    panel.apply_button.click()
    canvas = loaded.document.project.canvas
    assert (canvas.width, canvas.height, canvas.background.color) == (1234, 999, "#112233")
    assert canvas.background.kind.value == "gradient"
    panel.refresh()
    assert panel.preset.currentData() == "custom"


# --- files ---------------------------------------------------------------------------------------


def test_save_open_and_recent(
    make_window: Callable[[], MainWindow], loaded: MainWindow, tmp_path: Path
) -> None:
    target = tmp_path / "trip.collagio"
    assert loaded._save_to(target)
    assert loaded.windowTitle() == "trip.collagio – Collagio"
    assert loaded.recent_files() == [str(target)]
    assert loaded.recent_menu.actions()[0].text() == "trip.collagio"

    other = make_window()
    assert other.open_file(target)
    assert other.document.project == loaded.document.project
    assert not other.document.modified


def test_save_uses_existing_path(loaded: MainWindow, tmp_path: Path) -> None:
    loaded._save_to(tmp_path / "a.collagio")
    loaded.document.relayout(seed=77)
    assert loaded.save()
    assert load_project(tmp_path / "a.collagio").seed == 77


def test_open_broken_file_reports(window: MainWindow, tmp_path: Path, errors: list[str]) -> None:
    broken = tmp_path / "broken.collagio"
    broken.write_text("{")
    assert not window.open_file(broken)
    assert "not valid JSON" in errors[0]


def test_new_collage(loaded: MainWindow) -> None:
    loaded.new_action.trigger()
    assert loaded.document.project.photos == []
    assert loaded.photo_list.list.count() == 0
    assert loaded.canvas.photo_items == {}


def test_autosave_and_recover(loaded: MainWindow, errors: list[str]) -> None:
    loaded.autosave()
    assert loaded.autosave_path.exists()
    photos = loaded.document.project
    loaded.new_action.trigger()
    assert loaded.recover()
    assert loaded.document.project == photos
    assert loaded.document.modified


def test_two_instances_autosave_and_recover_independently(
    make_window: Callable[[], MainWindow], sample_photos: list[Path]
) -> None:
    first, second = make_window(), make_window()
    first.add_photos([str(p) for p in sample_photos[:2]])
    second.add_photos([str(p) for p in sample_photos[2:5]])
    first.autosave()
    second.autosave()
    assert first.autosave_path != second.autosave_path
    assert first.recoverable() == [first.autosave_path]  # the other window is still running
    expected = second.document.project

    assert first.close()
    assert not first.autosave_path.exists()
    assert second.autosave_path.exists()  # not touched by the other window

    second._session_lock.unlock()  # as if the second instance had crashed
    third = make_window()
    assert third.recoverable() == [second.autosave_path]
    assert third.recover()
    assert third.document.project == expected
    assert third.autosave_path.exists()  # adopted: deleted when this window closes
    assert not second.autosave_path.exists()


def test_recover_asks_which_session(
    make_window: Callable[[], MainWindow], sample_photos: list[Path], tmp_path: Path
) -> None:
    window = make_window()
    for session, count in (("aaa", 2), ("bbb", 3)):
        project = Document()
        project.add_photos([str(p) for p in sample_photos[:count]])
        project.autosave(tmp_path / "cache" / autosave_name(session))
    offered: list[list[Path]] = []

    def choose(files: list[Path]) -> Path | None:
        offered.append(files)
        return files[-1] if len(offered) == 1 else None

    window.choose_recovery = choose  # type: ignore[method-assign]
    assert window.recover()
    assert len(offered[0]) == 2
    count = len(window.document.project.photos)
    assert count in (2, 3)
    assert window._recovery_label(window.autosave_path).startswith("Last saved")
    assert not window.recover()  # cancelled
    assert len(window.document.project.photos) == count


def test_recover_without_autosave(window: MainWindow, errors: list[str]) -> None:
    assert not window.recover()
    assert errors == ["There is no unsaved work to recover."]


def test_build_window_opens_project_or_photos(
    make_window: Callable[[], MainWindow], sample_photos: list[Path], tmp_path: Path
) -> None:
    window = build_window([str(p) for p in sample_photos[:2]], make_window())
    assert len(window.document.project.photos) == 2
    project = tmp_path / "p.collagio"
    save_project(window.document.project, project)
    reopened = build_window([str(project)], make_window())
    assert reopened.document.path == project


def test_close_with_unsaved_changes_can_be_cancelled(loaded: MainWindow) -> None:
    loaded.confirm_discard = lambda: False  # type: ignore[method-assign]
    assert not loaded.close()
    loaded.confirm_discard = lambda: True  # type: ignore[method-assign]
    loaded.autosave()
    assert loaded.close()
    assert not loaded.autosave_path.exists()


# --- export --------------------------------------------------------------------------------------


def test_export_in_background(loaded: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    target = tmp_path / "collage.jpg"
    job = loaded.export(target)
    assert job is not None
    with qtbot.waitSignal(job.signals.finished, timeout=20_000) as finished:
        pass
    assert finished.args == [str(target)]
    with Image.open(target) as image:
        assert image.size == (2480, 3508)


def test_export_can_be_cancelled(loaded: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    job = ExportJob(loaded.document.project, tmp_path / "x.png")
    job.cancel()
    with qtbot.waitSignal(job.signals.cancelled, timeout=10_000):
        loaded.export_pool.start(job)
    assert not (tmp_path / "x.png").exists()


def test_export_failure_is_reported(loaded: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    job = loaded.export(tmp_path / "missing" / "x.png")
    assert job is not None
    with qtbot.waitSignal(job.signals.failed, timeout=20_000) as failed:
        pass
    assert "cannot write" in failed.args[0]


@pytest.mark.parametrize(
    ("typed", "chosen", "expected"),
    [
        ("collage", 1, "collage.jpg"),  # no ending: the chosen type's
        ("collage", 2, "collage.pdf"),
        ("trip.v2", 0, "trip.v2.png"),  # not an image ending
        ("photo.JPEG", 2, "photo.JPEG"),  # a known ending is kept
    ],
)
def test_export_dialog_adds_the_chosen_ending(
    loaded: MainWindow,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    typed: str,
    chosen: int,
    expected: str,
) -> None:
    filters = export_filter().split(";;")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(tmp_path / typed), filters[chosen]),
    )
    asked: list[Path] = []

    def ask(path: Path) -> ExportOptions:
        asked.append(path)
        return ExportOptions()

    loaded.ask_export_options = ask  # type: ignore[method-assign]
    jobs: list[ExportJob] = []
    real_export = loaded.export
    loaded.export = lambda path, options=None: jobs.append(real_export(path, options))  # type: ignore[method-assign,func-returns-value]
    loaded.export_action.trigger()
    assert asked == [tmp_path / expected]
    (job,) = jobs
    assert job is not None
    with qtbot.waitSignal(job.signals.finished, timeout=20_000):
        pass
    assert (tmp_path / expected).exists()


def test_export_without_photos(window: MainWindow, tmp_path: Path) -> None:
    assert window.export(tmp_path / "x.png") is None


# --- undo / redo actions -------------------------------------------------------------------------


def test_undo_redo_actions(loaded: MainWindow) -> None:
    loaded.undo_action.trigger()
    assert loaded.document.project.photos == []
    assert loaded.redo_action.isEnabled()
    assert loaded.redo_action.text() == "&Redo Add photos"
    loaded.redo_action.trigger()
    assert len(loaded.document.project.photos) == 8


# --- phase 5: texts, backgrounds, print export ----------------------------------------------------


def test_text_panel_add_edit_remove(loaded: MainWindow) -> None:
    panel = loaded.text_panel
    panel.add_button.click()
    assert [t.text for t in loaded.document.project.texts] == ["Text"]
    assert panel.current_id() == "t001"
    assert loaded.canvas.selected_text == "t001"
    assert "t001" in loaded.canvas.text_items
    panel.text_edit.setPlainText("Summer\n2026")
    panel.size_spin.setValue(120)
    panel.color.set_color("#ff0000")
    panel.rotation.setValue(-10)
    panel.shadow.setChecked(True)
    panel.apply_button.click()
    text = loaded.document.project.texts[0]
    assert (text.text, text.size, text.color, text.rotation, text.shadow) == (
        "Summer\n2026", 120, "#ff0000", -10, True,
    )  # fmt: skip
    assert panel.list.item(0).text() == "Summer"
    panel.remove_button.click()
    assert loaded.document.project.texts == []
    assert loaded.canvas.text_items == {}


def test_text_with_missing_font_reports(
    loaded: MainWindow, errors: list[str], tmp_path: Path
) -> None:
    loaded.text_panel.add_button.click()
    loaded.text_panel.font_edit.setText(str(tmp_path / "missing.ttf"))
    loaded.text_panel.apply_button.click()
    assert any("cannot load font" in e for e in errors)
    assert loaded.document.project.texts[0].font == ""  # rejected: nothing changed


def test_drag_text_on_canvas(loaded: MainWindow) -> None:
    text_id = loaded.document.add_text("Drag me", size=150.0)
    # Copy the coordinates: the edit updates the text object in place.
    x, y = loaded.document.project.texts[0].x, loaded.document.project.texts[0].y
    loaded.canvas.select_text(None)
    drag(loaded, (x, y), (x + 200, y + 100))
    moved = loaded.document.project.texts[0]
    assert moved.x - x == pytest.approx(200, abs=6)
    assert moved.y - y == pytest.approx(100, abs=6)
    assert loaded.canvas.selected_text == text_id
    assert loaded.text_panel.current_id() == text_id
    assert loaded.undo_action.text() == "&Undo Move text"


def test_clicking_a_photo_deselects_the_text(loaded: MainWindow) -> None:
    loaded.document.add_text("Hi", x=200.0, y=200.0)
    loaded.canvas.select_text("t001")
    click(loaded, *_visible_point(loaded, "p005"))
    assert loaded.canvas.selected_text is None
    assert loaded.canvas.selected == ["p005"]


def test_delete_removes_selected_text(loaded: MainWindow) -> None:
    loaded.document.add_text("Bye")
    loaded.canvas.select_text("t001")
    assert loaded.remove_action.isEnabled()
    loaded.remove_action.trigger()
    assert loaded.document.project.texts == []
    assert len(loaded.document.project.photos) == 8


def test_layout_space_fields(loaded: MainWindow) -> None:
    loaded.layout_panel.space_bottom.setValue(10)
    loaded.layout_panel.apply_button.click()
    assert loaded.document.project.layout.space_bottom == pytest.approx(0.1)
    bottom = max(p.rect.bottom for p in loaded.document.project.photos if p.rect is not None)
    assert bottom <= 3508 - 0.02 * 2480 - 248 + 1e-6


def test_canvas_panel_texture_and_size_label(loaded: MainWindow) -> None:
    panel = loaded.canvas_panel
    assert panel.size_label.text() == "210 × 297 mm"
    panel.background_kind.setCurrentIndex(panel.background_kind.findData("texture"))
    assert panel._form.isRowVisible(panel.texture)
    assert not panel._form.isRowVisible(panel.color2)
    panel.texture.setCurrentIndex(panel.texture.findData("cork"))
    assert panel.color.color == "#b8875a"
    panel.apply_button.click()
    background = loaded.document.project.canvas.background
    assert (background.kind.value, background.texture, background.color) == (
        "texture",
        "cork",
        "#b8875a",
    )


def test_canvas_panel_photo_background(
    loaded: MainWindow, sample_photos: list[Path], qtbot: QtBot
) -> None:
    panel = loaded.canvas_panel
    panel.background_kind.setCurrentIndex(panel.background_kind.findData("photo"))
    assert panel._form.isRowVisible(panel.blur)
    assert not panel._form.isRowVisible(panel.color)
    panel.photo.setText(str(sample_photos[3]))
    panel.blur.setValue(40)
    panel.dim.setValue(0.5)
    panel.apply_button.click()
    background = loaded.document.project.canvas.background
    assert (background.photo, background.blur, background.dim) == (str(sample_photos[3]), 40, 0.5)
    settle(loaded, qtbot)
    assert not loaded.canvas._background.pixmap().isNull()


def test_export_pdf_with_options(loaded: MainWindow, qtbot: QtBot, tmp_path: Path) -> None:
    target = tmp_path / "print.pdf"
    job = loaded.export(target, ExportOptions(quality=90, bleed_mm=3, crop_marks=True))
    assert job is not None
    with qtbot.waitSignal(job.signals.finished, timeout=30_000):
        pass
    page = PdfReader(target).pages[0]
    assert float(page.trimbox.width) == pytest.approx(210 / 25.4 * 72, abs=0.5)
    assert float(page.mediabox.width) == pytest.approx((210 + 6 + 16) / 25.4 * 72, abs=0.5)


def test_export_options_dialog(window: MainWindow, tmp_path: Path) -> None:
    pdf = ExportOptionsDialog(tmp_path / "a.pdf", ExportOptions(80, 3, True))
    assert pdf.crop_marks.isEnabled() and pdf.crop_marks.isChecked()
    assert pdf.options() == ExportOptions(80, 3.0, True)
    png = ExportOptionsDialog(tmp_path / "a.png", ExportOptions(80, 3, True))
    assert not png.crop_marks.isEnabled()
    assert not png.quality.isEnabled()
    assert png.options().crop_marks is False


def test_export_dialog_flow(
    loaded: MainWindow, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "flow.jpg"
    monkeypatch.setattr(
        "collagio.app.main_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(target), "")
    )
    loaded.ask_export_options = lambda path: ExportOptions(85, 2.0, False)  # type: ignore[method-assign]
    loaded.export_dialog()
    assert loaded.export_job is not None
    with qtbot.waitSignal(loaded.export_job.signals.finished, timeout=30_000):
        pass
    with Image.open(target) as image:
        bleed = round(2 / 25.4 * 300)
        assert image.size == (2480 + 2 * bleed, 3508 + 2 * bleed)
    loaded.ask_export_options = lambda path: None  # type: ignore[method-assign]
    loaded.export_job = None
    loaded.export_dialog()  # cancelled in the options dialog
    assert loaded.export_job is None


# --- entry point -----------------------------------------------------------------------------


def test_gui_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert gui_main.main(["collagio-gui", "--version"]) == 0
    assert capsys.readouterr().out.strip() == f"collagio-gui {__version__}"


def test_gui_self_test(
    qapp: QApplication,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def settings() -> QSettings:
        return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)

    def window() -> MainWindow:
        quiet = MainWindow(settings=settings(), cache_dir=tmp_path / "cache")
        quiet.confirm_discard = lambda: True  # type: ignore[method-assign]
        return quiet

    monkeypatch.setattr(gui_main, "QSettings", settings)
    monkeypatch.setattr(gui_main, "MainWindow", window)
    assert gui_main.main(["collagio-gui", "--self-test"]) == 0
    assert "self-test: ok" in capsys.readouterr().out
