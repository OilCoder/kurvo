"""Importación DLIS y exportación CSV / Excel (mantenimiento, prioridad 8).

DLIS se lee con dlisio (dependencia opcional): cada frame de cada archivo lógico se convierte en
un registro con su canal índice como profundidad. Los canales con más de un valor por muestra
(imágenes, formas de onda) no caben en un LAS y se omiten, dejando constancia en `omitidos`."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .comun import NULO
from .las import RegistroLAS

# unidades de índice habituales en DLIS que conviene llevar a pies o metros
_INDICE = {"0.1 in": ("FT", 1 / 120.0), ".1in": ("FT", 1 / 120.0), "0.1in": ("FT", 1 / 120.0),
           "in": ("FT", 1 / 12.0), "0.5 ms": ("MS", 0.5), "mm": ("M", 0.001), "cm": ("M", 0.01)}


@dataclass
class FrameDLIS:
    registro: RegistroLAS
    archivo_logico: int
    frame: str
    omitidos: list[str] = field(default_factory=list)


def dlis_disponible() -> bool:
    try:
        import dlisio  # noqa: F401
        return True
    except ImportError:
        return False


def _texto(x) -> str:
    if x is None:
        return ""
    if isinstance(x, (list, tuple)):
        return ", ".join(map(str, x))
    return str(x).strip()


def leer_dlis(ruta, dlis_mod=None) -> list[FrameDLIS]:
    """Lee todos los frames del archivo. `dlis_mod` permite inyectar el módulo (pruebas)."""
    if dlis_mod is None:
        try:
            from dlisio import dlis as dlis_mod
        except ImportError as e:
            raise RuntimeError("DLIS support needs the 'dlisio' package (pip install dlisio).") from e
    out: list[FrameDLIS] = []
    with dlis_mod.load(str(ruta)) as archivos:
        for k, f in enumerate(archivos):
            pozo = ""
            try:
                origenes = list(f.origins)
                if origenes:
                    pozo = _texto(getattr(origenes[0], "well_name", "")) or _texto(getattr(origenes[0], "name", ""))
            except Exception:  # noqa: BLE001 - metadatos incompletos: se sigue sin nombre de pozo
                pozo = ""
            for fr in f.frames:
                datos = fr.curves()
                canales = list(fr.channels)
                if not canales:
                    continue
                reg = RegistroLAS(nombre=f"{Path(ruta).stem} {fr.name}".strip(), nombre_pozo=pozo)
                omitidos = []
                nombres_campos = list(datos.dtype.names or [])
                for i, ch in enumerate(canales):
                    campo = nombres_campos[i + 1] if len(nombres_campos) == len(canales) + 1 else ch.name
                    valores = np.asarray(datos[campo])
                    if valores.ndim != 1:
                        omitidos.append(f"{ch.name} {tuple(valores.shape[1:])}")
                        continue
                    valores = valores.astype(float)
                    unidad = _texto(getattr(ch, "units", ""))
                    if i == 0 and unidad.lower() in _INDICE:
                        unidad, factor = _INDICE[unidad.lower()]
                        valores = valores * factor
                    valores = np.where(np.isfinite(valores), valores, NULO)
                    nombre = ch.name
                    if reg.indice_columna(nombre) >= 0:
                        nombre = f"{nombre}_{i}"
                    reg.agregar_columna(nombre, valores, unidad, _texto(getattr(ch, "long_name", "")))
                if reg.n_columnas:
                    reg.fijar_indices(0, -1)
                    if reg.columnas[0].nombre.upper() in ("TDEP", "DEPT", "DEPTH", "MD", "INDEX"):
                        reg.columnas[0].nombre = "DEPT" if reg.indice_columna("DEPT") < 0 else reg.columnas[0].nombre
                    out.append(FrameDLIS(reg, k, fr.name, omitidos))
    return out


# ------------------------------------------------------------------ exportación
def tabla(reg) -> "pandas.DataFrame":  # noqa: F821
    import pandas as pd
    columnas = {}
    for c in reg.columnas:
        nombre = c.nombre if c.nombre not in columnas else f"{c.nombre}_{len(columnas)}"
        columnas[nombre] = np.where(c.datos == NULO, np.nan, c.datos)
    return pd.DataFrame(columnas)


def exportar_csv(reg, ruta, separador: str = ",", nulo: str = "", con_unidades: bool = True) -> None:
    """CSV con una fila de nombres y, opcionalmente, una de unidades. Nulos = `nulo` (vacío por defecto)."""
    import csv
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=separador)
        w.writerow([c.nombre for c in reg.columnas])
        if con_unidades:
            w.writerow([c.unidad for c in reg.columnas])
        for fila in range(reg.n_filas):
            w.writerow([nulo if c.datos[fila] == NULO else f"{c.datos[fila]:.6g}" for c in reg.columnas])


def _hoja(nombre: str, usados: set[str]) -> str:
    base = "".join(ch for ch in nombre if ch not in '[]:*?/\\')[:31] or "Log"
    n, k = base, 1
    while n.lower() in usados:
        sufijo = f"~{k}"
        n = base[:31 - len(sufijo)] + sufijo
        k += 1
    usados.add(n.lower())
    return n


def exportar_excel(registros, ruta) -> list[str]:
    """`registros`: lista de (pozo, registro). Una hoja por registro y una hoja "Curves" con la
    lista de curvas (unidad, descripción, mín., máx., % nulos). Devuelve los nombres de hoja."""
    import pandas as pd
    usados: set[str] = {"curves"}
    hojas = []
    resumen = []
    with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
        for pozo, reg in registros:
            hoja = _hoja(f"{pozo} {reg.nombre}" if pozo else reg.nombre, usados)
            df = tabla(reg)
            df.columns = [f"{c.nombre} [{c.unidad}]" if c.unidad else c.nombre for c in reg.columnas][:len(df.columns)]
            df.to_excel(xw, sheet_name=hoja, index=False)
            hojas.append(hoja)
            for c in reg.columnas:
                v = c.datos[c.datos != NULO]
                resumen.append({"Sheet": hoja, "Well": pozo, "Log": reg.nombre, "Curve": c.nombre, "Unit": c.unidad,
                                "Description": c.descripcion, "Min": float(v.min()) if v.size else None,
                                "Max": float(v.max()) if v.size else None,
                                "Null %": round(100 * (1 - v.size / max(len(c.datos), 1)), 2)})
        pd.DataFrame(resumen).to_excel(xw, sheet_name="Curves", index=False)
    return hojas
