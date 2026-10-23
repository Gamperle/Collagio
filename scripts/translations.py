"""Keep the translation files in sync with the source code.

    uv run python scripts/translations.py update   # refresh .ts files from the code
    uv run python scripts/translations.py release  # compile .ts to .qm

Edit the .ts files with Qt Linguist (`uv run pyside6-linguist`) or a text editor.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted(str(p) for p in (ROOT / "src" / "collagio" / "app").glob("*.py"))
TS_FILES = sorted((ROOT / "src" / "collagio" / "i18n").glob("collagio_*.ts"))


def update(ts_files: list[Path] = TS_FILES) -> None:
    for ts in ts_files:
        subprocess.run(
            ["pyside6-lupdate", *SOURCES, "-ts", str(ts), "-no-obsolete", "-locations", "none"],
            check=True,
        )


def release(ts_files: list[Path] = TS_FILES, out_dir: Path | None = None) -> list[Path]:
    written = []
    for ts in ts_files:
        qm = (out_dir or ts.parent) / ts.with_suffix(".qm").name
        subprocess.run(["pyside6-lrelease", "-silent", str(ts), "-qm", str(qm)], check=True)
        written.append(qm)
    return written


if __name__ == "__main__":
    commands = {"update": update, "release": release}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
