from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from collagio.core.document import (
    LEGACY_AUTOSAVE_NAME,
    Document,
    autosave_files,
    autosave_name,
    new_project,
    remove_old_autosaves,
)
from collagio.core.model import (
    Background,
    Canvas,
    CropBox,
    LayoutMode,
    LayoutSettings,
    Rect,
    Shadow,
    StyleRef,
    TextItem,
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
    assert saved == tmp_path / "my.collagio"
    assert (doc.modified, doc.title) == (False, "my.collagio")
    reopened = Document.open(saved, size_of=size_of)
    assert reopened.project == doc.project
    assert not reopened.modified
    assert Document(size_of=size_of).modified is False


def test_save_keeps_existing_suffix_and_path(tmp_path: Path) -> None:
    doc = _document(2)
    assert doc.save(tmp_path / "a.collagio") == tmp_path / "a.collagio"
    assert doc.save(tmp_path / "b.json") == tmp_path / "b.collagio"
    assert doc.save(tmp_path / "old.collagio.json") == tmp_path / "old.collagio.json"  # legacy
    assert doc.save(tmp_path / "b") == tmp_path / "b.collagio"
    doc.relayout(seed=3)
    assert doc.save() == tmp_path / "b.collagio"
    assert load_project(tmp_path / "b.collagio").seed == 3


def test_save_without_path() -> None:
    with pytest.raises(EditError, match="no file name"):
        _document(2).save()


def test_autosave(tmp_path: Path) -> None:
    doc = Document(size_of=size_of)
    target = tmp_path / "auto" / autosave_name("s1")
    assert doc.autosave(target) is None  # nothing to save
    doc.add_photos(["land.jpg", "port.jpg"])
    assert doc.autosave(target) == target
    assert load_project(target).photos[0].path.endswith("land.jpg")
    assert doc.modified  # autosave does not count as saving
    doc.save(tmp_path / "saved.collagio")
    assert doc.autosave(target) is None
    assert not target.exists()  # saved: nothing left to recover


def test_autosave_files_and_old_ones_removed(tmp_path: Path) -> None:
    assert autosave_files(tmp_path / "none") == []
    now = time.time()
    ages = {autosave_name("old"): 40, LEGACY_AUTOSAVE_NAME: 2, autosave_name("new"): 1}
    for name, days in ages.items():
        (tmp_path / name).write_text("{}")
        os.utime(tmp_path / name, (now - days * 86400, now - days * 86400))
    (tmp_path / "other.collagio").write_text("{}")
    assert [p.name for p in autosave_files(tmp_path)] == [
        autosave_name("new"),
        LEGACY_AUTOSAVE_NAME,
        autosave_name("old"),
    ]
    assert remove_old_autosaves(tmp_path) == [tmp_path / autosave_name("old")]
    assert len(autosave_files(tmp_path)) == 2


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


# --- texts ------------------------------------------------------------------------------------


def test_add_edit_move_remove_texts() -> None:
    doc = _document(2)
    first = doc.add_text("Hello")
    second = doc.add_text("World", size=90.0, color="#ff0000", y=100.0)
    assert (first, second) == ("t001", "t002")
    text = doc.project.texts[0]
    assert (text.x, text.y) == (2480 / 2, 3508 / 2)
    assert (doc.project.texts[1].size, doc.project.texts[1].y) == (90.0, 100.0)

    changed = TextItem(first, "Hi", 10, 20, size=30, rotation=5)
    doc.update_text(changed)
    assert doc.project.texts[0] == changed
    doc.move_text(second, 7, 8)
    assert (doc.project.texts[1].x, doc.project.texts[1].y) == (7, 8)
    doc.remove_texts([first])
    assert [t.id for t in doc.project.texts] == [second]
    assert doc.add_text("again") == "t003"
    for _ in range(5):
        doc.undo()
    assert [t.text for t in doc.project.texts] == ["Hello"]


def test_text_errors() -> None:
    doc = _document(2)
    with pytest.raises(EditError, match="unknown text field 'colour'"):
        doc.add_text("x", colour="red")
    with pytest.raises(EditError, match="no text with id 't404'"):
        doc.move_text("t404", 0, 0)
    with pytest.raises(EditError, match="no text"):
        doc.update_text(TextItem("t404", "x", 0, 0))
    with pytest.raises(EditError, match="no text"):
        doc.remove_texts(["t404"])
    doc.remove_texts([])
    assert doc.project.texts == []


def test_invalid_texts_are_rejected(tmp_path: Path) -> None:
    from collagio.errors import RenderError

    doc = _document(2)
    with pytest.raises(RenderError, match="cannot load font"):
        doc.add_text("x", font=str(tmp_path / "missing.ttf"))
    text_id = doc.add_text("x")
    with pytest.raises(RenderError, match="invalid colour"):
        doc.update_text(TextItem(text_id, "x", 0, 0, color="nope"))
    assert doc.project.texts[0].color == "#222222"
