"""Translations: complete, up to date, and actually used by the editor."""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from scripts import translations

from collagio.app import strings
from collagio.app.i18n import LANGUAGES, TRANSLATIONS_DIR, choose_language, install_translators
from collagio.app.main_window import MainWindow
from collagio.render.background import TEXTURES
from collagio.styles import available_styles, get_style

TS_FILES = sorted(TRANSLATIONS_DIR.glob("collagio_*.ts"))


def _messages(ts: Path) -> list[tuple[str, str, ET.Element]]:
    root = ET.parse(ts).getroot()
    return [
        (context.findtext("name") or "", message.findtext("source") or "", message)
        for context in root.iter("context")
        for message in context.iter("message")
    ]


def test_every_language_has_a_translation_file() -> None:
    assert {ts.stem.split("_")[1] for ts in TS_FILES} == set(LANGUAGES) - {"en"}


@pytest.mark.parametrize("ts", TS_FILES, ids=lambda p: p.name)
def test_translations_are_complete(ts: Path) -> None:
    for context, source, message in _messages(ts):
        translation = message.find("translation")
        assert translation is not None
        assert translation.get("type") is None, f"unfinished: {context}: {source!r}"
        texts = [f.text or "" for f in translation.iter("numerusform")] or [translation.text or ""]
        for text in texts:
            assert text.strip(), f"empty: {context}: {source!r}"
            assert text.count("{}") == source.count("{}"), f"placeholders: {source!r}"
            assert ("&" in text) == ("&" in source.replace("&amp;", "&")), f"shortcut: {source!r}"


@pytest.mark.parametrize("ts", TS_FILES, ids=lambda p: p.name)
def test_translation_files_are_up_to_date(ts: Path, tmp_path: Path) -> None:
    """Running lupdate must not find new texts, and the .qm must match the .ts."""
    copy = tmp_path / ts.name
    shutil.copy(ts, copy)
    translations.update([copy])
    assert [(c, s) for c, s, _ in _messages(copy)] == [(c, s) for c, s, _ in _messages(ts)]
    (compiled,) = translations.release([ts], out_dir=tmp_path)
    assert compiled.read_bytes() == ts.with_suffix(".qm").read_bytes(), (
        "run translations.py release"
    )


def test_dynamic_texts_are_listed() -> None:
    listed = strings.listed()
    for name in available_styles():
        style = get_style(name)
        for parameter in style.defaults:
            label = parameter.replace("_", " ").capitalize()
            assert (strings.PARAMETERS, label) in listed
        for values in style.choices.values():
            assert all((strings.CHOICES, value) in listed for value in values)
    assert all((strings.TEXTURES, name.capitalize()) in listed for name in TEXTURES)
    sources = "\n".join(p.read_text() for p in Path("src/collagio").rglob("*.py"))
    labels = set(re.findall(r'label: str = "([^"]+)"', sources))
    labels |= set(re.findall(r'self\._edit\(\s*"([^"]+)"', sources))
    labels |= set(re.findall(r'(?:label|"[A-Z][a-z]+ photo") if .* else "([^"]+)"', sources))
    assert labels
    assert all((strings.COMMANDS, label) in listed for label in labels)


def test_choose_language(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    monkeypatch.setenv("COLLAGIO_LANG", "de_AT")
    assert choose_language(settings) == "de"
    monkeypatch.setenv("COLLAGIO_LANG", "xx")
    settings.setValue("language", "de")
    assert choose_language(settings) == "de"
    settings.setValue("language", "en")
    assert choose_language(settings) == "en"


@pytest.fixture
def german(qapp: QApplication) -> Iterator[None]:
    translators = install_translators(qapp, "de")
    yield
    for translator in translators:
        qapp.removeTranslator(translator)
    install_translators(qapp, "en")


def test_english_installs_nothing(qapp: QApplication) -> None:
    assert install_translators(qapp, "en") == []


def test_window_in_german(german: None, make_window: Callable[[], MainWindow]) -> None:
    window = make_window()
    menus = [action.text() for action in window.menuBar().actions()]
    assert menus == ["&Datei", "&Bearbeiten", "&Ansicht", "&Hilfe"]
    assert window.windowTitle() == "Unbenannt – Collagio"
    assert window.layout_panel.shuffle_button.text() == "Mischen"
    assert strings.command_label("Move photo") == "Foto verschieben"
    assert strings.parameter_label("border_width") == "Randbreite"
    assert strings.texture_label("cork") == "Kork"
    assert window.photo_list.count_label.text() == "0 Fotos"
    assert window.redo_action.text() == "&Wiederholen"
    window.document.add_text("x")
    assert window.undo_action.text() == "&Rückgängig: Text hinzufügen"
    assert strings.export_filter().startswith("PNG-Bild (*.png)")
