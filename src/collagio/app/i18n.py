"""Loading the interface translations.

The language comes from the COLLAGIO_LANG environment variable, the "language"
setting (View > Language) or the system locale, in that order.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QSettings, QTranslator

LANGUAGES = {"en": "English", "de": "Deutsch"}
TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "i18n"


def choose_language(settings: QSettings) -> str:
    for candidate in (
        os.environ.get("COLLAGIO_LANG", ""),
        str(settings.value("language", "")),
        QLocale.system().name(),
    ):
        code = candidate.split("_")[0].lower()
        if code in LANGUAGES:
            return code
    return "en"


def install_translators(app: QCoreApplication, language: str) -> list[QTranslator]:
    """Load Collagio's and Qt's translations; keep the returned objects alive."""
    QLocale.setDefault(QLocale(language))
    if language == "en":
        return []
    installed = []
    sources = (
        (f"collagio_{language}", str(TRANSLATIONS_DIR)),
        (f"qtbase_{language}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
    )
    for name, directory in sources:
        translator = QTranslator(app)
        if translator.load(name, directory):
            app.installTranslator(translator)
            installed.append(translator)
    return installed
