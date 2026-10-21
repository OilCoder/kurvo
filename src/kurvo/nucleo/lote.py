"""Operaciones por lote sobre varios registros (mantenimiento, prioridad 5).

Cada operación se aplica registro a registro mediante historial.aplicar, así que cada pozo
conserva su bitácora y puede deshacer por separado. El resultado es un informe por registro."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..i18n import tr
from . import edicion, historial, mnemonicos, remuestreo, unidades, validacion
from .multipozo import buscar_curva


@dataclass
class Resultado:
    pozo: str
    registro: str
    ok: bool
    mensaje: str


@dataclass
class Operacion:
    clave: str
    titulo: str
    por_curva: bool = False            # necesita el nombre de una curva
    parametros: dict = field(default_factory=dict)


OPERACIONES = {
    "validate": Operacion("validate", "Validate LAS (report only)"),
    "fix": Operacion("fix", "Validate and fix all"),
    "mnemonics": Operacion("mnemonics", "Standardize mnemonics"),
    "resample": Operacion("resample", "Resample to constant step", parametros={"paso": 0.5, "metodo": "auto"}),
    "depth_units": Operacion("depth_units", "Convert depth units", parametros={"unidad": "M"}),
    "curve_units": Operacion("curve_units", "Convert curve units", True, {"unidad": "US/M"}),
    "despike": Operacion("despike", "Despike curve", True, {"ventana": 11, "umbral": 4.0}),
    "interpolate": Operacion("interpolate", "Interpolate gaps of curve", True, {"max_hueco": 0.0}),
    "clip": Operacion("clip", "Clip curve to range", True, {"vmin": 0.0, "vmax": 150.0, "modo": "clip"}),
    "smooth": Operacion("smooth", "Smooth curve", True, {"ventana": 5, "metodo": "mean"}),
}


def _curva(reg, nombre, alias):
    k = buscar_curva(reg, nombre, alias)
    if k < 0:
        raise LookupError(tr("curve {0} not found").format(nombre))
    return k


def ejecutar_uno(clave: str, reg, params: dict, curva: str = "", alias=None) -> str:
    """Aplica la operación a un registro y devuelve un mensaje corto. Lanza excepción si falla."""
    if clave == "validate":
        return validacion.resumen(validacion.validar(reg))
    if clave == "fix":
        hechas = historial.aplicar(reg, "Fix all (batch)", "", validacion.corregir_todo, reg)
        return (", ".join(hechas) or "nothing to fix") + " · now " + validacion.resumen(validacion.validar(reg))
    if clave == "mnemonics":
        props = mnemonicos.proponer(reg, alias)
        n = historial.aplicar(reg, "Standardize mnemonics (batch)",
                              ", ".join(f"{p.actual}->{p.nuevo}" for p in props if p.aplicable),
                              mnemonicos.aplicar, reg, props)
        omitidas = [p.actual for p in props if not p.aplicable]
        return tr("{0} renamed").format(n or 0) + (tr(", skipped {0}").format(", ".join(omitidas)) if omitidas else "")
    if clave == "resample":
        n = historial.aplicar(reg, "Resample (batch)", f"step {params['paso']:g}", remuestreo.remuestrear,
                              reg, params["paso"], None, None, params.get("metodo", "auto"))
        return tr("{0} rows").format(n)
    if clave == "depth_units":
        hechas = historial.aplicar(reg, "Convert depth units (batch)", params["unidad"],
                                   unidades.convertir_profundidad, reg, params["unidad"])
        return ("converted " + ", ".join(hechas)) if hechas else "already in " + params["unidad"]
    k = _curva(reg, curva, alias)
    c = reg.columnas[k]
    if clave == "curve_units":
        if unidades.canonica(c.unidad) == unidades.canonica(params["unidad"]):
            return tr("{0} already in {1}").format(c.nombre, params["unidad"])
        historial.aplicar(reg, "Convert units (batch)", f"{c.nombre} {c.unidad} -> {params['unidad']}",
                          unidades.convertir_columna, reg, k, params["unidad"])
        return f"{c.nombre} -> {params['unidad']}"
    prof = reg.columnas[reg.indice_md].datos if reg.existe_columna(reg.indice_md) else None
    if prof is None:
        raise ValueError("no MD depth column")
    if clave == "despike":
        nuevos, n = edicion.quitar_picos(c.datos, prof, params["ventana"], params["umbral"], "median",
                                         log=edicion.escala_log(c.unidad))
        detalle = tr("{0} spikes").format(n)
    elif clave == "interpolate":
        nuevos = edicion.interpolar_huecos(c.datos, prof, params["max_hueco"])
        detalle = tr("max gap {0}").format(f"{params['max_hueco']:g}")
    elif clave == "clip":
        nuevos, n = edicion.recortar(c.datos, params["vmin"], params["vmax"], params["modo"])
        detalle = tr("{0} samples out of [{1}, {2}]").format(n, f"{params['vmin']:g}", f"{params['vmax']:g}")
    elif clave == "smooth":
        nuevos = edicion.suavizar(c.datos, prof, params["ventana"], params["metodo"])
        detalle = f"{params['metodo']} {params['ventana']}"
    else:
        raise KeyError(clave)
    historial.aplicar(reg, OPERACIONES[clave].titulo + " (batch)", f"{c.nombre}: {detalle}",
                      setattr, c, "datos", nuevos)
    return f"{c.nombre}: {detalle}"


def ejecutar(clave: str, objetivos, params: dict | None = None, curva: str = "", alias=None) -> list[Resultado]:
    """`objetivos`: iterable de (nombre_pozo, registro)."""
    params = {**OPERACIONES[clave].parametros, **(params or {})}
    out = []
    for pozo, reg in objetivos:
        try:
            out.append(Resultado(pozo, reg.nombre, True, ejecutar_uno(clave, reg, params, curva, alias)))
        except Exception as e:  # noqa: BLE001 - el lote sigue con los demás registros
            out.append(Resultado(pozo, reg.nombre, False, str(e)))
    return out
