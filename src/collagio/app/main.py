"""Entry point of the desktop app (`collagio-gui`).

collagio-gui                       empty collage
collagio-gui my.collagio           open a project
collagio-gui photo.jpg folder/     start a collage from photos
collagio-gui --version             print the version
collagio-gui --self-test           build the main window and exit (checks an installation)
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings
from PySide6.QtWidgets import QApplication

from collagio import __version__
from collagio.app.i18n import choose_language, install_translators
from collagio.app.main_window import MainWindow, app_icon
from collagio.core.serialize import is_project_file


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if "--version" in args[1:]:
        print(f"collagio-gui {__version__}")
        return 0
    self_test = "--self-test" in args[1:]
    args = [a for a in args if a != "--self-test"]
    app = QApplication.instance() or QApplication(args)
    assert isinstance(app, QApplication)
    app.setApplicationName("Collagio")
    app.setOrganizationName("Collagio")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    translators = install_translators(app, choose_language(QSettings()))

    window = build_window(args[1:])
    window.translators = translators
    if self_test:
        return run_self_test(window)
    window.show()
    return app.exec()


def run_self_test(window: MainWindow) -> int:
    """Check that resources load and the window works; for installers and CI."""
    problems = []
    if window.windowIcon().isNull():
        problems.append("app icon missing")
    if window.translators == [] and QLocale().language() != QLocale.Language.English:
        problems.append("translations missing")
    window.close()
    for problem in problems:
        print(f"self-test: {problem}", file=sys.stderr)
    print("self-test: ok" if not problems else "self-test: failed")
    return 1 if problems else 0


def build_window(files: Sequence[str], window: MainWindow | None = None) -> MainWindow:
    """Main window with the project or photos given on the command line."""
    window = window if window is not None else MainWindow()
    projects = [f for f in files if is_project_file(f)]
    if projects:
        window.open_file(Path(projects[0]))
    elif files:
        window.add_photos(list(files))
    return window


if __name__ == "__main__":
    raise SystemExit(main())
