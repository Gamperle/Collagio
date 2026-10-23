"""Side panels: photo list, layout, style and canvas settings.

Panels show the document's current values and turn "Apply" into one document
edit (one undo step). They never change the project directly.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLocale, QSettings, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QImage,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from collagio.app.strings import (
    choice_label,
    error_message,
    font_filter,
    image_filter,
    parameter_label,
    texture_label,
)
from collagio.core.document import Document
from collagio.core.model import (
    Background,
    BackgroundKind,
    Canvas,
    LayoutMode,
    LayoutSettings,
    PlacementOrder,
    Project,
    Shadow,
    StyleRef,
    TextItem,
)
from collagio.core.units import PAPER_SIZES_MM, PIXEL_PRESETS, Orientation, parse_size, px_to_mm
from collagio.errors import CollagioError
from collagio.render.background import TEXTURES
from collagio.styles import Style, available_styles, get_style

CUSTOM = "custom"
MAX_SEED = 999_999


def language() -> str:
    return QLocale().name().split("_")[0]


def style_label(name: str) -> str:
    labels = get_style(name).labels
    return labels.get(language(), labels["en"])


# --- small widgets -------------------------------------------------------------------------------


class ColorButton(QPushButton):
    """Shows a colour swatch; clicking opens a colour dialog."""

    changed = Signal(str)

    def __init__(self, color: str = "#ffffff", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.clicked.connect(self._choose)
        self._refresh()

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self._refresh()

    def _refresh(self) -> None:
        self.setText(self._color)
        self.setStyleSheet(
            f"background-color: {self._color}; "
            f"color: {'black' if QColor(self._color).lightness() > 128 else 'white'}"
        )

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self)
        if chosen.isValid():
            self.set_color(chosen.name())
            self.changed.emit(self._color)


class StyleForm(QWidget):
    """Editor for one style's parameters, generated from its defaults, choices and ranges."""

    def __init__(self, style: Style, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.style_definition = style
        self.fields: dict[str, QWidget] = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for name, default in style.defaults.items():
            widget = self._make_field(name, default)
            self.fields[name] = widget
            layout.addRow(parameter_label(name), widget)

    def _make_field(self, name: str, default: Any) -> QWidget:
        style = self.style_definition
        if name in style.choices:
            combo = QComboBox()
            for value in style.choices[name]:
                combo.addItem(choice_label(value), value)
            return combo
        if isinstance(default, str) and name.endswith("color"):
            return ColorButton(default)
        if isinstance(default, str):
            return QLineEdit(default)
        low, high = style.ranges.get(name, (0.0, 1000.0))
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(2)
        spin.setSingleStep(0.05 if high <= 1 else 1.0)
        spin.setValue(float(default))
        return spin

    def set_values(self, params: Mapping[str, Any]) -> None:
        values = {**self.style_definition.defaults, **params}
        for name, widget in self.fields.items():
            value = values[name]
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(str(value))))
            elif isinstance(widget, ColorButton):
                widget.set_color(str(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))

    def values(self) -> dict[str, Any]:
        """Parameters that differ from the style's defaults."""
        result: dict[str, Any] = {}
        for name, widget in self.fields.items():
            value: Any
            if isinstance(widget, QComboBox):
                value = str(widget.currentData())
            elif isinstance(widget, ColorButton):
                value = widget.color
            elif isinstance(widget, QLineEdit):
                value = widget.text()
            else:
                assert isinstance(widget, QDoubleSpinBox)
                value = widget.value()
            default = self.style_definition.defaults[name]
            if isinstance(default, float | int) and not isinstance(default, bool):
                if abs(float(value) - float(default)) > 1e-9:
                    result[name] = float(value)
            elif value != default:
                result[name] = value
        return result


def _spin(low: float, high: float, step: float, decimals: int = 2) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(low, high)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    return spin


# --- photo list ----------------------------------------------------------------------------------


class PhotoList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


FileStamp = tuple[int, int] | None


def file_stamp(path: str) -> FileStamp:
    """Modification time and size, to notice a photo changed on disk (None: missing)."""
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


