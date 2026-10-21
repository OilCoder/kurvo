"""Operaciones entre pozos (mantenimiento, prioridad 6): normalización por percentiles y depth
shift automático por correlación cruzada."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .comun import NULO
from .historial import remuestrear_a


def _validos(d):
    d = np.asarray(d, float)
    return (d != NULO) & np.isfinite(d)


def buscar_curva(reg, nombre: str, alias=None) -> int:
    """Índice de la curva por nombre exacto o, si no está, por el mismo grupo de alias."""
    i = reg.indice_columna(nombre)
    if i >= 0 or alias is None:
        return i
    g = alias.grupo_de(nombre)
    if g < 0:
        return -1
    for k, c in enumerate(reg.columnas):
        if k not in (reg.indice_md, reg.indice_tvd) and alias.grupo_de(c.nombre) == g:
            return k
    return -1


def profundidad(reg) -> np.ndarray:
    if not reg.existe_columna(reg.indice_md):
        raise ValueError(f'{reg.nombre}: please select log column for "Depth MD".')
    return reg.columnas[reg.indice_md].datos


# ------------------------------------------------------------------ normalización
@dataclass
class Normalizacion:
    pozo: str
    curva: str
    p_bajo: float
    p_alto: float
    ref_bajo: float
    ref_alto: float
    muestras: int

    @property
    def ganancia(self) -> float:
        return (self.ref_alto - self.ref_bajo) / (self.p_alto - self.p_bajo) if self.p_alto != self.p_bajo else 1.0

    @property
    def desplazamiento(self) -> float:
        return self.ref_bajo - self.ganancia * self.p_bajo


def percentiles(datos, prof=None, tope=None, base=None, bajo: float = 5, alto: float = 95):
    d = np.asarray(datos, float)
    m = _validos(d)
    if prof is not None and (tope is not None or base is not None):
        p = np.asarray(prof, float)
        m &= _validos(p)
        if tope is not None:
            m &= p >= min(tope, base if base is not None else tope)
        if base is not None:
            m &= p <= max(base, tope if tope is not None else base)
    v = d[m]
    if v.size < 10:
        raise ValueError(f"Not enough valid samples ({v.size}) to compute percentiles.")
    return float(np.percentile(v, bajo)), float(np.percentile(v, alto)), int(v.size)


def normalizar(datos, p_bajo, p_alto, ref_bajo, ref_alto) -> np.ndarray:
    """Normalización lineal de dos puntos: los percentiles del pozo pasan a los de la referencia."""
    d = np.asarray(datos, float)
    out = np.full(d.shape, NULO)
    ok = _validos(d)
    g = (ref_alto - ref_bajo) / (p_alto - p_bajo) if p_alto != p_bajo else 1.0
    out[ok] = ref_bajo + g * (d[ok] - p_bajo)
    return out


# ------------------------------------------------------------------ depth shift automático
@dataclass
class Desfase:
    desfase: float          # profundidad a sumar a la curva desplazada (positivo = hacia abajo)
    correlacion: float      # Pearson en el mejor desfase
    correlacion_cero: float  # Pearson sin desfase
    muestras: int
    curva_r: np.ndarray | None = None   # correlación para cada desfase (para graficar)
    desfases: np.ndarray | None = None


def _pearson(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 10:
        return np.nan, int(ok.sum())
    x, y = a[ok] - a[ok].mean(), b[ok] - b[ok].mean()
    den = np.sqrt((x * x).sum() * (y * y).sum())
    return (float((x * y).sum() / den) if den > 0 else np.nan), int(ok.sum())


def desfase_por_correlacion(prof_ref, ref, prof, x, max_desfase: float, paso: float | None = None,
                            tope: float | None = None, base: float | None = None) -> Desfase:
    """Busca el desplazamiento Δ en [−max, +max] que maximiza la correlación de Pearson entre
    ref(z) y x(z − Δ), con ambas curvas llevadas a una malla común de paso `paso`.
    La ventana [tope, base] (en la profundidad de la referencia) limita el tramo comparado."""
    pr = np.asarray(prof_ref, float)
    p = np.asarray(prof, float)
    vr, vx = pr[_validos(pr)], p[_validos(p)]
    if not vr.size or not vx.size:
        raise ValueError("Depth columns have no valid values.")
    if paso is None or paso <= 0:
        pasos = np.abs(np.diff(np.sort(vr)))
        paso = float(np.median(pasos[pasos > 0])) if (pasos > 0).any() else 1.0
    lo = max(vr.min(), tope) if tope is not None else vr.min()
    hi = min(vr.max(), base) if base is not None else vr.max()
    if hi <= lo:
        raise ValueError("Empty correlation window.")
    malla = np.arange(lo, hi + paso / 2, paso)
    a = remuestrear_a(pr, ref, malla)
    a = np.where(a == NULO, np.nan, a)
    k = int(np.ceil(max_desfase / paso))
    desfases = np.arange(-k, k + 1) * paso
    rs = np.full(len(desfases), np.nan)
    ns = np.zeros(len(desfases), int)
    for i, d in enumerate(desfases):
        b = remuestrear_a(p, x, malla - d)
        b = np.where(b == NULO, np.nan, b)
        rs[i], ns[i] = _pearson(a, b)
    if np.all(np.isnan(rs)):
        raise ValueError("The curves do not overlap in depth within the search window.")
    j = int(np.nanargmax(rs))
    # refinamiento parabólico alrededor del máximo (resolución menor que el paso)
    fino = desfases[j]
    if 0 < j < len(rs) - 1 and np.isfinite(rs[j - 1]) and np.isfinite(rs[j + 1]):
        den = rs[j - 1] - 2 * rs[j] + rs[j + 1]
        if den < 0:
            fino = desfases[j] + paso * 0.5 * (rs[j - 1] - rs[j + 1]) / den
    cero = rs[k] if np.isfinite(rs[k]) else np.nan
    return Desfase(float(fino), float(rs[j]), float(cero), int(ns[j]), rs, desfases)


def desplazar_curva(prof, datos, desfase: float) -> np.ndarray:
    """La curva queda movida `desfase` en profundidad sobre la misma malla: y(z) = x(z − Δ)."""
    p = np.asarray(prof, float)
    return remuestrear_a(p, datos, np.where(_validos(p), p - desfase, NULO))


def desplazar_registro(reg, desfase: float, trayectoria=None) -> bool:
    """Suma el desfase a la columna MD (todas las curvas se mueven juntas). Si el registro tiene
    columna TVD y se da la trayectoria del pozo (con estaciones), la TVD se recalcula a partir de
    la MD nueva (v0.4, D100). Devuelve True si recalculó la TVD."""
    c = reg.columnas[reg.indice_md]
    ok = _validos(c.datos)
    c.datos = np.where(ok, c.datos + desfase, c.datos)
    return recalcular_tvd(reg, trayectoria)


def recalcular_tvd(reg, trayectoria) -> bool:
    if trayectoria is None or len(getattr(trayectoria, "estaciones", [])) < 2 \
            or not reg.existe_columna(reg.indice_tvd) or not reg.existe_columna(reg.indice_md):
        return False
    md = reg.columnas[reg.indice_md].datos
    reg.columnas[reg.indice_tvd].datos = np.array([NULO if v == NULO or not np.isfinite(v)
                                                    else trayectoria.tvd_en(v) for v in md], float)
    return True
