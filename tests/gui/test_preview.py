from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from collagio.app.preview import PreviewRenderer, TileResult, preview_scale, render_key
from collagio.core.model import Canvas, PhotoItem, Project, Rect, Shadow, StyleRef
from collagio.imaging.cache import ThumbnailCache


def _project(path: str = "a.jpg") -> Project:
    return Project(
        canvas=Canvas(4000, 3000),
        photos=[PhotoItem("p1", path, rect=Rect(100, 100, 800, 600))],
    )


def test_preview_scale() -> None:
    assert preview_scale(_project()) == 0.5
    assert preview_scale(Project(canvas=Canvas(800, 600))) == 1.0


def test_render_key_ignores_position_only() -> None:
    project = _project()
    item = project.photos[0]
    key = render_key(project, item)
    item.rect = Rect(500, 700, 800, 600)
    assert render_key(project, item) == key
    for change in (
        lambda: setattr(item, "rect", Rect(500, 700, 801, 600)),
        lambda: setattr(item, "rotation", 3.0),
        lambda: setattr(item, "style", StyleRef("stamp")),
        lambda: setattr(project, "shadow", Shadow(opacity=0.5)),
        lambda: setattr(project, "seed", 9),
    ):
        change()
        assert render_key(project, item) != key
        key = render_key(project, item)


def test_tiles_backgrounds_and_icons(
    qtbot: QtBot, sample_photos: list[Path], tmp_path: Path
) -> None:
    renderer = PreviewRenderer(ThumbnailCache(tmp_path / "cache"))
    project = _project(str(sample_photos[0]))
    with qtbot.waitSignal(renderer.tile_ready, timeout=10_000) as tile:
        renderer.render_tile(project, "p1", renderer.next_request())
    result: TileResult = tile.args[0]
    assert result.error is None
    assert (result.image.width(), result.image.height()) == (400, 300)
    assert result.offset == (0.0, 0.0)

    with qtbot.waitSignal(renderer.background_ready, timeout=10_000) as background:
        renderer.render_background(project, 7)
    assert background.args[0] == 7
    assert background.args[1].width() == 2000

    with qtbot.waitSignal(renderer.icon_ready, timeout=10_000) as icon:
        renderer.render_icon(str(sample_photos[0]))
    assert max(icon.args[1].width(), icon.args[1].height()) == 160
    renderer.wait()


def test_errors_are_reported_not_raised(qtbot: QtBot, tmp_path: Path) -> None:
    renderer = PreviewRenderer(ThumbnailCache())
    project = _project(str(tmp_path / "missing.jpg"))
    with qtbot.waitSignal(renderer.tile_ready, timeout=10_000) as tile:
        renderer.render_tile(project, "p1", 1)
    assert "not found" in tile.args[0].error
    with qtbot.waitSignal(renderer.icon_ready, timeout=10_000) as icon:
        renderer.render_icon(str(tmp_path / "missing.jpg"))
    assert icon.args[1].width() == 160
    project.canvas.background.color = "not-a-colour"
    with qtbot.waitSignal(renderer.background_ready, timeout=10_000) as background:
        renderer.render_background(project, 1)
    assert background.args[1].width() == 2000
    renderer.wait()
