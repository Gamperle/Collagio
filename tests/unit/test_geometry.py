from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from collagio.core.geometry import (
    MIN_CROP,
    MIN_SIZE,
    centre,
    normalise_angle,
    pan_crop,
    refit_crop,
    resize_free,
    resize_from_corner,
    resize_from_edge,
    rotate_by_drag,
    screen_angle,
    to_local,
    to_world,
    zoom_crop,
)
from collagio.core.model import CropBox, Rect
from collagio.layout.scattered import rotated_corners


@given(
    x=st.floats(-1000, 1000), y=st.floats(-1000, 1000), rotation=st.floats(-360, 360),
    ox=st.floats(-100, 100), oy=st.floats(-100, 100),
)  # fmt: skip
def test_local_world_round_trip(x: float, y: float, rotation: float, ox: float, oy: float) -> None:
    back = to_world(to_local((x, y), (ox, oy), rotation), (ox, oy), rotation)
    assert back == pytest.approx((x, y), abs=1e-6)


def test_local_frame_matches_rotated_corners() -> None:
    rect = Rect(100, 100, 200, 100)
    for corner, local in zip(
        rotated_corners(rect, 30), [(-100, -50), (100, -50), (100, 50), (-100, 50)], strict=True
    ):
        assert to_local(corner, centre(rect), 30) == pytest.approx(local)


@given(
    rotation=st.floats(-180, 180),
    corner=st.integers(0, 3),
    px=st.floats(-500, 1500),
    py=st.floats(-500, 1500),
)
def test_resize_keeps_aspect_and_opposite_corner(
    rotation: float, corner: int, px: float, py: float
) -> None:
    rect = Rect(400, 300, 200, 100)
    resized = resize_from_corner(rect, rotation, corner, (px, py))
    assert resized.aspect == pytest.approx(2.0)
    assert min(resized.width, resized.height) >= MIN_SIZE - 1e-9
    opposite = (corner + 2) % 4
    assert rotated_corners(resized, rotation)[opposite] == pytest.approx(
        rotated_corners(rect, rotation)[opposite], abs=1e-6
    )


def test_resize_follows_the_pointer_on_the_diagonal() -> None:
    rect = Rect(0, 0, 200, 100)
    resized = resize_from_corner(rect, 0, 2, (400, 200))  # drag bottom-right outwards
    assert resized == Rect(0, 0, 400, 200)
    smaller = resize_from_corner(rect, 0, 0, (100, 50))  # drag top-left inwards
    assert smaller == Rect(100, 50, 100, 50)


def test_resize_rotated_90() -> None:
    rect = Rect(0, 0, 200, 100)  # centre (100, 50)
    # Rotated 90° counter-clockwise, the local bottom-right corner sits at screen (150, -50).
    assert rotated_corners(rect, 90)[2] == pytest.approx((150, -50))
    # The fixed top-left corner sits at (50, 150); the diagonal to the dragged corner is
    # (100, -200), so this pointer is twice as far along it.
    assert rotated_corners(rect, 90)[0] == pytest.approx((50, 150))
    resized = resize_from_corner(rect, 90, 2, (250, -250))
    assert (resized.width, resized.height) == pytest.approx((400, 200))


def test_resize_has_a_minimum() -> None:
    resized = resize_from_corner(Rect(0, 0, 200, 100), 0, 2, (-50, -50))
    assert resized.height == pytest.approx(MIN_SIZE)


@pytest.mark.parametrize(
    ("point", "expected"), [((1, 0), 0), ((0, -1), 90), ((-1, 0), 180), ((0, 1), -90)]
)
def test_screen_angle(point: tuple[float, float], expected: float) -> None:
    assert screen_angle((0, 0), point) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("angle", "expected"), [(0, 0), (180, 180), (-180, 180), (190, -170), (540, 180), (-370, -10)]
)
def test_normalise_angle(angle: float, expected: float) -> None:
    assert normalise_angle(angle) == pytest.approx(expected)


def test_rotate_by_drag() -> None:
    # Dragging from the right of the centre to above it is a quarter turn counter-clockwise.
    assert rotate_by_drag((0, 0), (10, 0), (0, -10), 5.0) == pytest.approx(95.0)
    assert rotate_by_drag((0, 0), (10, 0), (10, -3), 0.0, snap=True) == 15.0
    assert rotate_by_drag((0, 0), (10, 0), (10, -1), 0.0, snap=True) == 0.0


def test_pan_crop_moves_opposite_to_drag_and_clamps() -> None:
    crop = CropBox(0.25, 0.0, 0.5, 1.0)
    moved = pan_crop(crop, (100, 200), dx=20, dy=0)  # content dragged right -> see more left
    assert moved == CropBox(pytest.approx(0.15), 0.0, 0.5, 1.0)
    assert pan_crop(crop, (100, 200), dx=1000, dy=50).x == 0.0
    assert pan_crop(crop, (100, 200), dx=-1000, dy=0).x == pytest.approx(0.5)


