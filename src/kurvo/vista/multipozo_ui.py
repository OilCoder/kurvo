"""Diálogos de varios pozos: operaciones por lote, normalización y depth shift automático."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHeaderView, QLabel,
                               QLineEdit, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..nucleo import historial, lote, multipozo
from ..nucleo.comun import NULO
from .dialogos import Campo, aviso, pedir
from ..i18n import tr
from . import iconos
from .dialogos import BarraAplicar

COLORES = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40), (148, 103, 189),
           (140, 86, 75), (227, 119, 194), (127, 127, 127), (188, 189, 34), (23, 190, 207)]


def _tabla(encabezados, filas) -> QTableWidget:
    t = QTableWidget(len(filas), len(encabezados))
    t.setHorizontalHeaderLabels([tr(e) for e in encabezados])
    for i, fila in enumerate(filas):
        for j, v in enumerate(fila):
            it = QTableWidgetItem(v if isinstance(v, str) else f"{v:.4g}")
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            t.setItem(i, j, it)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _llenar(t: QTableWidget, filas) -> None:
    """Rellena una tabla de _tabla() con filas nuevas (sin reemplazar el widget)."""
    t.setRowCount(len(filas))
    for i, fila in enumerate(filas):
        for j, v in enumerate(fila):
            it = QTableWidgetItem(v if isinstance(v, str) else f"{v:.4g}")
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            t.setItem(i, j, it)
    t.resizeColumnsToContents()
    t.horizontalHeader().setStretchLastSection(True)


def nombres_curvas(pr) -> list[str]:
    vistos: list[str] = []
    for p in pr.pozos:
        for r in p.logs:
            for k, c in enumerate(r.columnas):
                if k not in (r.indice_md, r.indice_tvd) and c.nombre not in vistos:
                    vistos.append(c.nombre)
    return vistos


def intervalo_zona(pr, i_zona: int, i_pozo: int) -> tuple[float | None, float | None]:
    """Del tope de la zona al tope de la zona siguiente (más profunda) en ese pozo. Si el pozo no
    tiene ese tope (NULO, D104) el intervalo queda vacío: la zona no está en el pozo."""
    if i_zona < 0:
        return None, None
    tope = pr.zonas[i_zona].prof(i_pozo)
    if tope == NULO:
        return NULO, NULO
    debajo = [z.prof(i_pozo) for z in pr.zonas if z.prof(i_pozo) > tope]
    return tope, (min(debajo) if debajo else None)


# ====================================================================== lote
class DialogoLote(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(tr("Batch Operations"))
        self.arbol = QTreeWidget()
        self.arbol.setHeaderLabels([tr("Wells / logs")])
        for i, p in enumerate(app.proyecto.pozos):
            ip = QTreeWidgetItem([p.nombre])
            ip.setFlags(ip.flags() | Qt.ItemIsAutoTristate | Qt.ItemIsUserCheckable)
            ip.setCheckState(0, Qt.Checked)
            for j, r in enumerate(p.logs):
                h = QTreeWidgetItem([r.nombre])
                h.setFlags(h.flags() | Qt.ItemIsUserCheckable)
                h.setCheckState(0, Qt.Checked)
                h.setData(0, Qt.UserRole, (i, j))
                ip.addChild(h)
            self.arbol.addTopLevelItem(ip)
        self.arbol.expandAll()
        self.ch_op = QComboBox()
        for clave, op in lote.OPERACIONES.items():
            self.ch_op.addItem(tr(op.titulo), clave)
        self.ch_curva = QComboBox()
        self.ch_curva.setEditable(True)
        self.ch_curva.addItems(nombres_curvas(app.proyecto))
        self.ch_curva.setToolTip(tr("Curve name; logs without it use another curve of the same alias group"))
        form = QFormLayout()
        form.addRow(tr("Operation"), self.ch_op)
        form.addRow(tr("Curve"), self.ch_curva)
        izq = QWidget()
        li = QVBoxLayout(izq)
        li.addWidget(self.arbol)
        li.addLayout(form)
        self.resultados = QTableWidget(0, 4)
        self.resultados.setHorizontalHeaderLabels([tr("Well"), tr("Log"), tr("Status"), tr("Result")])
        self.resultados.horizontalHeader().setStretchLastSection(True)
        sp = QSplitter()
        sp.addWidget(izq)
        sp.addWidget(self.resultados)
        sp.setSizes([300, 600])
        self.barra = BarraAplicar(self, aplicar=lambda: self.ejecutar(), texto_aplicar="Run")
        self.barra.b_aplicar.setIcon(iconos.icono("run"))
        lay = QVBoxLayout(self)
        lay.addWidget(sp)
        lay.addWidget(self.barra)
        self.ch_op.currentIndexChanged.connect(self._op)
        self._op()
        self.resize(980, 520)

    def _op(self, *_):
        self.ch_curva.setEnabled(lote.OPERACIONES[self.ch_op.currentData()].por_curva)

    def objetivos(self):
        pr = self.app.proyecto
        out = []
        for i in range(self.arbol.topLevelItemCount()):
            ip = self.arbol.topLevelItem(i)
            for k in range(ip.childCount()):
                h = ip.child(k)
                if h.checkState(0) == Qt.Checked:
                    a, b = h.data(0, Qt.UserRole)
                    out.append((pr.pozos[a].nombre, pr.pozos[a].logs[b]))
        return out

    def parametros(self, clave) -> dict | None:
        op = lote.OPERACIONES[clave]
        p = op.parametros
        campos = {
            "resample": [Campo("paso", "Step", "float", p.get("paso"), minimo=1e-4),
                         Campo("metodo", "Method", "opcion", "auto", ["auto", "linear", "nearest", "average"],
                                traducir_opciones=True)],
            "depth_units": [Campo("unidad", "Depth unit", "opcion", "M", ["M", "FT"])],
            "curve_units": [Campo("unidad", "Target unit", "texto", p.get("unidad"))],
            "despike": [Campo("ventana", "Window (samples)", "int", 11, minimo=3, maximo=501),
                        Campo("umbral", "Threshold (robust sigmas)", "float", 4.0, minimo=0.5, decimales=2)],
            "interpolate": [Campo("max_hueco", "Max gap thickness (0 = any)", "float", 0.0, minimo=0)],
            "clip": [Campo("vmin", "Minimum", "float", 0.0), Campo("vmax", "Maximum", "float", 150.0),
                     Campo("modo", "Out of range", "opcion", "clip", ["clip", "null"], traducir_opciones=True)],
            "smooth": [Campo("ventana", "Window (samples)", "int", 5, minimo=3, maximo=501),
                       Campo("metodo", "Method", "opcion", "mean", ["mean", "median", "gaussian"],
                              traducir_opciones=True)],
        }.get(clave)
        if campos is None:
            return {}
        return pedir(op.titulo, campos, self)

    def ejecutar(self, *_, params: dict | None = None):
        clave = self.ch_op.currentData()
        objetivos = self.objetivos()
        if not objetivos:
            aviso(self, tr("Select at least one log."))
            return None
        if params is None:
            params = self.parametros(clave)
            if params is None:
                return None
        with self.app.operacion(lote.OPERACIONES[clave].titulo):
            res = lote.ejecutar(clave, objetivos, params, self.ch_curva.currentText().strip(), self.app.alias)
        self.resultados.setRowCount(len(res))
        for i, r in enumerate(res):
            for j, v in enumerate((r.pozo, r.registro, "OK" if r.ok else tr("FAILED"), r.mensaje)):
                it = QTableWidgetItem(v)
                if j == 2 and not r.ok:
                    it.setForeground(Qt.red)
                self.resultados.setItem(i, j, it)
        self.resultados.resizeColumnsToContents()
        if clave != "validate":
            self.app.proyecto.modificado = True
            self.app.refrescar_editores()
        n_ok = sum(r.ok for r in res)
        self.app.registrar(tr("Batch '{0}': {1}/{2} log(s) OK").format(tr(lote.OPERACIONES[clave].titulo), n_ok, len(res)) + "\n"
                           + "\n".join(f"{r.pozo}/{r.registro}: {r.mensaje}" for r in res))
        return res


# ====================================================================== normalización
class DialogoNormalizacion(QDialog):
    """Normalización de una curva entre pozos (percentiles bajo/alto a los del pozo de referencia).

    Primero calcula y muestra los percentiles y los histogramas antes/después; con "Apply" crea en
    cada pozo la columna <curva>_NORM (la curva original no se toca)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        pr = app.proyecto
        self.setWindowTitle(tr("Multi-well Normalization"))
        self.ch_curva = QComboBox()
        self.ch_curva.setEditable(True)
        self.ch_curva.addItems(nombres_curvas(pr))
        if self.ch_curva.findText("GR") >= 0:
            self.ch_curva.setCurrentText("GR")
        self.ch_ref = QComboBox()
        self.ch_ref.addItems([p.nombre for p in pr.pozos])
        self.ch_zona = QComboBox()
        self.ch_zona.addItem(tr("(whole log)"))
        self.ch_zona.addItems([z.nombre for z in pr.zonas])
        self.sp_bajo, self.sp_alto = QDoubleSpinBox(), QDoubleSpinBox()
        for sp, v in ((self.sp_bajo, 5.0), (self.sp_alto, 95.0)):
            sp.setRange(0, 100)
            sp.setValue(v)
        self.txt_sufijo = QLineEdit("_NORM")
        form = QFormLayout()
        form.addRow(tr("Curve"), self.ch_curva)
        form.addRow(tr("Reference well"), self.ch_ref)
        form.addRow(tr("Interval (zone top to next top)"), self.ch_zona)
        form.addRow(tr("Low percentile"), self.sp_bajo)
        form.addRow(tr("High percentile"), self.sp_alto)
        form.addRow(tr("New column suffix"), self.txt_sufijo)
        self.tabla = _tabla(["Well", "Log", "P low", "P high", "Gain", "Offset", "Samples"], [])
        self.g_antes, self.g_despues = pg.PlotWidget(title=tr("Before")), pg.PlotWidget(title=tr("After"))
        for g in (self.g_antes, self.g_despues):
            g.addLegend()
        graf = QSplitter()
        graf.addWidget(self.g_antes)
        graf.addWidget(self.g_despues)
        self.barra = BarraAplicar(self, self.calcular, self.aplicar)
        self.b_aplicar = self.barra.b_aplicar
        self.b_aplicar.setEnabled(False)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.tabla)
        lay.addWidget(graf, 1)
        lay.addWidget(self.barra)
        self.resultados: list[tuple[int, object, int, multipozo.Normalizacion]] = []
        self.resize(900, 760)

    def calcular(self):
        pr, alias = self.app.proyecto, self.app.alias
        curva = self.ch_curva.currentText().strip()
        i_ref, i_zona = self.ch_ref.currentIndex(), self.ch_zona.currentIndex() - 1
        bajo, alto = self.sp_bajo.value(), self.sp_alto.value()
        if alto <= bajo:
            aviso(self, tr("High percentile must be greater than low percentile."))
            return False
        datos = []
        for i, p in enumerate(pr.pozos):
            for r in p.logs:
                k = multipozo.buscar_curva(r, curva, alias)
                if k >= 0 and r.existe_columna(r.indice_md):
                    datos.append((i, r, k))
                    break
        ref = next((d for d in datos if d[0] == i_ref), None)
        if ref is None:
            aviso(self, tr("The reference well has no curve {0}.").format(curva))
            return False
        self.resultados = []
        errores = []
        try:
            t, b = intervalo_zona(pr, i_zona, i_ref)
            rb, ra, _ = multipozo.percentiles(ref[1].columnas[ref[2]].datos, multipozo.profundidad(ref[1]),
                                              t, b, bajo, alto)
        except ValueError as e:
            aviso(self, tr("Reference well: {0}").format(e))
            return False
        for i, r, k in datos:
            try:
                t, b = intervalo_zona(pr, i_zona, i)
                pb, pa, n = multipozo.percentiles(r.columnas[k].datos, multipozo.profundidad(r), t, b, bajo, alto)
            except ValueError as e:
                errores.append(f"{pr.pozos[i].nombre}: {e}")
                continue
            self.resultados.append((i, r, k, multipozo.Normalizacion(pr.pozos[i].nombre, r.columnas[k].nombre,
                                                                      pb, pa, rb, ra, n)))
        filas = [(n.pozo, r.nombre, n.p_bajo, n.p_alto, n.ganancia, n.desplazamiento, str(n.muestras))
                 for _, r, _, n in self.resultados]
        _llenar(self.tabla, filas)
        self._histogramas()
        self.b_aplicar.setEnabled(bool(self.resultados))
        if errores:
            aviso(self, "\n".join(errores))
        return True

    def _histogramas(self):
        for g in (self.g_antes, self.g_despues):
            g.clear()
        todos = np.concatenate([r.columnas[k].datos[(r.columnas[k].datos != NULO)] for _, r, k, _ in self.resultados]
                               or [np.zeros(1)])
        lo, hi = np.percentile(todos, [0.5, 99.5]) if todos.size > 1 else (0, 1)
        bordes = np.linspace(lo, hi, 41)
        for c, (i, r, k, n) in enumerate(self.resultados):
            d = r.columnas[k].datos
            pluma = pg.mkPen(COLORES[c % len(COLORES)], width=2)
            for g, x in ((self.g_antes, d), (self.g_despues, multipozo.normalizar(d, n.p_bajo, n.p_alto,
                                                                                   n.ref_bajo, n.ref_alto))):
                v = x[x != NULO]
                h, _ = np.histogram(v, bordes)
                g.plot(bordes, h / max(h.sum(), 1) * 100, stepMode="center", pen=pluma, name=n.pozo)

    def aplicar(self):
        sufijo = self.txt_sufijo.text().strip() or "_NORM"
        with self.app.operacion("Normalize wells"):
            for i, r, k, n in self.resultados:
                nombre = r.columnas[k].nombre + sufijo
                datos = multipozo.normalizar(r.columnas[k].datos, n.p_bajo, n.p_alto, n.ref_bajo, n.ref_alto)

                def poner(r=r, k=k, nombre=nombre, datos=datos):
                    j = r.indice_columna(nombre)
                    if j >= 0:
                        r.columnas[j].datos = datos
                    else:
                        r.agregar_columna(nombre, datos, r.columnas[k].unidad,
                                          f"Normalized to {self.ch_ref.currentText()}")
                historial.aplicar(r, "Normalize", f"{r.columnas[k].nombre}: gain {n.ganancia:.4g}, "
                                  f"offset {n.desplazamiento:.4g} (ref {self.ch_ref.currentText()})", poner)
        self.app.proyecto.modificado = True
        self.app.refrescar_editores()
        self.app.registrar(tr("Normalization applied to {0} well(s)").format(len(self.resultados)))
        self.b_aplicar.setEnabled(False)


