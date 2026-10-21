"""Trayectoria del pozo: estaciones MD/inclinación/azimut y cálculo de TVD, norte, este y TVDSS
(método de mínima curvatura)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .comun import NULO, a_float, escribir_lineas, formato_num, leer_lineas

PI = 3.14159265358979


def _rad(g: float) -> float:
    return g / 180.0 * PI


@dataclass
class Estacion:
    md: float
    tvd: float = NULO
    azim: float = 0.0
    inc: float = NULO
    hd: float = 0.0
    norte: float = 0.0
    este: float = 0.0
    tvdss: float = 0.0


def calc_theta(i1: float, i2: float, a1: float, a2: float) -> float:
    """Dogleg en grados."""
    x = math.cos(_rad(i2 - i1)) - math.sin(_rad(i1)) * math.sin(_rad(i2)) * (1 - math.cos(_rad(a2 - a1)))
    x = max(-1.0, min(1.0, x))
    return math.acos(x) * 180.0 / PI


def calc_rf(theta: float) -> float:
    if theta == 0.0:
        return 0.0
    return 2.0 / _rad(theta) * math.tan(_rad(theta) / 2.0)


def calc_dtvd(md1, md2, i1, i2, a1, a2) -> float:
    t = calc_theta(i1, i2, a1, a2)
    if t == 0.0:
        return md2 - md1
    return (md2 - md1) * 0.5 * (math.cos(_rad(i1)) + math.cos(_rad(i2))) * calc_rf(t)


def calc_dnorte(md1, md2, i1, i2, a1, a2) -> float:
    t = calc_theta(i1, i2, a1, a2)
    if t == 0.0:
        return 0.0          # comportamiento fiel: sin límite RF→1
    return ((md2 - md1) * 0.5 * (math.sin(_rad(i1)) * math.cos(_rad(a1))
                                  + math.sin(_rad(i2)) * math.cos(_rad(a2))) * calc_rf(t))


def calc_deste(md1, md2, i1, i2, a1, a2) -> float:
    t = calc_theta(i1, i2, a1, a2)
    if t == 0.0:
        return 0.0
    return ((md2 - md1) * 0.5 * (math.sin(_rad(i1)) * math.sin(_rad(a1))
                                  + math.sin(_rad(i2)) * math.sin(_rad(a2))) * calc_rf(t))


def calc_xinc1(md1, md2, tvd1, tvd2, i1, a1, a2, tol: float = 0.0001) -> float:
    """CalcXInc1: inclinación de la estación 2 que reproduce el ΔTVD dado.

    El pseudocódigo pierde parte del cálculo x87; se resuelve la misma ecuación
    (ΔTVD de curvatura mínima = tvd2 − tvd1) por bisección con la tolerancia original."""
    objetivo = tvd2 - tvd1
    if calc_dtvd(md1, md2, i1, 0.0, a1, a2) <= objetivo:
        return 0.0
    lo, hi = 0.0, 180.0
    for _ in range(1000):
        mid = (lo + hi) / 2
        if calc_dtvd(md1, md2, i1, mid, a1, a2) > objetivo:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


@dataclass
class Trayectoria:
    estaciones: list[Estacion] = field(default_factory=list)
    tvd_a_ss: float = 0.0

    # ------------------------------------------------------------------ cálculo
    def calcular(self) -> None:
        """Completa TVD, norte, este, desplazamiento y TVDSS de las estaciones que no los tienen."""
        for i, e in enumerate(self.estaciones):
            if i == 0:
                if e.tvd == NULO:
                    e.tvd = e.md
                if e.inc == NULO:
                    e.inc = 0.0
                e.norte = e.este = e.hd = 0.0
            else:
                p = self.estaciones[i - 1]
                if e.tvd == NULO:
                    e.tvd = calc_dtvd(p.md, e.md, p.inc, e.inc, p.azim, e.azim) + p.tvd
                if e.inc == NULO:
                    e.inc = calc_xinc1(p.md, e.md, p.tvd, e.tvd, p.inc, p.azim, e.azim)
                e.este = calc_deste(p.md, e.md, p.inc, e.inc, p.azim, e.azim) + p.este
                e.norte = calc_dnorte(p.md, e.md, p.inc, e.inc, p.azim, e.azim) + p.norte
                e.hd = math.hypot(e.norte, e.este)
            e.tvdss = e.tvd - self.tvd_a_ss

    def tvd_en(self, md: float) -> float:
        """TVD a una MD: interpolación lineal con extrapolación por el primer/último tramo."""
        return self._interpolar(md, "md", "tvd")

    def md_en(self, tvd: float) -> float:
        """MD a una TVD (la inversa de tvd_en)."""
        return self._interpolar(tvd, "tvd", "md")

    def _interpolar(self, x: float, ax: str, ay: str) -> float:
        est = self.estaciones
        if len(est) < 2:
            return NULO          # sin tramo para interpolar
        xs = [getattr(e, ax) for e in est]
        ys = [getattr(e, ay) for e in est]
        if x <= xs[0]:
            i = 0
        elif x > xs[-1]:
            i = len(est) - 2
        else:
            i = next(k for k in range(len(est) - 1) if xs[k] < x <= xs[k + 1])
        x0, x1, y0, y1 = xs[i], xs[i + 1], ys[i], ys[i + 1]
        if x1 - x0 == 0.0:
            return NULO
        return (x - x0) / (x1 - x0) * (y1 - y0) + y0

    # ------------------------------------------------------------------ archivo
    @classmethod
    def desde_lineas(cls, lineas: list[str]) -> "Trayectoria":
        t = cls()
        modo_tvd = False
        for linea in lineas:
            s = linea.strip()
            if not s:
                continue
            if s.upper().startswith("#TVD_TO_SS"):
                t.tvd_a_ss = a_float(s[len("#TVD_TO_SS"):], 0.0)
                continue
            if s.startswith("#"):
                cab = s[1:].upper().split()
                modo_tvd = len(cab) >= 2 and cab[1] == "TVD"
                continue
            v = [a_float(x, NULO) for x in s.replace(",", " ").split()]
            if not v:
                continue
            if modo_tvd:
                t.estaciones.append(Estacion(md=v[0], tvd=v[1] if len(v) > 1 else NULO))
            else:
                t.estaciones.append(Estacion(md=v[0], inc=v[1] if len(v) > 1 else 0.0,
                                             azim=v[2] if len(v) > 2 else 0.0))
        t.calcular()
        return t

    @classmethod
    def abrir(cls, ruta: str | Path) -> "Trayectoria":
        return cls.desde_lineas(leer_lineas(ruta))

    def lineas(self) -> list[str]:
        out = ["#TVD_TO_SS " + formato_num(self.tvd_a_ss), "#MD INC AZIM"]
        for e in self.estaciones:
            out.append("\t".join(formato_num(x) for x in (e.md, e.inc, e.azim)))
        return out

    def guardar(self, ruta: str | Path) -> None:
        escribir_lineas(ruta, self.lineas())
