"""Interfaz de edición de curvas: menú "Curve Editing" del editor de logs, edición gráfica e
historial de cambios. La lógica está en nucleo/edicion.py y nucleo/historial.py."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..nucleo import edicion, historial
from ..nucleo.comun import NULO
from ..i18n import tr
from ..nucleo import preferencias
from .dialogos import BarraAplicar, Campo, aviso, boton, caja_botones, pedir


def profundidad(reg) -> tuple[np.ndarray, str]:
    """Profundidad de referencia: la MD del registro o, si no hay, el número de fila."""
    if reg.existe_columna(reg.indice_md):
        c = reg.columnas[reg.indice_md]
        return c.datos, f"{c.nombre} {c.unidad}".strip()
    return np.arange(1, reg.n_filas + 1, dtype=float), tr("Row")


def _rango(reg) -> tuple[float, float]:
    p, _ = profundidad(reg)
    v = p[(p != NULO) & np.isfinite(p)]
    return (float(v.min()), float(v.max())) if v.size else (0.0, 0.0)


def _campos_intervalo(reg) -> list[Campo]:
    lo, hi = _rango(reg)
    return [Campo("tope", "Top depth", "float", lo), Campo("base", "Bottom depth", "float", hi)]


# ------------------------------------------------------------------ acciones del menú
def acciones(ed) -> list[str]:
    """Claves (del registro de acciones de la ventana) del submenú "Curve Editing"."""
    return ["curve_null", "curve_value", "interpolate", "despike", "smooth", "clip", "splice", "-",
            "graphic_edit", "-", "compare_original", "restore_original"]


def _columna(ed):
    reg, c = ed.registro(), ed.columna_clic
    if reg is None or not reg.existe_columna(c):
        aviso(ed, tr("Select a curve first: click its column in the Basic Log Editor or its node in the "
                     "project tree."))
        return None, None
    return reg, c


def _aplicar_columna(ed, reg, c, operacion, detalle, nuevos):
    def poner():
        reg.columnas[c].datos = np.asarray(nuevos, float)
    ed.editar(operacion, detalle, poner)


def _pedir_con_vista(ed, reg, c, titulo, campos, calcular):
    """Diálogo de parámetros con vista previa antes/después de la curva (patrón común)."""
    p, _ = profundidad(reg)
    col = reg.columnas[c]
    etiqueta = f"{col.nombre} {col.unidad}".strip()

    def vista(v):
        return p, col.datos, calcular(v), etiqueta
    return pedir(f"{tr(titulo)} — {col.nombre}", campos, ed, vista_previa=vista)


def a_nulo(ed):
    reg, c = _columna(ed)
    if reg is None:
        return
    p, _ = profundidad(reg)
    calc = lambda v: edicion.a_nulo(reg.columnas[c].datos, p, v["tope"], v["base"])  # noqa: E731
    v = _pedir_con_vista(ed, reg, c, "Set Interval to Null", _campos_intervalo(reg), calc)
    if v:
        _aplicar_columna(ed, reg, c, "Set to null", f"{v['tope']:g}-{v['base']:g}", calc(v))


def constante(ed):
    reg, c = _columna(ed)
    if reg is None:
        return
    p, _ = profundidad(reg)
    calc = lambda v: edicion.poner_constante(reg.columnas[c].datos, p, v["tope"], v["base"], v["valor"])  # noqa: E731
    v = _pedir_con_vista(ed, reg, c, "Set Interval to Value",
                         _campos_intervalo(reg) + [Campo("valor", "Value", "float", 0.0)], calc)
    if v:
        _aplicar_columna(ed, reg, c, "Set to value", f"{v['tope']:g}-{v['base']:g} = {v['valor']:g}", calc(v))


def interpolar(ed):
    reg, c = _columna(ed)
    if reg is None:
        return
    p, _ = profundidad(reg)
    calc = lambda v: edicion.interpolar_huecos(reg.columnas[c].datos, p, v["max"], v["tope"],  # noqa: E731
                                               v["base"], v["met"])
    v = _pedir_con_vista(ed, reg, c, "Interpolate Gaps", _campos_intervalo(reg) + [
        Campo("max", "Max gap thickness (0 = any)", "float", 0.0, minimo=0),
        Campo("met", "Method", "opcion", "linear", ["linear", "pchip"], traducir_opciones=True)], calc)
    if v:
        _aplicar_columna(ed, reg, c, "Interpolate gaps", f"{v['met']}, max {v['max']:g}", calc(v))


def despike(ed):
    reg, c = _columna(ed)
    if reg is None:
        return
    p, _ = profundidad(reg)
    u = preferencias.actual().qc
    calc = lambda v: edicion.quitar_picos(reg.columnas[c].datos, p, v["ven"], v["umb"], v["rep"],  # noqa: E731
                                          v["tope"], v["base"], v.get("log", False))
    v = _pedir_con_vista(ed, reg, c, "Despike", _campos_intervalo(reg) + [
        Campo("ven", "Window (samples)", "int", u.ventana_picos, minimo=3, maximo=501),
        Campo("umb", "Threshold (robust sigmas)", "float", u.sigma_picos, minimo=0.5, maximo=50, decimales=2),
        Campo("rep", "Replace with", "opcion", "median", ["median", "null", "interpolate"], traducir_opciones=True),
        Campo("log", "Detect on log10 scale (resistivity)", "bool",
              edicion.escala_log(reg.columnas[c].unidad))], lambda v: calc(v)[0])
    if v:
        datos, n = calc(v)
        _aplicar_columna(ed, reg, c, "Despike", f"window {v['ven']}, {v['umb']:g} sigma, {v['rep']}, "
                         f"{n} spikes", datos)
        ed.app.registrar(tr("Despike: {0} spike(s) replaced in {1}").format(n, reg.columnas[c].nombre))


def suavizar(ed):
    reg, c = _columna(ed)
    if reg is None:
        return
    p, _ = profundidad(reg)
    calc = lambda v: edicion.suavizar(reg.columnas[c].datos, p, v["ven"], v["met"], v["tope"], v["base"])  # noqa: E731
    v = _pedir_con_vista(ed, reg, c, "Smooth", _campos_intervalo(reg) + [
        Campo("ven", "Window (samples)", "int", 5, minimo=3, maximo=501),
        Campo("met", "Method", "opcion", "mean", ["mean", "median", "gaussian"], traducir_opciones=True)], calc)
    if v:
        _aplicar_columna(ed, reg, c, "Smooth", f"{v['met']}, window {v['ven']}", calc(v))


def recortar(ed):
    reg, c = _columna(ed)
    if reg is None:
        return
    col = reg.columnas[c]
    p, _ = profundidad(reg)
    calc = lambda v: edicion.recortar(col.datos, v["min"], v["max"], v["modo"], p, v["tope"], v["base"])  # noqa: E731
    v = _pedir_con_vista(ed, reg, c, "Clip to Range", _campos_intervalo(reg) + [
        Campo("min", "Minimum", "float", col.minimo()), Campo("max", "Maximum", "float", col.maximo()),
        Campo("modo", "Out of range", "opcion", "clip", ["clip", "null"], traducir_opciones=True)],
        lambda v: calc(v)[0])
    if v:
        datos, n = calc(v)
        _aplicar_columna(ed, reg, c, "Clip", f"[{v['min']:g}, {v['max']:g}] {v['modo']}, {n} samples", datos)


def empalmar(ed):
    """Empalme de dos corridas que están en columnas del mismo LAS (p. ej. tras Combine Las)."""
    reg = ed.registro()
    if reg is None:
        return
    nombres = reg.nombres()
    c = ed.columna_clic if reg.existe_columna(ed.columna_clic) else 0
    p, _ = profundidad(reg)
    lo, hi = _rango(reg)

    def calc(v):
        if v["a"] < 0 or v["b"] < 0:
            raise ValueError(tr("Choose both runs."))
        return edicion.empalmar(p, reg.columnas[v["a"]].datos, reg.columnas[v["b"]].datos, v["prof"], v["tr"],
                                v["nivel"])

    def vista(v):
        return p, reg.columnas[v["a"]].datos, calc(v), nombres[v["a"]]
    v = pedir("Splice Runs", [
        Campo("a", "Upper run", "columna", nombres[c], nombres),
        Campo("b", "Lower run", "columna", nombres[min(c + 1, len(nombres) - 1)], nombres),
        Campo("prof", "Splice depth", "float", (lo + hi) / 2),
        Campo("tr", "Transition thickness", "float", 0.0, minimo=0),
        Campo("nivel", "Match level of lower run", "bool", False),
        Campo("nombre", "Result column", "texto", nombres[c] + "_SPL")], ed, vista_previa=vista)
    if not v or v["a"] < 0 or v["b"] < 0:
        return
    datos = calc(v)
    nombre = v["nombre"] or nombres[v["a"]] + "_SPL"

    def poner():
        i = reg.indice_columna(nombre)
        if i >= 0:
            reg.columnas[i].datos = datos
        else:
            reg.agregar_columna(nombre, datos, reg.columnas[v["a"]].unidad,
                                f"Splice {nombres[v['a']]}/{nombres[v['b']]} at {v['prof']:g}")
    ed.editar("Splice", f"{nombres[v['a']]} / {nombres[v['b']]} at {v['prof']:g}", poner)


def restaurar(ed):
    reg, c = _columna(ed)
    if reg is None:
        return
    nombre = reg.columnas[c].nombre
    if historial.original(reg, nombre) is None:
        aviso(ed, tr("{0} has not been edited; it is already the original curve.").format(nombre))
        return
    try:
        historial.restaurar_original(reg, nombre)
    except ValueError as e:
        aviso(ed, str(e))
    ed.actualizar_tabla()


def comparar_original(ed):
    reg, c = _columna(ed)
    if reg is None:
        return None
    nombre = reg.columnas[c].nombre
    o = historial.original(reg, nombre)
    if o is None:
        aviso(ed, tr("{0} has not been edited; there is no original version to compare.").format(nombre))
        return None
    if getattr(ed.app, "panel_qc", None) is not None:      # el antes/después vive en el panel de QC
        return ed.app.ventana_qc("before_after")
    d = QDialog(ed)
    d.setWindowTitle(tr("{0}: current vs original").format(nombre))
    g = pg.PlotWidget()
    g.invertY(True)
    g.addLegend()
    p, etiqueta = profundidad(reg)
    po = o.prof if o.prof is not None and len(o.prof) == len(o.datos) else p[:len(o.datos)]
    _trazar(g, o.datos, po, pg.mkPen((150, 150, 150), width=2), tr("original"))
    _trazar(g, reg.columnas[c].datos, p, pg.mkPen("b", width=1), tr("current"))
    g.setLabel("left", etiqueta)
    g.setLabel("bottom", f"{nombre} {reg.columnas[c].unidad}")
    QVBoxLayout(d).addWidget(g)
    d.resize(500, 800)
    d.show()
    ed.app._ventanas.append(d)
    return d


def _trazar(g, x, y, pluma, nombre=None):
    x = np.asarray(x, float)
    y = np.asarray(y, float)[:len(x)]
    x = x[:len(y)]
    ok = (x != NULO) & (y != NULO) & np.isfinite(x) & np.isfinite(y)
    xs, ys = np.where(ok, x, np.nan), np.where(ok, y, np.nan)
    return g.plot(xs, ys, pen=pluma, connect="finite", name=nombre)


# ------------------------------------------------------------------ edición gráfica
class EdicionGrafica(QDialog):
    """Curva contra profundidad con selección de intervalo y dibujo a mano alzada.

    - Arrastrar la franja (o sus bordes) elige el intervalo; los botones lo anulan, lo
      interpolan o le quitan los picos.
    - Con "Draw" activo, arrastrar con el botón izquierdo redibuja la curva por donde pasa el
      ratón. Cada acción queda en el historial (Undo en el diálogo o en el editor)."""

    def __init__(self, ed, reg, c):
        super().__init__(ed)
        self.ed, self.reg, self.c = ed, reg, c
        self.setWindowTitle(f"{tr('Graphic Edit')} — {reg.columnas[c].nombre}")
        self.g = pg.PlotWidget()
        self.g.invertY(True)
        self.g.showGrid(x=True, y=True, alpha=0.25)
        p, etiqueta = profundidad(reg)
        self.g.setLabel("left", etiqueta)
        self.g.setLabel("bottom", f"{reg.columnas[c].nombre} {reg.columnas[c].unidad}")
        lo, hi = _rango(reg)
        self.region = pg.LinearRegionItem(values=(lo + (hi - lo) * .4, lo + (hi - lo) * .6),
                                          orientation="horizontal", brush=(255, 200, 0, 50))
        self.g.addItem(self.region)
        self.curva_orig = None
        self.curva = None
        self.trazo: list[tuple[float, float]] = []
        self.linea_trazo = self.g.plot([], [], pen=pg.mkPen("r", width=2, style=Qt.DashLine))
        self.lbl = QLabel()
        b_nulo = boton("Null", "curve_null", "Set the yellow interval to null")
        b_interp = boton("Interpolate", "interpolate", "Null the yellow interval and interpolate across it")
        b_pico = boton("Despike", "despike", "Remove spikes inside the yellow interval")
        b_suav = boton("Smooth", "smooth", "Smooth the curve inside the yellow interval")
        self.b_dibujar = boton("Draw", "draw", "Drag with the left button to redraw the curve")
        self.b_dibujar.setCheckable(True)
        b_undo = boton("Undo", "undo", "Undo the last change to this log (Ctrl+Z)")
        b_redo = boton("Redo", "redo", "Redo (Ctrl+Y)")
        barra = QHBoxLayout()
        for w in (b_nulo, b_interp, b_pico, b_suav, self.b_dibujar, b_undo, b_redo):
            barra.addWidget(w)
        barra.addStretch(1)
        cerrar = BarraAplicar(self)
        lay = QVBoxLayout(self)
        lay.addLayout(barra)
        lay.addWidget(self.g)
        lay.addWidget(self.lbl)
        lay.addWidget(cerrar)
        u = preferencias.actual().qc
        b_nulo.clicked.connect(lambda: self._intervalo("Set to null", lambda d, p, a, b: edicion.a_nulo(d, p, a, b)))
        b_interp.clicked.connect(lambda: self._intervalo(
            "Interpolate gaps", lambda d, p, a, b: edicion.interpolar_huecos(edicion.a_nulo(d, p, a, b), p)))
        b_pico.clicked.connect(lambda: self._intervalo(
            "Despike", lambda d, p, a, b: edicion.quitar_picos(d, p, u.ventana_picos, u.sigma_picos, "median",
                                                               a, b)[0]))
        b_suav.clicked.connect(lambda: self._intervalo(
            "Smooth", lambda d, p, a, b: edicion.suavizar(d, p, 5, "mean", a, b)))
        b_undo.clicked.connect(lambda: (self.ed.deshacer(), self.redibujar()))
        b_redo.clicked.connect(lambda: (self.ed.rehacer(), self.redibujar()))
        self.b_dibujar.toggled.connect(self._modo_dibujo)
        self.g.scene().installEventFilter(self)
        self.resize(640, 860)
        self.redibujar()

    @property
    def nombre(self) -> str:
        return self.reg.columnas[self.c].nombre

    def redibujar(self):
        if not self.reg.existe_columna(self.c):
            self.reject()
            return
        p, _ = profundidad(self.reg)
        for item in (self.curva, self.curva_orig):
            if item is not None:
                self.g.removeItem(item)
        o = historial.original(self.reg, self.nombre)
        self.curva_orig = None
        if o is not None:
            po = o.prof if o.prof is not None and len(o.prof) == len(o.datos) else p
            self.curva_orig = _trazar(self.g, o.datos, po, pg.mkPen((160, 160, 160), width=2))
        self.curva = _trazar(self.g, self.reg.columnas[self.c].datos, p, pg.mkPen("b", width=1))
        a, b = self.region.getRegion()
        h = self.reg.historial
        self.lbl.setText(tr("Interval {0} – {1}   ·   {2} change(s) in log").format(
            f"{a:.2f}", f"{b:.2f}", len(h.bitacora)) + (tr("   ·   gray = original") if o is not None else ""))

    def _intervalo(self, operacion, funcion):
        a, b = sorted(self.region.getRegion())
        p, _ = profundidad(self.reg)
        nuevos = funcion(self.reg.columnas[self.c].datos, p, a, b)
        _aplicar_columna(self.ed, self.reg, self.c, operacion, f"graphic {a:.2f}-{b:.2f}", nuevos)
        self.redibujar()

    def _modo_dibujo(self, activo):
        self.g.setMouseEnabled(x=not activo, y=not activo)
        self.region.setMovable(not activo)

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if not self.b_dibujar.isChecked():
            return False
        t = ev.type()
        if t == QEvent.GraphicsSceneMousePress and ev.button() == Qt.LeftButton:
            self.trazo = [self._punto(ev)]
            return True
        if t == QEvent.GraphicsSceneMouseMove and self.trazo:
            self.trazo.append(self._punto(ev))
            xs, ys = zip(*self.trazo)
            self.linea_trazo.setData(list(xs), list(ys))
            return True
        if t == QEvent.GraphicsSceneMouseRelease and self.trazo:
            self.aplicar_trazo(self.trazo)
            self.trazo = []
            self.linea_trazo.setData([], [])
            return True
        return False

    def _punto(self, ev):
        q = self.g.getPlotItem().vb.mapSceneToView(ev.scenePos())
        return float(q.x()), float(q.y())

    def aplicar_trazo(self, trazo):
        p, _ = profundidad(self.reg)
        zs = [z for _, z in trazo]
        nuevos = edicion.pintar(self.reg.columnas[self.c].datos, p, trazo)
        _aplicar_columna(self.ed, self.reg, self.c, "Manual edit",
                         f"graphic draw {min(zs):.2f}-{max(zs):.2f}", nuevos)
        self.redibujar()


def edicion_grafica(ed):
    reg, c = _columna(ed)
    if reg is None:
        return None
    d = EdicionGrafica(ed, reg, c)
    d.show()
    ed.app._ventanas.append(d)
    return d


# ------------------------------------------------------------------ historial
class TablaHistorial(QWidget):
    """Bitácora de un registro (la usan el diálogo Change Log y el panel acoplable)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lbl = QLabel()
        self.tabla = QTableWidget(0, 5)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.lbl_orig = QLabel()
        self.lbl_orig.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.lbl)
        lay.addWidget(self.tabla, 1)
        lay.addWidget(self.lbl_orig)
        self.fijar(None)

    def fijar(self, reg) -> None:
        self.tabla.setHorizontalHeaderLabels([tr("Date"), tr("Operation"), tr("Curves"), tr("Detail"),
                                              tr("Samples")])
        if reg is None:
            self.tabla.setRowCount(0)
            self.lbl.setText(tr("No log selected."))
            self.lbl_orig.setText("")
            return
        h = reg.historial
        self.tabla.setRowCount(len(h.bitacora))
        for i, cambio in enumerate(reversed(h.bitacora)):
            for j, v in enumerate((cambio.fecha, tr(cambio.operacion), cambio.columnas, cambio.detalle,
                                   str(cambio.muestras))):
                self.tabla.setItem(i, j, QTableWidgetItem(v))
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.lbl.setText(f"<b>{reg.nombre}</b>   ·   " + tr("Undo steps: {0}   ·   Redo steps: {1}").format(
            len(h.deshacer), len(h.rehacer)))
        self.lbl_orig.setText(tr("Original versions kept for: {0}").format(", ".join(h.originales) or tr("(none)")))


class DialogoHistorial(QDialog):
    def __init__(self, ed, reg):
        super().__init__(ed)
        self.setWindowTitle(f"{tr('Change Log')} — {reg.nombre}")
        self.panel = TablaHistorial(self)
        self.panel.fijar(reg)
        self.tabla = self.panel.tabla
        b = caja_botones(QDialogButtonBox.Close)
        b.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.panel)
        lay.addWidget(b)
        self.resize(820, 420)