class PhotoListPanel(QWidget):
    selection_changed = Signal(list)  # photo ids
    add_requested = Signal()
    remove_requested = Signal()
    icon_requested = Signal(str)  # path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.list = PhotoList()
        self.list.setIconSize(QPixmap(64, 64).size())
        self.add_button = QPushButton(self.tr("Add photos…"))
        self.remove_button = QPushButton(self.tr("Remove"))
        self.count_label = QLabel()
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.count_label)
        layout.addWidget(self.list)
        layout.addLayout(buttons)

        self._icons: dict[str, tuple[FileStamp, QIcon]] = {}  # by path
        self._updating = False
        self.add_button.clicked.connect(self.add_requested)
        self.remove_button.clicked.connect(self.remove_requested)
        self.list.itemSelectionChanged.connect(self._on_selection)

    def show_project(self, project: Project, selected: list[str]) -> None:
        self._updating = True
        self.list.clear()
        for photo in project.photos:
            item = QListWidgetItem(Path(photo.path).name)
            item.setData(Qt.ItemDataRole.UserRole, photo.id)
            item.setToolTip(photo.path)
            cached = self._icons.get(photo.path)
            if cached is not None:
                item.setIcon(cached[1])  # until a newer one arrives
            if cached is None or cached[0] != file_stamp(photo.path):
                self.icon_requested.emit(photo.path)
            self.list.addItem(item)
            item.setSelected(photo.id in selected)
        count = len(project.photos)
        self.count_label.setText(self.tr("%n photo(s)", "", count))
        self.remove_button.setEnabled(bool(selected))
        self._updating = False

    def set_icon(self, path: str, image: QImage) -> None:
        icon = QIcon(QPixmap.fromImage(image))
        self._icons[path] = (file_stamp(path), icon)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.toolTip() == path:
                item.setIcon(icon)

    def select(self, photo_ids: list[str]) -> None:
        self._updating = True
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in photo_ids)
        self.remove_button.setEnabled(bool(photo_ids))
        self._updating = False

    def selected_ids(self) -> list[str]:
        return [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.list.selectedItems()]

    def _on_selection(self) -> None:
        if not self._updating:
            ids = self.selected_ids()
            self.remove_button.setEnabled(bool(ids))
            self.selection_changed.emit(ids)


# --- layout --------------------------------------------------------------------------------------


ASK_REPLACE_EDITS = "ask_before_replacing_edits"  # setting


