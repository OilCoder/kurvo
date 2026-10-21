"""Módulos "Depth Shifting" (desfase manual) y "Quick Plot" (gráfico rápido e histograma)."""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtWidgets import QDialog, QVBoxLayout

from ..i18n import tr
from ..calculos.graficos import desplazar, histograma
from ..nucleo.comun import NULO
from ..vista.dialogos import Campo, aviso, pedir
from .base import Modulo, agregar_resultado, contexto


class DepthShifting(Modulo):
    nombre = "Depth Shifting"

    def acciones_editor_logs(self, app):
        return [("Depth Shifting", lambda: self.ejecutar(app))]

    def ejecutar(self, app):
        _, reg, col = contexto(app)
        if reg is None:
            return
        v = pedir("Depth Shifting", [Campo("col", "Column Depth", "columna",
                                           reg.nombres()[max(col, 0)], reg.nombres()),
                                     Campo("shift", "Depth Shift", "float", 0.0),
                                     Campo("nueva", "Create New Column", "bool", True),
                                     Campo("nombre", "New column", "texto", "NewColumn")], app)
        if v is None or v["col"] < 0:
            return
        datos = desplazar(reg.columnas[v["col"]].datos, v["shift"])
        if v["nueva"]:
            if not v["nombre"]:
                aviso(app, tr("Empty name is not allowed!"))
                return
            agregar_resultado(app, v["nombre"], datos, reg.columnas[v["col"]].unidad)
        else:
            col = reg.columnas[v["col"]]
            app.editor_logs.editar("Depth shift", f"{col.nombre} {v['shift']:+g}", setattr, col, "datos",
                                   datos)


class VentanaGrafico(QDialog):
    def __init__(self, titulo, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(1039, 514)
        self.grafico = pg.PlotWidget()
        QVBoxLayout(self).addWidget(self.grafico)


class QuickPlot(Modulo):
    nombre = "Quick Plot"

    def acciones_editor_logs(self, app):
        return [("Quick plot data", lambda: self.curva(app)), ("Histogram plot", lambda: self.hist(app))]

    def curva(self, app):
        pozo, reg, col = contexto(app)
        if reg is None or not reg.existe_columna(col) or not reg.existe_columna(reg.indice_md):
            aviso(app, tr("Select a column and the MD depth column first."))
            return
        w = VentanaGrafico(reg.columnas[col].nombre, app)
        y = reg.columnas[reg.indice_md].datos
        x = reg.columnas[col].datos
        ok = (x != NULO) & (y != NULO)
        w.grafico.plot(x[ok], y[ok], pen=pg.mkPen("b", width=1), connect="finite")
        w.grafico.invertY(True)
        w.grafico.setLabel("bottom", tr("Value"))
        w.grafico.setLabel("left", tr("Depth"))
        w.grafico.setTitle(reg.columnas[col].nombre)
        w.show()
        app._ventanas.append(w)

    def hist(self, app):
        _, reg, col = contexto(app)
        if reg is None or not reg.existe_columna(col):
            return
        centros, pct, (lo, hi) = histograma(reg.columnas[col].datos, 20)
        w = VentanaGrafico(tr("Statistic Plot"), app)
        if len(centros):
            ancho = (hi - lo) / 20
            w.grafico.addItem(pg.BarGraphItem(x=centros, height=pct, width=ancho * 0.9, brush="c"))
            w.grafico.setYRange(0, max(1, pct.max()) * 1.05)
        w.grafico.setTitle(tr("Histogram of {0}").format(reg.columnas[col].nombre))
        w.grafico.setLabel("bottom", tr("Value"))
        w.grafico.setLabel("left", tr("Percentage"))
        w.show()
        app._ventanas.append(w)
