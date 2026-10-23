from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import collagio
from collagio.cli.main import main


@pytest.fixture
def photo_dir(sample_photos: list[Path]) -> Path:
    return sample_photos[0].parent


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


# --- argument handling --------------------------------------------------------------


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"collagio {collagio.__version__}"


def test_help_lists_presets_and_styles(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "A4" in out and "fullhd" in out and "plain" in out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["-i", "x"], "required: -o/--output"),
        (["-o", "x.png"], "no photos given"),
        (["-i", "a.jpg", "-p", "p.json", "-o", "x.png"], "either --input or --project"),
        (["-i", "a", "-o", "x.png", "--gap", "0.9"], "must be between 0 and 0.5"),
        (["-i", "a", "-o", "x.png", "--size-variation", "2"], "must be between 0 and 1"),
        (["-i", "a", "-o", "x.png", "--dpi", "0"], "must be positive"),
        (["-i", "a", "-o", "x.png", "--style", "nope"], "invalid choice"),
        (["-i", "a", "-o", "x.png", "--mode", "spiral"], "invalid choice"),
        (["-o", "x.png", "--bogus"], "unrecognized arguments"),
    ],
)
def test_usage_errors_exit_with_2(
    capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--size", "huge"], "invalid size"),
        (["--background", "blurple"], "invalid colour"),
        (["--background", "#fff,#000,#888"], "one colour or two"),
        (["--border-color", "blurple"], "invalid colour"),
        (["--border", "-3"], "must not be negative"),
        (["--quality", "0"], "quality"),
    ],
)
def test_invalid_options_report_errors(
    capsys: pytest.CaptureFixture[str],
    photo_dir: Path,
    tmp_path: Path,
    extra: list[str],
    message: str,
) -> None:
    code, _, err = _run(capsys, "-i", str(photo_dir), "-o", str(tmp_path / "x.jpg"), *extra)
    assert code == 1
    assert err.startswith("collagio: error:")
    assert message in err


def test_unsupported_output_fails_before_rendering(
    capsys: pytest.CaptureFixture[str], photo_dir: Path, tmp_path: Path
) -> None:
    code, _, err = _run(capsys, "-i", str(photo_dir), "-o", str(tmp_path / "x.gif"))
    assert code == 1
    assert "unsupported output format" in err


def test_missing_input(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, _, err = _run(capsys, "-i", str(tmp_path / "nope.jpg"), "-o", str(tmp_path / "x.png"))
    assert (code, "input not found" in err) == (1, True)


def test_unsupported_input(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hi")
    code, _, err = _run(capsys, "-i", str(tmp_path / "notes.txt"), "-o", str(tmp_path / "x.png"))
    assert (code, "unsupported file type" in err) == (1, True)


def test_too_few_photos(
    capsys: pytest.CaptureFixture[str], sample_photos: list[Path], tmp_path: Path
) -> None:
    code, _, err = _run(capsys, "-i", str(sample_photos[0]), "-o", str(tmp_path / "x.png"))
    assert (code, "2 to 100 photos" in err) == (1, True)


def test_broken_project_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    project = tmp_path / "p.collagio.json"
    project.write_text("{}")
    code, _, err = _run(capsys, "-p", str(project), "-o", str(tmp_path / "x.png"))
    assert (code, "not a Collagio project" in err) == (1, True)


def test_missing_project_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, _, err = _run(capsys, "-p", str(tmp_path / "nope.json"), "-o", str(tmp_path / "x.png"))
    assert code == 1
    assert "nope.json" in err


# --- generating collages ------------------------------------------------------------------


def test_folder_to_png(capsys: pytest.CaptureFixture[str], photo_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "collage.png"
    code, stdout, _ = _run(
        capsys, "-i", str(photo_dir), "-o", str(out), "--size", "800x600", "--seed", "5"
    )
    assert code == 0
    assert "800x600 px, 8 photos, seed 5" in stdout
    with Image.open(out) as image:
        assert (image.format, image.size) == ("PNG", (800, 600))


def test_files_and_folders_can_be_mixed(
    capsys: pytest.CaptureFixture[str], photo_dir: Path, sample_photos: list[Path], tmp_path: Path
) -> None:
    out = tmp_path / "c.jpg"
    code, stdout, _ = _run(
        capsys, "-i", str(photo_dir), "-i", str(sample_photos[0]), str(sample_photos[1]),
        "-o", str(out), "--size", "fullhd", "--seed", "1",
    )  # fmt: skip
    assert code == 0
    assert "10 photos" in stdout


def test_paper_size_dpi_and_orientation(
    capsys: pytest.CaptureFixture[str], photo_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "a5.jpg"
    code, _, _ = _run(
        capsys, "-i", str(photo_dir), "-o", str(out), "--size", "A5", "--dpi", "50",
        "--orientation", "landscape", "--seed", "2",
    )  # fmt: skip
    assert code == 0
    with Image.open(out) as image:
        assert image.size == (413, 291)
        assert image.info["dpi"] == (50, 50)


def test_style_and_background_options_are_saved(
    capsys: pytest.CaptureFixture[str], photo_dir: Path, tmp_path: Path
) -> None:
    project_path = tmp_path / "p.collagio.json"
    code, _, _ = _run(
        capsys, "-i", str(photo_dir), "-o", str(tmp_path / "x.png"), "--size", "400x300",
        "--seed", "3", "--gap", "0.02", "--margin", "0.05", "--size-variation", "0.8",
        "--border", "10", "--border-color", "#eeeeee", "--corner-radius", "6",
        "--background", "#000000,#ffffff", "--save-project", str(project_path),
    )  # fmt: skip
    assert code == 0
    document = json.loads(project_path.read_text())
    assert document["seed"] == 3
    assert document["layout"] == {
        "mode": "grid", "gap": 0.02, "margin": 0.05, "size_variation": 0.8,
    }  # fmt: skip
    assert document["default_style"] == {
        "name": "plain",
        "params": {"border_width": 10.0, "border_color": "#eeeeee", "corner_radius": 6.0},
    }
    assert document["canvas"]["background"]["kind"] == "gradient"


def test_random_seed_is_reported(
    capsys: pytest.CaptureFixture[str], photo_dir: Path, tmp_path: Path
) -> None:
    code, stdout, _ = _run(
        capsys, "-i", str(photo_dir), "-o", str(tmp_path / "x.png"), "--size", "300x200"
    )
    assert code == 0
    assert "seed " in stdout


def test_same_seed_same_output(
    capsys: pytest.CaptureFixture[str], photo_dir: Path, tmp_path: Path
) -> None:
    outputs = []
    for name in ("a.png", "b.png"):
        _run(capsys, "-i", str(photo_dir), "-o", str(tmp_path / name), "--size", "300x200",
             "--seed", "11")  # fmt: skip
        outputs.append((tmp_path / name).read_bytes())
    assert outputs[0] == outputs[1]


def test_module_runs_as_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "collagio.cli.main", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert collagio.__version__ in result.stdout
