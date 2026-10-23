# PyInstaller build: one folder "Collagio" with both programs sharing the libraries.
#   uv run --group build pyinstaller packaging/pyinstaller/collagio.spec --noconfirm
# -*- mode: python -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

HERE = Path(SPECPATH)
ROOT = HERE.parent.parent
ICON = ROOT / "packaging" / "icons" / ("collagio.ico" if sys.platform == "win32" else "collagio-256.png")
DATAS = collect_data_files("collagio", excludes=["**/*.ts"])
# Qt modules Collagio does not use (keeps the download small).
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "tkinter", "pytest", "hypothesis",
]


def analysis(script):
    return Analysis(
        [str(HERE / script)],
        pathex=[str(ROOT / "src")],
        datas=DATAS,
        hiddenimports=["PySide6.QtSvg"],
        excludes=EXCLUDES,
        noarchive=False,
    )


gui = analysis("entry_gui.py")
cli = analysis("entry_cli.py")
gui_exe = EXE(
    PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="collagio-gui",
    console=False, icon=str(ICON), upx=False,
)
cli_exe = EXE(
    PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="collagio",
    console=True, icon=str(ICON), upx=False,
)
COLLECT(
    gui_exe, cli_exe,
    gui.binaries, gui.datas, cli.binaries, cli.datas,
    name="Collagio", upx=False,
)
