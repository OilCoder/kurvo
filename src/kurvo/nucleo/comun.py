"""Constantes y utilidades compartidas por todo el núcleo."""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

NULO = -999.25

# Estilos de línea: 0 sólida, 1 punteada, 2 raya larga,
# 3 (wx 111, sin equivalente: se dibuja raya-punto-punto), 4 raya-punto.
ESTILOS_LINEA = ("solid", "dot", "dash", "dashdotdot", "dashdot")

_RGB = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.I)


def es_nulo(v: float) -> bool:
    return v == NULO


def a_float(texto, defecto: float = 0.0) -> float:
    """Convierte como wxString::ToDouble: si falla devuelve el defecto."""
    try:
        return float(str(texto).strip())
    except (TypeError, ValueError):
        return defecto


def a_int(texto, defecto: int = 0) -> int:
    try:
        return int(float(str(texto).strip()))
    except (TypeError, ValueError):
        return defecto


def a_bool(texto, defecto: bool = False) -> bool:
    t = str(texto).strip().lower()
    if t in ("1", "true", "yes"):
        return True
    if t in ("0", "false", "no"):
        return False
    return defecto


def texto_bool(v: bool) -> str:
    return "TRUE" if v else "FALSE"


def formato_num(v: float) -> str:
    """Número sin ceros sobrantes."""
    return "%.14g" % v


def parse_color(texto: str, defecto=(0, 0, 0)) -> tuple[int, int, int]:
    m = _RGB.search(texto or "")
    if not m:
        return defecto
    return tuple(max(0, min(255, int(x))) for x in m.groups())


def color_texto(rgb) -> str:
    return "rgb(%d, %d, %d)" % tuple(rgb)


def color_aleatorio(rng: random.Random | None = None) -> str:
    r = rng or random
    return color_texto((r.randrange(256), r.randrange(256), r.randrange(256)))


def leer_lineas(ruta: str | Path) -> list[str]:
    """Lee un archivo de texto detectando la codificación (como wxConvAuto)."""
    datos = Path(ruta).read_bytes()
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return datos.decode(cod).splitlines()
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", errors="replace").splitlines()


def escribir_lineas(ruta: str | Path, lineas: list[str]) -> None:
    Path(ruta).write_text("\r\n".join(lineas) + "\r\n", encoding="utf-8", newline="")


def valor_a_px(v: float, vmin: float, vmax: float, longitud: float, origen: float,
               log: bool = False) -> float:
    """Transformación lineal (o log10) de un valor a píxeles.

    El nulo no recibe trato especial."""
    if log:
        if vmax - vmin == 0.0 or v <= 0.0:
            return origen
        return origen + longitud * ((math.log10(v) - math.log10(vmin))
                                    / (math.log10(vmax) - math.log10(vmin)))
    if vmax - vmin == 0.0:
        return origen
    return (v - vmin) / (vmax - vmin) * longitud + origen


def entre(v: float, a: float, b: float) -> bool:
    """a <= v <= b."""
    return a <= v <= b


class GeneradorUID:
    """Enteros únicos dentro de la sesión."""

    def __init__(self, inicio: int = 1000):
        self._siguiente = inicio
        self._usados: set[int] = set()

    def registrar(self, uid: int) -> int:
        self._usados.add(uid)
        self._siguiente = max(self._siguiente, uid + 1)
        return uid

    def nuevo(self) -> int:
        while self._siguiente in self._usados:
            self._siguiente += 1
        uid = self._siguiente
        self._usados.add(uid)
        self._siguiente += 1
        return uid


UID = GeneradorUID()
