"""Project files (*.collagio): JSON with a schema version.

Photo paths are stored relative to the project file where possible, with
forward slashes, so a project folder can be moved or shared between Windows
and Linux.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from collagio.core.model import (
    SCHEMA_VERSION,
    Background,
    BackgroundKind,
    Canvas,
    CropBox,
    LayoutMode,
    LayoutSettings,
    PhotoItem,
    PlacementOrder,
    Project,
    Rect,
    Shadow,
    StyleRef,
    TextItem,
)
from collagio.errors import ProjectFormatError

PROJECT_SUFFIX = ".collagio"
LEGACY_SUFFIXES = (".collagio.json",)  # used before 0.1; still opened and saved in place


def is_project_file(path: str | Path) -> bool:
    name = str(path).lower()
    return name.endswith(PROJECT_SUFFIX) or name.endswith(LEGACY_SUFFIXES)


# Upgrades a document from version N to N + 1, keyed by N.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    # 2 added text items and texture/photo backgrounds; all optional with defaults.
    1: lambda document: document,
}


def _portable_path(path: str, base_dir: Path | None) -> str:
    candidate = Path(path)
    if base_dir is not None and candidate.is_absolute():
        with contextlib.suppress(ValueError):  # ValueError: different drive on Windows
            candidate = Path(os.path.relpath(candidate, base_dir))
    return candidate.as_posix()


def _resolve_path(stored: str, base_dir: Path | None) -> str:
    candidate = Path(stored)
    if base_dir is not None and not candidate.is_absolute():
        return os.path.normpath(base_dir / candidate)
    return str(candidate)


def _style_to_dict(style: StyleRef) -> dict[str, Any]:
    return {"name": style.name, "params": dict(style.params)}


def _style_from_dict(data: dict[str, Any]) -> StyleRef:
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise TypeError("style params must be an object")
    return StyleRef(name=str(data["name"]), params=dict(params))


def _box(values: Any) -> tuple[float, float, float, float]:
    if not isinstance(values, list) or len(values) != 4:
        raise TypeError(f"expected a list of 4 numbers, got {values!r}")
    x, y, w, h = (float(v) for v in values)
    return x, y, w, h


def project_to_dict(project: Project, base_dir: Path | None = None) -> dict[str, Any]:
    bg = project.canvas.background
    return {
        "app": "collagio",
        "schema_version": SCHEMA_VERSION,
        "seed": project.seed,
        "layout_edited": project.layout_edited,
        "canvas": {
            "width": project.canvas.width,
            "height": project.canvas.height,
            "dpi": project.canvas.dpi,
            "background": {
                "kind": bg.kind.value,
                "color": bg.color,
                "color2": bg.color2,
                "angle": bg.angle,
                "texture": bg.texture,
                "photo": _portable_path(bg.photo, base_dir) if bg.photo else "",
                "blur": bg.blur,
                "dim": bg.dim,
            },
        },
        "layout": {
            "mode": project.layout.mode.value,
            "gap": project.layout.gap,
            "margin": project.layout.margin,
            "size_variation": project.layout.size_variation,
            "order": project.layout.order.value,
            "max_rotation": project.layout.max_rotation,
            "overlap": project.layout.overlap,
            "min_visible": project.layout.min_visible,
            "space_top": project.layout.space_top,
            "space_bottom": project.layout.space_bottom,
        },
        "shadow": {
            "opacity": project.shadow.opacity,
            "blur": project.shadow.blur,
            "offset_x": project.shadow.offset_x,
            "offset_y": project.shadow.offset_y,
            "color": project.shadow.color,
        },
        "default_style": _style_to_dict(project.default_style),
        "texts": [
            {
                "id": text.id,
                "text": text.text,
                "x": text.x,
                "y": text.y,
                "size": text.size,
                "color": text.color,
                "rotation": text.rotation,
                "font": _portable_path(text.font, base_dir) if text.font else "",
                "shadow": text.shadow,
            }
            for text in project.texts
        ],
        "photos": [
            {
                "id": item.id,
                "path": _portable_path(item.path, base_dir),
                "rect": None
                if item.rect is None
                else [item.rect.x, item.rect.y, item.rect.width, item.rect.height],
                "rotation": item.rotation,
                "crop": None
                if item.crop is None
                else [item.crop.x, item.crop.y, item.crop.width, item.crop.height],
                "style": None if item.style is None else _style_to_dict(item.style),
                "z": item.z,
            }
            for item in project.photos
        ],
    }


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    version = data.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ProjectFormatError(f"invalid schema_version {version!r}")
    if version > SCHEMA_VERSION:
        raise ProjectFormatError(
            f"project was saved by a newer Collagio (schema {version}, supported {SCHEMA_VERSION})"
        )
    while version < SCHEMA_VERSION:
        data = MIGRATIONS[version](data)
        version += 1
        data["schema_version"] = version
    return data


def _photo_from_dict(data: dict[str, Any], base_dir: Path | None) -> PhotoItem:
    rect = None if data.get("rect") is None else Rect(*_box(data["rect"]))
    crop = None if data.get("crop") is None else CropBox(*_box(data["crop"]))
    style = None if data.get("style") is None else _style_from_dict(data["style"])
    return PhotoItem(
        id=str(data["id"]),
        path=_resolve_path(str(data["path"]), base_dir),
        rect=rect,
        rotation=float(data.get("rotation", 0.0)),
        crop=crop,
        style=style,
        z=int(data.get("z", 0)),
    )


def _text_from_dict(data: dict[str, Any], base_dir: Path | None) -> TextItem:
    defaults = TextItem("", "", 0.0, 0.0)
    font = str(data.get("font", ""))
    return TextItem(
        id=str(data["id"]),
        text=str(data["text"]),
        x=float(data["x"]),
        y=float(data["y"]),
        size=float(data.get("size", defaults.size)),
        color=str(data.get("color", defaults.color)),
        rotation=float(data.get("rotation", defaults.rotation)),
        font=_resolve_path(font, base_dir) if font else "",
        shadow=bool(data.get("shadow", False)),
    )


def project_from_dict(data: Any, base_dir: Path | None = None) -> Project:
    if not isinstance(data, dict) or data.get("app") != "collagio":
        raise ProjectFormatError("not a Collagio project file")
    data = _migrate(dict(data))
    try:
        canvas_data = data["canvas"]
        bg_data = canvas_data.get("background", {})
        defaults = Background()
        background = Background(
            kind=BackgroundKind(bg_data.get("kind", defaults.kind)),
            color=str(bg_data.get("color", defaults.color)),
            color2=str(bg_data.get("color2", defaults.color2)),
            angle=float(bg_data.get("angle", defaults.angle)),
            texture=str(bg_data.get("texture", defaults.texture)),
            photo=_resolve_path(str(bg_data["photo"]), base_dir) if bg_data.get("photo") else "",
            blur=float(bg_data.get("blur", defaults.blur)),
            dim=float(bg_data.get("dim", defaults.dim)),
        )
        canvas = Canvas(
            width=int(canvas_data["width"]),
            height=int(canvas_data["height"]),
            dpi=int(canvas_data.get("dpi", 300)),
            background=background,
        )
        layout_data = data.get("layout", {})
        layout_defaults = LayoutSettings()
        layout = LayoutSettings(
            mode=LayoutMode(layout_data.get("mode", layout_defaults.mode)),
            gap=float(layout_data.get("gap", layout_defaults.gap)),
            margin=float(layout_data.get("margin", layout_defaults.margin)),
            size_variation=float(layout_data.get("size_variation", layout_defaults.size_variation)),
            order=PlacementOrder(layout_data.get("order", layout_defaults.order)),
            max_rotation=float(layout_data.get("max_rotation", layout_defaults.max_rotation)),
            overlap=float(layout_data.get("overlap", layout_defaults.overlap)),
            min_visible=float(layout_data.get("min_visible", layout_defaults.min_visible)),
            space_top=float(layout_data.get("space_top", layout_defaults.space_top)),
            space_bottom=float(layout_data.get("space_bottom", layout_defaults.space_bottom)),
        )
        shadow_data = data.get("shadow", {})
        shadow_defaults = Shadow()
        shadow = Shadow(
            opacity=float(shadow_data.get("opacity", shadow_defaults.opacity)),
            blur=float(shadow_data.get("blur", shadow_defaults.blur)),
            offset_x=float(shadow_data.get("offset_x", shadow_defaults.offset_x)),
            offset_y=float(shadow_data.get("offset_y", shadow_defaults.offset_y)),
            color=str(shadow_data.get("color", shadow_defaults.color)),
        )
        default_style = (
            _style_from_dict(data["default_style"]) if "default_style" in data else StyleRef()
        )
        photos = [_photo_from_dict(p, base_dir) for p in data.get("photos", [])]
        texts = [_text_from_dict(t, base_dir) for t in data.get("texts", [])]
        return Project(
            canvas=canvas,
            photos=photos,
            layout=layout,
            default_style=default_style,
            shadow=shadow,
            texts=texts,
            seed=int(data.get("seed", 0)),
            # Unknown in files from 0.1.0: assume edits, so nothing is replaced unasked.
            layout_edited=bool(data.get("layout_edited", True)),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProjectFormatError(f"invalid project file: {exc!r}") from exc


def save_project(project: Project, path: Path) -> None:
    document = project_to_dict(project, base_dir=path.resolve().parent)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def load_project(path: Path) -> Project:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(f"{path}: not valid JSON ({exc})") from exc
    return project_from_dict(data, base_dir=path.resolve().parent)
