"""Main window: canvas, panels, menus, files and export."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer, QTranslator
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSpinBox,
    QTabWidget,
    QWidget,
)

from collagio import __version__
from collagio.app.canvas_view import CanvasView
from collagio.app.i18n import LANGUAGES, choose_language
from collagio.app.panels import CanvasPanel, LayoutPanel, PhotoListPanel, StylePanel, TextPanel
from collagio.app.preview import PreviewRenderer
from collagio.app.strings import command_label, export_filter, image_filter, project_filter
from collagio.app.workers import ExportJob
from collagio.core.document import AUTOSAVE_NAME, Document
from collagio.core.serialize import load_project
from collagio.errors import CollagioError
from collagio.imaging.cache import ThumbnailCache, default_cache_dir
from collagio.imaging.loader import find_images, is_supported

MAX_RECENT = 8
AUTOSAVE_INTERVAL_MS = 120_000


@dataclass
class ExportOptions:
    quality: int = 92
    bleed_mm: float = 0.0
    crop_marks: bool = False


class ExportOptionsDialog(QDialog):
    """Quality for JPEG/PDF, and bleed/crop marks for printing."""

    def __init__(self, path: Path, options: ExportOptions, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export options"))
        pdf = path.suffix.lower() == ".pdf"
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(options.quality)
        self.quality.setEnabled(path.suffix.lower() != ".png")
        self.bleed = QDoubleSpinBox()
        self.bleed.setRange(0, 20)
        self.bleed.setSuffix(" mm")
        self.bleed.setValue(options.bleed_mm)
        self.crop_marks = QCheckBox(self.tr("Crop marks"))
        self.crop_marks.setChecked(options.crop_marks and pdf)
        self.crop_marks.setEnabled(pdf)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow(self.tr("Quality"), self.quality)
        form.addRow(self.tr("Bleed"), self.bleed)
        form.addRow(self.crop_marks)
        form.addRow(buttons)

    def options(self) -> ExportOptions:
        return ExportOptions(self.quality.value(), self.bleed.value(), self.crop_marks.isChecked())


ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "collagio.svg"


def app_icon() -> QIcon:
    return QIcon(str(ICON_PATH))


def expand_paths(paths: list[str]) -> list[str]:
    """Files as given, folders replaced by the photos directly inside them."""
    result: list[str] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            result.extend(str(p) for p in find_images(path))
        elif is_supported(path):
            result.append(str(path))
    return result


class MainWindow(QMainWindow):
    translators: list[QTranslator]

    def __init__(
        self,
        document: Document | None = None,
        settings: QSettings | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings()
        self.cache_dir = cache_dir if cache_dir is not None else default_cache_dir()
        self.document = document if document is not None else Document()
        self.translators = []
        self.setWindowIcon(app_icon())
        self.selected: list[str] = []
        self.export_job: ExportJob | None = None
        self.export_options = ExportOptions()
        self.export_pool = QThreadPool(self)
        self.export_pool.setMaxThreadCount(1)

        self.renderer = PreviewRenderer(ThumbnailCache(self.cache_dir / "thumbnails"), self)
        self.canvas = CanvasView(self.document, self.renderer)
        self.setCentralWidget(self.canvas)

        self.photo_list = PhotoListPanel()
        self.layout_panel = LayoutPanel(self.document)
        self.style_panel = StylePanel(self.document)
        self.canvas_panel = CanvasPanel(self.document)
        self.text_panel = TextPanel(self.document)
        self._add_dock(self.tr("Photos"), self.photo_list, Qt.DockWidgetArea.LeftDockWidgetArea)
        tabs = QTabWidget()
        tabs.addTab(self.layout_panel, self.tr("Layout"))
        tabs.addTab(self.style_panel, self.tr("Style"))
        tabs.addTab(self.canvas_panel, self.tr("Canvas"))
        tabs.addTab(self.text_panel, self.tr("Text"))
        self.tabs = tabs
        self._add_dock(self.tr("Settings"), tabs, Qt.DockWidgetArea.RightDockWidgetArea)

        self._create_actions()
        self._connect()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        self.resize(1400, 900)
        self._watch(self.document)
        self.on_document_changed()

    # --- construction ----------------------------------------------------------------------------

    def _add_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> None:
        dock = QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(area, dock)

    def _action(
        self,
        text: str,
        handler: Callable[[], object],
        shortcut: QKeySequence | QKeySequence.StandardKey | str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(lambda: handler())
        return action

    def _create_actions(self) -> None:
        keys = QKeySequence.StandardKey
        self.new_action = self._action(self.tr("&New"), self.new_collage, keys.New)
        self.open_action = self._action(self.tr("&Open…"), self.open_dialog, keys.Open)
        self.save_action = self._action(self.tr("&Save"), self.save, keys.Save)
        self.save_as_action = self._action(self.tr("Save &as…"), self.save_as, keys.SaveAs)
        self.add_action = self._action(self.tr("&Add photos…"), self.add_dialog, "Ctrl+I")
        self.export_action = self._action(self.tr("&Export image…"), self.export_dialog, "Ctrl+E")
        self.recover_action = self._action(self.tr("&Recover unsaved work"), self.recover)
        self.quit_action = self._action(self.tr("&Quit"), self.close, keys.Quit)
        self.undo_action = self._action(self.tr("&Undo"), self.document_undo, keys.Undo)
        self.redo_action = self._action(self.tr("&Redo"), self.document_redo, keys.Redo)
        self.remove_action = self._action(
            self.tr("Re&move selected photos"), self.remove_selected, keys.Delete
        )
        self.front_action = self._action(
            self.tr("Bring to &front"), lambda: self.restack(True), "Ctrl+]"
        )
        self.back_action = self._action(
            self.tr("Send to &back"), lambda: self.restack(False), "Ctrl+["
        )
        self.reset_crop_action = self._action(self.tr("Reset &crop"), self.reset_crop)
        self.select_all_action = self._action(
            self.tr("Select &all"), self.select_all, keys.SelectAll
        )
        self.fit_action = self._action(
            self.tr("&Fit to window"), self.canvas.fit_to_window, "Ctrl+0"
        )
        self.zoom_in_action = self._action(
            self.tr("Zoom &in"), lambda: self.canvas.zoom(1.25), keys.ZoomIn
        )
        self.zoom_out_action = self._action(
            self.tr("Zoom &out"), lambda: self.canvas.zoom(0.8), keys.ZoomOut
        )
        self.about_action = self._action(self.tr("&About Collagio"), self.about)

        file_menu = self.menuBar().addMenu(self.tr("&File"))
        for action in (self.new_action, self.open_action):
            file_menu.addAction(action)
        self.recent_menu = file_menu.addMenu(self.tr("Open &recent"))
        file_menu.addSeparator()
        for action in (self.save_action, self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        for action in (self.add_action, self.export_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.recover_action)
        file_menu.addAction(self.quit_action)

        edit_menu = self.menuBar().addMenu(self.tr("&Edit"))
        for action in (self.undo_action, self.redo_action):
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        for action in (
            self.select_all_action,
            self.remove_action,
            self.front_action,
            self.back_action,
            self.reset_crop_action,
        ):
            edit_menu.addAction(action)

        view_menu = self.menuBar().addMenu(self.tr("&View"))
        for action in (self.fit_action, self.zoom_in_action, self.zoom_out_action):
            view_menu.addAction(action)
        language_menu = view_menu.addMenu(self.tr("&Language"))
        current = choose_language(self.settings)
        for code, name in LANGUAGES.items():
            action = language_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _=False, c=code: self.set_language(c))
        help_menu = self.menuBar().addMenu(self.tr("&Help"))
        help_menu.addAction(self.about_action)

        toolbar = self.addToolBar(self.tr("Main"))
        toolbar.setObjectName("main-toolbar")
        for action in (
            self.open_action,
            self.save_action,
            self.add_action,
            self.export_action,
            self.undo_action,
            self.redo_action,
            self.fit_action,
        ):
            toolbar.addAction(action)
        self._rebuild_recent_menu()

    def _connect(self) -> None:
        self.canvas.selection_changed.connect(self._on_canvas_selection)
        self.canvas.files_dropped.connect(self.add_photos)
        self.canvas.error.connect(self.show_error)
        self.photo_list.selection_changed.connect(self._on_list_selection)
        self.photo_list.add_requested.connect(self.add_dialog)
        self.photo_list.remove_requested.connect(self.remove_selected)
        self.photo_list.list.files_dropped.connect(self.add_photos)
        self.photo_list.icon_requested.connect(self.renderer.render_icon)
        self.renderer.icon_ready.connect(self.photo_list.set_icon)
        for panel in (self.layout_panel, self.style_panel, self.canvas_panel, self.text_panel):
            panel.error.connect(self.show_error)
        self.canvas.text_selected.connect(self._on_canvas_text)
        self.text_panel.text_selected.connect(self.canvas.select_text)

    # --- document --------------------------------------------------------------------------------

    def _watch(self, document: Document) -> None:
        document.subscribe(
            lambda: self.on_document_changed() if document is self.document else None
        )

    def set_document(self, document: Document) -> None:
        self.document = document
        for panel in (self.layout_panel, self.style_panel, self.canvas_panel, self.text_panel):
            panel.document = document
        self._watch(document)
        self.selected = []
        self.canvas.set_document(document)
        self.on_document_changed()

    def on_document_changed(self) -> None:
        document = self.document
        self.canvas.sync()
        self.selected = [
            i for i in self.selected if any(p.id == i for p in document.project.photos)
        ]
        self.photo_list.show_project(document.project, self.selected)
        self.layout_panel.refresh()
        self.style_panel.set_selection(self.selected)
        self.canvas_panel.refresh()
        self.text_panel.refresh(self.canvas.selected_text)
        name = document.path.name if document.path is not None else self.tr("Untitled")
        modified = "*" if document.modified else ""
        self.setWindowTitle(f"{name}{modified} \u2013 Collagio")
        stack = document.undo_stack
        self.undo_action.setEnabled(stack.can_undo)
        self.redo_action.setEnabled(stack.can_redo)
        self.undo_action.setText(
            self.tr("&Undo {}").format(command_label(stack.undo_label))
            if stack.undo_label
            else self.tr("&Undo")
        )
        self.redo_action.setText(
            self.tr("&Redo {}").format(command_label(stack.redo_label))
            if stack.redo_label
            else self.tr("&Redo")
        )
        has_photos = bool(document.project.photos)
        self.export_action.setEnabled(has_photos)
        self._update_selection_actions()

    def _update_selection_actions(self) -> None:
        single = len(self.selected) == 1
        self.remove_action.setEnabled(bool(self.selected) or self.canvas.selected_text is not None)
        for action in (self.front_action, self.back_action, self.reset_crop_action):
            action.setEnabled(single)

    def _on_canvas_selection(self, photo_ids: list[str]) -> None:
        self.selected = list(photo_ids)
        self.photo_list.select(self.selected)
        self.style_panel.set_selection(self.selected)
        self._update_selection_actions()

    def _on_canvas_text(self, text_id: str | None) -> None:
        self.text_panel.select(text_id)
        if text_id is not None:
            self.tabs.setCurrentWidget(self.text_panel)
        self._update_selection_actions()

    def _on_list_selection(self, photo_ids: list[str]) -> None:
        self.selected = list(photo_ids)
        self.canvas.select(self.selected)
        self.style_panel.set_selection(self.selected)
        self._update_selection_actions()

    def _run(self, edit: Callable[[], None]) -> bool:
        try:
            edit()
        except (CollagioError, OSError) as exc:
            self.show_error(str(exc))
            return False
        return True

    def document_undo(self) -> None:
        self.document.undo()

    def document_redo(self) -> None:
        self.document.redo()

    def add_photos(self, paths: list[str]) -> None:
        photos = expand_paths(paths)
        if not photos:
            self.show_error(self.tr("No supported photos found."))
            return
        self._run(lambda: self.document.add_photos(photos))

    def remove_selected(self) -> None:
        text_id = self.canvas.selected_text
        if text_id is not None:
            self._run(lambda: self.document.remove_texts([text_id]))
            return
        if self.selected:
            ids = list(self.selected)
            self._run(lambda: self.document.remove_photos(ids))

    def restack(self, to_front: bool) -> None:
        if len(self.selected) == 1:
            photo_id = self.selected[0]
            self._run(lambda: self.document.restack(photo_id, to_front))

    def reset_crop(self) -> None:
        if len(self.selected) == 1:
            photo_id = self.selected[0]
            self._run(lambda: self.document.crop_photo(photo_id, None))

    def select_all(self) -> None:
        self.canvas.select([p.id for p in self.document.project.photos])

    # --- files -----------------------------------------------------------------------------------

    def confirm_discard(self) -> bool:
        """Ask before unsaved changes are lost; True means go ahead."""
        if not self.document.modified:
            return True
        answer = QMessageBox.question(
            self,
            self.tr("Unsaved changes"),
            self.tr("Save the changes to {}?").format(
                self.document.path or self.tr("this collage")
            ),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def new_collage(self) -> None:
        if self.confirm_discard():
            self.set_document(Document())

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Open collage"), self._last_folder(), project_filter()
        )
        if path:
            self.open_file(Path(path))

    def open_file(self, path: Path) -> bool:
        if not self.confirm_discard():
            return False
        try:
            document = Document.open(path)
        except (CollagioError, OSError) as exc:
            self.show_error(str(exc))
            return False
        self.set_document(document)
        self._remember(path)
        return True

    def save(self) -> bool:
        if self.document.path is None:
            return self.save_as()
        return self._save_to(self.document.path)

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save collage"), self._last_folder(), project_filter()
        )
        return bool(path) and self._save_to(Path(path))

    def _save_to(self, path: Path) -> bool:
        saved: list[Path] = []
        if not self._run(lambda: saved.append(self.document.save(path))):
            return False
        self._remember(saved[0])
        self.statusBar().showMessage(self.tr("Saved {}").format(saved[0]), 5000)
        return True

    def add_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Add photos"), self._last_folder(), image_filter()
        )
        if paths:
            self.settings.setValue("last_folder", str(Path(paths[0]).parent))
            self.add_photos(paths)

    def _last_folder(self) -> str:
        return str(self.settings.value("last_folder", str(Path.home())))

    # --- recent files ----------------------------------------------------------------------------

    def recent_files(self) -> list[str]:
        value = self.settings.value("recent_files", [])
        if isinstance(value, str):  # QSettings returns a plain string for one entry
            return [value]
        return [str(v) for v in value] if isinstance(value, list) else []

    def _remember(self, path: Path) -> None:
        entry = str(path)
        recent = [entry, *(p for p in self.recent_files() if p != entry)][:MAX_RECENT]
        self.settings.setValue("recent_files", recent)
        self.settings.setValue("last_folder", str(path.parent))
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.recent_files()
        for entry in recent:
            action = self.recent_menu.addAction(Path(entry).name)
            action.setToolTip(entry)
            action.triggered.connect(lambda _=False, p=entry: self.open_file(Path(p)))
        self.recent_menu.setEnabled(bool(recent))

    # --- autosave --------------------------------------------------------------------------------

    @property
    def autosave_path(self) -> Path:
        return self.cache_dir / AUTOSAVE_NAME

    def autosave(self) -> None:
        try:
            self.document.autosave(self.cache_dir)
        except OSError as exc:
            self.statusBar().showMessage(self.tr("Autosave failed: {}").format(exc), 5000)

    def recover(self) -> bool:
        if not self.autosave_path.exists():
            self.show_error(self.tr("There is no unsaved work to recover."))
            return False
        if not self.confirm_discard():
            return False
        try:
            document = Document(load_project(self.autosave_path))
        except (CollagioError, OSError) as exc:
            self.show_error(str(exc))
            return False
        document.undo_stack.set_dirty()
        self.set_document(document)
        return True

    # --- export ----------------------------------------------------------------------------------

    def export_dialog(self) -> None:
        start = (
            self.document.path.with_suffix("").with_suffix(".jpg") if self.document.path else None
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export image"),
            str(start) if start else self._last_folder(),
            export_filter(),
        )
        if not path:
            return
        options = self.ask_export_options(Path(path))
        if options is not None:
            self.export(Path(path), options)

    def ask_export_options(self, path: Path) -> ExportOptions | None:
        dialog = ExportOptionsDialog(path, self.export_options, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        self.export_options = dialog.options()
        return self.export_options

    def export(self, path: Path, options: ExportOptions | None = None) -> ExportJob | None:
        if not self.document.project.photos:
            return None
        options = options if options is not None else ExportOptions()
        job = ExportJob(
            self.document.project, path, options.quality, options.bleed_mm, options.crop_marks
        )
        progress = QProgressDialog(
            self.tr("Exporting {}…").format(path.name), self.tr("Cancel"), 0, 1, self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.canceled.connect(job.cancel)

        def update(done: int, total: int) -> None:
            progress.setMaximum(max(1, total))
            progress.setValue(done)

        def finished(written: str) -> None:
            progress.close()
            self.statusBar().showMessage(self.tr("Exported {}").format(written), 5000)

        def failed(message: str) -> None:
            progress.close()
            self.show_error(message)

        job.signals.progress.connect(update)
        job.signals.finished.connect(finished)
        job.signals.failed.connect(failed)
        job.signals.cancelled.connect(progress.close)
        self.export_job = job
        self.export_pool.start(job)
        return job

    def set_language(self, code: str) -> None:
        self.settings.setValue("language", code)
        QMessageBox.information(
            self,
            self.tr("Language"),
            self.tr("The new language is used after restarting Collagio."),
        )

    # --- misc ------------------------------------------------------------------------------------

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)
        QMessageBox.warning(self, self.tr("Collagio"), message)

    def about(self) -> None:
        QMessageBox.about(
            self,
            self.tr("About Collagio"),
            self.tr(
                "<b>Collagio {}</b><br>Photo collages for Windows and Linux.<br>"
                "Free software under the GNU GPL v3 or later."
            ).format(__version__),
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.confirm_discard():
            event.ignore()
            return
        self.autosave_timer.stop()
        self.autosave_path.unlink(missing_ok=True)  # closed cleanly: nothing to recover
        if self.export_job is not None:
            self.export_job.cancel()
        self.export_pool.waitForDone()
        self.renderer.wait()
        event.accept()
