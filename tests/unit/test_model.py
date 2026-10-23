from __future__ import annotations

import pytest

from collagio.core.model import Canvas, PhotoItem, Project, Rect, StyleRef


def test_rect_derived_properties() -> None:
    rect = Rect(10, 20, 30, 15)
    assert rect.right == 40
    assert rect.bottom == 35
    assert rect.aspect == 2
    assert rect.area == 450


def test_rect_inflate() -> None:
    assert Rect(10, 10, 20, 20).inflate(5) == Rect(5, 5, 30, 30)
    assert Rect(10, 10, 20, 20).inflate(-5) == Rect(15, 15, 10, 10)


@pytest.mark.parametrize(
    ("other", "expected"),
    [
        (Rect(5, 5, 10, 10), True),  # partial overlap
        (Rect(2, 2, 2, 2), True),  # contained
        (Rect(10, 0, 10, 10), False),  # touching edge
        (Rect(20, 20, 5, 5), False),  # apart
        (Rect(9.9999999, 0, 10, 10), False),  # within tolerance
    ],
)
def test_rect_overlaps(other: Rect, expected: bool) -> None:
    rect = Rect(0, 0, 10, 10)
    assert rect.overlaps(other) is expected
    assert other.overlaps(rect) is expected


def test_canvas_short_edge() -> None:
    assert Canvas(2480, 3508).short_edge == 2480
    assert Canvas(1920, 1080).short_edge == 1080


def test_style_for_falls_back_to_project_default() -> None:
    project = Project(canvas=Canvas(100, 100), default_style=StyleRef("plain", {"border_width": 3}))
    inherited = PhotoItem(id="a", path="a.jpg")
    own = PhotoItem(id="b", path="b.jpg", style=StyleRef("plain", {"border_width": 9}))
    assert project.style_for(inherited).params == {"border_width": 3}
    assert project.style_for(own).params == {"border_width": 9}


def test_defaults_are_not_shared_between_instances() -> None:
    a, b = Project(canvas=Canvas(1, 1)), Project(canvas=Canvas(1, 1))
    a.default_style.params["x"] = 1
    a.photos.append(PhotoItem(id="p", path="p.jpg"))
    assert b.default_style.params == {}
    assert b.photos == []
