"""Edición de curvas (mantenimiento): funciones puras sobre arreglos de valores y profundidad.

Todas reciben `datos` y `prof` (misma longitud, nulo = NULO) y devuelven un arreglo nuevo; no
modifican la entrada. El intervalo [tope, base] se da en la profundidad de `prof`."""
from __future__ import annotations

import numpy as np

from .comun import NULO


def _validos(d: np.ndarray) -> np.ndarray:
    return (d != NULO) & np.isfinite(d)


def escala_log(unidad: str) -> bool:
    """Curvas que se analizan en log10 (resistividad, permeabilidad)."""
    from .unidades import canonica
    return canonica(unidad) in ("OHMM", "MD", "MMHO/M") or unidad.strip().upper() in ("OHMM", "MDARCY")


def mascara_intervalo(prof, tope: float | None = None, base: float | None = None) -> np.ndarray:
    """Muestras dentro de [tope, base] (None = sin límite); las de profundidad nula, fuera."""
    p = np.asarray(prof, float)
    m = _validos(p)
    if tope is not None and base is not None and tope > base:
        tope, base = base, tope
    if tope is not None:
        m &= p >= tope
    if base is not None:
        m &= p <= base
    return m


def a_nulo(datos, prof, tope, base) -> np.ndarray:
    """Intervalo a nulo."""
    d = np.array(datos, float)
    d[mascara_intervalo(prof, tope, base)] = NULO
    return d


def poner_constante(datos, prof, tope, base, valor: float) -> np.ndarray:
    d = np.array(datos, float)
    d[mascara_intervalo(prof, tope, base)] = valor
    return d


def huecos(datos) -> list[tuple[int, int]]:
    """Tramos de nulos (inicio, fin) inclusivos, en índices de fila."""
    return tramos_verdaderos(~_validos(np.asarray(datos, float)))


def tramos_verdaderos(mascara) -> list[tuple[int, int]]:
    """Tramos (inicio, fin) inclusivos de valores True consecutivos, vectorizado."""
    m = np.asarray(mascara, bool)
    if not m.size:
        return []
    borde = np.diff(np.concatenate(([False], m, [False])).astype(np.int8))
    inicios, fines = np.flatnonzero(borde == 1), np.flatnonzero(borde == -1) - 1
    return list(zip(inicios.tolist(), fines.tolist()))


def interpolar_huecos(datos, prof, max_hueco: float = 0.0, tope=None, base=None,
                      metodo: str = "linear") -> np.ndarray:
    """Rellena huecos interiores (con dato válido a ambos lados) por interpolación en profundidad.

    `max_hueco` limita el espesor del hueco (en unidades de profundidad; 0 = sin límite).
    `metodo`: "linear" o "pchip" (cúbica monótona, sin sobreoscilación)."""
    d = np.array(datos, float)
    p = np.asarray(prof, float)
    dentro = mascara_intervalo(p, tope, base)
    ok = _validos(d) & _validos(p)
    if ok.sum() < 2:
        return d
    interp = None
    if metodo == "pchip" and ok.sum() >= 3:
        from scipy.interpolate import PchipInterpolator
        orden = np.argsort(p[ok])
        pp, vv = p[ok][orden], d[ok][orden]
        unicos = np.concatenate(([True], np.diff(pp) > 0))
        interp = PchipInterpolator(pp[unicos], vv[unicos], extrapolate=False)
    for i, j in huecos(d):
        if i == 0 or j == len(d) - 1 or not (ok[i - 1] and ok[j + 1]):
            continue
        p0, p1 = p[i - 1], p[j + 1]
        if max_hueco > 0 and abs(p1 - p0) > max_hueco:
            continue
        filas = [k for k in range(i, j + 1) if dentro[k] and _validos(p[k:k + 1])[0]]
        if not filas:
            continue
        if interp is not None:
            d[filas] = interp(p[filas])
        else:
            v0, v1 = d[i - 1], d[j + 1]
            d[filas] = v0 + (v1 - v0) * (p[filas] - p0) / (p1 - p0) if p1 != p0 else v0
    return d


