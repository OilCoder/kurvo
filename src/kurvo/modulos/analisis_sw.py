"""Módulos "Pickett Plot" y "Hingle Plot": paneles con sus datos guardados en el proyecto."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QListWidget, QListWidgetItem, QSplitter, QVBoxLayout, QWidget)

from ..i18n import tr
from ..calculos.graficos import (AnalisisSw, ConjuntoDatos, linea_hingle, linea_pickett,
                                 sw_archie_recortada, y_hingle)
from ..nucleo.comun import NULO, UID
from ..nucleo.proyecto import Analisis
from ..vista.dialogos import Campo, aviso, boton, pedir
from .base import Modulo

COLORES = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]


class PanelSw(QWidget):
    def __init__(self, app, tipo: str):
        super().__init__()
        self.app, self.tipo = app, tipo
        self.analisis: list[tuple[Analisis, AnalisisSw]] = []
        self.ch_an = QComboBox()
        b_nuevo, b_borrar = boton("New", "new", "New analysis"), boton("Delete", "delete", "Delete this analysis")
        b_datos = boton("Add dataset...", "add", "Add the porosity and Rt of a well interval")
        b_sw = boton("Add Sw...", "add", "Add a constant Sw line")
        b_exp = boton("Export...", "export", "Save the plot as a PNG image")
        self.sp = {}
        form = QFormLayout()
        for k, et in (("a", "Constant a"), ("m", "m"), ("n", "n"), ("rw", "Rw")):
            s = QDoubleSpinBox()
            s.setDecimals(4)
            s.setRange(0.0001, 1e6)
            s.valueChanged.connect(self._params)
            self.sp[k] = s
            form.addRow(et, s)
        self.lista_datos, self.lista_sw = QListWidget(), QListWidget()
        izq = QWidget()
        li = QVBoxLayout(izq)
        fila = QHBoxLayout()
        for w in (self.ch_an, b_nuevo, b_borrar):
            fila.addWidget(w)
        li.addLayout(fila)
        li.addLayout(form)
        li.addWidget(QLabel(tr("Datasets")))
        li.addWidget(self.lista_datos)
        li.addWidget(b_datos)
        li.addWidget(QLabel(tr("Sw lines")))
        li.addWidget(self.lista_sw)
        li.addWidget(b_sw)
        li.addWidget(b_exp)
        izq.setMaximumWidth(300)
        self.grafico = pg.PlotWidget()
        self.grafico_sw = pg.PlotWidget()
        self.grafico_sw.invertY(True)
        sp = QSplitter()
        sp.addWidget(izq)
        sp.addWidget(self.grafico)
        sp.addWidget(self.grafico_sw)
        sp.setStretchFactor(1, 3)
        sp.setStretchFactor(2, 1)
        QVBoxLayout(self).addWidget(sp)
        self.ch_an.currentIndexChanged.connect(self._cargar)
        b_nuevo.clicked.connect(self.nuevo)
        b_borrar.clicked.connect(self.borrar)
        b_datos.clicked.connect(self.agregar_datos)
        b_sw.clicked.connect(self.agregar_sw)
        b_exp.clicked.connect(self.exportar)
        self.lista_datos.itemChanged.connect(self._visibles)
        self.lista_sw.itemChanged.connect(self._visibles)
        self._cargando = False

    # ------------------------------------------------------------ persistencia
    def desde_proyecto(self, pr) -> None:
        self.analisis = [(a, AnalisisSw.desde_texto(a.contenido)) for a in pr.analisis if a.tipo == self.tipo]
        self._combo()

    def a_proyecto(self, pr) -> None:
        pr.analisis = [a for a in pr.analisis if a.tipo != self.tipo]
        for meta, an in self.analisis:
            meta.contenido = an.a_texto()
            pr.analisis.append(meta)

    def _combo(self):
        self._cargando = True
        self.ch_an.clear()
        self.ch_an.addItems([m.nombre for m, _ in self.analisis])
        self._cargando = False
        self._cargar()

    def actual(self) -> AnalisisSw | None:
        i = self.ch_an.currentIndex()
        return self.analisis[i][1] if 0 <= i < len(self.analisis) else None

    def nuevo(self):
        nombre, ok = QInputDialog.getText(self, self.tipo, tr("Name"), text=f"{self.tipo}-{len(self.analisis) + 1}")
        if ok and nombre.strip():
            self.analisis.append((Analisis(self.tipo, UID.nuevo(), nombre.strip(), "0", ""), AnalisisSw()))
            self._combo()
            self.ch_an.setCurrentIndex(len(self.analisis) - 1)
            self.app.proyecto.modificado = True

    def borrar(self):
        i = self.ch_an.currentIndex()
        if 0 <= i < len(self.analisis):
            del self.analisis[i]
            self._combo()
            self.app.proyecto.modificado = True

    # ------------------------------------------------------------ edición
    def _cargar(self, *_):
        if self._cargando:
            return
        an = self.actual()
        self._cargando = True
        for k, s in self.sp.items():
            s.setValue(getattr(an, k) if an else 1.0)
        self.lista_datos.clear()
        self.lista_sw.clear()
        if an:
            for c in an.conjuntos:
                it = QListWidgetItem(f"{c.nombre} ({c.pozo})")
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if c.visible else Qt.Unchecked)
                self.lista_datos.addItem(it)
            for sw, vis in zip(an.sw, an.sw_visible):
                it = QListWidgetItem("Sw = %g" % sw)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if vis else Qt.Unchecked)
                self.lista_sw.addItem(it)
        self._cargando = False
        self.graficar()

    def _params(self, *_):
        an = self.actual()
        if an is None or self._cargando:
            return
        for k, s in self.sp.items():
            setattr(an, k, s.value())
        self.app.proyecto.modificado = True
        self.graficar()

    def _visibles(self, *_):
        an = self.actual()
        if an is None or self._cargando:
            return
        for i, c in enumerate(an.conjuntos):
            c.visible = self.lista_datos.item(i).checkState() == Qt.Checked
        an.sw_visible = [self.lista_sw.item(i).checkState() == Qt.Checked for i in range(self.lista_sw.count())]
        self.graficar()

    def agregar_sw(self):
        an = self.actual()
        if an is None:
            return
        v, ok = QInputDialog.getDouble(self, tr("Sw line"), tr("Add new Sw line:"), 0.5, 0.0, 1.0, 3)
        if ok:
            try:
                an.agregar_sw(v)
            except ValueError as e:
                aviso(self, str(e))
            self._cargar()

    def agregar_datos(self):
        """Datos del gráfico: pozo, LAS, columnas φ y Rt, intervalo de profundidad (MD)."""
        an, pr = self.actual(), self.app.proyecto
        if an is None:
            aviso(self, tr("Create an analysis first."))
            return
        pozos = [p.nombre for p in pr.pozos]
        v = pedir("Dataset", [Campo("pozo", "Well", "opcion", pozos[0] if pozos else "", pozos)], self)
        if v is None or not pozos:
            return
        pozo = pr.pozos[pozos.index(v["pozo"])]
        if not pozo.logs:
            aviso(self, tr("The well has no logs."))
            return
        logs = [r.nombre for r in pozo.logs]
        v2 = pedir("Dataset", [Campo("las", "Log", "opcion", logs[0], logs)], self)
        if v2 is None:
            return
        reg = pozo.logs[logs.index(v2["las"])]
        nombres = reg.nombres()
        md = reg.columnas[reg.indice_md].datos if reg.existe_columna(reg.indice_md) else None
        v3 = pedir("Dataset", [Campo("phi", "Porosity", "columna", nombres[0], nombres),
                               Campo("rt", "Rt", "columna", nombres[0], nombres),
                               Campo("top", "Top", "float", float(md.min()) if md is not None else 0),
                               Campo("bot", "Bottom", "float", float(md.max()) if md is not None else 0),
                               Campo("nombre", "Name", "texto", "DATASET")], self)
        if v3 is None or md is None:
            return
        sel = (md >= v3["top"]) & (md <= v3["bot"])
        c = ConjuntoDatos(f"{v3['nombre']} ({v3['top']:g}-{v3['bot']:g})", pozo.uid, reg.uid, pozo.nombre,
                          reg.nombre, nombres[v3["phi"]], nombres[v3["rt"]], v3["top"], v3["bot"], True,
                          md[sel].tolist(), reg.columnas[v3["phi"]].datos[sel].tolist(),
                          reg.columnas[v3["rt"]].datos[sel].tolist())
        an.conjuntos.append(c)
        self.app.proyecto.modificado = True
        self._cargar()

    def exportar(self):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export Plot"), "", "*.png")
        if ruta:
            self.grafico.grab().save(ruta)

    # ------------------------------------------------------------ gráficos
    def graficar(self):
        self.grafico.clear()
        self.grafico_sw.clear()
        an = self.actual()
        if an is None:
            return
        pickett = self.tipo == "Pickett"
        self.grafico.setLogMode(x=pickett, y=pickett)
        self.grafico.setLabel("bottom", tr("Rt (ohm-m)") if pickett else tr("Porosity (fraction)"))
        self.grafico.setLabel("left", tr("Porosity (fraction)") if pickett else tr("Rt^(-1/m)"))
        self.grafico_sw.setLabel("bottom", tr("Sw (fraction)"))
        self.grafico_sw.setLabel("left", tr("Depth"))
        self.grafico_sw.setXRange(0, 1)
        for k, c in enumerate(an.conjuntos):
            if not c.visible:
                continue
            phi, rt, prof = (np.array(x, dtype=float) for x in (c.phi, c.rt, c.prof))
            ok = (phi != NULO) & (rt != NULO) & (phi > 0) & (rt > 0)
            color = COLORES[k % len(COLORES)]
            if pickett:
                xs, ys = rt[ok], phi[ok]
            else:
                xs, ys = phi[ok], y_hingle(rt[ok], an.m)
            self.grafico.plot(xs, ys, pen=None, symbol="o", symbolSize=5, symbolBrush=color, name=c.nombre)
            sw = sw_archie_recortada(phi[ok], rt[ok], an.a, an.m, an.n, an.rw)
            self.grafico_sw.plot(sw, prof[ok], pen=pg.mkPen(color, width=1))
        for sw, vis in zip(an.sw, an.sw_visible):
            if not vis:
                continue
            pts = linea_pickett(sw, an.a, an.m, an.n, an.rw) if pickett else linea_hingle(sw, an.a, an.m, an.n, an.rw)
            xs, ys = zip(*pts)
            self.grafico.plot(list(xs), list(ys), pen=pg.mkPen("k", width=1, style=Qt.DashLine))
            t = pg.TextItem("%g" % sw, color="k", anchor=(0.5, 1) if pickett else (0, 0.5))
            x, y = pts[1]
            t.setPos(np.log10(x) if pickett else x, np.log10(y) if pickett else y)
            self.grafico.addItem(t)


class _PluginSw(Modulo):
    tipo = ""

    def instalar(self, app):
        self.panel = PanelSw(app, self.tipo)
        app.agregar_pestana(self.nombre, self.panel)

    def cargar(self, proyecto):
        if hasattr(self, "panel"):
            self.panel.desde_proyecto(proyecto)

    def guardar(self, proyecto):
        if hasattr(self, "panel"):
            self.panel.a_proyecto(proyecto)


class PickettPlot(_PluginSw):
    nombre = "Pickett Plot"
    tipo = "Pickett"


class HinglePlot(_PluginSw):
    nombre = "Hingle Plot"
    tipo = "Hingle"
