"""Golden images for the scattered layout. Regenerate with `pytest --update-golden`."""

from __future__ import annotations

from itertools import cycle, islice
from pathlib import Path

import pytest

from collagio.core.model import (
    Background,
    Canvas,
    LayoutMode,
    LayoutSettings,
    Shadow,
    StyleRef,
)
from collagio.layout.apply import build_project
from collagio.render.renderer import render_project
from tests.conftest import AssertGolden

CASES = {
    "scattered_5": (5, 800, 600, 0.4),
    "scattered_25": (25, 600, 800, 0.8),
}


@pytest.mark.golden
@pytest.mark.parametrize("name", CASES)
def test_scattered(name: str, sample_photos: list[Path], assert_golden: AssertGolden) -> None:
    count, width, height, overlap = CASES[name]
    project = build_project(
        list(islice(cycle(sample_photos), count)),
        Canvas(width, height, background=Background(color="#3a3833")),
        LayoutSettings(mode=LayoutMode.SCATTERED, margin=0.03, overlap=overlap, max_rotation=15),
        StyleRef("plain", {"border_width": 12}),
        seed=2026,
    )
    project.shadow = Shadow(opacity=0.5, blur=8)
    assert_golden(render_project(project), name)
