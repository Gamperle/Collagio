"""Entry point of the desktop app (`collagio-gui`).

collagio-gui                       empty collage
collagio-gui my.collagio.json      open a project
collagio-gui photo.jpg folder/     start a collage from photos
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication

from collagio import __version__
from collagio.app.main_window import MainWindow
from collagio.core.serialize import PROJECT_SUFFIX


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(args)
    assert isinstance(app, QApplication)
    app.setApplicationName("Collagio")
    app.setOrganizationName("Collagio")
    app.setApplicationVersion(__version__)

    window = build_window(args[1:])
    window.show()
    return app.exec()


def build_window(files: Sequence[str], window: MainWindow | None = None) -> MainWindow:
    """Main window with the project or photos given on the command line."""
    window = window if window is not None else MainWindow()
    projects = [f for f in files if f.endswith(PROJECT_SUFFIX)]
    if projects:
        window.open_file(Path(projects[0]))
    elif files:
        window.add_photos(list(files))
    return window


if __name__ == "__main__":
    raise SystemExit(main())
