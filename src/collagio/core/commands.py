"""Undoable edits of a project.

Every manual change goes through a command so the GUI can offer undo/redo for
all of them (the undo stack follows in Phase 4). `apply` performs the edit and
remembers what it needs to restore; `revert` undoes exactly that.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from collagio.core.model import CropBox, PhotoItem, Project, Rect, StyleRef
from collagio.errors import EditError


class Command(Protocol):
    label: str

    def apply(self, project: Project) -> None: ...

    def revert(self, project: Project) -> None: ...


@runtime_checkable
class MergeableCommand(Command, Protocol):
    """A command that can absorb the command applied right after it (one undo step)."""

    def merge_with(self, other: Command) -> bool:
        """Take over `other`'s result if both belong together; False leaves self unchanged."""
        ...


@dataclass
class _ManualEdit:
    """Marks the layout as edited by hand; `revert` restores the previous mark."""

    _was_edited: bool = field(default=False, repr=False, kw_only=True)

    def _mark_edited(self, project: Project) -> None:
        self._was_edited = project.layout_edited
        project.layout_edited = True

    def _restore_mark(self, project: Project) -> None:
        project.layout_edited = self._was_edited


def find_photo(project: Project, photo_id: str) -> PhotoItem:
    for item in project.photos:
        if item.id == photo_id:
            return item
    raise EditError(f"no photo with id {photo_id!r}")


_Placement = tuple[Rect | None, float, CropBox | None, int]


def _placement(item: PhotoItem) -> _Placement:
    return copy.deepcopy((item.rect, item.rotation, item.crop, item.z))


def _set_placement(item: PhotoItem, placement: _Placement) -> None:
    item.rect, item.rotation, item.crop, item.z = copy.deepcopy(placement)


@dataclass
class SwapPhotos(_ManualEdit):
    """Exchange the positions of two photos (cell, rotation, stacking order).

    Each photo keeps its own style. Crops are reset to automatic, because a crop
    chosen for one cell rarely suits the other cell's shape.
    """

    first_id: str
    second_id: str
    label: str = "Swap photos"
    _before: list[_Placement] = field(default_factory=list, repr=False)

    def apply(self, project: Project) -> None:
        if self.first_id == self.second_id:
            raise EditError(f"cannot swap photo {self.first_id!r} with itself")
        first = find_photo(project, self.first_id)
        second = find_photo(project, self.second_id)
        self._before = [_placement(first), _placement(second)]
        self._mark_edited(project)
        first.rect, second.rect = second.rect, first.rect
        first.rotation, second.rotation = second.rotation, first.rotation
        first.z, second.z = second.z, first.z
        first.crop = second.crop = None

    def revert(self, project: Project) -> None:
        if not self._before:
            raise EditError("swap was not applied")
        _set_placement(find_photo(project, self.first_id), self._before[0])
        _set_placement(find_photo(project, self.second_id), self._before[1])
        self._restore_mark(project)
        self._before = []


@dataclass
class SetPhotoStyle:
    """Give one photo its own style, or `None` to use the project default again."""

    photo_id: str
    style: StyleRef | None
    label: str = "Change style"
    _before: list[StyleRef | None] = field(default_factory=list, repr=False)

    def apply(self, project: Project) -> None:
        item = find_photo(project, self.photo_id)
        self._before = [copy.deepcopy(item.style)]
        item.style = copy.deepcopy(self.style)

    def revert(self, project: Project) -> None:
        if not self._before:
            raise EditError("style change was not applied")
        find_photo(project, self.photo_id).style = self._before[0]
        self._before = []


def _restore(project: Project, snapshot: Project) -> None:
    """Make `project` equal to `snapshot` in place (views keep their reference)."""
    for name in vars(snapshot):
        setattr(project, name, copy.deepcopy(getattr(snapshot, name)))


@dataclass
class EditProject:
    """Any change made by `mutate`, undone by restoring a snapshot.

    For larger edits (new layout, canvas size, adding photos) where writing a
    dedicated inverse is not worth it. Redo restores the result of the first
    `apply`, so `mutate` runs only once.
    """

    label: str
    mutate: Callable[[Project], None] = field(repr=False)
    _before: Project | None = field(default=None, repr=False)
    _after: Project | None = field(default=None, repr=False)

    def apply(self, project: Project) -> None:
        self._before = copy.deepcopy(project)
        if self._after is None:
            try:
                self.mutate(project)
            except Exception:
                _restore(project, self._before)
                self._before = None
                raise
            self._after = copy.deepcopy(project)
        else:
            _restore(project, self._after)

    def revert(self, project: Project) -> None:
        if self._before is None:
            raise EditError(f"{self.label!r} was not applied")
        _restore(project, self._before)
        self._before = None


@dataclass
class SetPlacement(_ManualEdit):
    """Move, resize and/or rotate one photo (the result of one drag)."""

    photo_id: str
    rect: Rect
    rotation: float
    label: str = "Move photo"
    _before: list[_Placement] = field(default_factory=list, repr=False)

    def apply(self, project: Project) -> None:
        item = find_photo(project, self.photo_id)
        self._before = [_placement(item)]
        self._mark_edited(project)
        item.rect = copy.deepcopy(self.rect)
        item.rotation = self.rotation

    def revert(self, project: Project) -> None:
        if not self._before:
            raise EditError("move was not applied")
        _set_placement(find_photo(project, self.photo_id), self._before[0])
        self._restore_mark(project)
        self._before = []


@dataclass
class SetCrop(_ManualEdit):
    """Choose the visible part of a photo, or `None` for the automatic crop."""

    photo_id: str
    crop: CropBox | None
    label: str = "Crop photo"
    _before: list[CropBox | None] = field(default_factory=list, repr=False)

    def apply(self, project: Project) -> None:
        item = find_photo(project, self.photo_id)
        self._before = [copy.deepcopy(item.crop)]
        self._mark_edited(project)
        item.crop = copy.deepcopy(self.crop)

    def revert(self, project: Project) -> None:
        if not self._before:
            raise EditError("crop was not applied")
        find_photo(project, self.photo_id).crop = self._before[0]
        self._restore_mark(project)
        self._before = []

    def merge_with(self, other: Command) -> bool:
        """Successive crops of the same photo (e.g. one zoom gesture) undo together."""
        if not isinstance(other, SetCrop) or other.photo_id != self.photo_id:
            return False
        self.crop = copy.deepcopy(other.crop)
        return True


@dataclass
class Restack(_ManualEdit):
    """Bring a photo to the front (`to_front`) or send it to the back.

    Stacking orders are renumbered 0..n-1 afterwards.
    """

    photo_id: str
    to_front: bool
    label: str = "Change stacking order"
    _before: list[int] = field(default_factory=list, repr=False)

    def apply(self, project: Project) -> None:
        item = find_photo(project, self.photo_id)
        self._before = [p.z for p in project.photos]
        self._mark_edited(project)
        others = sorted((p for p in project.photos if p is not item), key=lambda p: p.z)
        ordered = [*others, item] if self.to_front else [item, *others]
        for z, photo in enumerate(ordered):
            photo.z = z

    def revert(self, project: Project) -> None:
        if not self._before:
            raise EditError("stacking change was not applied")
        for photo, z in zip(project.photos, self._before, strict=True):
            photo.z = z
        self._restore_mark(project)
        self._before = []
