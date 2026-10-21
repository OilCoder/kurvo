"""Control de calidad de curvas: estadísticas, huecos, rango físico, saturación, tramos planos,
picos, condición de pozo, columna de bandera y los análisis de la ventana de QC (cobertura,
cajas, CDF, correlación, Mahalanobis, paso de profundidad, crossplot neutrón-densidad y
antes/después). (D32–D36 y D70–D79).

Los umbrales y los rangos físicos salen de las preferencias del usuario (nucleo/preferencias.py)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..i18n import tr
from . import preferencias
from .comun import NULO
from .edicion import detectar_picos, escala_log, huecos, tramos_verdaderos


class _Rangos(dict):
    """Vista de solo lectura de los rangos de las preferencias (compatibilidad con `qc.RANGOS`)."""

    def __getitem__(self, k):
        return preferencias.actual().rangos[k]

    def get(self, k, defecto=None):
        return preferencias.actual().rangos.get(k, defecto)

    def __contains__(self, k):
        return k in preferencias.actual().rangos

    def __iter__(self):
        return iter(preferencias.actual().rangos)

    def __len__(self):
        return len(preferencias.actual().rangos)


RANGOS = _Rangos()

# curvas constantes por naturaleza (diámetro de la broca): no se buscan tramos planos en ellas (D70)
CONSTANTES = ("BS", "BIT", "BITSIZE", "BIT_SIZE", "HOLE_SIZE")


def _plana_esperada(nombre: str) -> bool:
    return nombre.strip().upper() in CONSTANTES


@dataclass
class EstadoCurva:
    nombre: str
    unidad: str
    muestras: int
    validas: int
    pct_nulos: float
    n_huecos: int
    hueco_max: float                 # espesor del mayor hueco interior (unidades de profundidad)
    minimo: float = np.nan
    maximo: float = np.nan
    media: float = np.nan
    mediana: float = np.nan
    desv: float = np.nan
    p10: float = np.nan
    p50: float = np.nan
    p90: float = np.nan
    fuera_rango: int = 0
    rango: tuple[float, float] | None = None
    saturacion: float = 0.0          # % de muestras pegadas al mínimo o al máximo
    tramos_planos: int = 0
    muestras_planas: int = 0
    picos: int = 0
    cerradas: int = 0                # muestras de calibre con el brazo cerrado o en casing (D110)
    intervalo: tuple[float, float] | None = None    # profundidad de la primera y la última muestra válida
    avisos: list[str] = field(default_factory=list)

    @property
    def nota(self) -> str:
        """A (sin problemas), B (avisos menores) o C (no apta sin revisar)."""
        u = preferencias.actual().qc
        if self.validas == 0 or self.pct_nulos > u.nulos_malo or \
                self.fuera_rango > u.fuera_malo / 100 * max(self.validas - self.cerradas, 1):
            return "C"
        return "B" if self.avisos else "A"


def _validos(d):
    return (d != NULO) & np.isfinite(d)


def rango_fisico(nombre: str, unidad: str, alias=None) -> tuple[float, float] | None:
    from .unidades import canonica
    claves = [nombre.upper()]
    if alias is not None:
        g = alias.grupo_de(nombre)
        if g >= 0:
            claves.insert(0, alias.grupos[g].nombre.upper())
    u = canonica(unidad)
    for clave in claves:
        for unidad_rango, lo, hi in RANGOS.get(clave, []):
            if canonica(unidad_rango) == u:
                return lo, hi
    return None


def calibre_cerrado(nombre: str, unidad: str, alias=None) -> float | None:
    """Valor por debajo del cual una curva del grupo CAL es el brazo cerrado o el casing (D110), en
    la unidad de la curva; None si no es un calibre con unidad de longitud. El DCAL de los LAS del
    KGS (calibre de la herramienta de densidad) baja a −2.9 … 2.4 in en el tramo en que se sube con
    el brazo cerrado: no son datos fuera de rango sino tramo sin registrar."""
    from .unidades import convertir, magnitud
    if alias is None:
        return None
    g = alias.grupo_de(nombre)
    if g < 0 or alias.grupos[g].nombre.upper() != "CAL" or magnitud(unidad) != "length":
        return None
    return float(convertir([preferencias.actual().qc.calibre_cerrado], "IN", unidad)[0])


def tramos_planos(datos, minimo: int | None = None) -> list[tuple[int, int]]:
    """Tramos de al menos `minimo` muestras válidas consecutivas con el mismo valor."""
    minimo = minimo or preferencias.actual().qc.minimo_plano
    d = np.asarray(datos, float)
    ok = _validos(d)
    if len(d) < 2:
        return [(0, 0)] if len(d) and ok[0] and minimo <= 1 else []
    # igual[i]: la muestra i+1 es válida, igual a la i y la i también es válida → tramos de "iguales"
    igual = ok[:-1] & ok[1:] & (d[1:] == d[:-1])
    tramos = [(i, j + 1) for i, j in tramos_verdaderos(igual)]
    if minimo <= 1:     # cada muestra válida suelta es un "tramo" de una muestra
        dentro = np.zeros(len(d), bool)
        for i, j in tramos:
            dentro[i:j + 1] = True
        tramos += [(i, i) for i in np.flatnonzero(ok & ~dentro).tolist()]
        tramos.sort()
    return [(i, j) for i, j in tramos if j - i + 1 >= minimo]


def mascara(reg, prof=None, tope=None, base=None) -> np.ndarray:
    n = reg.n_filas
    if prof is None or (tope is None and base is None):
        return np.ones(n, bool)
    p = np.asarray(prof, float)
    m = _validos(p)
    if tope is not None:
        m &= p >= tope
    if base is not None:
        m &= p < base
    return m


def _picos(d, unidad):
    u = preferencias.actual().qc
    return detectar_picos(d, u.ventana_picos, u.sigma_picos, log=escala_log(unidad))


def evaluar_curva(datos, prof, nombre: str, unidad: str = "", alias=None, sel=None,
                  minimo_plano: int | None = None) -> EstadoCurva:
    u = preferencias.actual().qc
    d = np.asarray(datos, float)
    p = np.asarray(prof, float) if prof is not None else np.arange(len(d), dtype=float)
    if sel is not None:
        d, p = d[sel], p[sel]
    ok = _validos(d)
    v = d[ok]
    huecos_int = [(i, j) for i, j in huecos(d) if i > 0 and j < len(d) - 1]
    esp = [abs(p[j + 1] - p[i - 1]) for i, j in huecos_int]
    # nulos dentro del intervalo registrado (de la primera a la última muestra válida, D108): que una
    # curva empiece más abajo que el registro no es un defecto (los LAS reales traen curvas de
    # corridas distintas en una misma tabla)
    if ok.any():
        i0, i1 = np.flatnonzero(ok)[[0, -1]]
        pct = round(100 * (1 - ok[i0:i1 + 1].mean()), 2)
    else:
        pct = 100.0
    e = EstadoCurva(nombre, unidad, len(d), int(ok.sum()), pct, len(huecos_int), float(max(esp)) if esp else 0.0)
    if ok.any():
        e.intervalo = (float(p[i0]), float(p[i1]))
    if v.size:
        e.minimo, e.maximo = float(v.min()), float(v.max())
        e.media, e.mediana, e.desv = float(v.mean()), float(np.median(v)), float(v.std())
        e.p10, e.p50, e.p90 = (float(x) for x in np.percentile(v, [10, 50, 90]))
        e.rango = rango_fisico(nombre, unidad, alias)
        cerrado = calibre_cerrado(nombre, unidad, alias)
        abiertas = v
        if cerrado is not None:
            m = ok & (d < cerrado)
            e.cerradas = int(m.sum())
            abiertas = v[v >= cerrado]
            if e.cerradas:
                i_c = np.flatnonzero(m)
                e.avisos.append(tr("caliper closed or in casing (< {0}): {1} sample(s), {2}–{3}").format(
                    f"{cerrado:g}", e.cerradas, f"{p[i_c[0]]:.6g}", f"{p[i_c[-1]]:.6g}"))
        if e.rango is not None:
            e.fuera_rango = int(((abiertas < e.rango[0]) | (abiertas > e.rango[1])).sum())
        if v.size >= 20 and e.maximo > e.minimo:
            pegadas = max((v == e.minimo).sum(), (v == e.maximo).sum())
            e.saturacion = round(100 * pegadas / v.size, 2)
        planos = [] if _plana_esperada(nombre) else tramos_planos(d, minimo_plano)
        e.tramos_planos, e.muestras_planas = len(planos), int(sum(j - i + 1 for i, j in planos))
        e.picos = int(_picos(d, unidad).sum()) if v.size >= 20 else 0
    if e.validas == 0:
        e.avisos.append(tr("no valid data"))
    if e.pct_nulos > u.nulos_aviso:
        e.avisos.append(tr("{0}% nulls").format(f"{e.pct_nulos:g}"))
    if e.n_huecos:
        e.avisos.append(tr("{0} gap(s), largest {1}").format(e.n_huecos, f"{e.hueco_max:.4g}"))
    if e.fuera_rango:
        e.avisos.append(tr("{0} sample(s) out of physical range {1}–{2}").format(
            e.fuera_rango, f"{e.rango[0]:g}", f"{e.rango[1]:g}"))
    if e.saturacion > u.saturacion:
        e.avisos.append(tr("{0}% samples clipped at min/max").format(f"{e.saturacion:g}"))
    if e.tramos_planos:
        e.avisos.append(tr("{0} flat run(s) ({1} samples)").format(e.tramos_planos, e.muestras_planas))
    # unos pocos picos en miles de muestras son normales en un registro real: avisan (nota B) solo si
    # pasan de `picos_por_mil` cada 1000 muestras válidas (D110)
    if e.picos and e.picos > u.picos_por_mil / 1000 * max(e.validas, 1):
        e.avisos.append(tr("{0} spike(s)").format(e.picos))
    return e


@dataclass
class InformeRegistro:
    pozo: str
    registro: str
    filas: int
    prof_min: float
    prof_max: float
    paso: float
    unidad_prof: str
    validacion: list
    curvas: list[EstadoCurva]
    zonas: list[tuple[str, float, float | None, list[EstadoCurva]]] = field(default_factory=list)
    pozo_malo: list[str] = field(default_factory=list)


def condicion_pozo(reg, alias=None) -> list[str]:
    """Indicadores de mala condición de pozo si existen las curvas: derrumbe (CALI − BS > umbral) y
    corrección de densidad |DRHO| > umbral."""
    u = preferencias.actual().qc
    c = curvas_condicion(reg, alias)
    out = []
    if c["cali"] is not None and c["bs"] is not None:
        ok = _validos(c["cali"]) & _validos(c["bs"])
        if ok.any():
            n = int(((c["cali"] - c["bs"]) > u.derrumbe)[ok].sum())
            out.append(tr("Washout (CALI − BS > {0}): {1} sample(s), {2}%").format(
                f"{u.derrumbe:g}", n, f"{100 * n / ok.sum():.1f}"))
    if c["drho"] is not None:
        d = c["drho"]
        ok = _validos(d)
        if ok.any():
            n = int((np.abs(d[ok]) > u.drho).sum())
            out.append(tr("|DRHO| > {0}: {1} sample(s), {2}%").format(f"{u.drho:g}", n, f"{100 * n / ok.sum():.1f}"))
    return out


def curvas_condicion(reg, alias=None) -> dict:
    """CALI, BS y DRHO del registro (None si no están). BS por nombre (BS o BIT)."""
    from .multipozo import buscar_curva
    k_cal = buscar_curva(reg, "CALI", alias)
    k_bs = buscar_curva(reg, "BS", alias)
    if k_bs < 0:
        k_bs = reg.indice_columna("BIT")
    k_dr = buscar_curva(reg, "DRHO", alias)          # también HDRA, DCOR... (D93)
    col = lambda k: reg.columnas[k].datos if k >= 0 else None  # noqa: E731
    return {"cali": col(k_cal), "bs": col(k_bs), "drho": col(k_dr)}


def informe(reg, pozo: str = "", zonas=None, alias=None) -> InformeRegistro:
    """`zonas`: lista de (nombre, tope, base) en la profundidad MD del registro."""
    from .validacion import paso_regular, validar
    prof = reg.columnas[reg.indice_md].datos if reg.existe_columna(reg.indice_md) else None
    pv = prof[_validos(prof)] if prof is not None else np.zeros(0)
    curvas = [evaluar_curva(c.datos, prof, c.nombre, c.unidad, alias) for k, c in enumerate(reg.columnas)
              if k not in (reg.indice_md, reg.indice_tvd)]
    inf = InformeRegistro(pozo, reg.nombre, reg.n_filas, float(pv.min()) if pv.size else np.nan,
                          float(pv.max()) if pv.size else np.nan, paso_regular(prof) if prof is not None else 0.0,
                          reg.columnas[reg.indice_md].unidad if prof is not None else "", validar(reg), curvas)
    for nombre, tope, base in zonas or []:
        sel = mascara(reg, prof, tope, base)
        if sel.sum() == 0:
            continue
        inf.zonas.append((nombre, tope, base, [evaluar_curva(c.datos, prof, c.nombre, c.unidad, alias, sel)
                                               for k, c in enumerate(reg.columnas)
                                               if k not in (reg.indice_md, reg.indice_tvd)]))
    inf.pozo_malo = condicion_pozo(reg, alias)
    return inf


def bandera(reg, indice: int, alias=None, minimo_plano: int | None = None) -> np.ndarray:
    """1 donde la muestra es dudosa (nula, fuera de rango físico, pico o tramo plano); 0 si no."""
    c = reg.columnas[indice]
    d = c.datos
    f = ~_validos(d)
    r = rango_fisico(c.nombre, c.unidad, alias)
    if r is not None:
        with np.errstate(invalid="ignore"):
            f |= _validos(d) & ((d < r[0]) | (d > r[1]))
    f |= _picos(d, c.unidad)
    for i, j in ([] if _plana_esperada(c.nombre) else tramos_planos(d, minimo_plano)):
        f[i:j + 1] = True
    return f.astype(float)


def dudosas(reg, indice: int, alias=None) -> np.ndarray:
    """Máscara de muestras con dato pero dudosas (bandera sin contar los nulos)."""
    d = reg.columnas[indice].datos
    return (bandera(reg, indice, alias) > 0) & _validos(d)


def zonas_de_pozo(pr, i_pozo: int) -> list[tuple[str, float, float | None]]:
    """Intervalos de zona del pozo: cada tope hasta el siguiente, ordenados por profundidad. Las
    zonas sin tope en este pozo (NULO, p. ej. una formación de otro pozo, D104) no cuentan."""
    topes = sorted(((z.prof(i_pozo), z.nombre) for z in pr.zonas if z.prof(i_pozo) != NULO), key=lambda t: t[0])
    return [(n, t, topes[k + 1][0] if k + 1 < len(topes) else None) for k, (t, n) in enumerate(topes)]


# ====================================================================== caché de notas
_cache: dict[int, tuple[tuple, dict[str, EstadoCurva]]] = {}


def firma(reg) -> tuple:
    """Huella barata del contenido del registro (cambia con cualquier edición)."""
    with np.errstate(all="ignore"):
        cols = tuple((c.nombre, c.unidad, len(c.datos), float(np.nansum(c.datos[::7])), float(np.nansum(c.datos)))
                     for c in reg.columnas)
    return (cols, reg.indice_md, reg.indice_tvd, id(preferencias.actual()))


def notas(reg, alias=None) -> dict[str, EstadoCurva]:
    """Estado (con nota A/B/C) de cada curva del registro, con caché por contenido."""
    f = firma(reg)
    previo = _cache.get(id(reg))
    if previo is not None and previo[0] == f:
        return previo[1]
    prof = reg.columnas[reg.indice_md].datos if reg.existe_columna(reg.indice_md) else None
    res = {c.nombre: evaluar_curva(c.datos, prof, c.nombre, c.unidad, alias)
           for k, c in enumerate(reg.columnas) if k not in (reg.indice_md, reg.indice_tvd)}
    _cache[id(reg)] = (f, res)
    return res


def notas_varios(registros, alias=None, hilos: int | None = None) -> None:
    """Calcula (en paralelo) las notas que faltan en la caché de varios registros. numpy suelta
    el GIL en los ordenamientos, así que los hilos aprovechan varios núcleos (D90)."""
    faltan = []
    for r in registros:
        previo = _cache.get(id(r))
        if previo is None or previo[0] != firma(r):
            faltan.append(r)
    if len(faltan) <= 1:
        for r in faltan:
            notas(r, alias)
        return
    import os
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=hilos or min(8, os.cpu_count() or 2)) as ex:
        list(ex.map(lambda r: notas(r, alias), faltan))


def invalidar(reg=None) -> None:
    if reg is None:
        _cache.clear()
    else:
        _cache.pop(id(reg), None)


def peor_nota(estados) -> str:
    notas_ = [e.nota for e in estados]
    return "C" if "C" in notas_ else "B" if "B" in notas_ else "A" if notas_ else ""


# ====================================================================== análisis de la ventana de QC
def cobertura(reg, alias=None) -> tuple[list[str], np.ndarray]:
    """Matriz (curvas × muestras): 0 nulo, 1 dato, 2 dato dudoso."""
    nombres, filas = [], []
    for k, c in enumerate(reg.columnas):
        if k in (reg.indice_md, reg.indice_tvd):
            continue
        m = _validos(c.datos).astype(np.int8)
        m[dudosas(reg, k, alias)] = 2
        nombres.append(c.nombre)
        filas.append(m)
    return nombres, (np.vstack(filas) if filas else np.zeros((0, reg.n_filas), np.int8))


def caja(valores) -> tuple[float, float, float, float, float] | None:
    """Percentiles P5, P25, P50, P75 y P95 (diagrama de cajas)."""
    v = np.asarray(valores, float)
    v = v[_validos(v)]
    if v.size < 2:
        return None
    return tuple(float(x) for x in np.percentile(v, [5, 25, 50, 75, 95]))


def cdf(valores) -> tuple[np.ndarray, np.ndarray]:
    """Distribución acumulada empírica: (valores ordenados, fracción 0..1)."""
    v = np.sort(np.asarray(valores, float)[_validos(np.asarray(valores, float))])
    return v, (np.arange(1, v.size + 1) / v.size if v.size else np.zeros(0))


def valores_log(valores, log: bool) -> np.ndarray:
    """Valores válidos, en log10 si `log` (los ≤ 0 se descartan)."""
    v = np.asarray(valores, float)
    v = v[_validos(v)]
    if log:
        v = np.log10(v[v > 0])
    return v


def correlacion(reg, nombres: list[str] | None = None, sel=None) -> tuple[list[str], np.ndarray]:
    """Matriz de Pearson entre curvas, por pares de muestras válidas (resistividad en log10)."""
    idx = [k for k, c in enumerate(reg.columnas) if k not in (reg.indice_md, reg.indice_tvd)
           and (nombres is None or c.nombre in nombres)]
    datos = []
    for k in idx:
        c = reg.columnas[k]
        d = np.where(_validos(c.datos), c.datos, np.nan).astype(float)
        if escala_log(c.unidad):
            with np.errstate(all="ignore"):
                d = np.where(d > 0, np.log10(np.where(d > 0, d, 1)), np.nan)
        if sel is not None:
            d = np.where(sel, d, np.nan)
        datos.append(d)
    n = len(idx)
    m = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(i, n):
            ok = np.isfinite(datos[i]) & np.isfinite(datos[j])
            if ok.sum() >= 3 and np.std(datos[i][ok]) > 0 and np.std(datos[j][ok]) > 0:
                m[i, j] = m[j, i] = float(np.corrcoef(datos[i][ok], datos[j][ok])[0, 1])
    return [reg.columnas[k].nombre for k in idx], m


def mahalanobis(X, umbral_p: float = 0.999) -> tuple[np.ndarray, np.ndarray, float]:
    """Distancia de Mahalanobis robusta (mediana y covarianza de las muestras centrales) de cada
    fila de X (n × p, NaN = falta). Devuelve (distancia², atípicas, umbral χ²)."""
    from scipy.stats import chi2
    X = np.asarray(X, float)
    ok = np.all(np.isfinite(X), axis=1)
    d2 = np.full(len(X), np.nan)
    p = X.shape[1] if X.ndim == 2 else 0
    lim = float(chi2.ppf(umbral_p, max(p, 1)))
    if p == 0 or ok.sum() < p + 5:
        return d2, np.zeros(len(X), bool), lim
    Y = X[ok]
    centro = np.median(Y, axis=0)
    cov = np.cov(Y, rowvar=False).reshape(p, p)
    # una pasada de recorte: se recalcula sin el 5 % más alejado para que los atípicos no inflen la covarianza
    inv = np.linalg.pinv(cov)
    r = np.einsum("ij,jk,ik->i", Y - centro, inv, Y - centro)
    nucleo_ = Y[r <= np.percentile(r, 95)]
    if len(nucleo_) > p + 2:
        centro = nucleo_.mean(axis=0)
        inv = np.linalg.pinv(np.cov(nucleo_, rowvar=False).reshape(p, p))
    d2[ok] = np.einsum("ij,jk,ik->i", Y - centro, inv, Y - centro)
    return d2, np.nan_to_num(d2, nan=0) > lim, lim


def paso_profundidad(prof) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """(profundidad media de cada intervalo, paso, irregular, paso típico). Un paso es irregular si
    se aparta más de un 1 % del paso típico (la mediana) o es ≤ 0."""
    p = np.asarray(prof, float)
    p = p[_validos(p)]
    if p.size < 2:
        return np.zeros(0), np.zeros(0), np.zeros(0, bool), 0.0
    dz = np.diff(p)
    tipico = float(np.median(dz))
    mal = (dz <= 0) | (np.abs(dz - tipico) > 0.01 * abs(tipico))
    return (p[:-1] + p[1:]) / 2, dz, mal, tipico


# líneas de litología del crossplot neutrón-densidad (aproximación de las cartas estándar,
# agua dulce, neutrón calibrado en caliza; ver D74)
LITOLOGIAS_ND = {"Sandstone": (2.65, lambda f: f - 0.04 * (1 - f)),
                 "Limestone": (2.71, lambda f: f),
                 "Dolomite": (2.87, lambda f: 0.01 + 1.2 * f)}


def lineas_nd(rho_fluido: float = 1.0, escala_neutron: float = 1.0, escala_densidad: float = 1.0,
              porosidades=None) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Por litología: (neutrón, densidad, porosidad) de 0 a 40 %. `escala_neutron` = 100 si el
    neutrón está en PU o %; `escala_densidad` = 1000 si la densidad está en kg/m3."""
    f = np.linspace(0, 0.4, 9) if porosidades is None else np.asarray(porosidades, float)
    out = {}
    for nombre, (rho_ma, neutron) in LITOLOGIAS_ND.items():
        out[nombre] = (neutron(f) * escala_neutron, (rho_ma - f * (rho_ma - rho_fluido)) * escala_densidad, f)
    return out


