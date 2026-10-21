import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# ajustes en un .ini temporal: las pruebas no leen ni escriben los QSettings del usuario
os.environ["KURVO_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="kurvo_ajustes_"), "ajustes.ini")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

CAPTURAS = Path(__file__).resolve().parents[1] / "docs" / "capturas"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def capturas():
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    return CAPTURAS
