"""Golden images: every style in both layout modes, and a mixed-style collage.

Regenerate with `pytest --update-golden`.
"""

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
from collagio.layout.apply import apply_layout, build_project
from collagio.render.renderer import render_project
from collagio.styles import available_styles
from tests.conftest import AssertGolden

PARAMS = {
    "plain": {"border_width": 10},
    "stamp": {"value": "60"},
    "polaroid": {"caption": "Collagio"},
}


@pytest.mark.golden
@pytest.mark.parametrize("mode", list(LayoutMode))
@pytest.mark.parametrize("style", available_styles())
def test_style(
    style: str, mode: LayoutMode, sample_photos: list[Path], assert_golden: AssertGolden
) -> None:
    project = build_project(
        sample_photos[:4],
        Canvas(480, 360, background=Background(color="#5a564e")),
        LayoutSettings(mode=mode, gap=0.03, margin=0.04, max_rotation=10),
        StyleRef(style, PARAMS.get(style, {})),
        seed=7,
    )
    project.shadow = Shadow(opacity=0.4, blur=8)
    assert_golden(render_project(project), f"style_{style}_{mode.value}")


@pytest.mark.golden
def test_mixed_styles(sample_photos: list[Path], assert_golden: AssertGolden) -> None:
    project = build_project(
        list(islice(cycle(sample_photos), 7)),
        Canvas(640, 480, background=Background(color="#3c3a35")),
        LayoutSettings(mode=LayoutMode.SCATTERED, overlap=0.6),
        seed=11,
    )
    for item, style in zip(project.photos, available_styles(), strict=True):
        item.style = StyleRef(style, PARAMS.get(style, {}))
    apply_layout(project)
    project.shadow = Shadow(opacity=0.45)
    assert_golden(render_project(project), "mixed_styles")