class LayoutPanel(QWidget):
    error = Signal(str)

    def __init__(
        self,
        document: Document,
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self.app_settings = settings if settings is not None else QSettings()
        self.mode = QComboBox()
        self.mode.addItem(self.tr("Grid"), LayoutMode.GRID)
        self.mode.addItem(self.tr("Scattered"), LayoutMode.SCATTERED)
        self.order = QComboBox()
        self.order.addItem(self.tr("By shape (least cropping)"), PlacementOrder.SHAPE)
        self.order.addItem(self.tr("Random"), PlacementOrder.RANDOM)
        self.order.addItem(self.tr("Photo order"), PlacementOrder.INPUT)
        self.gap = _spin(0, 50, 0.5, 1)
        self.margin = _spin(0, 50, 0.5, 1)
        self.size_variation = _spin(0, 1, 0.05)
        self.rotation = _spin(0, 45, 1, 0)
        self.overlap = _spin(0, 1, 0.05)
        self.min_visible = _spin(0, 1, 0.05)
        self.space_top = _spin(0, 50, 0.5, 1)
        self.space_bottom = _spin(0, 50, 0.5, 1)
        self.seed = QSpinBox()
        self.seed.setRange(0, MAX_SEED)
        self.shuffle_button = QPushButton(self.tr("Shuffle"))
        self.apply_button = QPushButton(self.tr("Apply layout"))

        form = self._form = QFormLayout()
        form.addRow(self.tr("Mode"), self.mode)
        form.addRow(self.tr("Photo placement"), self.order)
        form.addRow(self.tr("Gap (%)"), self.gap)
        form.addRow(self.tr("Margin (%)"), self.margin)
        form.addRow(self.tr("Size variation"), self.size_variation)
        form.addRow(self.tr("Max. rotation (°)"), self.rotation)
        form.addRow(self.tr("Overlap"), self.overlap)
        form.addRow(self.tr("Min. visible"), self.min_visible)
        form.addRow(self.tr("Space above (%)"), self.space_top)
        form.addRow(self.tr("Space below (%)"), self.space_bottom)
        seed_row = QHBoxLayout()
        seed_row.addWidget(self.seed)
        seed_row.addWidget(self.shuffle_button)
        form.addRow(self.tr("Seed"), seed_row)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.apply_button)
        layout.addStretch()

        self.mode.currentIndexChanged.connect(self._update_visibility)
        self.apply_button.clicked.connect(self.apply)
        self.shuffle_button.clicked.connect(self.shuffle)
        self.refresh()

    def current_mode(self) -> LayoutMode:
        # Qt hands enum item data back as plain strings.
        return LayoutMode(self.mode.currentData())

    def _rows(self) -> dict[QWidget, bool]:
        """Widgets and whether they apply to grid (True) or scattered (False) mode."""
        return {
            self.order: True,
            self.gap: True,
            self.rotation: False,
            self.overlap: False,
            self.min_visible: False,
        }

    def _update_visibility(self) -> None:
        grid = self.current_mode() is LayoutMode.GRID
        for widget, for_grid in self._rows().items():
            self._form.setRowVisible(widget, for_grid == grid)

    def refresh(self) -> None:
        settings = self.document.project.layout
        self.mode.setCurrentIndex(self.mode.findData(settings.mode))
        self.order.setCurrentIndex(self.order.findData(settings.order))
        self.gap.setValue(settings.gap * 100)
        self.margin.setValue(settings.margin * 100)
        self.size_variation.setValue(settings.size_variation)
        self.rotation.setValue(settings.max_rotation)
        self.overlap.setValue(settings.overlap)
        self.min_visible.setValue(settings.min_visible)
        self.space_top.setValue(settings.space_top * 100)
        self.space_bottom.setValue(settings.space_bottom * 100)
        self.seed.setValue(self.document.project.seed % (MAX_SEED + 1))
        self._update_visibility()

    def settings(self) -> LayoutSettings:
        return LayoutSettings(
            mode=self.current_mode(),
            gap=self.gap.value() / 100,
            margin=self.margin.value() / 100,
            size_variation=self.size_variation.value(),
            order=PlacementOrder(self.order.currentData()),
            max_rotation=self.rotation.value(),
            overlap=self.overlap.value(),
            min_visible=self.min_visible.value(),
            space_top=self.space_top.value() / 100,
            space_bottom=self.space_bottom.value() / 100,
        )

    def apply(self) -> bool:
        """Lay the photos out again; False if cancelled or failed."""
        if not self.confirm_replace():
            return False
        try:
            self.document.relayout(self.settings(), self.seed.value())
        except CollagioError as exc:
            self.error.emit(error_message(exc))
            return False
        return True

    def shuffle(self) -> None:
        previous = self.seed.value()
        self.seed.setValue(random.randrange(MAX_SEED + 1))
        if not self.apply():
            self.seed.setValue(previous)

    def confirm_replace(self) -> bool:
        """Ask before a new layout replaces changes made by hand; True means go ahead."""
        if not self.document.project.layout_edited:
            return True
        if not self.app_settings.value(ASK_REPLACE_EDITS, True, type=bool):
            return True
        go_ahead, dont_ask = self.ask_replace()
        if go_ahead and dont_ask:
            self.app_settings.setValue(ASK_REPLACE_EDITS, False)
        return go_ahead

    def ask_replace(self) -> tuple[bool, bool]:
        """The question itself: (replace?, don't ask again?)."""
        box = QMessageBox(
            QMessageBox.Icon.Question,
            self.tr("Replace manual changes?"),
            self.tr(
                "The new layout replaces the photos you moved, resized, rotated, swapped "
                "or cropped by hand. Undo brings them back."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            self,
        )
        box.button(QMessageBox.StandardButton.Yes).setText(self.tr("Replace"))
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dont_ask = QCheckBox(self.tr("Don't ask again"))  # keep a reference for PySide
        box.setCheckBox(dont_ask)
        go_ahead = box.exec() == QMessageBox.StandardButton.Yes
        return go_ahead, dont_ask.isChecked()


# --- style ---------------------------------------------------------------------------------------


class StylePanel(QWidget):
    error = Signal(str)

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self.selected: list[str] = []

        self.target_all = QRadioButton(self.tr("All photos"))
        self.target_selected = QRadioButton(self.tr("Selected photos"))
        self.target_all.setChecked(True)
        targets = QButtonGroup(self)
        targets.addButton(self.target_all)
        targets.addButton(self.target_selected)
        self.style_combo = QComboBox()
        for name in available_styles():
            self.style_combo.addItem(style_label(name), name)
        self.form_holder = QVBoxLayout()
        self.form: StyleForm | None = None
        self.apply_button = QPushButton(self.tr("Apply style"))
        self.reset_button = QPushButton(self.tr("Use the style for all photos"))

        self.shadow_opacity = _spin(0, 1, 0.05)
        self.shadow_blur = _spin(0, 100, 1, 1)
        self.shadow_button = QPushButton(self.tr("Apply shadow"))
        shadow_box = QGroupBox(self.tr("Drop shadow"))
        shadow_form = QFormLayout(shadow_box)
        shadow_form.addRow(self.tr("Opacity"), self.shadow_opacity)
        shadow_form.addRow(self.tr("Blur"), self.shadow_blur)
        shadow_form.addRow(self.shadow_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.target_all)
        layout.addWidget(self.target_selected)
        layout.addWidget(self.style_combo)
        layout.addLayout(self.form_holder)
        layout.addWidget(self.apply_button)
        layout.addWidget(self.reset_button)
        layout.addWidget(shadow_box)
        layout.addStretch()

        self.style_combo.currentIndexChanged.connect(lambda _: self._build_form({}))
        self.target_all.toggled.connect(lambda _: self.refresh())
        self.apply_button.clicked.connect(self.apply)
        self.reset_button.clicked.connect(self.reset_selected)
        self.shadow_button.clicked.connect(self.apply_shadow)
        self.refresh()

    def _build_form(self, params: Mapping[str, Any]) -> None:
        if self.form is not None:
            self.form_holder.removeWidget(self.form)
            self.form.deleteLater()
        self.form = StyleForm(get_style(str(self.style_combo.currentData())))
        self.form.set_values(params)
        self.form_holder.addWidget(self.form)

    def set_selection(self, photo_ids: list[str]) -> None:
        self.selected = list(photo_ids)
        self.target_selected.setEnabled(bool(photo_ids))
        if photo_ids:
            self.target_selected.setChecked(True)
        else:
            self.target_all.setChecked(True)
        self.refresh()

    def _shown_style(self) -> StyleRef:
        project = self.document.project
        if self.target_selected.isChecked() and self.selected:
            photo = next((p for p in project.photos if p.id == self.selected[0]), None)
            if photo is not None:
                return project.style_for(photo)
        return project.default_style

    def refresh(self) -> None:
        style = self._shown_style()
        self.style_combo.blockSignals(True)
        self.style_combo.setCurrentIndex(self.style_combo.findData(style.name))
        self.style_combo.blockSignals(False)
        self._build_form(style.params)
        self.reset_button.setVisible(self.target_selected.isChecked() and bool(self.selected))
        self.shadow_opacity.setValue(self.document.project.shadow.opacity)
        self.shadow_blur.setValue(self.document.project.shadow.blur)

    def current_style(self) -> StyleRef:
        assert self.form is not None
        return StyleRef(str(self.style_combo.currentData()), self.form.values())

    def apply(self) -> None:
        style = self.current_style()
        try:
            get_style(style.name).resolve(style.params)
            if self.target_selected.isChecked() and self.selected:
                self.document.set_photo_styles(self.selected, style)
            else:
                self.document.set_default_style(style)
        except CollagioError as exc:
            self.error.emit(error_message(exc))

    def reset_selected(self) -> None:
        if self.selected:
            self.document.set_photo_styles(self.selected, None)

    def apply_shadow(self) -> None:
        shadow = self.document.project.shadow
        self.document.set_shadow(
            Shadow(
                opacity=self.shadow_opacity.value(),
                blur=self.shadow_blur.value(),
                offset_x=shadow.offset_x,
                offset_y=shadow.offset_y,
                color=shadow.color,
            )
        )


# --- canvas --------------------------------------------------------------------------------------


class CanvasPanel(QWidget):
    error = Signal(str)

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self.preset = QComboBox()
        for name, (w_mm, h_mm) in PAPER_SIZES_MM.items():
            self.preset.addItem(f"{name} ({w_mm:g} \u00d7 {h_mm:g} mm)", name)
        for name, (w_px, h_px) in PIXEL_PRESETS.items():
            self.preset.addItem(f"{name} ({w_px} \u00d7 {h_px} px)", name)
        self.preset.addItem(self.tr("Custom"), CUSTOM)
        self.orientation = QComboBox()
        self.orientation.addItem(self.tr("Portrait"), Orientation.PORTRAIT)
        self.orientation.addItem(self.tr("Landscape"), Orientation.LANDSCAPE)
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(1, 30_000)
            spin.setSuffix(" px")
        self.dpi = QSpinBox()
        self.dpi.setRange(10, 1200)
        self.background_kind = QComboBox()
        self.background_kind.addItem(self.tr("Solid colour"), BackgroundKind.SOLID)
        self.background_kind.addItem(self.tr("Gradient"), BackgroundKind.GRADIENT)
        self.background_kind.addItem(self.tr("Texture"), BackgroundKind.TEXTURE)
        self.background_kind.addItem(self.tr("Blurred photo"), BackgroundKind.PHOTO)
        self.texture = QComboBox()
        for name in TEXTURES:
            self.texture.addItem(texture_label(name), name)
        self.photo = QLineEdit()
        self.photo.setReadOnly(True)
        self.photo_button = QPushButton(self.tr("Choose…"))
        self.blur = _spin(0, 200, 1, 0)
        self.dim = _spin(0, 1, 0.05)
        self.size_label = QLabel()
        self.color = ColorButton()
        self.color2 = ColorButton()
        self.angle = _spin(0, 360, 15, 0)
        self.apply_button = QPushButton(self.tr("Apply canvas"))

        form = self._form = QFormLayout()
        form.addRow(self.tr("Size"), self.preset)
        form.addRow(self.tr("Orientation"), self.orientation)
        form.addRow(self.tr("Width"), self.width_spin)
        form.addRow(self.tr("Height"), self.height_spin)
        form.addRow(self.tr("DPI"), self.dpi)
        form.addRow("", self.size_label)
        form.addRow(self.tr("Background"), self.background_kind)
        form.addRow(self.tr("Texture"), self.texture)
        photo_row = QHBoxLayout()
        photo_row.addWidget(self.photo)
        photo_row.addWidget(self.photo_button)
        self._photo_row = QWidget()
        self._photo_row.setLayout(photo_row)
        photo_row.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.tr("Photo"), self._photo_row)
        form.addRow(self.tr("Blur"), self.blur)
        form.addRow(self.tr("Darken"), self.dim)
        form.addRow(self.tr("Colour"), self.color)
        form.addRow(self.tr("Second colour"), self.color2)
        form.addRow(self.tr("Gradient angle"), self.angle)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.apply_button)
        layout.addStretch()

        for signal in (self.preset.currentIndexChanged, self.orientation.currentIndexChanged):
            signal.connect(self._preset_changed)
        self.dpi.valueChanged.connect(self._preset_changed)
        self.background_kind.currentIndexChanged.connect(self._update_enabled)
        self.texture.currentIndexChanged.connect(self._texture_changed)
        self.photo_button.clicked.connect(self.choose_photo)
        for spin in (self.width_spin, self.height_spin, self.dpi):
            spin.valueChanged.connect(self._update_size_label)
        self.apply_button.clicked.connect(self.apply)
        self.refresh()

    def _preset_changed(self) -> None:
        name = self.preset.currentData()
        custom = name == CUSTOM
        self.width_spin.setEnabled(custom)
        self.height_spin.setEnabled(custom)
        self.orientation.setEnabled(not custom)
        if not custom:
            orientation = Orientation(self.orientation.currentData())
            width, height = parse_size(str(name), self.dpi.value(), orientation)
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)

    def current_kind(self) -> BackgroundKind:
        return BackgroundKind(self.background_kind.currentData())

    def _update_enabled(self) -> None:
        kind = self.current_kind()
        rows: dict[QWidget, bool] = {
            self.texture: kind is BackgroundKind.TEXTURE,
            self._photo_row: kind is BackgroundKind.PHOTO,
            self.blur: kind is BackgroundKind.PHOTO,
            self.dim: kind is BackgroundKind.PHOTO,
            self.color: kind is not BackgroundKind.PHOTO,
            self.color2: kind is BackgroundKind.GRADIENT,
            self.angle: kind is BackgroundKind.GRADIENT,
        }
        for widget, visible in rows.items():
            self._form.setRowVisible(widget, visible)

    def _texture_changed(self) -> None:
        self.color.set_color(TEXTURES[str(self.texture.currentData())])

    def _update_size_label(self) -> None:
        dpi = self.dpi.value()
        width = px_to_mm(self.width_spin.value(), dpi)
        height = px_to_mm(self.height_spin.value(), dpi)
        self.size_label.setText(f"{width:.0f} \u00d7 {height:.0f} mm")

    def choose_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Background photo"), self.photo.text(), image_filter()
        )
        if path:
            self.photo.setText(path)

    def _matching_preset(self, canvas: Canvas) -> tuple[str, Orientation]:
        for index in range(self.preset.count()):
            name = self.preset.itemData(index)
            if name == CUSTOM:
                continue
            for orientation in Orientation:
                if parse_size(str(name), canvas.dpi, orientation) == (canvas.width, canvas.height):
                    return str(name), orientation
        orientation = (
            Orientation.LANDSCAPE if canvas.width > canvas.height else Orientation.PORTRAIT
        )
        return CUSTOM, orientation

    def refresh(self) -> None:
        canvas = self.document.project.canvas
        widgets = (self.preset, self.orientation, self.dpi)
        for widget in widgets:
            widget.blockSignals(True)
        self.dpi.setValue(canvas.dpi)
        name, orientation = self._matching_preset(canvas)
        self.preset.setCurrentIndex(self.preset.findData(name))
        self.orientation.setCurrentIndex(self.orientation.findData(orientation))
        for widget in widgets:
            widget.blockSignals(False)
        self.width_spin.setValue(canvas.width)
        self.height_spin.setValue(canvas.height)
        custom = name == CUSTOM
        self.width_spin.setEnabled(custom)
        self.height_spin.setEnabled(custom)
        self.orientation.setEnabled(not custom)
        background = canvas.background
        self.background_kind.setCurrentIndex(self.background_kind.findData(background.kind))
        self.texture.blockSignals(True)
        self.texture.setCurrentIndex(max(0, self.texture.findData(background.texture)))
        self.texture.blockSignals(False)
        self.photo.setText(background.photo)
        self.blur.setValue(background.blur)
        self.dim.setValue(background.dim)
        self.color.set_color(background.color)
        self.color2.set_color(background.color2)
        self.angle.setValue(background.angle)
        self._update_enabled()
        self._update_size_label()

    def canvas(self) -> Canvas:
        return Canvas(
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            dpi=self.dpi.value(),
            background=Background(
                kind=self.current_kind(),
                color=self.color.color,
                color2=self.color2.color,
                angle=self.angle.value(),
                texture=str(self.texture.currentData()),
                photo=self.photo.text(),
                blur=self.blur.value(),
                dim=self.dim.value(),
            ),
        )

    def apply(self) -> None:
        try:
            self.document.set_canvas(self.canvas())
        except CollagioError as exc:
            self.error.emit(error_message(exc))


