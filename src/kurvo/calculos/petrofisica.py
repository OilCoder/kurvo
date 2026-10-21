"""Fórmulas petrofísicas del módulo de análisis de registros: arcillosidad, porosidad y saturación.

Todas operan muestra a muestra sobre arreglos numpy con el nulo −999.25 y lo propagan. Se usan las
formas de libro (arcilla dispersa de Hilchie; Simandoux 1/Rt = x·Sw^n + y·Sw)."""
from __future__ import annotations

import math

import numpy as np

from ..nucleo.comun import NULO

MATRIZ_DENSIDAD = {"Quarts": 2.648, "Calcite": 2.71, "Dolomite": 2.85, "Anhydrite": 2.977,
                   "Sylvite": 1.863, "Halite": 2.032, "Gypsum": 2.351, "Anthracite Coal": 1.355,
                   "Bituminous Coal": 1.173}
MATRIZ_SONICO = {"Sandstones": 55.5, "Limestones": 47.5, "Dolomites": 43.5, "Anhydrite": 50.0,
                 "Salt": 67.0, "Iron": 57.0}


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _recortar(v: np.ndarray, limitar: bool) -> np.ndarray:
    if not limitar:
        return v
    out = v.copy()
    ok = out != NULO
    out[ok] = np.clip(out[ok], 0.0, 1.0)
    return out


def _por_muestra(func, *cols):
    cols = [_arr(c) for c in cols]
    n = len(cols[0])
    return np.array([func(*(c[i] for c in cols)) for i in range(n)], dtype=float)


# ------------------------------------------------------------------- VShale
def vsh_indice(curva, limpio: float = 0.0, arcilla: float = 100.0, limitar: bool = True):
    """VShale desde GR o SP: (x − limpio)/(arcilla − limpio)."""
    c = _arr(curva)
    out = np.full_like(c, NULO)
    if arcilla == limpio:
        return out
    ok = c != NULO
    out[ok] = (c[ok] - limpio) / (arcilla - limpio)
    return _recortar(out, limitar)


def vsh_neutron(phin, phin_arcilla: float = 0.5, limitar: bool = True):
    c = _arr(phin)
    out = np.full_like(c, NULO)
    ok = c != NULO
    out[ok] = c[ok] / phin_arcilla
    return _recortar(out, limitar)


def vsh_neutron_densidad(phin, phid, phin_sh: float = 0.5, phid_sh: float = 0.2, limitar=True):
    if phin_sh == phid_sh:
        raise ValueError("Neutron and density porosity of shale formation cannot be the same!")
    a, b = _arr(phin), _arr(phid)
    out = np.full_like(a, NULO)
    ok = (a != NULO) & (b != NULO)
    out[ok] = (a[ok] - b[ok]) / (phin_sh - phid_sh)
    return _recortar(out, limitar)


# ---------------------------------------------------------------- porosidad
def porosidad_densidad(rhob, rho_matriz: float = 2.648, rho_fluido: float = 1.0):
    c = _arr(rhob)
    out = np.full_like(c, NULO)
    if rho_matriz == rho_fluido:
        return out
    ok = c != NULO
    out[ok] = (rho_matriz - c[ok]) / (rho_matriz - rho_fluido)
    return out


def porosidad_sonico(dt, dt_matriz: float = 55.0, dt_fluido: float = 189.0):
    c = _arr(dt)
    out = np.full_like(c, NULO)
    if dt_matriz == dt_fluido:
        return out
    ok = c != NULO
    out[ok] = (c[ok] - dt_matriz) / (dt_fluido - dt_matriz)
    return out


# ----------------------------------------------------------------- Sw
def sw_archie_valor(phi, rt, a=1.0, m=2.0, n=2.0, rw=0.1) -> float:
    if NULO in (phi, rt, a, m, n, rw) or rt == 0.0 or phi == 0.0:
        return NULO
    try:
        return (a * rw / (rt * phi ** m)) ** (1.0 / n)
    except (ZeroDivisionError, ValueError, OverflowError):
        return NULO


def sw_archie(phi, rt, a=1.0, m=2.0, n=2.0, rw=0.1, limitar=True):
    return _recortar(_por_muestra(lambda p, r: sw_archie_valor(p, r, a, m, n, rw), phi, rt), limitar)


def _simandoux_valor(phi, rt, vsh, a, m, n, rw, rsh, modificado) -> float:
    if NULO in (a, m, n, rw, rsh, rt, phi, vsh) or rt == 0 or a == 0 or rw == 0 or rsh == 0:
        return NULO
    try:
        x = phi ** m / (a * rw)
        if modificado:
            x = x / (1.0 - vsh)
        y = vsh / rsh
        if n == 2.0:
            return (math.sqrt(y * y + 4.0 * x / rt) - y) / (x + x)
        inv_rt = 1.0 / rt

        def f(s):                       # 1/Rt = x·Sw^n + y·Sw, resuelta por Newton
            return abs(inv_rt - x * s ** n - y * s) / inv_rt

        s = 1.0
        fd = (f(1.01) - f(0.99)) / 0.02
        fv = f(1.0)
        it = 0
        while fv > 0.001 and it <= 0x31:
            s = s - fv / fd
            fd = (f(s + 0.01) - f(s - 0.01)) / 0.02
            fv = f(s)
            it += 1
        return s
    except (ZeroDivisionError, ValueError, OverflowError):
        return NULO


def sw_simandoux(phi, rt, vsh, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=1.0, limitar=True,
                 modificado=False):
    v = _por_muestra(lambda p, r, s: _simandoux_valor(p, r, s, a, m, n, rw, rsh, modificado),
                     phi, rt, vsh)
    return _recortar(v, limitar)


def _indonesia_valor(phi, rt, vsh, a, m, n, rw, rsh, modificado) -> float:
    if NULO in (a, m, n, rw, rsh, rt, phi, vsh) or rt == 0 or a == 0 or rw == 0 or rsh == 0:
        return NULO
    try:
        exp_v = (1.0 - vsh) * 0.5 if modificado else 1.0 - 0.5 * vsh
        den = vsh ** exp_v / math.sqrt(rsh) + math.sqrt(phi ** m / (a * rw))
        return ((1.0 / math.sqrt(rt)) / den) ** (2.0 / n)
    except (ZeroDivisionError, ValueError, OverflowError):
        return NULO


def sw_indonesia(phi, rt, vsh, a=1.0, m=2.0, n=2.0, rw=0.1, rsh=1.0, limitar=True,
                 modificado=False):
    v = _por_muestra(lambda p, r, s: _indonesia_valor(p, r, s, a, m, n, rw, rsh, modificado),
                     phi, rt, vsh)
    return _recortar(v, limitar)


def _arcilla_dispersa_valor(phid, phis, rt, rw) -> float:
    if NULO in (phid, phis, rt) or phis == 0 or rt == 0:
        return NULO
    q = (phis - phid) / phis
    if 1.0 - q <= 0.0:
        return NULO
    t = 0.8 * rw / (phis * phis * rt)
    return (math.sqrt(t + (q / 2) ** 2) - q / 2) / (1.0 - q)  # Hilchie


def sw_arcilla_dispersa(phid, phis, rt, rw=0.1, limitar=True):
    if rw <= 0:
        raise ValueError("Water resistivity should be more than 0!")
    v = _por_muestra(lambda a, b, c: _arcilla_dispersa_valor(a, b, c, rw), phid, phis, rt)
    return _recortar(v, limitar)
