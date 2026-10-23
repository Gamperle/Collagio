from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from collagio.core import serialize
from collagio.core.model import (
    SCHEMA_VERSION,
    Background,
    BackgroundKind,
    Canvas,
    CropBox,
    LayoutSettings,
    PhotoItem,
    Project,
    Rect,
    StyleRef,
)
from collagio.core.serialize import (
    load_project,
    project_from_dict,
    project_to_dict,
    save_project,
)
from collagio.errors import ProjectFormatError


def _project(photo_dir: Path) -> Project:
    return Project(
        canvas=Canvas(
            2480,
            3508,
            dpi=300,
            background=Background(BackgroundKind.GRADIENT, "#112233", "#ddeeff", 45.0),
        ),
        photos=[
            PhotoItem(id="p001", path=str(photo_dir / "a.jpg"), rect=Rect(10, 20, 300, 200)),
            PhotoItem(
                id="p002",
                path=str(photo_dir / "sub" / "b.png"),
                rect=Rect(320.5, 20, 100, 150.25),
                rotation=-7.5,
                crop=CropBox(0.1, 0.0, 0.8, 1.0),
                style=StyleRef("plain", {"border_width": 12, "border_color": "#fff"}),
                z=3,
            ),
            PhotoItem(id="p003", path=str(photo_dir / "c.webp")),
        ],
        layout=LayoutSettings(gap=0.015, margin=0.03, size_variation=0.8),
        default_style=StyleRef("plain", {"corner_radius": 4}),
        seed=1234,
    )


def test_dict_round_trip_without_base_dir(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert project_from_dict(project_to_dict(project)) == project


def test_dict_is_json_serialisable(tmp_path: Path) -> None:
    document = project_to_dict(_project(tmp_path))
    assert json.loads(json.dumps(document)) == document
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["app"] == "collagio"


def test_file_round_trip(tmp_path: Path) -> None:
    project = _project(tmp_path / "photos")
    path = tmp_path / "my.collagio.json"
    save_project(project, path)
    assert load_project(path) == project


def test_paths_are_stored_relative_with_forward_slashes(tmp_path: Path) -> None:
    project = _project(tmp_path / "photos")
    path = tmp_path / "my.collagio.json"
    save_project(project, path)
    stored = [p["path"] for p in json.loads(path.read_text())["photos"]]
    assert stored == ["photos/a.jpg", "photos/sub/b.png", "photos/c.webp"]


def test_moving_the_project_folder_keeps_photos_resolvable(tmp_path: Path) -> None:
    original = tmp_path / "old"
    original.mkdir()
    project = _project(original / "photos")
    save_project(project, original / "p.collagio.json")
    moved = tmp_path / "new"
    original.rename(moved)
    loaded = load_project(moved / "p.collagio.json")
    assert loaded.photos[0].path == str(moved / "photos" / "a.jpg")


def test_relative_paths_without_base_dir_are_kept() -> None:
    project = Project(canvas=Canvas(10, 10), photos=[PhotoItem(id="a", path="x/y.jpg")])
    assert project_to_dict(project)["photos"][0]["path"] == "x/y.jpg"


def test_unrelatable_path_stays_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object) -> str:
        raise ValueError("path is on mount 'C:', start on mount 'D:'")

    monkeypatch.setattr(serialize.os.path, "relpath", fail)
    project = Project(canvas=Canvas(10, 10), photos=[PhotoItem(id="a", path=str(tmp_path / "a"))])
    stored = project_to_dict(project, base_dir=Path("/elsewhere"))["photos"][0]["path"]
    assert stored == (tmp_path / "a").as_posix()


def test_missing_optional_fields_get_defaults() -> None:
    document = {
        "app": "collagio",
        "schema_version": 1,
        "canvas": {"width": 100, "height": 50},
        "photos": [{"id": "a", "path": "a.jpg"}],
    }
    project = project_from_dict(document)
    assert project.canvas.dpi == 300
    assert project.canvas.background == Background()
    assert project.layout == LayoutSettings()
    assert project.default_style == StyleRef()
    assert project.photos == [PhotoItem(id="a", path="a.jpg")]
    assert project.seed == 0


def _valid() -> dict[str, Any]:
    return project_to_dict(Project(canvas=Canvas(10, 10), photos=[PhotoItem("a", "a.jpg")]))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(app="other"), "not a Collagio project"),
        (lambda d: d.update(schema_version=SCHEMA_VERSION + 1), "newer Collagio"),
        (lambda d: d.update(schema_version=0), "invalid schema_version"),
        (lambda d: d.update(schema_version="1"), "invalid schema_version"),
        (lambda d: d.pop("canvas"), "invalid project file"),
        (lambda d: d["canvas"].update(width="wide"), "invalid project file"),
        (lambda d: d["layout"].update(mode="spiral"), "invalid project file"),
        (lambda d: d["photos"][0].update(rect=[1, 2, 3]), "invalid project file"),
        (lambda d: d["photos"][0].update(crop="all"), "invalid project file"),
        (lambda d: d["photos"][0].pop("id"), "invalid project file"),
        (lambda d: d["photos"].append("not an object"), "invalid project file"),
        (lambda d: d["default_style"].update(params=[1]), "invalid project file"),
    ],
)
def test_invalid_documents_are_rejected(mutate: Any, message: str) -> None:
    document = _valid()
    mutate(document)
    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict(document)


def test_non_object_document_is_rejected() -> None:
    with pytest.raises(ProjectFormatError, match="not a Collagio project"):
        project_from_dict([1, 2, 3])


def test_invalid_json_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.collagio.json"
    path.write_text("{ nope", encoding="utf-8")
    with pytest.raises(ProjectFormatError, match="not valid JSON"):
        load_project(path)


def test_migrations_run_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a future schema 3 reading a schema 1 document."""
    calls: list[int] = []

    def to_2(doc: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        doc["canvas"]["width"] = 111
        return doc

    def to_3(doc: dict[str, Any]) -> dict[str, Any]:
        calls.append(2)
        return doc

    monkeypatch.setattr(serialize, "SCHEMA_VERSION", 3)
    monkeypatch.setattr(serialize, "MIGRATIONS", {1: to_2, 2: to_3})
    document = _valid()
    document["schema_version"] = 1
    project = project_from_dict(document)
    assert calls == [1, 2]
    assert project.canvas.width == 111
