from __future__ import annotations

import copy

import pytest

from collagio.core.commands import SetPhotoStyle, SwapPhotos, find_photo
from collagio.core.model import Canvas, CropBox, PhotoItem, Project, Rect, StyleRef
from collagio.errors import EditError


def _project() -> Project:
    return Project(
        canvas=Canvas(1000, 1000),
        photos=[
            PhotoItem("a", "a.jpg", rect=Rect(0, 0, 400, 300), rotation=5,
                      crop=CropBox(0.1, 0, 0.8, 1), style=StyleRef("plain", {"border_width": 4}),
                      z=0),
            PhotoItem("b", "b.jpg", rect=Rect(500, 0, 200, 600), rotation=-3, z=2),
            PhotoItem("c", "c.jpg", rect=Rect(0, 500, 300, 300), z=1),
        ],
    )  # fmt: skip


def test_find_photo() -> None:
    project = _project()
    assert find_photo(project, "b") is project.photos[1]
    with pytest.raises(EditError, match="no photo with id 'x'"):
        find_photo(project, "x")


def test_swap_exchanges_placement_and_keeps_styles() -> None:
    project = _project()
    SwapPhotos("a", "b").apply(project)
    a, b, c = project.photos
    assert (a.rect, a.rotation, a.z) == (Rect(500, 0, 200, 600), -3, 2)
    assert (b.rect, b.rotation, b.z) == (Rect(0, 0, 400, 300), 5, 0)
    assert a.crop is None and b.crop is None
    assert a.style == StyleRef("plain", {"border_width": 4})
    assert b.style is None
    assert c == _project().photos[2]


def test_revert_restores_exactly() -> None:
    project = _project()
    original = copy.deepcopy(project)
    command = SwapPhotos("a", "b")
    command.apply(project)
    command.revert(project)
    assert project == original


def test_apply_revert_apply_is_stable() -> None:
    once, twice = _project(), _project()
    SwapPhotos("a", "c").apply(once)
    command = SwapPhotos("a", "c")
    command.apply(twice)
    command.revert(twice)
    command.apply(twice)
    assert twice == once


def test_saved_state_is_not_aliased() -> None:
    project = _project()
    command = SwapPhotos("a", "b")
    command.apply(project)
    project.photos[1].rect.x = 999  # type: ignore[union-attr]  # mutate in place after swap
    command.revert(project)
    assert project.photos[0].rect == Rect(0, 0, 400, 300)


def test_errors() -> None:
    project = _project()
    with pytest.raises(EditError, match="itself"):
        SwapPhotos("a", "a").apply(project)
    with pytest.raises(EditError, match="no photo"):
        SwapPhotos("a", "zzz").apply(project)
    with pytest.raises(EditError, match="not applied"):
        SwapPhotos("a", "b").revert(project)
    assert project == _project()


def test_label() -> None:
    assert SwapPhotos("a", "b").label == "Swap photos"


# --- SetPhotoStyle --------------------------------------------------------------------------


def test_set_style_and_revert() -> None:
    project = _project()
    command = SetPhotoStyle("b", StyleRef("polaroid", {"caption": "Hi"}))
    command.apply(project)
    assert project.photos[1].style == StyleRef("polaroid", {"caption": "Hi"})
    command.revert(project)
    assert project == _project()


def test_reset_to_default_style() -> None:
    project = _project()
    SetPhotoStyle("a", None).apply(project)
    assert project.photos[0].style is None
    assert project.style_for(project.photos[0]) == project.default_style


def test_set_style_copies_the_style() -> None:
    project = _project()
    style = StyleRef("stamp", {"value": "1"})
    SetPhotoStyle("c", style).apply(project)
    style.params["value"] = "changed"
    assert project.photos[2].style == StyleRef("stamp", {"value": "1"})


def test_set_style_errors() -> None:
    with pytest.raises(EditError, match="no photo"):
        SetPhotoStyle("zzz", None).apply(_project())
    with pytest.raises(EditError, match="not applied"):
        SetPhotoStyle("a", None).revert(_project())
    assert SetPhotoStyle("a", None).label == "Change style"
