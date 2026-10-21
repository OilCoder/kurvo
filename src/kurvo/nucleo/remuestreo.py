"""Remuestreo de un registro a paso constante (mantenimiento, prioridad 3)."""
from __future__ import annotations

import math

import numpy as np

from .comun import NULO
from .historial import remuestrear_a
from .validacion import paso_regular


def _validos(d):
    return (d != NULO) & np.isfinite(d)


def malla(inicio: float, fin: float, paso: float, alinear: bool = True) -> np.ndarray:
    """Profundidades inicio..fin con paso constante. `alinear` las lleva a múltiplos del paso."""
    if paso <= 0:
        raise ValueError("Step must be greater than zero.")
    if fin < inicio:
        inicio, fin = fin, inicio
    if alinear:
        inicio = math.ceil(round(inicio / paso, 9)) * paso
    n = int(math.floor(round((fin - inicio) / paso, 9))) + 1
    return np.round(inicio + paso * np.arange(max(n, 0)), 10)


def promedio_bloques(prof, valores, destino, paso) -> np.ndarray:
    """Media de las muestras válidas en [z − paso/2, z + paso/2) (para pasar a un paso mayor)."""
    p = np.asarray(prof, float)
    v = np.asarray(valores, float)
    ok = _validos(p) & _validos(v)
    p, v = p[ok], v[ok]
    orden = np.argsort(p)
    p, v = p[orden], v[orden]
    acum = np.concatenate(([0.0], np.cumsum(v)))
    out = np.full(len(destino), NULO)
    a = np.searchsorted(p, np.asarray(destino) - paso / 2, side="left")
    b = np.searchsorted(p, np.asarray(destino) + paso / 2, side="left")
    n = b - a
    sel = n > 0
    out[sel] = (acum[b[sel]] - acum[a[sel]]) / n[sel]
    return out


def mas_cercano(prof, valores, destino, tolerancia: float) -> np.ndarray:
    p = np.asarray(prof, float)
    v = np.asarray(valores, float)
    ok = _validos(p)
    p, v = p[ok], v[ok]
    orden = np.argsort(p)
    p, v = p[orden], v[orden]
    out = np.full(len(destino), NULO)
    if not len(p):
        return out
    j = np.clip(np.searchsorted(p, destino), 1, len(p) - 1) if len(p) > 1 else np.zeros(len(destino), int)
    if len(p) > 1:
        izq = np.abs(np.asarray(destino) - p[j - 1]) <= np.abs(p[j] - np.asarray(destino))
        j = np.where(izq, j - 1, j)
    dist = np.abs(p[j] - np.asarray(destino))
    sel = dist <= tolerancia
    out[sel] = v[j][sel]
    return out


def remuestrear(reg, paso: float, inicio: float | None = None, fin: float | None = None,
                metodo: str = "auto", alinear: bool = True) -> int:
    """Lleva todas las curvas del registro a una malla de paso constante en MD.

    `metodo`: "linear" (interpolación que no cruza nulos), "nearest" (muestra más cercana, para
    curvas discretas o banderas), "average" (media por bloque, para pasar a un paso mayor) o
    "auto" (average si el paso nuevo es 1,5 veces mayor que el actual; si no, linear).
    Devuelve el número de filas nuevo."""
    if not reg.existe_columna(reg.indice_md):
        raise ValueError('Please select log column for "Depth MD".')
    p = reg.columnas[reg.indice_md].datos.copy()
    v = p[_validos(p)]
    if not v.size:
        raise ValueError("The depth column has no valid values.")
    inicio = float(v.min()) if inicio is None else inicio
    fin = float(v.max()) if fin is None else fin
    nueva = malla(inicio, fin, paso, alinear)
    actual = paso_regular(p) or float(np.median(np.abs(np.diff(np.sort(v))))) if v.size > 1 else paso
    if metodo == "auto":
        metodo = "average" if actual and paso > 1.5 * actual else "linear"
    for k, c in enumerate(reg.columnas):
        if k == reg.indice_md:
            c.datos = nueva.copy()
        elif metodo == "average" and k != reg.indice_tvd:
            c.datos = promedio_bloques(p, c.datos, nueva, paso)
        elif metodo == "nearest" and k != reg.indice_tvd:
            c.datos = mas_cercano(p, c.datos, nueva, max(paso, actual or paso))
        else:
            c.datos = remuestrear_a(p, c.datos, nueva)
    return len(nueva)
