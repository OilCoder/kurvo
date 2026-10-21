"""Cálculos de Pickett, Hingle, histograma y desfase en profundidad."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..nucleo.comun import NULO, a_bool, a_float, formato_num, texto_bool

PHI_PICKETT = (0.01, 1.0)
PHI_HINGLE_FIN = 0.46


def linea_pickett(sw: float, a: float, m: float, n: float, rw: float):
    """Dos puntos (Rt, φ) de la línea de Sw: Rt = a·Rw/(φ^m·Sw^n)."""
    pts = []
    for phi in PHI_PICKETT:
        log_rt = math.log10(a * rw) - m * math.log10(phi) + math.log10(1.0 / sw ** n)
        pts.append((10 ** log_rt, phi))
    return pts


def pendiente_hingle(sw: float, a: float, m: float, n: float, rw: float) -> float:
    return (sw ** n / (a * rw)) ** (1.0 / m)


def linea_hingle(sw, a, m, n, rw):
    k = pendiente_hingle(sw, a, m, n, rw)
    return [(0.0, 0.0), (PHI_HINGLE_FIN, PHI_HINGLE_FIN * k)]


def y_hingle(rt, m: float):
    rt = np.asarray(rt, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.power(rt, -1.0 / m)


def sw_archie_recortada(phi, rt, a, m, n, rw):
    """Sw para el gráfico Sw vs profundidad de Pickett/Hingle (sin trato del nulo, recortada)."""
    phi = np.asarray(phi, dtype=float)
    rt = np.asarray(rt, dtype=float)
    with np.errstate(all="ignore"):
        sw = np.power(a * rw / (phi ** m * rt), 1.0 / n)
    return np.clip(np.nan_to_num(sw, nan=0.0), 0.0, 1.0)


# --------------------------------------------------------------- análisis
@dataclass
class ConjuntoDatos:
    nombre: str
    uid_pozo: int = 0
    uid_las: int = 0
    pozo: str = ""
    las: str = ""
    col_phi: str = ""
    col_rt: str = ""
    tope: float = 0.0
    base: float = 0.0
    visible: bool = True
    prof: list[float] = field(default_factory=list)
    phi: list[float] = field(default_factory=list)
    rt: list[float] = field(default_factory=list)


@dataclass
class AnalisisSw:
    """Contenido de un archivo .Pickett / .Hingle."""
    a: float = 1.0
    m: float = 2.0
    n: float = 2.0
    rw: float = 0.1
    sw: list[float] = field(default_factory=lambda: [round(0.1 * i, 1) for i in range(1, 11)])
    sw_visible: list[bool] = field(default_factory=lambda: [True] * 10)
    conjuntos: list[ConjuntoDatos] = field(default_factory=list)

    @classmethod
    def desde_texto(cls, texto: str) -> "AnalisisSw":
        an = cls(sw=[], sw_visible=[])
        actual = None
        for i, linea in enumerate(texto.splitlines()):
            s = linea.strip()
            if not s:
                continue
            if i == 0 and not s.startswith("DATA"):
                v = [a_float(x) for x in s.split(";")]
                an.a, an.m, an.n, an.rw = (v + [1, 2, 2, 0.1])[:4]
                continue
            c = s.split("|")
            if c[0] == "DATASW":
                an.sw = [a_float(x) for x in c[1:]]
            elif c[0] == "DATASWX":
                an.sw_visible = [a_bool(x, True) for x in c[1:]]
            elif c[0] == "DATA":
                c += [""] * (11 - len(c))
                actual = ConjuntoDatos(c[1], int(a_float(c[2])), int(a_float(c[3])), c[4], c[5],
                                       c[6], c[7], a_float(c[8]), a_float(c[9]), a_bool(c[10], True))
                an.conjuntos.append(actual)
            elif actual is not None:
                v = [x.strip() for x in s.split(";")]
                actual.prof.append(a_float(v[0], NULO))
                actual.phi.append(a_float(v[1], NULO) if len(v) > 1 else NULO)
                actual.rt.append(a_float(v[2], NULO) if len(v) > 2 and v[2] else NULO)
        an.sw_visible += [True] * (len(an.sw) - len(an.sw_visible))
        return an

    def a_texto(self) -> str:
        n = formato_num
        out = [f"{n(self.a)}; {n(self.m)}; {n(self.n)}; {n(self.rw)}",
               "DATASW" + "".join("|" + n(x) for x in self.sw),
               "DATASWX" + "".join("|" + texto_bool(x) for x in self.sw_visible)]
        for c in self.conjuntos:
            out.append("|".join(["DATA", c.nombre, str(c.uid_pozo), str(c.uid_las), c.pozo, c.las,
                                 c.col_phi, c.col_rt, n(c.tope), n(c.base), texto_bool(c.visible)]))
            out += [f"{n(p)}; {n(f)}; {n(r)}" for p, f, r in zip(c.prof, c.phi, c.rt)]
        return "\n".join(out)

    def agregar_sw(self, sw: float) -> None:
        if not (0 < sw <= 1):
            raise ValueError("Sw must be more than 0 and less or equal to 1.")
        if sw in self.sw:
            raise ValueError("Sw value already exists in the list.")
        self.sw.append(sw)
        self.sw_visible.append(True)


# --------------------------------------------------------------- QuickPlot
def histograma(valores, nbins: int = 20):
    """Histogram plot: bins sobre [min·0.999, max·1.001], % = conteo·100 // N (N incluye nulos)."""
    v = np.asarray(valores, dtype=float)
    validos = v[v != NULO]
    if validos.size == 0:
        return np.zeros(0), np.zeros(0, dtype=int), (0.0, 0.0)
    xmax = validos.max() * 1.001
    xmin = validos.min() * 0.999
    ancho = (xmax - xmin) / nbins
    bordes = [xmin + k * ancho for k in range(nbins)]
    conteos = np.zeros(nbins, dtype=int)
    for x in validos:
        for k, lo in enumerate(bordes):
            if lo <= x < lo + ancho:
                conteos[k] += 1
                break
    pct = (conteos * 100) // len(v)
    centros = np.array([lo + ancho / 2 for lo in bordes])
    return centros, pct, (xmin, xmax)


# --------------------------------------------------------------- DepthShift
def desplazar(columna, desplazamiento: float):
    c = np.asarray(columna, dtype=float)
    out = c.copy()
    ok = c != NULO
    out[ok] = c[ok] + desplazamiento
    return out
