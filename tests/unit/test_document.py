from __future__ import annotations

from pathlib import Path

import pytest

from collagio.core.document import AUTOSAVE_NAME, Document, new_project
from collagio.core.model import (
    Background,
    Canvas,
    CropBox,
    LayoutMode,
    LayoutSettings,
    Rect,
    Shadow,
    StyleRef,
)
from collagio.core.serialize import load_project
from collagio.errors import EditError, ImageLoadError, LayoutError

SIZES = {"land.jpg": (600, 400), "port.jpg": (400, 600), "square.jpg": (500, 500)}


def size_of(path: str) -> tuple[int, int]:
    name = Path(path).name
    if name not in SIZES:
        raise ImageLoadError(f"photo not found: {path}")
    return SIZES[name]


def _document(count: int = 3) -> Document:
    doc = Document(size_of=size_of)
    doc.add_photos((list(SIZES) * 40)[:count])
    return doc


def test_new_document_is_empty_and_clean() -> None:
    doc = Document(size_of=size_of)
    assert doc.project == new_project()
    assert (doc.title, doc.modified, doc.path) == ("Untitled", False, None)


def test_add_photos_lays_them_out() -> None:
    doc = _document(3)
    assert [p.id for p in doc.project.photos] == ["p001", "p002", "p003"]
    assert all(Path(p.path).is_absolute() for p in doc.project.photos)
    assert all(p.rect is not None for p in doc.project.photos)
    assert doc.modified
    assert doc.title == "Untitled*"


def test_single_photo_is_allowed_while_building() -> None:
    doc = _document(1)
    assert doc.project.photos[0].rect is not None


def test_add_more_photos_continues_ids_and_is_one_undo_step() -> None:
    doc = _document(2)
    doc.add_photos(["square.jpg", "land.jpg"])
    assert [p.id for p in doc.project.photos] == ["p001", "p002", "p003", "p004"]
    doc.undo()
    assert len(doc.project.photos) == 2


def test_add_photos_limits() -> None:
    doc = _document(99)
    with pytest.raises(EditError, match="at most 100"):
        doc.add_photos(["land.jpg", "land.jpg"])
    doc.add_photos([])
    assert len(doc.project.photos) == 99


def test_unreadable_photo_changes_nothing() -> None:
    doc = _document(2)
    with pytest.raises(ImageLoadError):
        doc.add_photos(["land.jpg", "missing.jpg"])
    assert len(doc.project.photos) == 2
    assert doc.undo_stack.undo_label == "Add photos"  # only the first add


def test_remove_photos() -> None:
    doc = _document(4)
    doc.remove_photos(["p002", "p004"])
    assert [p.id for p in doc.project.photos] == ["p001", "p003"]
    assert all(p.rect is not None for p in doc.project.photos)
    doc.remove_photos([])
    with pytest.raises(EditError, match="no photo with id 'p009'"):
        doc.remove_photos(["p009"])
    doc.undo()
    assert len(doc.project.photos) == 4


def test_remove_all_photos() -> None:
    doc = _document(2)
    doc.remove_photos(["p001", "p002"])
    assert doc.project.photos == []


def test_relayout_with_settings_and_seed() -> None:
    doc = _document(6)
    before = [p.rect for p in doc.project.photos]
    doc.relayout(seed=42)
    assert doc.project.seed == 42
    assert [p.rect for p in doc.project.photos] != before
    doc.relayout(LayoutSettings(mode=LayoutMode.SCATTERED))
    assert any(p.rotation for p in doc.project.photos)
    doc.undo()
    doc.undo()
    assert [p.rect for p in doc.project.photos] == before


def test_relayout_replaces_manual_moves() -> None:
    doc = _document(3)
    doc.move_photo("p001", Rect(1, 2, 30, 20), 10.0, "Move photo")
    doc.relayout()
    assert doc.project.photos[0].rotation == 0.0
    assert doc.project.photos[0].rect != Rect(1, 2, 30, 20)


def test_set_canvas_relayouts_only_when_resized() -> None:
    doc = _document(3)
    doc.move_photo("p001", Rect(1, 2, 30, 20), 10.0, "Move photo")
    canvas = Canvas(2480, 3508, dpi=150, background=Background(color="#000000"))
    doc.set_canvas(canvas)
    assert doc.project.canvas == canvas
    assert doc.project.photos[0].rect == Rect(1, 2, 30, 20)  # same size: kept
    doc.set_canvas(Canvas(3000, 2000))
    assert doc.project.photos[0].rect != Rect(1, 2, 30, 20)


