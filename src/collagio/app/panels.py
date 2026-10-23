"""Side panels: photo list, layout, style and canvas settings.

Panels show the document's current values and turn "Apply" into one document
edit (one undo step). They never change the project directly.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLocale, Qt, Signal
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
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
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
)
from collagio.core.units import PAPER_SIZES_MM, PIXEL_PRESETS, Orientation, parse_size
from collagio.errors import CollagioError
from collagio.styles import Style, available_styles, get_style

CUSTOM = "custom"
MAX_SEED = 999_999


def language() -> str:
    return QLocale().name().split("_")[0]


def style_label(name: str) -> str:
    labels = get_style(name).labels
    return labels.get(language(), labels["en"])


def param_label(name: str) -> str:
    return name.replace("_", " ").capitalize()


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
            layout.addRow(param_label(name), widget)

    def _make_field(self, name: str, default: Any) -> QWidget:
        style = self.style_definition
        if name in style.choices:
            combo = QComboBox()
            combo.addItems(list(style.choices[name]))
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
                widget.setCurrentText(str(value))
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
                value = widget.currentText()
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

        self._icons: dict[str, QIcon] = {}
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
            if photo.path in self._icons:
                item.setIcon(self._icons[photo.path])
            else:
                self.icon_requested.emit(photo.path)
            self.list.addItem(item)
            item.setSelected(photo.id in selected)
        count = len(project.photos)
        self.count_label.setText(self.tr("%n photo(s)", "", count))
        self.remove_button.setEnabled(bool(selected))
        self._updating = False

    def set_icon(self, path: str, image: QImage) -> None:
        icon = QIcon(QPixmap.fromImage(image))
        self._icons[path] = icon
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


class LayoutPanel(QWidget):
    error = Signal(str)

    def __init__(self, document: Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
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
        )

    def apply(self) -> None:
        try:
            self.document.relayout(self.settings(), self.seed.value())
        except CollagioError as exc:
            self.error.emit(str(exc))

    def shuffle(self) -> None:
        self.seed.setValue(random.randrange(MAX_SEED + 1))
        self.apply()


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
            self.error.emit(str(exc))

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
        self.color = ColorButton()
        self.color2 = ColorButton()
        self.angle = _spin(0, 360, 15, 0)
        self.apply_button = QPushButton(self.tr("Apply canvas"))

        form = QFormLayout()
        form.addRow(self.tr("Size"), self.preset)
        form.addRow(self.tr("Orientation"), self.orientation)
        form.addRow(self.tr("Width"), self.width_spin)
        form.addRow(self.tr("Height"), self.height_spin)
        form.addRow(self.tr("DPI"), self.dpi)
        form.addRow(self.tr("Background"), self.background_kind)
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

    def _update_enabled(self) -> None:
        gradient = BackgroundKind(self.background_kind.currentData()) is BackgroundKind.GRADIENT
        self.color2.setEnabled(gradient)
        self.angle.setEnabled(gradient)

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
        self.color.set_color(background.color)
        self.color2.set_color(background.color2)
        self.angle.setValue(background.angle)
        self._update_enabled()

    def canvas(self) -> Canvas:
        return Canvas(
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            dpi=self.dpi.value(),
            background=Background(
                kind=BackgroundKind(self.background_kind.currentData()),
                color=self.color.color,
                color2=self.color2.color,
                angle=self.angle.value(),
            ),
        )

    def apply(self) -> None:
        try:
            self.document.set_canvas(self.canvas())
        except CollagioError as exc:
            self.error.emit(str(exc))
