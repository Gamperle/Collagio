from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from collagio.core.commands import (
    EditProject,
    Restack,
    SetCrop,
    SetPhotoStyle,
    SetPlacement,
    SwapPhotos,
)
from collagio.core.model import Canvas, CropBox, PhotoItem, Project, Rect, StyleRef
from collagio.core.undo import UndoStack


def _project() -> Project:
    return Project(
        canvas=Canvas(1000, 800),
        photos=[
            PhotoItem(f"p{i}", f"{i}.jpg", rect=Rect(i * 100, 0, 90, 60), z=i) for i in range(4)
        ],
    )


def _move(photo_id: str = "p0", x: float = 500) -> SetPlacement:
    return SetPlacement(photo_id, Rect(x, 10, 90, 60), 15.0)


def test_push_undo_redo() -> None:
    stack = UndoStack(_project())
    stack.push(_move())
    assert stack.project.photos[0].rect == Rect(500, 10, 90, 60)
    assert (stack.can_undo, stack.can_redo, stack.undo_label) == (True, False, "Move photo")
    stack.undo()
    assert stack.project == _project()
    assert (stack.can_undo, stack.can_redo, stack.redo_label) == (False, True, "Move photo")
    stack.redo()
    assert stack.project.photos[0].rotation == 15.0


def test_undo_redo_on_empty_stack_do_nothing() -> None:
    stack = UndoStack(_project())
    stack.undo()
    stack.redo()
    assert stack.project == _project()
    assert stack.undo_label is None
    assert stack.redo_label is None


def test_push_clears_redo() -> None:
    stack = UndoStack(_project())
    stack.push(_move(x=1))
    stack.undo()
    stack.push(_move(x=2))
    assert not stack.can_redo


def test_modified_tracks_clean_state() -> None:
    stack = UndoStack(_project())
    assert not stack.modified
    stack.push(_move(x=1))
    assert stack.modified
    stack.set_clean()
    assert not stack.modified
    stack.push(_move(x=2))
    assert stack.modified
    stack.undo()
    assert not stack.modified
    stack.undo()
    assert stack.modified


def test_clean_state_lost_when_redo_history_is_discarded() -> None:
    stack = UndoStack(_project())
    stack.push(_move(x=1))
    stack.set_clean()
    stack.undo()
    stack.push(_move(x=2))  # the saved state can no longer be reached
    assert stack.modified
    stack.undo()
    assert stack.modified


def test_limit_drops_oldest() -> None:
    stack = UndoStack(_project(), limit=3)
    for x in range(5):
        stack.push(_move(x=x))
    undone = 0
    while stack.can_undo:
        stack.undo()
        undone += 1
    assert undone == 3
    assert stack.project.photos[0].rect == Rect(1, 10, 90, 60)


def test_limit_and_clean_state() -> None:
    stack = UndoStack(_project(), limit=2)
    stack.push(_move(x=1))
    stack.set_clean()
    stack.push(_move(x=2))
    stack.push(_move(x=3))  # drops the first command; the clean state is the oldest one kept
    stack.undo()
    assert stack.modified
    stack.undo()
    assert not stack.modified
    stack.redo()
    stack.redo()
    stack.push(_move(x=4))
    stack.push(_move(x=5))  # the clean state falls off the history
    while stack.can_undo:
        stack.undo()
    assert stack.modified


def test_set_dirty() -> None:
    stack = UndoStack(_project())
    stack.set_dirty()
    assert stack.modified
    stack.set_clean()
    assert not stack.modified


def test_invalid_limit() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        UndoStack(_project(), limit=0)


def test_clear_and_listeners() -> None:
    stack = UndoStack(_project())
    calls: list[int] = []
    stack.subscribe(lambda: calls.append(1))
    stack.push(_move())
    stack.undo()
    stack.redo()
    stack.set_clean()
    stack.clear()
    assert len(calls) == 5
    assert not stack.can_undo
    assert not stack.modified


# --- all commands together -----------------------------------------------------------------------

COMMANDS = st.one_of(
    st.builds(
        SetPlacement,
        st.sampled_from(["p0", "p1", "p2", "p3"]),
        st.builds(Rect, st.floats(0, 900), st.floats(0, 700), st.floats(10, 200),
                  st.floats(10, 200)),
        st.floats(-45, 45),
    ),
    st.builds(SetCrop, st.sampled_from(["p0", "p1"]),
              st.none() | st.builds(CropBox, st.just(0.1), st.just(0.1), st.just(0.5),
                                    st.just(0.5))),
    st.builds(Restack, st.sampled_from(["p0", "p1", "p2", "p3"]), st.booleans()),
    st.builds(SetPhotoStyle, st.sampled_from(["p2", "p3"]),
              st.none() | st.just(StyleRef("stamp"))),
    st.tuples(st.sampled_from(["p0", "p1"]), st.sampled_from(["p2", "p3"])).map(
        lambda ids: SwapPhotos(*ids)
    ),
    st.integers(0, 1000).map(
        lambda seed: EditProject("Change seed", lambda p, s=seed: setattr(p, "seed", s))
    ),
)  # fmt: skip


@settings(max_examples=100)
@given(commands=st.lists(COMMANDS, min_size=1, max_size=20))
def test_undo_all_restores_and_redo_all_replays(commands: list[object]) -> None:
    stack = UndoStack(_project())
    states = [copy.deepcopy(stack.project)]
    for command in commands:
        stack.push(command)  # type: ignore[arg-type]
        states.append(copy.deepcopy(stack.project))
    for expected in reversed(states[:-1]):
        stack.undo()
        assert stack.project == expected
    for expected in states[1:]:
        stack.redo()
        assert stack.project == expected
