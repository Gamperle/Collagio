"""Export in a background thread with progress and cancel."""

from __future__ import annotations

import copy
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from collagio.app.strings import error_message
from collagio.core.model import Project
from collagio.errors import CollagioError
from collagio.render.export import export_image
from collagio.render.renderer import RenderCancelledError


class ExportSignals(QObject):
    progress = Signal(int, int)  # done, total
    finished = Signal(str)  # path
    failed = Signal(str)  # message
    cancelled = Signal()


class ExportJob(QRunnable):
    def __init__(
        self,
        project: Project,
        path: Path,
        quality: int = 92,
        bleed_mm: float = 0.0,
        crop_marks: bool = False,
    ) -> None:
        super().__init__()
        self.project = copy.deepcopy(project)
        self.path = path
        self.quality = quality
        self.bleed_mm = bleed_mm
        self.crop_marks = crop_marks
        self.signals = ExportSignals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _progress(self, done: int, total: int) -> None:
        if self._cancel.is_set():
            raise RenderCancelledError
        self.signals.progress.emit(done, total)

    def run(self) -> None:
        try:
            export_image(
                self.project,
                self.path,
                quality=self.quality,
                progress=self._progress,
                bleed_mm=self.bleed_mm,
                crop_marks=self.crop_marks,
            )
        except RenderCancelledError:
            self.signals.cancelled.emit()
        except (CollagioError, OSError) as exc:
            self.signals.failed.emit(error_message(exc))
        else:
            self.signals.finished.emit(str(self.path))
