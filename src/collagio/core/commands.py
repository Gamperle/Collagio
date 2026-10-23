"""Undoable edits of a project.

Every manual change goes through a command so the GUI can offer undo/redo for
all of them (the undo stack follows in Phase 4). `apply` performs the edit and
remembers what it needs to restore; `revert` undoes exactly that.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Protocol

from collagio.core.model import CropBox, PhotoItem, Project, Rect
from collagio.errors import EditError


class Command(Protocol):
    label: str

    def apply(self, project: Project) -> None: ...

    def revert(self, project: Project) -> None: ...


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
class SwapPhotos:
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
        first.rect, second.rect = second.rect, first.rect
        first.rotation, second.rotation = second.rotation, first.rotation
        first.z, second.z = second.z, first.z
        first.crop = second.crop = None

    def revert(self, project: Project) -> None:
        if not self._before:
            raise EditError("swap was not applied")
        _set_placement(find_photo(project, self.first_id), self._before[0])
        _set_placement(find_photo(project, self.second_id), self._before[1])
        self._before = []
