"""Preparación de datos (solo numpy): selección de curvas por pozo, transformación, normalización,
máscaras de nulos y ventanas de profundidad."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..nucleo.comun import NULO
from ..nucleo.edicion import escala_log
from ..nucleo.multipozo import buscar_curva

IGNORAR = -1          # etiqueta de clase "sin dato" (fuera de los intervalos de litología)


@dataclass
class Pozo:
    """Datos de un registro listos para la red. X: (C, N) con NaN donde falta el dato."""
    nombre: str
    prof: np.ndarray
    X: np.ndarray
    y: np.ndarray | None = None          # regresión: valores (NaN = sin dato); clasificación: enteros
    curvas: list[str] = field(default_factory=list)
    excluidas: int = 0                   # muestras con bandera de QC que no se usan (v0.3, D80)


@dataclass
class Normalizador:
    """Estadísticos robustos (mediana, IQR) por curva de entrada y media/desviación del objetivo."""
    por_pozo: bool = True
    centro: np.ndarray | None = None      # (C,) global, si no es por pozo
    escala: np.ndarray | None = None
    y_media: float = 0.0
    y_desv: float = 1.0
    log_entrada: list[bool] = field(default_factory=list)
    log_objetivo: bool = False

    def a_dict(self) -> dict:
        return {"por_pozo": self.por_pozo, "centro": None if self.centro is None else self.centro.tolist(),
                "escala": None if self.escala is None else self.escala.tolist(), "y_media": self.y_media,
                "y_desv": self.y_desv, "log_entrada": self.log_entrada, "log_objetivo": self.log_objetivo}

    @classmethod
    def desde_dict(cls, d: dict) -> "Normalizador":
        n = cls(d["por_pozo"], None, None, d["y_media"], d["y_desv"], d["log_entrada"], d["log_objetivo"])
        n.centro = None if d["centro"] is None else np.array(d["centro"])
        n.escala = None if d["escala"] is None else np.array(d["escala"])
        return n


def _a_nan(d) -> np.ndarray:
    d = np.asarray(d, float)
    return np.where((d == NULO) | ~np.isfinite(d), np.nan, d)


def _log(d) -> np.ndarray:
    with np.errstate(all="ignore"):
        return np.where(d > 0, np.log10(np.where(d > 0, d, 1.0)), np.nan)


def es_log(nombre: str, unidad: str, alias=None) -> bool:
    if escala_log(unidad):
        return True
    if alias is not None:
        g = alias.grupo_de(nombre)
        return g >= 0 and alias.grupos[g].nombre.upper().startswith("RES")
    return False


def extraer(reg, nombre_pozo: str, entradas: list[str], objetivo: str | None = None, alias=None,
            litologia=None, excluir_qc: bool = False) -> Pozo:
    """Curvas de entrada (por nombre o alias; las que falten quedan en NaN) y objetivo.

    Con `litologia` (una Litologia del pozo) el objetivo es la clase de cada muestra. Con
    `excluir_qc`, las muestras que el control de calidad marca como dudosas (fuera de rango, picos,
    tramos planos) pasan a NaN: la red no aprende de ellas (las entradas quedan enmascaradas)."""
    if not reg.existe_columna(reg.indice_md):
        raise ValueError(f'{nombre_pozo}/{reg.nombre}: please select log column for "Depth MD".')
    prof = _a_nan(reg.columnas[reg.indice_md].datos)
    X = np.full((len(entradas), len(prof)), np.nan)
    usadas = []
    excluidas = np.zeros(len(prof), bool)
    if excluir_qc:
        from ..nucleo import qc
    for i, n in enumerate(entradas):
        k = buscar_curva(reg, n, alias)
        if k >= 0:
            X[i] = _a_nan(reg.columnas[k].datos)
            if excluir_qc:
                m = qc.dudosas(reg, k, alias)
                X[i][m] = np.nan
                excluidas |= m
            usadas.append(reg.columnas[k].nombre)
        else:
            usadas.append("")
    y = None
    if litologia is not None:
        y = np.full(len(prof), IGNORAR, dtype=np.int64)
        for it in litologia.intervalos:
            y[(prof >= min(it.tope, it.base)) & (prof < max(it.tope, it.base))] = it.tipo
    elif objetivo:
        k = buscar_curva(reg, objetivo, alias)
        if k >= 0:
            y = _a_nan(reg.columnas[k].datos)
            if excluir_qc:
                m = qc.dudosas(reg, k, alias)
                y[m] = np.nan
                excluidas |= m
    return Pozo(nombre_pozo, prof, X, y, usadas, int(excluidas.sum()))


def ajustar_normalizador(pozos: list[Pozo], entradas: list[str], unidades: list[str], objetivo_log: bool,
                         por_pozo: bool = True, alias=None, regresion: bool = True) -> Normalizador:
    n = Normalizador(por_pozo, log_entrada=[es_log(e, u, alias) for e, u in zip(entradas, unidades)],
                     log_objetivo=objetivo_log)
    if not por_pozo:
        todos = np.concatenate([transformar_entrada(p.X, n.log_entrada) for p in pozos], axis=1)
        n.centro, n.escala = _robustos(todos)
    if regresion:
        ys = np.concatenate([transformar_objetivo(p.y, objetivo_log) for p in pozos if p.y is not None])
        ys = ys[np.isfinite(ys)]
        if ys.size < 10:
            raise ValueError("Not enough samples of the target curve to train.")
        n.y_media, n.y_desv = float(ys.mean()), float(ys.std() or 1.0)
    return n


def _robustos(X) -> tuple[np.ndarray, np.ndarray]:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        c = np.nanmedian(X, axis=1)
        q = np.nanpercentile(X, 75, axis=1) - np.nanpercentile(X, 25, axis=1)
    c = np.where(np.isfinite(c), c, 0.0)
    q = np.where(np.isfinite(q) & (q > 0), q, 1.0)
    return c, q


def transformar_entrada(X, logs: list[bool]) -> np.ndarray:
    X = np.array(X, float)
    for i, es in enumerate(logs):
        if es:
            X[i] = _log(X[i])
    return X


def transformar_objetivo(y, log: bool) -> np.ndarray:
    y = np.asarray(y, float)
    return _log(y) if log else y


def entrada_red(p: Pozo, n: Normalizador) -> np.ndarray:
    """(2C, N): valores normalizados (0 donde falta) y máscara 1/0 de dato presente."""
    X = transformar_entrada(p.X, n.log_entrada)
    c, s = _robustos(X) if n.por_pozo else (n.centro, n.escala)
    Z = (X - c[:, None]) / s[:, None]
    m = np.isfinite(Z)
    Z = np.clip(np.where(m, Z, 0.0), -10, 10)
    return np.concatenate([Z, m.astype(float)], axis=0).astype(np.float32)


def objetivo_red(p: Pozo, n: Normalizador) -> np.ndarray:
    y = (transformar_objetivo(p.y, n.log_objetivo) - n.y_media) / n.y_desv
    return y.astype(np.float32)


def desnormalizar(z, n: Normalizador) -> np.ndarray:
    y = np.asarray(z, float) * n.y_desv + n.y_media
    return 10 ** y if n.log_objetivo else y


def ventanas(N: int, largo: int, paso: int) -> list[int]:
    """Inicios de ventanas que cubren 0..N (la última termina en N)."""
    if N <= largo:
        return [0]
    ini = list(range(0, N - largo + 1, max(paso, 1)))
    if ini[-1] != N - largo:
        ini.append(N - largo)
    return ini


def cortar(A: np.ndarray, largo: int) -> np.ndarray:
    """Rellena con ceros por la derecha hasta `largo` (último eje)."""
    falta = largo - A.shape[-1]
    if falta <= 0:
        return A
    relleno = [(0, 0)] * (A.ndim - 1) + [(0, falta)]
    return np.pad(A, relleno, constant_values=0)


def peso_ventana(largo: int) -> np.ndarray:
    """Pesos de Hann (más peso al centro) para promediar ventanas solapadas al predecir."""
    w = np.hanning(largo + 2)[1:-1]
    return np.maximum(w, 1e-3).astype(np.float32)