@given(
    factor=st.floats(0.1, 10), ax=st.floats(0, 1), ay=st.floats(0, 1),
    w=st.floats(0.1, 1), h=st.floats(0.1, 1),
)  # fmt: skip
def test_zoom_crop_properties(factor: float, ax: float, ay: float, w: float, h: float) -> None:
    crop = CropBox((1 - w) / 2, (1 - h) / 2, w, h)
    zoomed = zoom_crop(crop, factor, (ax, ay))
    assert zoomed.width / zoomed.height == pytest.approx(w / h)  # shape kept
    assert -1e-9 <= zoomed.x <= 1 - zoomed.width + 1e-9
    assert -1e-9 <= zoomed.y <= 1 - zoomed.height + 1e-9
    assert zoomed.width <= 1 + 1e-9 and zoomed.height <= 1 + 1e-9
    assert min(zoomed.width, zoomed.height) >= MIN_CROP - 1e-9


def test_zoom_crop_keeps_anchor() -> None:
    zoomed = zoom_crop(CropBox(0.0, 0.0, 1.0, 1.0), 2.0, (0.25, 0.25))
    assert zoomed == CropBox(0.125, 0.125, 0.5, 0.5)
    assert zoom_crop(zoomed, 0.5, (0.25, 0.25)) == CropBox(0.0, 0.0, 1.0, 1.0)


def test_zoom_crop_invalid_factor() -> None:
    with pytest.raises(ValueError, match="positive"):
        zoom_crop(CropBox(0, 0, 1, 1), 0)


def test_centre() -> None:
    assert centre(Rect(10, 20, 30, 40)) == (25, 40)
    assert math.isclose(centre(Rect(0, 0, 1, 1))[0], 0.5)


def test_contains_respects_rotation() -> None:
    from collagio.core.geometry import contains

    rect = Rect(0, 0, 200, 20)  # long thin bar, centre (100, 10)
    assert contains(rect, 0, (190, 10))
    assert not contains(rect, 90, (190, 10))  # rotated upright
    assert contains(rect, 90, (100, -80))


def test_photo_at_picks_topmost() -> None:
    from collagio.core.geometry import photo_at
    from collagio.core.model import PhotoItem

    below = PhotoItem("below", "a", rect=Rect(0, 0, 100, 100), z=0)
    above = PhotoItem("above", "b", rect=Rect(50, 50, 100, 100), z=1)
    unplaced = PhotoItem("none", "c")
    photos = [above, below, unplaced]
    assert photo_at(photos, (75, 75)) is above
    assert photo_at(photos, (25, 25)) is below
    assert photo_at(photos, (500, 500)) is None


def test_refit_crop_keeps_centre_and_area() -> None:
    crop = CropBox(0.2, 0.3, 0.4, 0.4)  # square part of a square photo
    wide = refit_crop(crop, (1000, 1000), 2.0)
    assert wide.width / wide.height == pytest.approx(2.0)
    assert wide.width * wide.height == pytest.approx(0.16)
    assert (wide.x + wide.width / 2, wide.y + wide.height / 2) == pytest.approx((0.4, 0.5))


def test_refit_crop_stays_inside_the_photo() -> None:
    full = refit_crop(CropBox(0.0, 0.0, 1.0, 1.0), (600, 400), 1.0)
    assert (full.width, full.height) == pytest.approx((400 / 600, 1.0))
    assert full.x == pytest.approx((1 - 400 / 600) / 2)
    edge = refit_crop(CropBox(0.8, 0.0, 0.2, 0.2), (1000, 1000), 0.5)
    assert edge.x + edge.width <= 1.0 + 1e-9
    assert edge.y >= 0.0
    with pytest.raises(ValueError, match="positive"):
        refit_crop(full, (600, 400), 0)


@pytest.mark.parametrize("rotation", [0.0, 30.0, -100.0])
def test_resize_from_edge_changes_one_side_only(rotation: float) -> None:
    rect = Rect(100, 100, 200, 100)
    corners = rotated_corners(rect, rotation)
    right_middle = ((corners[1][0] + corners[2][0]) / 2, (corners[1][1] + corners[2][1]) / 2)
    pushed = to_world((150.0, 0.0), centre(rect), rotation)  # 50 beyond the right edge
    wider = resize_from_edge(rect, rotation, 1, pushed)
    assert (wider.width, wider.height) == pytest.approx((250, 100))
    left = rotated_corners(wider, rotation)
    assert left[0] == pytest.approx(corners[0])  # the left edge stays
    assert left[3] == pytest.approx(corners[3])
    assert right_middle != pytest.approx(centre(wider))
    taller = resize_from_edge(rect, rotation, 2, to_world((0.0, 80.0), centre(rect), rotation))
    assert (taller.width, taller.height) == pytest.approx((200, 130))
    assert rotated_corners(taller, rotation)[0] == pytest.approx(corners[0])


def test_resize_from_edge_keeps_a_minimum_size() -> None:
    rect = Rect(0, 0, 100, 50)
    squashed = resize_from_edge(rect, 0.0, 0, (50, 500))  # top edge dragged below the bottom
    assert squashed.height == pytest.approx(MIN_SIZE)
    assert squashed.bottom == pytest.approx(50)


def test_resize_free_does_not_keep_the_aspect_ratio() -> None:
    rect = Rect(100, 100, 200, 100)
    free = resize_free(rect, 0.0, 2, (400, 400))  # bottom-right corner
    assert (free.x, free.y, free.width, free.height) == pytest.approx((100, 100, 300, 300))
    rotated = resize_free(rect, 45.0, 0, to_world((-150.0, -60.0), centre(rect), 45.0))
    assert (rotated.width, rotated.height) == pytest.approx((250, 110))
    assert rotated_corners(rotated, 45.0)[2] == pytest.approx(rotated_corners(rect, 45.0)[2])
