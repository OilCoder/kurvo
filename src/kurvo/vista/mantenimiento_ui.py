"""Diálogos de mantenimiento a nivel de registro: remuestreo, unidades y mnemónicos."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from ..nucleo import mnemonicos, remuestreo, unidades
from ..nucleo.comun import NULO
from ..nucleo.validacion import paso_regular
from .dialogos import Campo, aviso, pedir
from ..i18n import tr
from .dialogos import BarraAplicar


def remuestrear(ed):
    reg = ed.registro()
    if reg is None:
        return
    if not reg.existe_columna(reg.indice_md):
        aviso(ed, tr('Please select log column for "Depth MD" first.'))
        return
    p = reg.columnas[reg.indice_md].datos
    v = p[(p != NULO) & np.isfinite(p)]
    actual = paso_regular(p)
    sugerido = actual or (float(np.median(np.abs(np.diff(np.sort(v))))) if v.size > 1 else 0.5)
    v = pedir(tr("Resample — current step: {0}").format(f"{actual:g}" if actual else tr("irregular")), [
        Campo("paso", "New step", "float", round(sugerido, 4) or 0.5, minimo=1e-4, maximo=1e5),
        Campo("ini", "Start depth", "float", float(v.min()) if v.size else 0.0),
        Campo("fin", "End depth", "float", float(v.max()) if v.size else 0.0),
        Campo("met", "Method", "opcion", "auto", ["auto", "linear", "nearest", "average"], traducir_opciones=True),
        Campo("ali", "Align depths to multiples of the step", "bool", True)], ed)
    if not v:
        return
    try:
        n = ed.editar("Resample", f"step {v['paso']:g}, {v['met']}, {v['ini']:g}-{v['fin']:g}",
                      remuestreo.remuestrear, reg, v["paso"], v["ini"], v["fin"], v["met"], v["ali"])
    except ValueError as e:
        aviso(ed, str(e))
        return
    ed.app.registrar(tr("Resampled {0}: {1} rows, step {2}").format(reg.nombre, n, f"{v['paso']:g}"))


def convertir_unidades(ed):
    reg, c = ed.registro(), ed.columna_clic
    if reg is None or not reg.existe_columna(c):
        aviso(ed, tr("Select a curve first: click its column in the Basic Log Editor or its node in the "
                     "project tree."))
        return
    col = reg.columnas[c]
    opciones = unidades.destinos(col.unidad)
    if not opciones:
        aviso(ed, tr("Unit '{0}' of {1} is not recognised. Known units: ").format(col.unidad, col.nombre)
              + ", ".join(u for us in unidades.MAGNITUDES.values() for u in us))
        return
    es_prof = c in (reg.indice_md, reg.indice_tvd)
    campos = [Campo("a", tr("Convert {0} from {1} to").format(col.nombre, col.unidad), "opcion", opciones[0], opciones)]
    if es_prof:
        campos.append(Campo("ambas", "Convert MD and TVD together", "bool", True))
    v = pedir("Convert Units", campos, ed)
    if not v:
        return
    if es_prof and v.get("ambas"):
        ed.editar("Convert units", f"depth {col.unidad} -> {v['a']}", unidades.convertir_profundidad, reg, v["a"])
    else:
        ed.editar("Convert units", f"{col.nombre} {col.unidad} -> {v['a']}", unidades.convertir_columna,
                  reg, c, v["a"])


class DialogoMnemonicos(QDialog):
    """Vista previa de la estandarización: se puede desmarcar o cambiar cada nombre."""

    def __init__(self, parent, reg, alias):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('Standardize Mnemonics')} — {reg.nombre}")
        self.propuestas = mnemonicos.proponer(reg, alias)
        t = QTableWidget(len(self.propuestas), 4)
        t.setHorizontalHeaderLabels([tr("Current"), tr("Standard"), tr("Group"), tr("Note")])
        for i, p in enumerate(self.propuestas):
            a = QTableWidgetItem(p.actual)
            a.setFlags((a.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            a.setCheckState(Qt.Checked if p.aplicable else Qt.Unchecked)
            t.setItem(i, 0, a)
            t.setItem(i, 1, QTableWidgetItem(p.nuevo))
            for j, txt in ((2, p.grupo), (3, tr(p.motivo))):
                it = QTableWidgetItem(txt)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                t.setItem(i, j, it)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla = t
        b = BarraAplicar(self, aplicar=self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Curves found in the alias database (Advance → Log Grouping). "
                                "Uncheck or edit the standard name before applying.")
                             if self.propuestas else tr("No curve needs renaming.")))
        lay.addWidget(t)
        lay.addWidget(b)
        self.resize(640, 400)

    def elegidas(self) -> list[mnemonicos.Propuesta]:
        out = []
        for i, p in enumerate(self.propuestas):
            if self.tabla.item(i, 0).checkState() == Qt.Checked:
                p.nuevo = self.tabla.item(i, 1).text().strip() or p.nuevo
                p.motivo = ""
                out.append(p)
        return out


def estandarizar(ed):
    reg = ed.registro()
    if reg is None:
        return
    d = DialogoMnemonicos(ed, reg, ed.app.alias)
    if d.exec() != QDialog.Accepted:
        return
    elegidas = d.elegidas()
    usados = [c.nombre.upper() for k, c in enumerate(reg.columnas) if k not in {p.indice for p in elegidas}]
    nuevos = [p.nuevo.upper() for p in elegidas]
    repetidos = {n for n in nuevos if nuevos.count(n) > 1 or n in usados}
    if repetidos:
        aviso(ed, tr("Name is already used! Please use a different name: ") + ", ".join(sorted(repetidos)))
        return
    ed.editar("Standardize mnemonics", ", ".join(f"{p.actual}->{p.nuevo}" for p in elegidas),
              mnemonicos.aplicar, reg, elegidas)