# ====================================================================== depth shift automático
class DialogoDesfaseAuto(QDialog):
    """Depth shift automático: correlación cruzada entre una curva de referencia y la del
    registro a corregir; muestra r(Δ), las curvas superpuestas y aplica el desfase."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(tr("Automatic Depth Shift (cross-correlation)"))
        self.logs = [(p.nombre, r) for p in app.proyecto.pozos for r in p.logs]
        etiquetas = [f"{p} / {r.nombre}" for p, r in self.logs]
        self.ch_ref, self.ch_obj = QComboBox(), QComboBox()
        self.ch_ref.addItems(etiquetas)
        self.ch_obj.addItems(etiquetas)
        if len(etiquetas) > 1:
            self.ch_obj.setCurrentIndex(1)
        self.ch_curva = QComboBox()
        self.ch_curva.setEditable(True)
        self.ch_curva.addItems(nombres_curvas(app.proyecto))
        if self.ch_curva.findText("GR") >= 0:
            self.ch_curva.setCurrentText("GR")
        self.sp_max, self.sp_tope, self.sp_base = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        self.sp_max.setRange(0.01, 1e4)
        self.sp_max.setValue(10.0)
        for sp in (self.sp_tope, self.sp_base):
            sp.setRange(-1e6, 1e6)
            sp.setDecimals(2)
        self.sp_tope.setSpecialValueText(tr("(start)"))
        self.sp_tope.setValue(self.sp_tope.minimum())
        self.sp_base.setSpecialValueText(tr("(end)"))
        self.sp_base.setValue(self.sp_base.minimum())
        self.ch_modo = QComboBox()
        self.ch_modo.addItems([tr("Shift whole log (MD column)"), tr("Shift only the curve (new column)")])
        form = QFormLayout()
        form.addRow(tr("Reference log"), self.ch_ref)
        form.addRow(tr("Log to shift"), self.ch_obj)
        form.addRow(tr("Correlation curve"), self.ch_curva)
        form.addRow(tr("Max shift (±)"), self.sp_max)
        form.addRow(tr("Window top (reference depth)"), self.sp_tope)
        form.addRow(tr("Window bottom"), self.sp_base)
        form.addRow(tr("Apply as"), self.ch_modo)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.g_r = pg.PlotWidget(title=tr("Correlation vs shift"))
        self.g_r.setLabel("bottom", tr("Shift"))
        self.g_r.setLabel("left", "Pearson r")
        self.g_c = pg.PlotWidget(title=tr("Curves"))
        self.g_c.invertY(True)
        self.g_c.addLegend()
        graf = QSplitter()
        graf.addWidget(self.g_r)
        graf.addWidget(self.g_c)
        self.barra = BarraAplicar(self, self.calcular, self.aplicar, texto_aplicar="Apply Shift")
        self.b_aplicar = self.barra.b_aplicar
        self.b_aplicar.setEnabled(False)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(graf, 1)
        lay.addWidget(self.lbl)
        lay.addWidget(self.barra)
        self.resultado = None
        self.resize(980, 780)

    def _sel(self):
        (_, ref), (_, obj) = self.logs[self.ch_ref.currentIndex()], self.logs[self.ch_obj.currentIndex()]
        curva = self.ch_curva.currentText().strip()
        kr, ko = multipozo.buscar_curva(ref, curva, self.app.alias), multipozo.buscar_curva(obj, curva, self.app.alias)
        return ref, kr, obj, ko

    def calcular(self):
        ref, kr, obj, ko = self._sel()
        if kr < 0 or ko < 0:
            aviso(self, tr("Curve {0} not found in both logs.").format(self.ch_curva.currentText()))
            return None
        tope = None if self.sp_tope.value() == self.sp_tope.minimum() else self.sp_tope.value()
        base = None if self.sp_base.value() == self.sp_base.minimum() else self.sp_base.value()
        try:
            res = multipozo.desfase_por_correlacion(multipozo.profundidad(ref), ref.columnas[kr].datos,
                                                    multipozo.profundidad(obj), obj.columnas[ko].datos,
                                                    self.sp_max.value(), None, tope, base)
        except ValueError as e:
            aviso(self, str(e))
            return None
        self.resultado = (res, obj, ko)
        self.g_r.clear()
        self.g_r.plot(res.desfases, res.curva_r, pen=pg.mkPen("b", width=2))
        self.g_r.addItem(pg.InfiniteLine(res.desfase, pen=pg.mkPen("r", style=Qt.DashLine)))
        self.g_r.plot([res.desfase], [res.correlacion], pen=None, symbol="o", symbolSize=9, symbolBrush="r")
        marca = pg.TextItem(f"{res.desfase:+.3f} (r={res.correlacion:.3f})", color=(200, 0, 0), anchor=(0.5, 1.3))
        marca.setPos(res.desfase, res.correlacion)
        self.g_r.addItem(marca)
        self.g_c.clear()
        from .edicion_curvas import _trazar
        _trazar(self.g_c, ref.columnas[kr].datos, multipozo.profundidad(ref), pg.mkPen("k", width=1), tr("reference"))
        _trazar(self.g_c, obj.columnas[ko].datos, multipozo.profundidad(obj), pg.mkPen((150, 150, 150)), tr("before"))
        _trazar(self.g_c, obj.columnas[ko].datos, multipozo.profundidad(obj) + res.desfase,
                pg.mkPen("r", width=1), tr("after"))
        aviso_baja = tr("  (low correlation: check the result)") if res.correlacion < 0.5 else ""
        self.lbl.setText(tr("Best shift {0}  ·  r = {1} (r at 0 = {2})  ·  {3} samples").format(
            f"{res.desfase:+.3f}", f"{res.correlacion:.3f}", f"{res.correlacion_cero:.3f}", res.muestras) + aviso_baja)
        self.b_aplicar.setEnabled(True)
        return res

    def aplicar(self):
        if self.resultado is None:
            return
        res, obj, ko = self.resultado
        with self.app.operacion("Auto depth shift"):
            if self.ch_modo.currentIndex() == 0:
                pozo = next((p for p in self.app.proyecto.pozos if obj in p.logs), None)
                tray = pozo.trayectoria if pozo is not None else None
                con_tvd = tray is not None and len(tray.estaciones) >= 2 and obj.existe_columna(obj.indice_tvd)
                historial.aplicar(obj, "Auto depth shift", f"{res.desfase:+.4f} (r={res.correlacion:.3f}) whole log"
                                  + (", TVD recomputed from the trajectory" if con_tvd else ""),
                                  multipozo.desplazar_registro, obj, res.desfase, tray)
            else:
                nombre = obj.columnas[ko].nombre + "_DS"
                datos = multipozo.desplazar_curva(multipozo.profundidad(obj), obj.columnas[ko].datos, res.desfase)

                def poner():
                    j = obj.indice_columna(nombre)
                    if j >= 0:
                        obj.columnas[j].datos = datos
                    else:
                        obj.agregar_columna(nombre, datos, obj.columnas[ko].unidad, f"Depth shifted {res.desfase:+.4f}")
                historial.aplicar(obj, "Auto depth shift", f"{nombre} {res.desfase:+.4f} (r={res.correlacion:.3f})", poner)
        self.app.proyecto.modificado = True
        self.app.refrescar_editores()
        self.app.registrar(tr("Depth shift {0} applied to {1}").format(f"{res.desfase:+.4f}", obj.nombre))
        self.b_aplicar.setEnabled(False)
