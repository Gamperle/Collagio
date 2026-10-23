from __future__ import annotations

import subprocess
import sys

import pytest

import collagio
from collagio.cli.main import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"collagio {collagio.__version__}"


def test_no_arguments_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: collagio" in capsys.readouterr().out


def test_unknown_option_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--bogus"])
    assert exc.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_module_runs_as_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "collagio.cli.main", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert collagio.__version__ in result.stdout
