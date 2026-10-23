"""An open collage: project, file, undo history and the edits the editor offers.

Free of GUI code so the editing logic is testable on its own; the Qt layer
only translates user actions into these calls and listens for changes.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from collagio.core.commands import (
    Command,
    EditProject,
    Restack,
    SetCrop,
    SetPhotoStyle,
    SetPlacement,
    SwapPhotos,
)
from collagio.core.model import (
    MAX_PHOTOS,
    Canvas,
    CropBox,
    LayoutSettings,
    PhotoItem,
    Project,
    Rect,
    Shadow,
    StyleRef,
    TextItem,
)
from collagio.core.serialize import (
    PROJECT_SUFFIX,
    is_project_file,
    load_project,
    save_project,
)
from collagio.core.undo import UndoStack
from collagio.errors import EditError
from collagio.imaging.loader import oriented_size
from collagio.layout.apply import SizeOf, apply_layout
from collagio.render.background import parse_color
from collagio.render.text import text_size

Listener = Callable[[], None]

AUTOSAVE_NAME = f"autosave{PROJECT_SUFFIX}"
DEFAULT_CANVAS = (2480, 3508)  # A4 portrait at 300 DPI


def new_project() -> Project:
    width, height = DEFAULT_CANVAS
    return Project(canvas=Canvas(width, height, dpi=300))


class Document:
    def __init__(
        self,
        project: Project | None = None,
        path: Path | None = None,
        size_of: SizeOf = oriented_size,
    ) -> None:
        self.project = project if project is not None else new_project()
        self.path = path
        self.size_of = size_of
        self.undo_stack = UndoStack(self.project)
        self._listeners: list[Listener] = []
        self.undo_stack.subscribe(self._notify)

    # --- files -----------------------------------------------------------------------------------

    @classmethod
    def open(cls, path: Path, size_of: SizeOf = oriented_size) -> Document:
        return cls(load_project(path), path, size_of)

    def save(self, path: Path | None = None) -> Path:
        target = path if path is not None else self.path
        if target is None:
            raise EditError("no file name given")
        if not is_project_file(target):
            target = target.with_name(target.name.removesuffix(".json") + PROJECT_SUFFIX)
        save_project(self.project, target)
        self.path = target
        self.undo_stack.set_clean()
        return target

    def autosave(self, directory: Path) -> Path | None:
        """Save a recovery copy if there are unsaved changes; returns its path."""
        if not self.modified:
            return None
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / AUTOSAVE_NAME
        save_project(self.project, target)
        return target

    @property
    def modified(self) -> bool:
        return self.undo_stack.modified

    @property
    def title(self) -> str:
        name = self.path.name if self.path is not None else "Untitled"
        return f"{name}*" if self.modified else name

    # --- change notification ---------------------------------------------------------------------

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    # --- undo ------------------------------------------------------------------------------------

    def execute(self, command: Command, merge: bool = False) -> None:
        self.undo_stack.push(command, merge)

    def undo(self) -> None:
        self.undo_stack.undo()

    def redo(self) -> None:
        self.undo_stack.redo()

    # --- edits -----------------------------------------------------------------------------------

    def _edit(self, label: str, mutate: Callable[[Project], None], relayout: bool) -> None:
        def run(project: Project) -> None:
            mutate(project)
            if relayout and project.photos:
                apply_layout(project, self.size_of)

        self.execute(EditProject(label, run))

    def relayout(self, layout: LayoutSettings | None = None, seed: int | None = None) -> None:
        """New automatic layout; manual position changes are replaced."""

        def change(project: Project) -> None:
            if layout is not None:
                project.layout = copy.deepcopy(layout)
            if seed is not None:
                project.seed = seed

        self._edit("New layout", change, relayout=True)

    def set_canvas(self, canvas: Canvas) -> None:
        def change(project: Project) -> None:
            resized = (canvas.width, canvas.height) != (
                project.canvas.width,
                project.canvas.height,
            )
            project.canvas = copy.deepcopy(canvas)
            if resized and project.photos:
                apply_layout(project, self.size_of)

        self._edit("Change canvas", change, relayout=False)

    def set_default_style(self, style: StyleRef) -> None:
        """Style for all photos without their own style; tiles are re-fitted to the frame."""
        self._edit(
            "Change style",
            lambda p: setattr(p, "default_style", copy.deepcopy(style)),
            relayout=True,
        )

    def set_photo_styles(self, photo_ids: Iterable[str], style: StyleRef | None) -> None:
        """Own style for some photos (None: back to the default), positions unchanged."""
        ids = list(photo_ids)

        def change(project: Project) -> None:
            for photo_id in ids:
                SetPhotoStyle(photo_id, style).apply(project)

        self._edit("Change style", change, relayout=False)

    def set_shadow(self, shadow: Shadow) -> None:
        self._edit(
            "Change shadow",
            lambda p: setattr(p, "shadow", copy.deepcopy(shadow)),
            relayout=False,
        )

    def add_photos(self, paths: Sequence[str | Path]) -> None:
        """Add photos and lay out the collage again."""
        if not paths:
            return
        total = len(self.project.photos) + len(paths)
        if total > MAX_PHOTOS:
            raise EditError(f"a collage can have at most {MAX_PHOTOS} photos ({total} requested)")
        for path in paths:
            self.size_of(str(path))  # fail before changing anything if a photo is unreadable

        def change(project: Project) -> None:
            next_number = 1 + max(
                (int(p.id[1:]) for p in project.photos if p.id[1:].isdigit()), default=0
            )
            for offset, path in enumerate(paths):
                # Absolute, so the project file can store it relative to itself.
                absolute = str(Path(path).absolute())
                project.photos.append(PhotoItem(id=f"p{next_number + offset:03d}", path=absolute))

        self._edit("Add photos", change, relayout=True)

    def remove_photos(self, photo_ids: Iterable[str]) -> None:
        """Remove photos and lay out the remaining ones again."""
        ids = set(photo_ids)
        known = {p.id for p in self.project.photos}
        if not ids <= known:
            raise EditError(f"no photo with id {sorted(ids - known)[0]!r}")
        if not ids:
            return
        self._edit(
            "Remove photos",
            lambda p: setattr(p, "photos", [x for x in p.photos if x.id not in ids]),
            relayout=True,
        )

    def move_photo(self, photo_id: str, rect: Rect, rotation: float, label: str) -> None:
        self.execute(SetPlacement(photo_id, rect, rotation, label))

    def move_photos(self, placements: dict[str, tuple[Rect, float]], label: str) -> None:
        """Move several photos as one undo step."""
        if len(placements) == 1:
            ((photo_id, (rect, rotation)),) = placements.items()
            self.move_photo(photo_id, rect, rotation, label)
            return

        def change(project: Project) -> None:
            for photo_id, (rect, rotation) in placements.items():
                SetPlacement(photo_id, rect, rotation).apply(project)

        self._edit(label, change, relayout=False)

    def crop_photo(self, photo_id: str, crop: CropBox | None, merge: bool = False) -> None:
        """Set the crop; `merge` makes it one undo step with the previous crop of this photo."""
        self.execute(SetCrop(photo_id, crop), merge)

    def swap_photos(self, first_id: str, second_id: str) -> None:
        self.execute(SwapPhotos(first_id, second_id))

    def restack(self, photo_id: str, to_front: bool) -> None:
        self.execute(Restack(photo_id, to_front))

    # --- texts ---------------------------------------------------------------------------------

    def _text_index(self, text_id: str) -> int:
        for index, text in enumerate(self.project.texts):
            if text.id == text_id:
                return index
        raise EditError(f"no text with id {text_id!r}")

    @staticmethod
    def _check_text(item: TextItem) -> None:
        """Fail before the project changes if the font or colour cannot be used."""
        parse_color(item.color)
        text_size(item, 1.0)

    def add_text(self, text: str = "Text", **fields: object) -> str:
        """Add a text in the middle of the canvas (or where `fields` say); returns its id."""
        number = 1 + max(
            (int(t.id[1:]) for t in self.project.texts if t.id[1:].isdigit()), default=0
        )
        canvas = self.project.canvas
        item = TextItem(f"t{number:03d}", text, canvas.width / 2, canvas.height / 2)
        for name, value in fields.items():
            if not hasattr(item, name):
                raise EditError(f"unknown text field {name!r}")
            setattr(item, name, value)
        self._check_text(item)
        self._edit("Add text", lambda p: p.texts.append(copy.deepcopy(item)), relayout=False)
        return item.id

    def update_text(self, item: TextItem) -> None:
        """Replace the text with the same id."""
        index = self._text_index(item.id)
        self._check_text(item)

        def change(project: Project) -> None:
            project.texts[index] = copy.deepcopy(item)

        self._edit("Edit text", change, relayout=False)

    def move_text(self, text_id: str, x: float, y: float) -> None:
        index = self._text_index(text_id)

        def change(project: Project) -> None:
            project.texts[index].x, project.texts[index].y = x, y

        self._edit("Move text", change, relayout=False)

    def remove_texts(self, text_ids: Iterable[str]) -> None:
        ids = set(text_ids)
        for text_id in ids:
            self._text_index(text_id)
        if ids:
            self._edit(
                "Remove text",
                lambda p: setattr(p, "texts", [t for t in p.texts if t.id not in ids]),
                relayout=False,
            )
