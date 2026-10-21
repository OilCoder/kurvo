"""Archivo de proyecto de Kurvo (`.kurvo`, D124).

Un zip con:
- `proyecto.json`: pozos (nombre, coordenadas, trayectoria, registros, completaciones, litologías),
  zonas, plantillas, gráficos de registros, corte, análisis y ajustes de QC del proyecto, como JSON
  legible. Cada objeto se guarda con los mismos campos que tiene en memoria.
- `registros/<uid>.las`: cada registro en LAS 2.0, el estándar de la industria, legible con cualquier
  programa.
- `historial/<uid>.bitacora` y `historial/<uid>.originales`: la bitácora de cambios del registro y las
  curvas como estaban antes de editarlas.

`version` cambia solo si un archivo nuevo deja de poder leerse con el lector de una versión anterior."""
from __future__ import annotations

import dataclasses
import datetime as dt
import io
import json
import typing
import zipfile
from pathlib import Path

from . import historial
from .comun import UID
from .las import RegistroLAS

EXTENSION = ".kurvo"
FORMATO = "kurvo-proyecto"
VERSION = 1


class ErrorArchivo(Exception):
    pass


# ------------------------------------------------------------------ objetos ↔ JSON
def a_json(obj):
    """Dataclasses, listas, diccionarios y fechas a tipos de JSON."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: a_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [a_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): a_json(v) for k, v in obj.items()}
    if isinstance(obj, dt.date):
        return obj.isoformat()
    return obj


def desde_json(tipo, valor):
    """Reconstruye un objeto del tipo indicado (dataclass, list[...], dict[...], fecha o simple). Los
    campos que falten en el archivo toman su valor por defecto; los que sobren se ignoran."""
    if valor is None:
        return None
    origen = typing.get_origin(tipo)
    if dataclasses.is_dataclass(tipo):
        tipos = typing.get_type_hints(tipo)
        kw = {f.name: desde_json(tipos[f.name], valor[f.name]) for f in dataclasses.fields(tipo)
              if f.init and f.name in valor}
        obj = tipo(**kw)
        if isinstance(getattr(obj, "uid", None), int):
            UID.registrar(obj.uid)
        return obj
    if origen is list:
        (arg,) = typing.get_args(tipo)
        return [desde_json(arg, x) for x in valor]
    if origen is dict:
        _, arg = typing.get_args(tipo)
        return {k: desde_json(arg, v) for k, v in valor.items()}
    if tipo is dt.date:
        return dt.date.fromisoformat(valor)
    if tipo is float:
        return float(valor)
    if tipo is int:
        return int(valor)
    return valor


# ------------------------------------------------------------------ guardar
def guardar(pr, ruta: str | Path) -> None:
    from .. import __version__
    pozos = []
    archivos: dict[str, list[str]] = {}
    for p in pr.pozos:
        regs = []
        for r in p.logs:
            regs.append({"uid": r.uid, "nombre": r.nombre, "indice_md": r.indice_md, "indice_tvd": r.indice_tvd})
            archivos[f"registros/{r.uid}.las"] = r.lineas_las(p.nombre)
            if r.historial.bitacora:
                archivos[f"historial/{r.uid}.bitacora"] = historial.lineas_bitacora(r.historial)
            if r.historial.originales:
                archivos[f"historial/{r.uid}.originales"] = historial.lineas_originales(r.historial)
        pozos.append({"uid": p.uid, "nombre": p.nombre, "x": p.x, "y": p.y, "trayectoria": a_json(p.trayectoria),
                      "registros": regs, "completaciones": a_json(p.completaciones),
                      "litologias": a_json(p.litologias)})
    datos = {"formato": FORMATO, "version": VERSION, "aplicacion": f"Kurvo {__version__}",
             "pozos": pozos, "zonas": a_json(pr.zonas), "plantillas": a_json(pr.plantillas),
             "graficos": a_json(pr.logplots), "grafico_actual": pr.logplot_actual, "corte": a_json(pr.corte),
             "editores": pr.editores, "analisis": a_json(pr.analisis), "qc_ajustes": pr.qc_ajustes}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:   # rápido (D90)
        z.writestr("proyecto.json", json.dumps(datos, ensure_ascii=False, indent=1))
        for nombre, lineas in archivos.items():
            z.writestr(nombre, ("\n".join(lineas) + "\n").encode("utf-8"))
    Path(ruta).write_bytes(buf.getvalue())


# ------------------------------------------------------------------ abrir
def abrir(cls, ruta: str | Path):
    """Proyecto (de la clase `cls`) leído de un archivo .kurvo."""
    from .intervalos import Completacion, Litologia, Zona
    from .plantilla import Plantilla
    from .proyecto import Analisis, CorteTransversal, LogPlot, Pozo
    from .trayectoria import Trayectoria
    ruta = Path(ruta)
    try:
        zf = zipfile.ZipFile(ruta)
        datos = json.loads(zf.read("proyecto.json").decode("utf-8"))
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        raise ErrorArchivo("Unable to open the project: the file is damaged or is not a Kurvo "
                           "project.") from e
    with zf:
        if datos.get("formato") != FORMATO:
            raise ErrorArchivo("Unable to open the project: the file is not a Kurvo project.")
        if int(datos.get("version", 0)) > VERSION:
            raise ErrorArchivo("The project was saved by a newer version of Kurvo.")
        nombres = set(zf.namelist())

        def lineas(nombre: str) -> list[str]:
            return zf.read(nombre).decode("utf-8").splitlines() if nombre in nombres else []

        pr = cls(ruta=str(ruta))
        for dp in datos.get("pozos", []):
            pozo = Pozo(dp["nombre"], float(dp.get("x", 0.0)), float(dp.get("y", 0.0)),
                        uid=UID.registrar(int(dp["uid"])))
            pozo.trayectoria = desde_json(Trayectoria, dp.get("trayectoria", {}))
            for dr in dp.get("registros", []):
                uid = int(dr["uid"])
                reg = RegistroLAS.desde_lineas(lineas(f"registros/{uid}.las"))
                reg.nombre, reg.uid = dr["nombre"], UID.registrar(uid)
                reg.indice_md, reg.indice_tvd = int(dr.get("indice_md", -1)), int(dr.get("indice_tvd", -1))
                historial.leer_bitacora(reg.historial, lineas(f"historial/{uid}.bitacora"))
                historial.leer_originales(reg.historial, lineas(f"historial/{uid}.originales"))
                pozo.logs.append(reg)
            pozo.completaciones = desde_json(list[Completacion], dp.get("completaciones", []))
            pozo.litologias = desde_json(list[Litologia], dp.get("litologias", []))
            pr.pozos.append(pozo)
        pr.zonas = desde_json(list[Zona], datos.get("zonas", []))
        for z in pr.zonas:
            z.profundidades += [0.0] * (len(pr.pozos) - len(z.profundidades))
        pr.plantillas = desde_json(list[Plantilla], datos.get("plantillas", []))
        pr.logplots = desde_json(list[LogPlot], datos.get("graficos", []))
        pr.logplot_actual = int(datos.get("grafico_actual", -1))
        pr.corte = desde_json(CorteTransversal, datos.get("corte", {})) or CorteTransversal()
        pr.editores = {k: int(v) for k, v in datos.get("editores", {}).items()}
        pr.analisis = desde_json(list[Analisis], datos.get("analisis", []))
        pr.qc_ajustes = datos.get("qc_ajustes", "") or ""
    return pr
