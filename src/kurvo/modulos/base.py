"""Interfaz de los módulos (Pickett, Hingle, calculadora...): nombre, entradas de menú, carga y guardado.

Un módulo se descubre automáticamente en este paquete. Puede:
- `acciones_editor_logs(app)`: entradas para el menú contextual del editor de logs
  (lista de (texto, función) o (texto, [subentradas])), como hacen los plugins originales;
- `instalar(app)`: crear paneles/pestañas propias;
- `cargar(proyecto)` / `guardar(proyecto)`: persistir su estado en ANALYSES/ del proyecto."""
from __future__ import annotations

import numpy as np

from ..nucleo.comun import NULO


class Modulo:
    nombre = "Sin nombre"
    descripcion = ""

    def acciones_editor_logs(self, app) -> list:
        return []

    def instalar(self, app) -> None:
        pass

    def cargar(self, proyecto) -> None:
        pass

    def guardar(self, proyecto) -> None:
        pass


def contexto(app):
    """(pozo, registro, columna clicada) del editor de logs activo."""
    ed = app.editor_logs
    return ed.pozo(), ed.registro(), ed.columna_clic


def agregar_resultado(app, nombre: str, datos, unidad: str = "", descripcion: str = "") -> None:
    """Agrega (o reemplaza) la columna en el LAS activo, con registro en el historial."""
    _, reg, _ = contexto(app)
    datos = np.asarray(datos, dtype=float)
    datos = np.where(np.isfinite(datos), datos, NULO)

    def poner():
        i = reg.indice_columna(nombre)
        if i >= 0:
            reg.columnas[i].datos = datos
        else:
            reg.agregar_columna(nombre, datos, unidad, descripcion)
    app.editor_logs.editar("Add column" if reg.indice_columna(nombre) < 0 else "Replace column",
                           f"{nombre} {descripcion}".strip(), poner)