def escala_neutron(unidad: str) -> float:
    u = unidad.strip().upper()
    return 100.0 if u in ("PU", "%", "P.U.", "PERCENT", "LPU", "SPU") else 1.0


def escala_densidad(unidad: str) -> float:
    return 1000.0 if unidad.strip().upper().replace(" ", "") in ("KG/M3", "KG/M^3") else 1.0


def antes_despues(reg, nombre: str):
    """(profundidad, original llevada a la profundidad actual, actual, diferencia) o None si la curva
    no se editó."""
    from . import historial
    o = historial.original(reg, nombre)
    k = reg.indice_columna(nombre)
    if o is None or k < 0:
        return None
    actual = np.asarray(reg.columnas[k].datos, float)
    prof = reg.columnas[reg.indice_md].datos if reg.existe_columna(reg.indice_md) else \
        np.arange(len(actual), dtype=float)
    if len(o.datos) == len(actual):
        orig = np.asarray(o.datos, float)
    elif o.prof is not None:
        orig = historial.remuestrear_a(o.prof, o.datos, prof)
    else:
        return None
    ok = _validos(orig) & _validos(actual)
    dif = np.where(ok, actual - orig, np.nan)
    return prof, orig, actual, dif


def repetibilidad(prof, principal, prof_rep, repetida, tolerancia: float | None = None) -> dict | None:
    """Pasada repetida contra principal: la repetida se lleva a la profundidad de la principal y se
    calculan la diferencia y su estadística. `tolerancia` por defecto: 5 % del rango P10–P90 de la
    principal. Devuelve None si no hay solape."""
    from . import historial
    p = np.asarray(prof, float)
    a = np.asarray(principal, float)
    b = historial.remuestrear_a(prof_rep, repetida, p)
    ok = _validos(a) & _validos(b)
    if ok.sum() < 3:
        return None
    dif = np.where(ok, b - a, np.nan)
    d = dif[ok]
    if tolerancia is None:
        p10, p90 = np.percentile(a[ok], [10, 90])
        tolerancia = 0.05 * (p90 - p10) or 1e-9
    r = float(np.corrcoef(a[ok], b[ok])[0, 1]) if np.std(a[ok]) > 0 and np.std(b[ok]) > 0 else float("nan")
    return {"repetida": np.where(_validos(b), b, np.nan), "diferencia": dif, "muestras": int(ok.sum()),
            "media": float(d.mean()), "desv": float(d.std()), "r": r, "tolerancia": float(tolerancia),
            "dentro": float(100 * (np.abs(d) <= tolerancia).mean())}