def nanmediana_filas(vistas: np.ndarray) -> np.ndarray:
    """Igual que `np.nanmedian(vistas, axis=1)` (NaN si la fila no tiene datos), pero ordenando
    cada fila con los NaN al final: unas 20 veces más rápido que nanmedian, que pasa por arreglos
    enmascarados (v0.4, D90)."""
    v = np.asarray(vistas, float)
    nan = np.isnan(v)
    x = np.where(nan, np.inf, v)
    x.sort(axis=1)
    k = v.shape[1] - nan.sum(axis=1)
    out = np.full(v.shape[0], np.nan)
    ok = np.flatnonzero(k > 0)
    if ok.size:
        a, b = x[ok, (k[ok] - 1) // 2], x[ok, k[ok] // 2]
        out[ok] = np.where(a == b, a, (a + b) / 2)
    return out


def _mediana_movil(d: np.ndarray, ventana: int, excluir_centro: bool = False) -> np.ndarray:
    """Mediana móvil centrada que ignora nulos (NaN donde la ventana no tiene datos).
    `excluir_centro` la calcula solo con los vecinos (la muestra no se influye a sí misma)."""
    x = np.where(_validos(d), d, np.nan)
    m = ventana // 2
    pad = np.pad(x, m, constant_values=np.nan)
    vistas = np.lib.stride_tricks.sliding_window_view(pad, 2 * m + 1)
    if excluir_centro:
        vistas = np.delete(vistas, m, axis=1)
    return nanmediana_filas(vistas)


def detectar_picos(datos, ventana: int = 11, umbral: float = 4.0, log: bool = False) -> np.ndarray:
    """Máscara de picos: |x − mediana móvil(ventana)| > umbral · 1.4826 · MAD de esos residuos
    (MAD calculada en una ventana 5 veces mayor para que la escala sea estable).
    `log` evalúa log10(x), para curvas de variación multiplicativa como la resistividad."""
    d = np.asarray(datos, float)
    if log:
        with np.errstate(all="ignore"):
            d = np.where(_validos(d) & (d > 0), np.log10(np.where(d > 0, d, 1.0)), NULO)
    ventana = max(3, int(ventana) | 1)
    med = _mediana_movil(d, ventana)
    dev = np.where(_validos(d), np.abs(d - med), np.nan)
    # Escala robusta de los residuos en una ventana amplia. Los residuos exactamente nulos (la
    # muestra es su propia mediana) se excluyen: si no, la MAD sale sesgada hacia abajo y el
    # umbral efectivo baja de 4σ a ~3σ.
    m = max(ventana * 5, 51) // 2
    positivos = np.where(dev > 0, dev, np.nan)
    pad = np.pad(positivos, m, constant_values=np.nan)
    mad = nanmediana_filas(np.lib.stride_tricks.sliding_window_view(pad, 2 * m + 1))
    global_mad = nanmediana_filas(positivos[None, :])[0]      # sin avisos: apto para hilos (D90)
    escala = 1.4826 * np.where(np.isfinite(mad) & (mad > 0), mad, global_mad if np.isfinite(global_mad) else 0)
    with np.errstate(invalid="ignore"):
        picos = _validos(d) & (escala > 0) & (dev > umbral * escala)
    return _solo_excursiones(d, picos, umbral * escala)


ANCHO_MAX_PICO = 3        # muestras: un tramo más ancho que se aparta de la mediana es una capa


def _solo_excursiones(d, candidatos, umbral) -> np.ndarray:
    """De los candidatos, solo los que forman un pico: un tramo corto (≤ ANCHO_MAX_PICO muestras) que
    sale y vuelve, es decir, que queda por encima (o por debajo) de los valores válidos de ambos lados
    por al menos medio umbral. Las muestras de la transición entre dos capas quedan *entre* los
    valores de los lados y no son picos (D108: con los LAS reales digitalizados del KGS, el criterio
    solo de la mediana marcaba ~2 % de las muestras, casi todas en los cambios de capa)."""
    ok = _validos(d)
    idx_ok = np.flatnonzero(ok)
    out = np.zeros(len(d), bool)
    for i, j in tramos_verdaderos(candidatos):
        if j - i + 1 > ANCHO_MAX_PICO:
            continue
        k = np.searchsorted(idx_ok, i)              # vecino válido anterior: idx_ok[k-1]
        m = np.searchsorted(idx_ok, j, side="right")  # vecino válido siguiente: idx_ok[m]
        lados = ([d[idx_ok[k - 1]]] if k > 0 else []) + ([d[idx_ok[m]]] if m < len(idx_ok) else [])
        if not lados:
            continue
        tramo = d[i:j + 1][ok[i:j + 1]]
        tol = 0.5 * float(np.nanmin(umbral[i:j + 1]))
        if tramo.min() > max(lados) + tol or tramo.max() < min(lados) - tol:
            out[i:j + 1] = ok[i:j + 1]
    return out


def quitar_picos(datos, prof=None, ventana: int = 11, umbral: float = 4.0, reemplazo: str = "median",
                 tope=None, base=None, log: bool = False, pasadas: int = 5) -> tuple[np.ndarray, int]:
    """Despike. `reemplazo`: "median" (mediana móvil), "null" o "interpolate". Devuelve (datos, nº de
    muestras cambiadas). Repite la detección hasta `pasadas` veces: al quitar los picos más grandes la
    escala robusta se achica y el QC (mismo detector) encontraba otros (Sara 1-28: DT 82 → 36 → 6 → 0).
    Así, tras quitar picos con los parámetros del QC, el QC ya no cuenta ninguno."""
    d = np.array(datos, float)
    en_intervalo = mascara_intervalo(prof, tope, base) if prof is not None else np.ones(len(d), bool)
    cambiados = np.zeros(len(d), bool)
    for _ in range(max(1, int(pasadas))):
        picos = detectar_picos(d, ventana, umbral, log) & en_intervalo
        if not picos.any():
            break
        cambiados |= picos
        if reemplazo == "median":
            med = _mediana_movil(np.where(picos, NULO, d), max(3, int(ventana) | 1))
            d[picos] = np.where(np.isfinite(med[picos]), med[picos], NULO)
        else:
            d[picos] = NULO
    if reemplazo == "interpolate" and prof is not None and cambiados.any():
        d = interpolar_huecos(d, prof)
    return d, int(cambiados.sum())


def suavizar(datos, prof=None, ventana: int = 5, metodo: str = "mean", tope=None, base=None) -> np.ndarray:
    """Suavizado móvil centrado que ignora nulos y los conserva. `metodo`: mean, median, gaussian."""
    d = np.asarray(datos, float)
    ventana = max(3, int(ventana) | 1)
    ok = _validos(d)
    m = ventana // 2
    if metodo == "median":
        s = _mediana_movil(d, ventana)
    else:
        if metodo == "gaussian":
            sigma = ventana / 6.0
            k = np.exp(-0.5 * (np.arange(-m, m + 1) / sigma) ** 2)
        else:
            k = np.ones(ventana)
        x = np.where(ok, d, 0.0)
        w = ok.astype(float)
        num = np.convolve(np.pad(x, m), k, mode="valid")
        den = np.convolve(np.pad(w, m), k, mode="valid")
        with np.errstate(invalid="ignore", divide="ignore"):
            s = num / den
    out = np.array(d, float)
    sel = ok & np.isfinite(s)
    if prof is not None:
        sel &= mascara_intervalo(prof, tope, base)
    out[sel] = s[sel]
    return out


def recortar(datos, vmin: float | None, vmax: float | None, modo: str = "clip", prof=None,
             tope=None, base=None) -> tuple[np.ndarray, int]:
    """Recorte a rango: "clip" lleva al límite, "null" anula lo que queda fuera."""
    d = np.array(datos, float)
    ok = _validos(d)
    if prof is not None:
        ok &= mascara_intervalo(prof, tope, base)
    fuera = np.zeros(len(d), bool)
    if vmin is not None:
        fuera |= ok & (d < vmin)
    if vmax is not None:
        fuera |= ok & (d > vmax)
    if modo == "null":
        d[fuera] = NULO
    else:
        if vmin is not None:
            d[ok & (d < vmin)] = vmin
        if vmax is not None:
            d[ok & (d > vmax)] = vmax
    return d, int(fuera.sum())


def empalmar(prof, arriba, abajo, prof_empalme: float, transicion: float = 0.0,
             ajustar_nivel: bool = False) -> np.ndarray:
    """Empalme de dos corridas: `arriba` sobre `prof_empalme` y `abajo` debajo.

    `transicion` (espesor) mezcla linealmente ambas alrededor del punto de empalme.
    `ajustar_nivel` desplaza `abajo` para que coincida con `arriba` en el traslape (medianas)."""
    p = np.asarray(prof, float)
    a = np.asarray(arriba, float)
    b = np.array(abajo, float)
    va, vb = _validos(a), _validos(b)
    if ajustar_nivel:
        tras = va & vb
        if transicion > 0:
            tras &= np.abs(p - prof_empalme) <= max(transicion, 0)
        if tras.any():
            b[vb] += float(np.median(a[tras]) - np.median(b[tras]))
    out = np.full(len(p), NULO)
    pv = _validos(p)
    if transicion > 0:
        t = np.clip((p - (prof_empalme - transicion / 2)) / transicion, 0.0, 1.0)
    else:
        t = (p >= prof_empalme).astype(float)
    ambos = va & vb & pv
    out[ambos] = (1 - t[ambos]) * a[ambos] + t[ambos] * b[ambos]
    solo_a = va & ~vb & pv & (t < 1)
    solo_b = vb & ~va & pv & (t > 0)
    out[solo_a] = a[solo_a]
    out[solo_b] = b[solo_b]
    return out


def pintar(datos, prof, trazo: list[tuple[float, float]]) -> np.ndarray:
    """Edición manual: `trazo` = puntos (valor, profundidad) dibujados con el ratón; las muestras
    entre el primer y el último punto toman el valor interpolado del trazo."""
    d = np.array(datos, float)
    if not trazo:
        return d
    pts = sorted(((float(z), float(v)) for v, z in trazo), key=lambda t: t[0])
    zs = np.array([z for z, _ in pts])
    vs = np.array([v for _, v in pts])
    p = np.asarray(prof, float)
    if len(pts) == 1:
        if len(p):
            k = int(np.argmin(np.where(_validos(p), np.abs(p - zs[0]), np.inf)))
            d[k] = vs[0]
        return d
    sel = _validos(p) & (p >= zs[0]) & (p <= zs[-1])
    d[sel] = np.interp(p[sel], zs, vs)
    return d
