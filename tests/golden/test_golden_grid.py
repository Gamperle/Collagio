"""Golden images for the grid layout. Regenerate with `pytest --update-golden`."""

from __future__ import annotations

from itertools import cycle, islice
from pathlib import Path

import pytest

from collagio.core.model import Background, BackgroundKind, Canvas, LayoutSettings, StyleRef
from collagio.layout.apply import build_project
from collagio.render.renderer import render_project
from tests.conftest import AssertGolden

CASES = {
    "grid_3_plain": (3, 800, 600, StyleRef()),
    "grid_7_border": (7, 600, 800, StyleRef("plain", {"border_width": 8})),
    "grid_20_rounded": (
        20,
        800,
        800,
        StyleRef("plain", {"border_width": 4, "border_color": "#fdfbf7", "corner_radius": 12}),
    ),
}


@pytest.mark.golden
@pytest.mark.parametrize("name", CASES)
def test_grid(name: str, sample_photos: list[Path], assert_golden: AssertGolden) -> None:
    count, width, height, style = CASES[name]
    photos = list(islice(cycle(sample_photos), count))
    project = build_project(
        photos,
        Canvas(
            width,
            height,
            background=Background(BackgroundKind.GRADIENT, "#e9e4da", "#c9c2b4", 60),
        ),
        LayoutSettings(gap=0.012, margin=0.025, size_variation=0.6),
        style,
        seed=2026,
    )
    assert_golden(render_project(project), name)
