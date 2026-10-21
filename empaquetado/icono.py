"""Genera empaquetado/kurvo.ico con el icono propio de la aplicación (dibujado por código en
vista/iconos.py), en 16, 24, 32, 48, 64, 128 y 256 px."""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

TAMANOS = (16, 24, 32, 48, 64, 128, 256)


def png(lado: int) -> bytes:
    from kurvo.vista import iconos
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    iconos.pixmap("app", lado).save(buf, "PNG")
    return bytes(buf.data())


def ico(destino: Path) -> Path:
    """ICO con imágenes PNG embebidas (formato válido desde Windows Vista)."""
    imagenes = [png(t) for t in TAMANOS]
    cabecera = struct.pack("<HHH", 0, 1, len(imagenes))
    entradas, datos = b"", b""
    desplaz = 6 + 16 * len(imagenes)
    for t, im in zip(TAMANOS, imagenes):
        entradas += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(im), desplaz + len(datos))
        datos += im
    destino.write_bytes(cabecera + entradas + datos)
    return destino


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    print(ico(Path(__file__).with_name("kurvo.ico")))
