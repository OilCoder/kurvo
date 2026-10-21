"""Validación de registros LAS y correcciones automáticas (mantenimiento, prioridad 7).

`validar(reg)` devuelve una lista de `Problema` (ERROR, WARNING o INFO). Si un problema se puede
corregir, lleva en `correccion` el nombre de la función de este módulo que lo arregla. Las
correcciones modifican el registro y se ejecutan a través de historial.aplicar."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .comun import NULO, a_float, formato_num
from .las import Mnemonico
from ..i18n import tr

ERROR, AVISO, INFO = "ERROR", "WARNING", "INFO"
SECCION_W = 1
UNIDADES_PROF = {"M", "FT", "F", "FEET", "METER", "METERS", "METRE", "METRES", "M.", "FT.", ".1IN"}
# nulos de otros sistemas que aparecen en archivos que declaran otro NULL (D107): -999 en un archivo
# con NULL -999.25 (curva DGA de los LAS del KGS). Ninguno es un valor físico de un registro.
NULOS_COMUNES = (-999.0, -9999.0, -99999.0, -999.9, -999.99, -999.95, -9999.25, -9999.9)

_alias = None


def fijar_alias(alias) -> None:
    """Base de alias con la que se reconocen los grupos (la de la ventana; si no, la de fábrica)."""
    global _alias
    _alias = alias


def _base_alias():
    global _alias
    if _alias is None:
        from .bases import alias_por_defecto
        _alias = alias_por_defecto()
    return _alias


def _grupo(nombre: str) -> str:
    a = _base_alias()
    g = a.grupo_de(nombre)
    return a.grupos[g].nombre.upper() if g >= 0 else nombre.strip().upper()


def unidad_sugerida(nombre: str, unidad: str, datos) -> str:
    """Unidad que indican los valores cuando la del archivo falta o no cuadra (D107): p. ej. PHIN en
    PU con valores de 0.1 (es V/V), DCAL en GAPI con valores de 8 (son pulgadas), DT en MS/F con
    valores de 60 (µs/ft). Solo se cambia la etiqueta, no los datos. Vacío si no hay sugerencia."""
    from .unidades import ALIAS, canonica, magnitud
    v = np.asarray(datos, float)
    v = v[_valida(v)]
    if v.size < 20:
        return ""
    med, p95 = float(np.median(v)), float(np.percentile(np.abs(v), 95))
    g, cu = _grupo(nombre), canonica(unidad)
    if g in ("PHIN", "PHID", "PHIS", "POR"):
        if cu in ("PU", "%") and p95 <= 1.0:
            return "V/V"
        if cu == "V/V" and med > 1.5 and p95 <= 100:
            return "PU"
        if cu == "":
            return "V/V" if p95 <= 1.0 else ("PU" if p95 <= 100 else "")
    elif g == "CAL" and magnitud(cu) != "length" and (cu == "" or cu in ALIAS.values()):
        # solo el hueco abierto: el tramo con el brazo cerrado (≈ −3…2.5) baja la mediana; una unidad
        # desconocida ("units" de C1/C2 en un registro de gas de lodo) no es un calibre mal etiquetado (D110)
        abierto = v[v >= 3]
        if abierto.size >= 20 and 3 <= float(np.median(abierto)) <= 30:
            return "IN"
    elif g == "DTC" and magnitud(cu) != "slowness" and 40 <= med <= (130 if cu == "" else 200):
        return "US/FT"
    elif g == "RHOB":
        if cu in ("", "G/CC") and 1500 <= med <= 3200:
            return "KG/M3"
        if cu in ("", "KG/M3") and 1.5 <= med <= 3.2:
            return "G/CC"
    elif g == "DRHO" and cu == "" and abs(med) < 0.5:
        return "G/CC"
    elif cu == "":
        return {"GR": "GAPI", "SP": "MV", "RESD": "OHMM", "RESM": "OHMM", "RESS": "OHMM", "RMIC": "OHMM",
                "COND": "MMHO/M", "PE": "B/E"}.get(g, "") if (g == "SP" or med > 0) else ""
    return ""


@dataclass
class Problema:
    nivel: str
    codigo: str
    mensaje: str
    correccion: str = ""          # función de este módulo que lo corrige (o "")
    filas: tuple[int, ...] = ()   # filas afectadas (base 0), si aplica

    def __str__(self) -> str:
        return f"[{self.nivel}] {self.mensaje}"


def _prof(reg):
    return reg.columnas[reg.indice_md].datos if reg.existe_columna(reg.indice_md) else None


def _valida(d):
    return (d != NULO) & np.isfinite(d)


def paso_regular(prof, tolerancia: float = 1e-3) -> float:
    """Paso constante del muestreo (0 si es irregular), como pide LAS 2.0 para STEP."""
    p = np.asarray(prof, float)
    p = p[_valida(p)]
    if len(p) < 2:
        return 0.0
    d = np.diff(p)
    paso = float(np.median(d))
    if paso == 0 or np.any(np.abs(d - paso) > tolerancia * max(abs(paso), 1e-9) + 1e-6):
        return 0.0
    return paso


def valores_cabecera(reg) -> dict[str, float]:
    """STRT, STOP, STEP y NULL que corresponden a los datos."""
    p = _prof(reg)
    if p is None or not _valida(p).any():
        return {"NULL": NULO}
    v = p[_valida(p)]
    return {"STRT": float(v[0]), "STOP": float(v[-1]), "STEP": paso_regular(p), "NULL": NULO}


def _w(reg, nombre: str) -> Mnemonico | None:
    return next((m for m in reg.mnemonicos if m.seccion == SECCION_W and m.nombre.upper() == nombre), None)


def validar(reg) -> list[Problema]:
    out: list[Problema] = []
    if reg.n_columnas == 0:
        return [Problema(ERROR, "NO_CURVES", tr("The log has no curves."))]
    if reg.n_filas == 0:
        out.append(Problema(ERROR, "NO_DATA", tr("The ~A section has no data rows.")))

    # ---------------------------------------------------------------- profundidad
    p = _prof(reg)
    if p is None:
        out.append(Problema(ERROR, "NO_DEPTH", tr("No depth (MD) column selected.")))
    else:
        col = reg.columnas[reg.indice_md]
        malas = np.where(~_valida(p))[0]
        if len(malas):
            out.append(Problema(ERROR, "NULL_DEPTH", tr("{0} row(s) with null or invalid depth.").format(len(malas)),
                                "quitar_filas_sin_profundidad", tuple(malas[:1000])))
        v = p[_valida(p)]
        if len(v) > 1:
            d = np.diff(v)
            dup = np.where(d == 0)[0]
            if len(dup):
                out.append(Problema(ERROR, "DUPLICATE_DEPTH", tr("{0} duplicated depth value(s) (first at {1}).").format(
                                    len(dup), formato_num(float(v[dup[0]]))), "quitar_duplicados",
                                    tuple(dup[:1000])))
            sube, baja = (d > 0).sum(), (d < 0).sum()
            if sube and baja:
                out.append(Problema(ERROR, "NOT_MONOTONIC", tr("Depth is not monotonic ({0} step(s) go against the main direction).").format(baja), "ordenar_por_profundidad"))
            elif baja and not sube:
                out.append(Problema(AVISO, "DECREASING", tr("Depth decreases downwards (bottom-up log)."),
                                    "ordenar_por_profundidad"))
            if not (sube and baja) and paso_regular(p) == 0 and not len(dup):
                pasos = np.abs(d)
                out.append(Problema(INFO, "IRREGULAR_STEP", tr("Irregular sampling (step {0} to {1}); STEP must be 0. Resample to a constant step "
                                       "if needed.").format(f"{float(pasos.min()):.6g}", f"{float(pasos.max()):.6g}")))
        if col.unidad.strip().upper() not in UNIDADES_PROF:
            out.append(Problema(AVISO, "DEPTH_UNIT", tr("Depth unit '{0}' is missing or not recognised (expected M or FT).").format(col.unidad)))

    # ---------------------------------------------------------------- cabecera ~W
    esperado = valores_cabecera(reg)
    faltan = [n for n in ("STRT", "STOP", "STEP", "NULL", "WELL") if _w(reg, n) is None]
    if faltan:
        out.append(Problema(AVISO, "HEADER_MISSING", tr("Missing ~W mnemonic(s): ") + ", ".join(faltan) + ".",
                            "actualizar_cabecera"))
    paso_ref = abs(esperado.get("STEP", 0)) or 1e-6
    for n in ("STRT", "STOP", "STEP"):
        m = _w(reg, n)
        if m is None or n not in esperado:
            continue
        valor = a_float(m.valor, np.nan)
        if not np.isfinite(valor) or abs(valor - esperado[n]) > paso_ref / 2 + 1e-6:
            out.append(Problema(ERROR if n != "STEP" else AVISO, f"HEADER_{n}",
                                tr("{0} in header is '{1}' but the data give {2}.").format(n, m.valor, formato_num(esperado[n])),
                                "actualizar_cabecera"))
    m = _w(reg, "WELL")
    if m is not None and not m.valor.strip():
        out.append(Problema(AVISO, "WELL_EMPTY", tr("WELL mnemonic is empty."), "actualizar_cabecera"))

    # ---------------------------------------------------------------- nulos y valores
    nulo = reg.nulo_archivo
    if nulo != NULO:
        n = sum(int(np.count_nonzero(c.datos == nulo)) for c in reg.columnas)
        if n:
            out.append(Problema(ERROR, "FILE_NULL", tr("{0} value(s) equal the file NULL {1}, which differs from {2} and would be taken as data.").format(
                                    n, formato_num(nulo), formato_num(NULO)), "convertir_nulos"))
    no_finitos = sum(int(np.count_nonzero(~np.isfinite(c.datos))) for c in reg.columnas)
    if no_finitos:
        out.append(Problema(ERROR, "NOT_FINITE", tr("{0} NaN/infinite value(s).").format(no_finitos), "convertir_nulos"))
    comunes = {c.nombre: int(np.count_nonzero(np.isin(c.datos, _nulos_comunes(reg)))) for c in reg.columnas}
    comunes = {n: k for n, k in comunes.items() if k}
    if comunes:
        out.append(Problema(AVISO, "UNDECLARED_NULL", tr("{0} value(s) equal a common null code (-999, -9999...) other "
                                                         "than the file NULL: {1}.").format(
                                sum(comunes.values()), ", ".join(f"{n} ({k})" for n, k in comunes.items())),
                            "convertir_nulos_comunes"))

    # ---------------------------------------------------------------- curvas
    nombres = [c.nombre.upper() for c in reg.columnas]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        out.append(Problema(ERROR, "DUPLICATE_CURVE", tr("Duplicated curve name(s): ") + ", ".join(repetidos) + ".",
                            "renombrar_duplicadas"))
    for k, c in enumerate(reg.columnas):
        if k == reg.indice_md:
            continue
        if len(c.datos) and not _valida(c.datos).any():
            out.append(Problema(AVISO, "EMPTY_CURVE", tr("Curve {0} has only null values.").format(c.nombre)))
        elif len(c.datos) and np.nanstd(np.where(_valida(c.datos), c.datos, np.nan)) == 0:
            out.append(Problema(INFO, "CONSTANT_CURVE", tr("Curve {0} is constant.").format(c.nombre)))
        if k == reg.indice_tvd:
            continue
        sugerida = unidad_sugerida(c.nombre, c.unidad, c.datos)
        if sugerida and not c.unidad.strip():
            out.append(Problema(INFO, "NO_UNIT", tr("Curve {0} has no unit; its values suggest {1}.").format(
                c.nombre, sugerida), "corregir_unidades"))
        elif sugerida:
            out.append(Problema(AVISO, "UNIT_MISMATCH", tr("Curve {0}: unit '{1}' does not match its values (median "
                                                           "{2}); they look like {3}.").format(
                c.nombre, c.unidad, formato_num(float(np.median(c.datos[_valida(c.datos)]))), sugerida),
                "corregir_unidades"))
        elif not c.unidad.strip():
            out.append(Problema(INFO, "NO_UNIT", tr("Curve {0} has no unit.").format(c.nombre)))
    return out


def resumen(problemas: list[Problema]) -> str:
    n = {lvl: sum(p.nivel == lvl for p in problemas) for lvl in (ERROR, AVISO, INFO)}
    return tr("{0} error(s), {1} warning(s), {2} note(s)").format(n[ERROR], n[AVISO], n[INFO])


# ------------------------------------------------------------------ correcciones
def _filtrar_filas(reg, mantener: np.ndarray) -> None:
    for c in reg.columnas:
        c.datos = c.datos[mantener]


def quitar_filas_sin_profundidad(reg) -> int:
    p = _prof(reg)
    if p is None:
        return 0
    ok = _valida(p)
    _filtrar_filas(reg, ok)
    return int((~ok).sum())


def ordenar_por_profundidad(reg) -> int:
    """Ordena las filas por profundidad creciente (orden estable)."""
    p = _prof(reg)
    if p is None:
        return 0
    orden = np.argsort(np.where(_valida(p), p, np.inf), kind="stable")
    cambiadas = int(np.count_nonzero(orden != np.arange(len(orden))))
    _filtrar_filas(reg, orden)
    return cambiadas


def quitar_duplicados(reg, criterio: str = "first") -> int:
    """Une filas con la misma profundidad: "first" conserva la primera, "mean" promedia los válidos."""
    p = _prof(reg)
    if p is None:
        return 0
    if np.any(np.diff(p[_valida(p)]) < 0):
        ordenar_por_profundidad(reg)
        p = _prof(reg)
    unicos, inicio, cuenta = np.unique(p, return_index=True, return_counts=True)
    if len(unicos) == len(p):
        return 0
    orden_inicio = np.sort(inicio)
    if criterio == "mean":
        for c in reg.columnas:
            nuevos = []
            for i0 in orden_inicio:
                bloque = c.datos[p == p[i0]]
                ok = bloque[_valida(bloque)]
                nuevos.append(float(ok.mean()) if ok.size else NULO)
            c.datos = np.array(nuevos)
    else:
        _filtrar_filas(reg, orden_inicio)
    return int(len(p) - len(unicos))


def convertir_nulos(reg) -> int:
    """Valores iguales al NULL del archivo, NaN o infinitos → −999.25."""
    n = 0
    for c in reg.columnas:
        malo = ~np.isfinite(c.datos)
        if reg.nulo_archivo != NULO:
            malo |= c.datos == reg.nulo_archivo
        n += int(malo.sum())
        c.datos = np.where(malo, NULO, c.datos)
    reg.nulo_archivo = NULO
    m = _w(reg, "NULL")
    if m is not None:
        m.valor = formato_num(NULO)
    return n


def _nulos_comunes(reg) -> list[float]:
    return [x for x in NULOS_COMUNES if x not in (reg.nulo_archivo, NULO)]


def convertir_nulos_comunes(reg) -> int:
    """Códigos de nulo de otros sistemas (-999, -9999...) → −999.25 (D107)."""
    otros = _nulos_comunes(reg)
    n = 0
    for k, c in enumerate(reg.columnas):
        if k == reg.indice_md:
            continue
        malo = np.isin(c.datos, otros)
        n += int(malo.sum())
        c.datos = np.where(malo, NULO, c.datos)
    return n


def corregir_unidades(reg) -> int:
    """Pone la unidad que indican los valores (unidad_sugerida) donde falta o no cuadra; no convierte
    los datos. Devuelve cuántas curvas cambió."""
    n = 0
    for k, c in enumerate(reg.columnas):
        if k in (reg.indice_md, reg.indice_tvd):
            continue
        u = unidad_sugerida(c.nombre, c.unidad, c.datos)
        if u:
            c.unidad = u
            n += 1
    return n


def renombrar_duplicadas(reg) -> int:
    vistos: dict[str, int] = {}
    n = 0
    for c in reg.columnas:
        u = c.nombre.upper()
        if u in vistos:
            vistos[u] += 1
            c.nombre = f"{c.nombre}_{vistos[u]}"
            n += 1
        else:
            vistos[u] = 0
    return n


def actualizar_cabecera(reg) -> int:
    """Escribe en ~W los STRT, STOP, STEP, NULL y WELL que corresponden a los datos."""
    vals = valores_cabecera(reg)
    unidad = reg.columnas[reg.indice_md].unidad if reg.existe_columna(reg.indice_md) else ""
    desc = {"STRT": "START DEPTH", "STOP": "STOP DEPTH", "STEP": "STEP", "NULL": "NULL VALUE",
            "WELL": "WELL"}
    n = 0
    for nombre in ("STRT", "STOP", "STEP", "NULL", "WELL"):
        if nombre == "WELL":
            valor = (reg.nombre_pozo.strip() or (_w(reg, "WELL").valor.strip() if _w(reg, "WELL") else "")
                     or reg.nombre.strip() or "UNKNOWN")
        elif nombre in vals:
            valor = formato_num(vals[nombre])
        else:
            continue
        m = _w(reg, nombre)
        u = unidad if nombre in ("STRT", "STOP", "STEP") else ""
        if m is None:
            reg.mnemonicos.append(Mnemonico(nombre, u, valor, desc[nombre], SECCION_W))
            n += 1
        elif m.valor != valor or (u and m.unidad != u):
            if nombre == "WELL" and m.valor.strip():
                continue
            m.valor, m.unidad = valor, u or m.unidad
            n += 1
    if not reg.nombre_pozo.strip():
        reg.nombre_pozo = _w(reg, "WELL").valor
    return n


def corregir(reg, problema: Problema) -> int:
    if not problema.correccion:
        return 0
    return globals()[problema.correccion](reg)


def corregir_todo(reg) -> list[str]:
    """Aplica todas las correcciones disponibles en un orden seguro; devuelve lo hecho."""
    hechas = []
    for nombre in ("convertir_nulos", "convertir_nulos_comunes", "quitar_filas_sin_profundidad",
                   "ordenar_por_profundidad", "quitar_duplicados", "renombrar_duplicadas", "corregir_unidades",
                   "actualizar_cabecera"):
        if any(p.correccion == nombre for p in validar(reg)):
            n = globals()[nombre](reg)
            hechas.append(f"{nombre}: {n}")
    return hechas