# --- texts -------------------------------------------------------------------------------------


class TextPanel(QWidget):
    """List of the collage's texts and an editor for the selected one."""

    error = Signal(str)
    text_selected = Signal(object)  # text id or None

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self.list = QListWidget()
        self.add_button = QPushButton(self.tr("Add text"))
        self.remove_button = QPushButton(self.tr("Remove"))
        self.text_edit = QPlainTextEdit()
        self.text_edit.setMaximumHeight(80)
        self.size_spin = _spin(1, 1000, 5, 0)
        self.color = ColorButton("#222222")
        self.rotation = _spin(-180, 180, 1, 0)
        self.font_edit = QLineEdit()
        self.font_edit.setReadOnly(True)
        self.font_edit.setPlaceholderText(self.tr("Built-in font"))
        self.font_button = QPushButton(self.tr("Choose…"))
        self.font_reset = QPushButton(self.tr("Built-in"))
        self.shadow = QCheckBox(self.tr("Drop shadow"))
        self.apply_button = QPushButton(self.tr("Apply text"))

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_edit)
        font_row.addWidget(self.font_button)
        font_row.addWidget(self.font_reset)
        self.editor = QGroupBox(self.tr("Selected text"))
        form = QFormLayout(self.editor)
        form.addRow(self.tr("Text"), self.text_edit)
        form.addRow(self.tr("Size"), self.size_spin)
        form.addRow(self.tr("Colour"), self.color)
        form.addRow(self.tr("Rotation (°)"), self.rotation)
        form.addRow(self.tr("Font"), font_row)
        form.addRow(self.shadow)
        form.addRow(self.apply_button)
        hint = QLabel(self.tr("Drag texts on the canvas to move them."))
        hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addLayout(buttons)
        layout.addWidget(self.editor)
        layout.addWidget(hint)
        layout.addStretch()

        self._updating = False
        self.list.itemSelectionChanged.connect(self._on_list_selection)
        self.add_button.clicked.connect(self.add)
        self.remove_button.clicked.connect(self.remove)
        self.apply_button.clicked.connect(self.apply)
        self.font_button.clicked.connect(self.choose_font)
        self.font_reset.clicked.connect(self.font_edit.clear)
        self.refresh()

    def current_id(self) -> str | None:
        items = self.list.selectedItems()
        return str(items[0].data(Qt.ItemDataRole.UserRole)) if items else None

    def _current_text(self) -> TextItem | None:
        text_id = self.current_id()
        return next((t for t in self.document.project.texts if t.id == text_id), None)

    def refresh(self, selected: str | None = None) -> None:
        selected = selected if selected is not None else self.current_id()
        self._updating = True
        self.list.clear()
        for text in self.document.project.texts:
            first_line = text.text.splitlines()[0] if text.text.strip() else self.tr("(empty)")
            item = QListWidgetItem(first_line)
            item.setData(Qt.ItemDataRole.UserRole, text.id)
            self.list.addItem(item)
            item.setSelected(text.id == selected)
        self._updating = False
        self._show(self._current_text())

    def select(self, text_id: str | None) -> None:
        self._updating = True
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) == text_id)
        self._updating = False
        self._show(self._current_text())

    def _show(self, text: TextItem | None) -> None:
        self.editor.setEnabled(text is not None)
        self.remove_button.setEnabled(text is not None)
        if text is None:
            return
        self.text_edit.setPlainText(text.text)
        self.size_spin.setValue(text.size)
        self.color.set_color(text.color)
        self.rotation.setValue(text.rotation)
        self.font_edit.setText(text.font)
        self.shadow.setChecked(text.shadow)

    def _on_list_selection(self) -> None:
        if not self._updating:
            self._show(self._current_text())
            self.text_selected.emit(self.current_id())

    def add(self) -> None:
        try:
            text_id = self.document.add_text(self.tr("Text"))
        except CollagioError as exc:
            self.error.emit(error_message(exc))
            return
        self.select(text_id)
        self.text_selected.emit(text_id)

    def remove(self) -> None:
        text_id = self.current_id()
        if text_id is not None:
            self.document.remove_texts([text_id])

    def apply(self) -> None:
        text = self._current_text()
        if text is None:
            return
        updated = TextItem(
            id=text.id,
            text=self.text_edit.toPlainText(),
            x=text.x,
            y=text.y,
            size=self.size_spin.value(),
            color=self.color.color,
            rotation=self.rotation.value(),
            font=self.font_edit.text(),
            shadow=self.shadow.isChecked(),
        )
        try:
            self.document.update_text(updated)
        except CollagioError as exc:
            self.error.emit(error_message(exc))

    def choose_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Font"), self.font_edit.text(), font_filter()
        )
        if path:
            self.font_edit.setText(path)
