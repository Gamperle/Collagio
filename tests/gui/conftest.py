from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from collagio.app.main_window import MainWindow


@pytest.fixture
def errors() -> list[str]:
    return []


@pytest.fixture
def make_window(
    qtbot: QtBot, tmp_path: Path, errors: list[str]
) -> Iterator[Callable[[], MainWindow]]:
    windows: list[MainWindow] = []

    def make() -> MainWindow:
        settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
        window = MainWindow(settings=settings, cache_dir=tmp_path / "cache")
        window.show_error = errors.append  # type: ignore[method-assign]
        window.confirm_discard = lambda: True  # type: ignore[method-assign]
        qtbot.addWidget(window)
        window.resize(1400, 900)
        window.show()
        qtbot.waitExposed(window)
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.renderer.wait()
        window.export_pool.waitForDone()


@pytest.fixture
def window(make_window: Callable[[], MainWindow]) -> MainWindow:
    return make_window()


@pytest.fixture
def loaded(window: MainWindow, sample_photos: list[Path], qtbot: QtBot) -> MainWindow:
    """Window with the 8 sample photos and all previews rendered."""
    window.add_photos([str(sample_photos[0].parent)])
    settle(window, qtbot)
    return window


def settle(window: MainWindow, qtbot: QtBot) -> None:
    """Let background previews finish and their results arrive."""
    window.renderer.wait()
    qtbot.wait(50)


def view_point(window: MainWindow, x: float, y: float) -> QPoint:
    return window.canvas.mapFromScene(QPointF(x, y))


def drag(
    window: MainWindow,
    start: tuple[float, float],
    end: tuple[float, float],
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    steps: int = 5,
) -> None:
    viewport = window.canvas.viewport()
    a, b = view_point(window, *start), view_point(window, *end)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, modifiers, a)
    for i in range(1, steps + 1):
        point = a + (b - a) * (i / steps)
        QTest.mouseMove(viewport, point)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, modifiers, b)


def click(
    window: MainWindow,
    x: float,
    y: float,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    viewport = window.canvas.viewport()
    point = view_point(window, x, y)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, modifiers, point)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, modifiers, point)
