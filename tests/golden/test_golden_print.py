"""Golden images for backgrounds and texts. Regenerate with `pytest --update-golden`."""

from __future__ import annotations

from pathlib import Path

import pytest

from collagio.core.model import (
    Background,
    BackgroundKind,
    Canvas,
    LayoutSettings,
    StyleRef,
    TextItem,
)
from collagio.layout.apply import build_project
from collagio.render.background import TEXTURES, render_background
from collagio.render.renderer import render_project
from tests.conftest import AssertGolden


@pytest.mark.golden
@pytest.mark.parametrize("texture", list(TEXTURES))
def test_texture_backgrounds(texture: str, assert_golden: AssertGolden) -> None:
    background = Background(BackgroundKind.TEXTURE, color=TEXTURES[texture], texture=texture)
    assert_golden(
        render_background(background, (320, 240), unit=0.24, seed=5), f"texture_{texture}"
    )


@pytest.mark.golden
def test_photo_background_with_title(
    sample_photos: list[Path], assert_golden: AssertGolden
) -> None:
    background = Background(BackgroundKind.PHOTO, photo=str(sample_photos[5]), blur=30, dim=0.3)
    project = build_project(
        sample_photos[:3],
        Canvas(480, 360, background=background),
        LayoutSettings(margin=0.05, gap=0.04, space_bottom=0.18),
        StyleRef("plain", {"border_width": 8}),
        seed=1,
    )
    project.texts.append(
        TextItem("t001", "Collagio", x=240, y=320, size=90, color="#ffffff", shadow=True)
    )
    project.texts.append(TextItem("t002", "tilted", x=400, y=40, size=50, rotation=20))
    assert_golden(render_project(project), "photo_background_title")
