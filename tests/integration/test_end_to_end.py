"""CLI -> project file -> re-render: the saved project reproduces the collage exactly."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from collagio.cli.main import main
from collagio.core.serialize import load_project
from collagio.render.renderer import render_project


@pytest.fixture
def workspace(sample_photos: list[Path], tmp_path: Path) -> Path:
    photos = tmp_path / "photos"
    photos.mkdir()
    for photo in sample_photos:
        shutil.copy(photo, photos)
    return tmp_path


def test_project_reproduces_cli_output(workspace: Path) -> None:
    first = workspace / "first.png"
    project = workspace / "my.collagio"
    assert main([
        "-i", str(workspace / "photos"), "-o", str(first), "--size", "640x480",
        "--seed", "21", "--border", "8", "--save-project", str(project),
    ]) == 0  # fmt: skip

    second = workspace / "second.png"
    assert main(["-p", str(project), "-o", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_project_folder_can_be_moved(
    workspace: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    project = workspace / "my.collagio"
    original = workspace / "original.png"
    assert main([
        "-i", str(workspace / "photos"), "-o", str(original), "--size", "320x240",
        "--seed", "4", "--save-project", str(project),
    ]) == 0  # fmt: skip

    moved = tmp_path_factory.mktemp("moved") / "collage"
    shutil.move(workspace, moved)
    loaded = load_project(moved / "my.collagio")
    rendered = render_project(loaded)
    with Image.open(moved / "original.png") as expected:
        assert rendered.tobytes() == expected.convert("RGB").tobytes()


def test_all_sample_formats_render(sample_photos: list[Path], tmp_path: Path) -> None:
    out = tmp_path / "all.jpg"
    assert main(["-i", *map(str, sample_photos), "-o", str(out), "--size", "fullhd",
                 "--seed", "0"]) == 0  # fmt: skip
    with Image.open(out) as image:
        assert image.size == (1920, 1080)
        # Mostly photo content, not background.
        white = sum(count for count, rgb in image.getcolors(1920 * 1080) or [] if min(rgb) > 245)
        assert white < 0.2 * 1920 * 1080
