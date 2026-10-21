"""Flujo de trabajo de mantenimiento por pozo y estado de cada paso (barra de pasos, "Siguiente paso"
y panel "Workflow").

Los siete pasos son las páginas de la barra superior (D123): Preparar → Revisar → Corregir →
Alinear y comparar → Reconstruir → Comprobar → Entregar. El estado se deduce de los datos
(validación, notas de QC, columnas generadas) y de la bitácora de cambios de cada registro, así que
no hay nada que guardar aparte (ver D57)."""
from __future__ import annotations

from dataclasses import dataclass

from ..i18n import tr
from . import qc, validacion

HECHO, AVISO, PENDIENTE, OPCIONAL = "done", "warning", "pending", "optional"

# (clave, título, acción del registro que lo abre); el orden es el de las páginas de la barra
PASOS = [("prepare", "Prepare", "import_las"),
         ("review", "Review", "qc_window"),
         ("correct", "Correct", "graphic_edit"),
         ("align", "Align and Compare", "normalize"),
         ("reconstruct", "Reconstruct", "deep_learning"),
         ("check", "Check", "qc_report"),
         ("deliver", "Deliver", "export_las")]

OPS_EDICION = ("Set to null", "Set to value", "Interpolate gaps", "Despike", "Smooth", "Clip", "Splice",
               "Manual edit", "Edit cell", "Restore original", "Despike curve", "Interpolate gaps of curve",
               "Clip curve to range", "Smooth curve")
OPS_PROFUNDIDAD = ("Normalize", "Auto depth shift", "Depth shift", "Depth Shifting")
OPS_EXPORTAR = ("Export LAS", "Export CSV", "Export Excel")
SUFIJOS_DL = ("_DL", "_FILL")


@dataclass
class EstadoPaso:
    clave: str
    titulo: str
    accion: str
    estado: str
    detalle: str = ""


def _ops(regs) -> list[str]:
    return [c.operacion for r in regs for c in r.historial.bitacora]


def _hay(ops, nombres) -> bool:
    return any(o == n or o.startswith(n + " (") for o in ops for n in nombres)


def estado_pozo(pozo, alias=None) -> list[EstadoPaso]:
    regs = list(pozo.logs)
    ops = _ops(regs)
    out = []

    def paso(clave, estado, detalle=""):
        k = next(p for p in PASOS if p[0] == clave)
        out.append(EstadoPaso(clave, tr(k[1]), k[2], estado, detalle))

    if not regs:
        paso("prepare", PENDIENTE, tr("no logs"))
        for clave, *_ in PASOS[1:]:
            paso(clave, PENDIENTE)
        return out

    errores = avisos = 0
    for r in regs:
        for p in validacion.validar(r):
            errores += p.nivel == validacion.ERROR
            avisos += p.nivel == validacion.AVISO
    detalle = tr("{0} log(s)").format(len(regs))
    if errores or avisos:
        detalle += " · " + tr("{0} error(s), {1} warning(s)").format(errores, avisos)
    paso("prepare", PENDIENTE if errores else AVISO if avisos else HECHO, detalle)

    estados = [e for r in regs for e in qc.notas(r, alias).values()]
    cuenta = {n: sum(e.nota == n for e in estados) for n in "ABC"}
    resumen = f"A {cuenta['A']} · B {cuenta['B']} · C {cuenta['C']}"
    peor = qc.peor_nota(estados)
    paso("review", HECHO if peor == "A" else AVISO, resumen)

    editado = _hay(ops, OPS_EDICION)
    paso("correct", HECHO if editado else (PENDIENTE if peor == "C" else OPCIONAL),
         tr("{0} change(s)").format(sum(_hay([o], OPS_EDICION) for o in ops)) if editado
         else tr("{0} curve(s) with grade C").format(cuenta["C"]) if peor == "C" else "")

    prof = _hay(ops, OPS_PROFUNDIDAD)
    paso("align", HECHO if prof else OPCIONAL)

    dl = [c.nombre for r in regs for c in r.columnas if c.nombre.upper().endswith(SUFIJOS_DL)]
    paso("reconstruct", HECHO if dl else OPCIONAL, ", ".join(dl[:3]) + ("…" if len(dl) > 3 else ""))

    if editado or prof or dl:
        paso("check", HECHO if peor != "C" else AVISO, resumen)
    else:
        paso("check", PENDIENTE)

    exportado = _hay(ops, OPS_EXPORTAR)
    paso("deliver", HECHO if exportado else PENDIENTE)
    return out


def siguiente(pasos: list[EstadoPaso]) -> int:
    """Índice del primer paso pendiente, o con avisos mientras no se haya hecho ninguno posterior
    (recién importado, "Revisar" con notas B va antes que "Comprobar"); -1 si no queda ninguno."""
    for i, p in enumerate(pasos):
        if p.estado == PENDIENTE:
            return i
        if p.estado == AVISO and not any(q.estado == HECHO for q in pasos[i + 1:]):
            return i
    return -1
