"""An open collage: project, file, undo history and the edits the editor offers.

Free of GUI code so the editing logic is testable on its own; the Qt layer
only translates user actions into these calls and listens for changes.
"""

from __future__ import annotations

import copy
import math
import time
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
from collagio.core.geometry import centre, refit_crop
from collagio.core.model import (
    MAX_PHOTOS,
    Canvas,
    CropBox,
    LayoutMode,
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
from collagio.layout.apply import SizeOf, apply_layout, framed_aspect
from collagio.render.background import parse_color
from collagio.render.renderer import content_aspect
from collagio.render.text import text_size

Listener = Callable[[], None]

AUTOSAVE_PREFIX = "autosave-"
LEGACY_AUTOSAVE_NAME = f"autosave{PROJECT_SUFFIX}"  # one file for all windows (0.1.0)
AUTOSAVE_MAX_AGE_DAYS = 30
DEFAULT_CANVAS = (2480, 3508)  # A4 portrait at 300 DPI


def autosave_name(session: str) -> str:
    """File name of the recovery copy of one editor session (one per window)."""
    return f"{AUTOSAVE_PREFIX}{session}{PROJECT_SUFFIX}"


def autosave_files(directory: Path) -> list[Path]:
    """Recovery copies in `directory`, the most recent first."""
    if not directory.is_dir():
        return []
    files = [*directory.glob(f"{AUTOSAVE_PREFIX}*{PROJECT_SUFFIX}")]
    legacy = directory / LEGACY_AUTOSAVE_NAME
    if legacy.is_file():
        files.append(legacy)
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def remove_old_autosaves(
    directory: Path, max_age_days: float = AUTOSAVE_MAX_AGE_DAYS
) -> list[Path]:
    """Delete recovery copies not written for `max_age_days`; returns the deleted files."""
    limit = time.time() - max_age_days * 24 * 3600
    removed = []
    for path in autosave_files(directory):
        if path.stat().st_mtime < limit:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed


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

    def autosave(self, target: Path) -> Path | None:
        """Save a recovery copy if there are unsaved changes; returns its path.

        Without unsaved changes an earlier copy at `target` is deleted, so only
        work that would otherwise be lost can be recovered.
        """
        if not self.modified:
            target.unlink(missing_ok=True)
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
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
            if relayout:
                if project.photos:
                    apply_layout(project, self.size_of)
                project.layout_edited = False

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
        """Style for all photos without their own style; tiles are re-fitted to the frame.

        An automatic layout is laid out again. Manual changes are kept: see `_refit`.
        """

        def change(project: Project) -> None:
            project.default_style = copy.deepcopy(style)
            if project.layout_edited:
                self._refit(project, [p for p in project.photos if p.style is None])
            elif project.photos:
                apply_layout(project, self.size_of)

        self._edit("Change style", change, relayout=False)

    def _refit(self, project: Project, photos: Iterable[PhotoItem]) -> None:
        """Fit tiles to a changed frame without moving them.

        Scattered tiles take the frame's shape around their centre, keeping their
        area and rotation; grid tiles keep their cells. Chosen crops get the shape
        of the new photo area, so the photo is not stretched.
        """
        for item in photos:
            if item.rect is None:
                continue
            width, height = self.size_of(item.path)
            if project.layout.mode is LayoutMode.SCATTERED:
                rect = item.rect
                area = rect.width * rect.height
                aspect = framed_aspect(project, item, width / height, area)
                new_w = math.sqrt(area * aspect)
                new_h = area / new_w
                cx, cy = centre(rect)
                item.rect = Rect(cx - new_w / 2, cy - new_h / 2, new_w, new_h)
            if item.crop is not None:
                frame = content_aspect(project, item, width / height)
                item.crop = refit_crop(item.crop, (width, height), frame)

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
            raise EditError(
                "a collage can have at most {maximum} photos ({total} requested)",
                maximum=MAX_PHOTOS,
                total=total,
            )
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
            raise EditError("no photo with id {photo_id!r}", photo_id=sorted(ids - known)[0])
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
        raise EditError("no text with id {text_id!r}", text_id=text_id)

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
                raise EditError("unknown text field {name!r}", name=name)
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