def test_set_canvas_on_empty_document() -> None:
    doc = Document(size_of=size_of)
    doc.set_canvas(Canvas(800, 600))
    assert doc.project.canvas.width == 800


def test_default_style_refits_tiles() -> None:
    doc = _document(3)
    land = doc.project.photos[0].rect
    doc.set_default_style(StyleRef("polaroid"))
    assert doc.project.default_style == StyleRef("polaroid")
    assert doc.project.photos[0].rect != land


def test_photo_styles_keep_positions_and_are_one_step() -> None:
    doc = _document(3)
    rects = [p.rect for p in doc.project.photos]
    doc.set_photo_styles(["p001", "p003"], StyleRef("stamp"))
    assert [p.style for p in doc.project.photos] == [StyleRef("stamp"), None, StyleRef("stamp")]
    assert [p.rect for p in doc.project.photos] == rects
    doc.undo()
    assert all(p.style is None for p in doc.project.photos)


def test_shadow() -> None:
    doc = _document(2)
    doc.set_shadow(Shadow(opacity=0.5))
    assert doc.project.shadow.opacity == 0.5


def test_direct_edits() -> None:
    doc = _document(3)
    first, second = doc.project.photos[0].rect, doc.project.photos[1].rect
    doc.swap_photos("p001", "p002")
    assert (doc.project.photos[0].rect, doc.project.photos[1].rect) == (second, first)
    doc.crop_photo("p001", CropBox(0, 0, 0.5, 0.5))
    assert doc.project.photos[0].crop == CropBox(0, 0, 0.5, 0.5)
    doc.restack("p001", to_front=True)
    assert doc.project.photos[0].z == 2
    doc.move_photo("p002", Rect(5, 5, 50, 50), -3.0, "Rotate photo")
    assert doc.undo_stack.undo_label == "Rotate photo"


def test_save_and_open(tmp_path: Path) -> None:
    doc = _document(3)
    saved = doc.save(tmp_path / "my")
    assert saved == tmp_path / "my.collagio.json"
    assert (doc.modified, doc.title) == (False, "my.collagio.json")
    reopened = Document.open(saved, size_of=size_of)
    assert reopened.project == doc.project
    assert not reopened.modified
    assert Document(size_of=size_of).modified is False


def test_save_keeps_existing_suffix_and_path(tmp_path: Path) -> None:
    doc = _document(2)
    assert doc.save(tmp_path / "a.collagio.json") == tmp_path / "a.collagio.json"
    assert doc.save(tmp_path / "b.json") == tmp_path / "b.collagio.json"
    doc.relayout(seed=3)
    assert doc.save() == tmp_path / "b.collagio.json"
    assert load_project(tmp_path / "b.collagio.json").seed == 3


def test_save_without_path() -> None:
    with pytest.raises(EditError, match="no file name"):
        _document(2).save()


def test_autosave(tmp_path: Path) -> None:
    doc = Document(size_of=size_of)
    assert doc.autosave(tmp_path / "auto") is None  # nothing to save
    doc.add_photos(["land.jpg", "port.jpg"])
    target = doc.autosave(tmp_path / "auto")
    assert target == tmp_path / "auto" / AUTOSAVE_NAME
    assert load_project(target).photos[0].path.endswith("land.jpg")
    assert doc.modified  # autosave does not count as saving


def test_listeners_are_notified() -> None:
    doc = Document(size_of=size_of)
    calls: list[int] = []
    doc.subscribe(lambda: calls.append(1))
    doc.add_photos(["land.jpg", "port.jpg"])
    doc.undo()
    doc.redo()
    assert len(calls) == 3


def test_failed_layout_leaves_document_unchanged() -> None:
    doc = _document(3)
    before = doc.project.canvas
    with pytest.raises(LayoutError):
        doc.relayout(LayoutSettings(margin=0.6))
    assert doc.project.canvas == before
    assert doc.undo_stack.undo_label == "Add photos"


def test_move_photos_is_one_undo_step() -> None:
    doc = _document(3)
    before = [p.rect for p in doc.project.photos]
    doc.move_photos({"p001": (Rect(0, 0, 10, 10), 0.0), "p002": (Rect(5, 5, 10, 10), 3.0)}, "Move")
    assert doc.project.photos[1].rotation == 3.0
    doc.undo()
    assert [p.rect for p in doc.project.photos] == before
    doc.move_photos({"p003": (Rect(1, 1, 10, 10), 0.0)}, "Move photo")
    assert doc.project.photos[2].rect == Rect(1, 1, 10, 10)
