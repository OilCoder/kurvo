"""Vistas de edición: tabla de datos, trayectoria, litología, completación, topes de formación y
plantillas."""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFrame, QSizePolicy, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QSpinBox,
                               QSplitter, QTableView, QTableWidget, QTableWidgetItem, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QCheckBox, QScrollArea)

from ..nucleo import historial, operaciones
from ..nucleo.comun import NULO, a_float, formato_num, parse_color
from ..nucleo.intervalos import Herramienta, IntervaloLito
from ..nucleo.plantilla import (PISTA_COMPLETACION, PISTA_CURVAS, PISTA_LITOLOGIA, AreaPlantilla)
from ..nucleo.trayectoria import Estacion, Trayectoria
from ..i18n import tr
from . import iconos
from .dialogos import Campo, aviso, boton, confirmar, pedir


# ====================================================================== base
class EditorBase(QWidget):
    cambiado = Signal()

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app

    @property
    def pr(self):
        return self.app.proyecto

    def refrescar(self) -> None:          # recargar combos/tablas tras cambiar el proyecto
        pass

    def _combo_pozos(self, combo: QComboBox, actual: int = -1) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([p.nombre for p in self.pr.pozos])
        combo.setCurrentIndex(actual if 0 <= actual < combo.count() else (0 if combo.count() else -1))
        combo.blockSignals(False)

    def _notificar(self) -> None:
        self.pr.modificado = True
        self.cambiado.emit()


# ============================================================ editor de logs
class ModeloLAS(QAbstractTableModel):
    def __init__(self, reg=None, al_editar=None):
        super().__init__()
        self.reg = reg
        self.al_editar = al_editar      # al_editar(operación, detalle, función): pasa por el historial

    def fijar(self, reg) -> None:
        self.beginResetModel()
        self.reg = reg
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return self.reg.n_filas if self.reg else 0

    def columnCount(self, parent=QModelIndex()):
        return self.reg.n_columnas if self.reg else 0

    def data(self, idx, rol=Qt.DisplayRole):
        if not idx.isValid() or self.reg is None:
            return None
        if rol in (Qt.DisplayRole, Qt.EditRole):
            d = self.reg.columnas[idx.column()].datos
            return formato_num(float(d[idx.row()])) if idx.row() < len(d) else ""
        if rol == Qt.ForegroundRole:
            d = self.reg.columnas[idx.column()].datos
            if idx.row() < len(d) and d[idx.row()] == NULO:
                return QColor(170, 170, 170)
        return None

    def setData(self, idx, valor, rol=Qt.EditRole):
        if rol != Qt.EditRole or self.reg is None:
            return False
        col, fila = self.reg.columnas[idx.column()], idx.row()
        nuevo = a_float(valor, NULO)

        def poner():
            col.datos[fila] = nuevo
        if self.al_editar is not None:
            self.al_editar("Edit cell", f"{col.nombre} row {fila + 1} = {formato_num(nuevo)}", poner)
        else:
            poner()
        self.dataChanged.emit(idx, idx)
        return True

    def flags(self, idx):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def headerData(self, s, orient, rol=Qt.DisplayRole):
        if rol != Qt.DisplayRole or self.reg is None:
            return None
        if orient == Qt.Horizontal:
            c = self.reg.columnas[s]
            marca = " [MD]" if s == self.reg.indice_md else " [TVD]" if s == self.reg.indice_tvd else ""
            return f"{c.nombre}{marca}\n{c.unidad}"
        return str(s + 1)


class EditorLogs(EditorBase):
    """Basic Log Editor. Sigue la selección global (pozo/log/curva) y la actualiza."""

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.ch_pozo, self.ch_log = QComboBox(), QComboBox()
        self.ch_md, self.ch_tvd = QComboBox(), QComboBox()
        barra = QHBoxLayout()
        for txt, w in (("Well", self.ch_pozo), ("Log", self.ch_log), ("Depth MD", self.ch_md),
                       ("Depth TVD", self.ch_tvd)):
            barra.addWidget(QLabel(tr(txt)))
            barra.addWidget(w, 1)
        self.modelo = ModeloLAS(al_editar=self._editar_celda)
        self.b_undo = boton("Undo", "undo", "", self.deshacer)
        self.b_redo = boton("Redo", "redo", "", self.rehacer)
        barra2 = QHBoxLayout()
        barra2.addWidget(self.b_undo)
        barra2.addWidget(self.b_redo)
        self.barra_herramientas = barra2
        self._botones_acciones = []
        for clave in ("history", "graphic_edit", "validate", "qc_window"):
            if clave in getattr(app, "acciones", {}):
                b = QToolButton()
                b.setDefaultAction(app.acciones[clave])
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                b.setIconSize(QSize(18, 18))
                barra2.addWidget(b)
                self._botones_acciones.append(b)
        barra2.addStretch(1)
        self.tabla = QTableView()
        self.tabla.setModel(self.modelo)
        self.tabla.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla.horizontalHeader().customContextMenuRequested.connect(self._menu_columna)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabla.horizontalHeader().sectionClicked.connect(self._columna_elegida)
        lay = QVBoxLayout(self)
        lay.addLayout(barra)
        lay.addLayout(barra2)
        lay.addWidget(self.tabla)
        self.columna_clic = -1
        self.ch_pozo.currentIndexChanged.connect(self._al_pozo)
        self.ch_log.currentIndexChanged.connect(self._al_log)
        self.ch_md.currentIndexChanged.connect(lambda i: self._fijar_indice("indice_md", i))
        self.ch_tvd.currentIndexChanged.connect(lambda i: self._fijar_indice("indice_tvd", i))
        self.tabla.selectionModel().currentColumnChanged.connect(lambda a, b: self._columna_elegida(a.column()))

    # ---------------------------------------------------------------- selección
    def pozo(self):
        i = self.ch_pozo.currentIndex()
        return self.pr.pozos[i] if 0 <= i < len(self.pr.pozos) else None

    def registro(self):
        p = self.pozo()
        i = self.ch_log.currentIndex()
        return p.logs[i] if p and 0 <= i < len(p.logs) else None

    def indices(self) -> tuple[int, int]:
        return self.ch_pozo.currentIndex(), self.ch_log.currentIndex()

    def refrescar(self) -> None:
        self._combo_pozos(self.ch_pozo, self.ch_pozo.currentIndex())
        self._al_pozo()

    def mostrar(self, i_pozo: int, i_log: int) -> None:
        self.ch_pozo.setCurrentIndex(i_pozo)
        self._al_pozo()
        self.ch_log.setCurrentIndex(i_log)

    def seguir_seleccion(self) -> None:
        """Muestra el pozo/log de la selección global y toma su curva como columna activa."""
        s = getattr(self.app, "seleccion", None)
        if s is None or s.pozo < 0:
            return
        if self.ch_pozo.count() != len(self.pr.pozos):
            self._combo_pozos(self.ch_pozo, s.pozo)
        if (self.ch_pozo.currentIndex(), self.ch_log.currentIndex()) != (s.pozo, s.log):
            self._siguiendo = True
            self.mostrar(s.pozo, s.log)
            self._siguiendo = False
        k = s.indice_curva()
        if k >= 0:
            self.columna_clic = k

    def _avisar_seleccion(self, curva: str | None = None):
        s = getattr(self.app, "seleccion", None)
        if s is None or getattr(self, "_siguiendo", False):
            return
        i, j = self.indices()
        if i >= 0:
            s.fijar(pozo=i, log=j if j >= 0 else None, curva=curva)

    def _columna_elegida(self, c: int):
        r = self.registro()
        if r is not None and r.existe_columna(c) and c not in (r.indice_md, r.indice_tvd):
            self.columna_clic = c
            self._avisar_seleccion(r.columnas[c].nombre)

    def _al_pozo(self, *_):
        p = self.pozo()
        self.ch_log.blockSignals(True)
        actual = self.ch_log.currentIndex()
        self.ch_log.clear()
        if p:
            self.ch_log.addItems([r.nombre for r in p.logs])
            self.ch_log.setCurrentIndex(actual if 0 <= actual < len(p.logs) else 0)
        self.ch_log.blockSignals(False)
        self._al_log()

    def _al_log(self, *_):
        r = self.registro()
        self.modelo.fijar(r)
        for ch, idx in ((self.ch_md, r.indice_md if r else -1), (self.ch_tvd, r.indice_tvd if r else -1)):
            ch.blockSignals(True)
            ch.clear()
            ch.addItem(tr("(none)"))
            if r:
                ch.addItems(r.nombres())
            ch.setCurrentIndex(idx + 1)
            ch.blockSignals(False)
        self._estado_botones()
        s = getattr(self.app, "seleccion", None)
        if s is not None and (s.pozo, s.log) != self.indices():
            self._avisar_seleccion("")

    # ---------------------------------------------------------------- historial
    def editar(self, operacion: str, detalle: str, funcion, *args, **kwargs):
        """Ejecuta una edición del registro activo registrándola en su historial."""
        r = self.registro()
        if r is None:
            return None
        operacion_app = getattr(self.app, "operacion", None)
        if operacion_app is None:
            resultado = historial.aplicar(r, operacion, detalle, funcion, *args, **kwargs)
        else:       # una sola entrada de deshacer, con las curvas nuevas agregadas a la plantilla
            with operacion_app(operacion):
                resultado = historial.aplicar(r, operacion, detalle, funcion, *args, **kwargs)
        self.actualizar_tabla()
        return resultado

    def _editar_celda(self, operacion, detalle, funcion):
        r = self.registro()
        if r is not None:
            historial.aplicar(r, operacion, detalle, funcion)
            self._estado_botones()
            self._notificar()

    def _estado_botones(self):
        r = self.registro()
        h = r.historial if r is not None else None
        self.b_undo.setEnabled(bool(h and h.puede_deshacer))
        self.b_redo.setEnabled(bool(h and h.puede_rehacer))
        self.b_undo.setToolTip(tr("Undo {0} (Ctrl+Z)").format(tr(h.deshacer[-1].descripcion)) if h and h.deshacer
                               else tr("Nothing to undo"))
        self.b_redo.setToolTip(tr("Redo {0} (Ctrl+Y)").format(tr(h.rehacer[-1].descripcion)) if h and h.rehacer
                               else tr("Nothing to redo"))

    def deshacer(self):
        if hasattr(self.app, "operacion"):       # mismo camino que Ctrl+Z (operaciones compuestas)
            self._avisar_seleccion()
            return self.app.deshacer()
        r = self.registro()
        if r is not None and historial.deshacer(r) is not None:
            self.actualizar_tabla()

    def rehacer(self):
        if hasattr(self.app, "operacion"):
            self._avisar_seleccion()
            return self.app.rehacer()
        r = self.registro()
        if r is not None and historial.rehacer(r) is not None:
            self.actualizar_tabla()

    def ver_historial(self):
        r = self.registro()
        if r is not None:
            from .edicion_curvas import DialogoHistorial
            DialogoHistorial(self, r).exec()

    def validar(self):
        r = self.registro()
        if r is not None:
            from .validacion_ui import DialogoValidacion
            DialogoValidacion(self, r).exec()

    def _grafica_columna_actual(self):
        r = self.registro()
        if r is None:
            return
        c = self.tabla.currentIndex().column()
        if not r.existe_columna(c):
            c = self.columna_clic
        if not r.existe_columna(c):
            aviso(self, tr("Select a cell of the curve to edit first."))
            return
        self.columna_clic = c
        from .edicion_curvas import edicion_grafica
        edicion_grafica(self)

    def _fijar_indice(self, attr: str, i: int) -> None:
        r = self.registro()
        if r is not None:
            historial.aplicar(r, "Set depth column", f"{attr} = {i - 1}", setattr, r, attr, i - 1)
            self.modelo.headerDataChanged.emit(Qt.Horizontal, 0, max(0, r.n_columnas - 1))
            self._estado_botones()
            self._notificar()

    # ---------------------------------------------------------------- menú de columna
    def _menu_columna(self, pos) -> None:
        m = self.menu_columna(pos)
        if m is not None:
            m.exec(self.tabla.horizontalHeader().mapToGlobal(pos))

    def menu_columna(self, pos) -> QMenu | None:
        """Menú de la cabecera: operaciones de columna y atajos a las acciones del registro
        (las mismas QAction del ribbon, con su icono y su atajo)."""
        r = self.registro()
        if r is None:
            return None
        self.columna_clic = self.tabla.horizontalHeader().logicalIndexAt(pos)
        c = self.columna_clic
        if r.existe_columna(c):
            self._columna_elegida(c)
        a = getattr(self.app, "acciones", None)
        m = QMenu(self)
        if c >= 0:
            m.addAction(tr("Rename"), self.renombrar)
            m.addAction(iconos.icono("delete"), tr("Delete"), self.borrar)
            m.addSeparator()
            m.addAction(iconos.icono("up"), tr("Move Up"), lambda: self.mover(c - 1))
            m.addAction(iconos.icono("down"), tr("Move Down"), lambda: self.mover(c + 1))
            m.addAction(tr("Move to First"), lambda: self.mover(0))
            m.addAction(tr("Move to Last"), lambda: self.mover(r.n_columnas - 1))
            m.addSeparator()
            if a is not None:
                from .edicion_curvas import acciones as acciones_edicion
                sub = m.addMenu(iconos.icono("curve_null"), tr("Curve Editing"))
                for k in acciones_edicion(self):
                    sub.addSeparator() if k == "-" else sub.addAction(a[k])
                for k in ("convert_units", "qc_flags", "qc_window"):
                    m.addAction(a[k])
                m.addSeparator()
        if a is None:
            return m
        sub = m.addMenu(iconos.icono("validate"), tr("Log Maintenance"))
        for k in ("validate", "resample", "mnemonics", "history"):
            sub.addAction(a[k])
        sub = m.addMenu(iconos.icono("normalize"), tr("Wells"))
        for k in ("normalize", "depth_shift", "batch", "deep_learning", "qc_report", "dashboard"):
            sub.addAction(a[k])
        m.addSeparator()
        for k in ("create_tvd", "create_md", "partial_log", "filter", "calculator"):
            m.addAction(a[k])
        for modulo in self.app.modulos:
            entradas = a.modulos.get(modulo.nombre)
            if not entradas:
                continue
            sub = m.addMenu(tr(modulo.nombre))
            for texto, func in entradas:
                if texto == "-":
                    sub.addSeparator()
                elif isinstance(func, list):
                    s2 = sub.addMenu(tr(texto))
                    for t2, _ in func:
                        s2.addAction(a[f"mod:{modulo.nombre}/{texto}/{t2}"])
                else:
                    sub.addAction(a[f"mod:{modulo.nombre}/{texto}"])
        return m

    def actualizar_tabla(self) -> None:
        self._al_log()
        self._notificar()

    def renombrar(self):
        r, c = self.registro(), self.columna_clic
        nombre, ok = QInputDialog.getText(self, tr("Rename"), tr("New name"), text=r.columnas[c].nombre)
        if not ok:
            return
        if not nombre.strip():
            aviso(self, tr("Empty name is not allowed! Please set new name."))
            return
        viejo = r.columnas[c].nombre

        def poner():
            r.columnas[c].nombre = nombre.strip()
            historial.renombrar_original(r, viejo, nombre.strip())
        self.editar("Rename", f"{viejo} -> {nombre.strip()}", poner)

    def borrar(self):
        r, c = self.registro(), self.columna_clic
        if confirmar(self, tr("Delete column {0}?").format(r.columnas[c].nombre)):
            self.editar("Delete column", r.columnas[c].nombre, r.borrar_columna, c)

    def mover(self, destino: int):
        r, c = self.registro(), self.columna_clic
        if 0 <= destino < r.n_columnas:
            def poner():
                md = r.columnas[r.indice_md] if r.existe_columna(r.indice_md) else None
                tvd = r.columnas[r.indice_tvd] if r.existe_columna(r.indice_tvd) else None
                r.mover_columna(c, destino)
                r.indice_md = r.columnas.index(md) if md is not None else -1
                r.indice_tvd = r.columnas.index(tvd) if tvd is not None else -1
            self.editar("Move column", f"{r.columnas[c].nombre} -> {destino + 1}", poner)

    def crear_tvd(self):
        try:
            self.editar("Create TVD from MD", "", operaciones.crear_tvd, self.registro(),
                        self.pozo().trayectoria)
        except ValueError as e:
            aviso(self, str(e))

    def crear_md(self):
        try:
            self.editar("Create MD from TVD", "", operaciones.crear_md, self.registro(),
                        self.pozo().trayectoria)
        except ValueError as e:
            aviso(self, str(e))

    def filtrar(self):
        """Filtrar filas por una condición."""
        r = self.registro()
        v = pedir("Filter Rows", [Campo("col", "Column", "columna", 0, r.nombres()),
                             Campo("op", "Operator", "opcion", ">=", [">=", "<=", "between", "is null",
                                                                     "not null"], traducir_opciones=True),
                             Campo("v1", "Value 1", "float", 0.0), Campo("v2", "Value 2", "float", 0.0),
                             Campo("acc", "Action", "opcion", "Delete rows",
                                   ["Delete rows", "Set to null"], traducir_opciones=True)], self)
        if v is None or v["col"] < 0:
            return
        detalle = f"{r.columnas[v['col']].nombre} {v['op']} {v['v1']:g}"
        if v["op"] == "between":
            detalle += f"..{v['v2']:g}"
        self.editar("Filter", f"{detalle}, {v['acc']}", operaciones.filtrar, r, v["col"], v["op"],
                    v["v1"], v["v2"], v["acc"])


# ======================================================== editor de trayectoria
class EditorTrayectoria(EditorBase):
    COLS = ("MD", "INC", "AZIM", "TVD", "NORTH", "EAST", "HD", "TVDSS")

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.ch_pozo = QComboBox()
        self.txt_ss = QDoubleSpinBox()
        self.txt_ss.setRange(-1e6, 1e6)
        self.txt_ss.setDecimals(3)
        self.ch_x, self.ch_y = QComboBox(), QComboBox()
        self.ch_x.addItems(self.COLS)
        self.ch_y.addItems(self.COLS)
        self.ch_x.setCurrentText("EAST")
        self.ch_y.setCurrentText("TVD")
        b_add, b_del = boton("Add", "add", "Add a station"), boton("Delete", "delete", "Delete the selected stations")
        b_imp = boton("Import...", "import", "Import the trajectory from a text file")
        b_exp = boton("Export...", "export", "Export the trajectory to a text file")
        barra = QHBoxLayout()
        for w in (QLabel(tr("Well")), self.ch_pozo, QLabel(tr("TVD to SS")), self.txt_ss, b_add, b_del,
                  b_imp, b_exp, QLabel("X"), self.ch_x, QLabel("Y"), self.ch_y):
            barra.addWidget(w)
        self.tabla = QTableWidget(0, len(self.COLS))
        self.tabla.setHorizontalHeaderLabels(self.COLS)
        self.grafico = pg.PlotWidget()
        self.grafico.invertY(True)
        sp = QSplitter()
        sp.addWidget(self.tabla)
        sp.addWidget(self.grafico)
        # cada cambio deja ver su efecto: la profundidad al fondo en TVD y TVDSS (nota 6, D123)
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setFrameShape(QFrame.StyledPanel)
        self.lbl_resumen.setMargin(4)
        self.lbl_resumen.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        lay = QVBoxLayout(self)
        lay.addLayout(barra)
        lay.addWidget(self.lbl_resumen)
        lay.addWidget(sp)
        self.ch_pozo.currentIndexChanged.connect(self.cargar)
        self.tabla.itemChanged.connect(self._editado)
        self.txt_ss.valueChanged.connect(self._ss)
        b_add.clicked.connect(self.agregar)
        b_del.clicked.connect(self.borrar)
        b_imp.clicked.connect(self.importar)
        b_exp.clicked.connect(self.exportar)
        self.ch_x.currentIndexChanged.connect(self.graficar)
        self.ch_y.currentIndexChanged.connect(self.graficar)

    def tray(self) -> Trayectoria | None:
        i = self.ch_pozo.currentIndex()
        return self.pr.pozos[i].trayectoria if 0 <= i < len(self.pr.pozos) else None

    def refrescar(self):
        self._combo_pozos(self.ch_pozo, self.ch_pozo.currentIndex())
        self.cargar()

    def cargar(self, *_):
        t = self.tray()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        if t is not None:
            self.txt_ss.blockSignals(True)
            self.txt_ss.setValue(t.tvd_a_ss)
            self.txt_ss.blockSignals(False)
            self.tabla.setRowCount(len(t.estaciones))
            for i, e in enumerate(t.estaciones):
                for j, v in enumerate((e.md, e.inc, e.azim, e.tvd, e.norte, e.este, e.hd, e.tvdss)):
                    it = QTableWidgetItem("%.4f" % v)
                    if j >= 3:
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                        it.setForeground(QColor(90, 90, 90))
                    self.tabla.setItem(i, j, it)
        self.tabla.blockSignals(False)
        self._resumen(t)
        self.graficar()

    def _resumen(self, t):
        i = self.ch_pozo.currentIndex()
        if t is None:
            texto = ""
        elif len(t.estaciones) < 2:
            texto = tr("{0}: no survey stations, so its TVD is unknown. Import them, add them, or choose TVD in the "
                       "depth axis of the Log Plot and answer that the well is vertical.").format(self.pr.pozos[i].nombre)
        else:
            e = t.estaciones[-1]
            texto = tr("{0} at the last station: MD {1:.2f} → TVD {2:.2f} → TVDSS {3:.2f} (KB {4:g}); "
                       "horizontal displacement {5:.1f}").format(self.pr.pozos[i].nombre, e.md, e.tvd,
                                                                 e.tvd - t.tvd_a_ss, t.tvd_a_ss, e.hd)
        self.lbl_resumen.setText(texto)

    def _editado(self, item):
        t = self.tray()
        e = t.estaciones[item.row()]
        v = a_float(item.text(), 0.0)
        if item.column() == 0:
            e.md = v
        elif item.column() == 1:
            e.inc = v
        elif item.column() == 2:
            e.azim = v
        self._recalcular()

    def _recalcular(self):
        t = self.tray()
        for e in t.estaciones:
            e.tvd = NULO
        t.calcular()
        self.cargar()
        self._notificar()

    def _ss(self, v):
        t = self.tray()
        if t is not None:
            t.tvd_a_ss = v
            t.calcular()
            self.cargar()
            self._notificar()

    def agregar(self):
        t = self.tray()
        if t is None:
            return
        md = t.estaciones[-1].md + 100 if t.estaciones else 0.0
        t.estaciones.append(Estacion(md=md, inc=t.estaciones[-1].inc if t.estaciones else 0.0,
                                     azim=t.estaciones[-1].azim if t.estaciones else 0.0))
        self._recalcular()

    def borrar(self):
        t = self.tray()
        filas = sorted({i.row() for i in self.tabla.selectedIndexes()}, reverse=True)
        for f in filas:
            del t.estaciones[f]
        self._recalcular()

    def importar(self):
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Import trajectory"), "", tr("Text (*.txt *.dat)") + ";;" + tr("All (*.*)"))
        if ruta and self.tray() is not None:
            nueva = Trayectoria.abrir(ruta)
            if nueva.tvd_a_ss == 0.0:          # el archivo no trae #TVD_TO_SS: se queda la KB del pozo
                nueva.tvd_a_ss = self.tray().tvd_a_ss
            nueva.calcular()
            self.pr.pozos[self.ch_pozo.currentIndex()].trayectoria = nueva
            self.cargar()
            self._notificar()

    def exportar(self):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export trajectory"), "", tr("Text (*.txt)"))
        if ruta and self.tray() is not None:
            self.tray().guardar(ruta)

    def graficar(self, *_):
        self.grafico.clear()
        t = self.tray()
        if t is None or not t.estaciones:
            return
        atr = {"MD": "md", "INC": "inc", "AZIM": "azim", "TVD": "tvd", "NORTH": "norte",
               "EAST": "este", "HD": "hd", "TVDSS": "tvdss"}
        xs = [getattr(e, atr[self.ch_x.currentText()]) for e in t.estaciones]
        ys = [getattr(e, atr[self.ch_y.currentText()]) for e in t.estaciones]
        self.grafico.plot(xs, ys, pen=pg.mkPen("b", width=2), symbol="o", symbolSize=5)
        self.grafico.setLabel("bottom", self.ch_x.currentText())
        self.grafico.setLabel("left", self.ch_y.currentText())


# ======================================================= editores de intervalos
class EditorTablaIntervalos(EditorBase):
    """Base para litología y completación: pozo + elemento + tabla editable."""
    columnas: tuple = ()

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.ch_pozo, self.ch_item = QComboBox(), QComboBox()
        b_add, b_del = boton("Add", "add", "Add an interval"), boton("Delete", "delete", "Delete the selected rows")
        b_up, b_down = boton("Move Up", "up"), boton("Move Down", "down")
        barra = QHBoxLayout()
        for w in (QLabel(tr("Well")), self.ch_pozo, QLabel(tr(self.etiqueta_item)), self.ch_item, b_add, b_del,
                  b_up, b_down):
            barra.addWidget(w)
        barra.addStretch(1)
        self.tabla = QTableWidget(0, len(self.columnas))
        self.tabla.setHorizontalHeaderLabels([tr(c) for c in self.columnas])
        self.tabla.horizontalHeader().setStretchLastSection(True)
        lay = QVBoxLayout(self)
        lay.addLayout(barra)
        lay.addWidget(self.tabla)
        self.ch_pozo.currentIndexChanged.connect(self._al_pozo)
        self.ch_item.currentIndexChanged.connect(self.cargar)
        self.tabla.itemChanged.connect(self._editado)
        b_add.clicked.connect(self.agregar)
        b_del.clicked.connect(self.borrar)
        b_up.clicked.connect(lambda: self.mover(-1))
        b_down.clicked.connect(lambda: self.mover(1))

    def lista_items(self, pozo):
        raise NotImplementedError

    def filas(self, item):
        raise NotImplementedError

    def item(self):
        i = self.ch_pozo.currentIndex()
        if not 0 <= i < len(self.pr.pozos):
            return None
        lista = self.lista_items(self.pr.pozos[i])
        j = self.ch_item.currentIndex()
        return lista[j] if 0 <= j < len(lista) else None

    def refrescar(self):
        self._combo_pozos(self.ch_pozo, self.ch_pozo.currentIndex())
        self._al_pozo()

    def _al_pozo(self, *_):
        i = self.ch_pozo.currentIndex()
        self.ch_item.blockSignals(True)
        self.ch_item.clear()
        if 0 <= i < len(self.pr.pozos):
            self.ch_item.addItems([x.nombre for x in self.lista_items(self.pr.pozos[i])])
        self.ch_item.blockSignals(False)
        self.cargar()

    def cargar(self, *_):
        it = self.item()
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        if it is not None:
            filas = self.filas(it)
            self.tabla.setRowCount(len(filas))
            for i, fila in enumerate(filas):
                for j, v in enumerate(fila):
                    self.tabla.setItem(i, j, QTableWidgetItem(v if isinstance(v, str) else formato_num(v)))
        self.tabla.blockSignals(False)

    def mover(self, delta):
        it = self.item()
        f = self.tabla.currentRow()
        lista = self.registros(it) if it else []
        if it and 0 <= f < len(lista) and 0 <= f + delta < len(lista):
            lista[f], lista[f + delta] = lista[f + delta], lista[f]
            self.cargar()
            self.tabla.selectRow(f + delta)
            self._notificar()

    def borrar(self):
        it = self.item()
        if it is None:
            return
        lista = self.registros(it)
        for f in sorted({i.row() for i in self.tabla.selectedIndexes()}, reverse=True):
            del lista[f]
        self.cargar()
        self._notificar()


class EditorLitologia(EditorTablaIntervalos):
    columnas = ("Depth Start", "Depth End", "Lithology Type", "Remarks")
    etiqueta_item = "Interpretation"

    def lista_items(self, pozo):
        return pozo.litologias

    def registros(self, lit):
        return lit.intervalos

    def filas(self, lit):
        nombres = {}
        if self.app.base_lito is not None:
            nombres = {t.id: t.nombre for t in self.app.base_lito.tipos}
        return [(i.tope, i.base, str(i.tipo) + (f" - {nombres[i.tipo]}" if i.tipo in nombres else ""),
                 i.comentario) for i in lit.intervalos]

    def cargar(self, *_):
        super().cargar()
        it = self.item()
        if it is None:
            return
        from .logplot import imagen_litologia
        self.tabla.blockSignals(True)
        for f, x in enumerate(it.intervalos):
            celda = self.tabla.item(f, 2)
            if celda is not None:
                img = imagen_litologia(x.tipo, self.app.base_lito)
                celda.setIcon(QIcon(QPixmap.fromImage(img)))
        self.tabla.blockSignals(False)

    def _editado(self, celda):
        it = self.item()
        x = it.intervalos[celda.row()]
        t = celda.text()
        if celda.column() == 0:
            x.tope = a_float(t, x.tope)
        elif celda.column() == 1:
            x.base = a_float(t, x.base)
        elif celda.column() == 2:
            x.tipo = int(a_float(t.split("-")[0], x.tipo))
        else:
            x.comentario = t
        self._notificar()

    def agregar(self):
        it = self.item()
        if it is None:
            return
        tope = it.intervalos[-1].base if it.intervalos else 0.0
        it.intervalos.append(IntervaloLito(tope, tope + 10, 0, ""))
        self.cargar()
        self._notificar()


class EditorCompletacion(EditorTablaIntervalos):
    columnas = ("Remarks", "Tool", "Top", "Bottom")
    etiqueta_item = "Package"

    def lista_items(self, pozo):
        return pozo.completaciones

    def registros(self, comp):
        return comp.herramientas

    def filas(self, comp):
        return [(h.comentario, h.nombre_herramienta, h.tope, h.base) for h in comp.herramientas]

    def _editado(self, celda):
        h = self.item().herramientas[celda.row()]
        t = celda.text()
        if celda.column() == 0:
            h.comentario = t
        elif celda.column() == 1:
            h.nombre_herramienta = t
        elif celda.column() == 2:
            h.tope = a_float(t, h.tope)
        else:
            h.base = a_float(t, h.base)
        self._notificar()

    def agregar(self):
        it = self.item()
        if it is None:
            return
        nombres = [i.nombre for i in self.app.base_herr.items] if self.app.base_herr else ["Casing"]
        v = pedir("Add Tool", [Campo("tool", "Tool", "opcion", nombres[0], nombres),
                               Campo("rem", "Remarks", "texto", ""), Campo("top", "Top", "float", 0.0),
                               Campo("bot", "Bottom", "float", 100.0)], self)
        if v:
            it.herramientas.append(Herramienta(v["rem"], v["tool"], v["top"], v["bot"]))
            self.cargar()
            self._notificar()


# ============================================================ editor de zonas
class EditorZonas(EditorBase):
    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        b_add, b_del = boton("Add", "add", "Add a zone"), boton("Delete", "delete", "Delete the selected zone")
        b_up, b_down = boton("Move Up", "up"), boton("Move Down", "down")
        b_color = boton("Color...", "color", "Line color of the zone")
        self.ch_tipo, self.sp_ancho = QComboBox(), QSpinBox()
        self.ch_tipo.addItems([tr(x) for x in ("Solid", "Dot", "Long dash", "Dash dot dot", "Dot dash")])
        self.sp_ancho.setRange(1, 10)
        barra = QHBoxLayout()
        for w in (b_add, b_del, b_up, b_down, b_color, QLabel(tr("Line")), self.ch_tipo, QLabel(tr("Width")),
                  self.sp_ancho):
            barra.addWidget(w)
        barra.addStretch(1)
        self.tabla = QTableWidget()
        lay = QVBoxLayout(self)
        lay.addLayout(barra)
        lay.addWidget(self.tabla)
        self.tabla.itemChanged.connect(self._editado)
        self.tabla.currentCellChanged.connect(self._sel)
        b_add.clicked.connect(self.agregar)
        b_del.clicked.connect(self.borrar)
        b_up.clicked.connect(lambda: self.mover(-1))
        b_down.clicked.connect(lambda: self.mover(1))
        b_color.clicked.connect(self.color)
        self.ch_tipo.currentIndexChanged.connect(self._estilo)
        self.sp_ancho.valueChanged.connect(self._estilo)

    def refrescar(self):
        pozos = [p.nombre for p in self.pr.pozos]
        self.tabla.blockSignals(True)
        self.tabla.setColumnCount(1 + len(pozos))
        self.tabla.setHorizontalHeaderLabels([tr("Zone")] + pozos)
        self.tabla.setRowCount(len(self.pr.zonas))
        for i, z in enumerate(self.pr.zonas):
            it = QTableWidgetItem(z.nombre)
            it.setForeground(QColor(*parse_color(z.color)))
            self.tabla.setItem(i, 0, it)
            for j in range(len(pozos)):
                self.tabla.setItem(i, j + 1, QTableWidgetItem(formato_num(z.prof(j))))
        self.tabla.blockSignals(False)

    def _sel(self, fila, *_):
        if 0 <= fila < len(self.pr.zonas):
            z = self.pr.zonas[fila]
            for w, v in ((self.ch_tipo, z.tipo_linea), (self.sp_ancho, z.ancho)):
                w.blockSignals(True)
                (w.setCurrentIndex if w is self.ch_tipo else w.setValue)(v)
                w.blockSignals(False)

    def _editado(self, celda):
        z = self.pr.zonas[celda.row()]
        if celda.column() == 0:
            z.nombre = celda.text().strip() or z.nombre
        else:
            j = celda.column() - 1
            while len(z.profundidades) <= j:
                z.profundidades.append(0.0)
            z.profundidades[j] = a_float(celda.text(), z.profundidades[j])
        self._notificar()

    def _estilo(self, *_):
        f = self.tabla.currentRow()
        if 0 <= f < len(self.pr.zonas):
            self.pr.zonas[f].tipo_linea = self.ch_tipo.currentIndex()
            self.pr.zonas[f].ancho = self.sp_ancho.value()
            self._notificar()

    def agregar(self):
        self.pr.nueva_zona()
        self.refrescar()
        self._notificar()

    def borrar(self):
        f = self.tabla.currentRow()
        if 0 <= f < len(self.pr.zonas):
            del self.pr.zonas[f]
            for lp in self.pr.logplots:
                if f < len(lp.zonas_visibles):
                    del lp.zonas_visibles[f]
            self.refrescar()
            self._notificar()

    def mover(self, d):
        f = self.tabla.currentRow()
        if 0 <= f < len(self.pr.zonas) and 0 <= f + d < len(self.pr.zonas):
            self.pr.mover(self.pr.zonas, f, f + d)
            self.refrescar()
            self.tabla.selectRow(f + d)
            self._notificar()

    def color(self):
        f = self.tabla.currentRow()
        if 0 <= f < len(self.pr.zonas):
            c = QColorDialog.getColor(QColor(*parse_color(self.pr.zonas[f].color)), self)
            if c.isValid():
                self.pr.zonas[f].color = "rgb(%d, %d, %d)" % (c.red(), c.green(), c.blue())
                self.refrescar()
                self._notificar()


# ======================================================== editor de plantillas
class EditorPlantillas(EditorBase):
    """Template Editor: árbol General/Tracks/Curves/Areas + propiedades + vista previa."""

    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.ch_plantilla = QComboBox()
        b_track = boton("Add Track", "add", "Add a curve track")
        b_comp = boton("Add Comp. Track", "completion", "Add a completion track")
        b_lito = boton("Add Litho Track", "lithology", "Add a lithology track")
        b_curva = boton("Add Curve", "curve", "Add a curve to the selected track")
        b_area = boton("Add Area", "templates", "Add a filled area to the selected track")
        b_borrar = boton("Delete", "delete", "Delete the selected item")
        barra = QHBoxLayout()
        for w in (QLabel(tr("Template")), self.ch_plantilla, b_track, b_comp, b_lito, b_curva, b_area, b_borrar):
            barra.addWidget(w)
        barra.addStretch(1)
        self.arbol = QTreeWidget()
        self.arbol.setHeaderLabel(tr("Template"))
        self.props = QWidget()
        self.form = QFormLayout(self.props)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.props)
        from .visor import VisorLogPlot
        self.preview = VisorLogPlot()
        izq = QSplitter(Qt.Vertical)
        izq.addWidget(self.arbol)
        izq.addWidget(sc)
        sp = QSplitter()
        sp.addWidget(izq)
        sp.addWidget(self.preview)
        sp.setStretchFactor(1, 3)
        lay = QVBoxLayout(self)
        lay.addLayout(barra)
        lay.addWidget(sp)
        self.ch_plantilla.currentIndexChanged.connect(self.cargar)
        self.arbol.currentItemChanged.connect(self._sel)
        b_track.clicked.connect(lambda: self._nueva_pista(PISTA_CURVAS))
        b_comp.clicked.connect(lambda: self._nueva_pista(PISTA_COMPLETACION))
        b_lito.clicked.connect(lambda: self._nueva_pista(PISTA_LITOLOGIA))
        b_curva.clicked.connect(self._nueva_curva)
        b_area.clicked.connect(self._nueva_area)
        b_borrar.clicked.connect(self._borrar)

    def plantilla(self):
        i = self.ch_plantilla.currentIndex()
        return self.pr.plantillas[i] if 0 <= i < len(self.pr.plantillas) else None

    def refrescar(self):
        i = self.ch_plantilla.currentIndex()
        self.ch_plantilla.blockSignals(True)
        self.ch_plantilla.clear()
        self.ch_plantilla.addItems([t.nombre for t in self.pr.plantillas])
        self.ch_plantilla.setCurrentIndex(i if 0 <= i < len(self.pr.plantillas) else 0)
        self.ch_plantilla.blockSignals(False)
        self.cargar()

    def cargar(self, *_):
        self.arbol.clear()
        t = self.plantilla()
        if t is None:
            self.preview.lienzo.fijar_plot(None)
            return
        raiz = QTreeWidgetItem([tr("General")])
        raiz.setData(0, Qt.UserRole, ("all",))
        self.arbol.addTopLevelItem(raiz)
        for i, p in enumerate(t.pistas):
            tipo = tr({PISTA_CURVAS: "Track", PISTA_COMPLETACION: "Completion", PISTA_LITOLOGIA: "Lithology"}[p.tipo])
            it = QTreeWidgetItem([f"{tipo} {i + 1}"])
            it.setData(0, Qt.UserRole, ("pista", i))
            raiz.addChild(it)
            for j, c in enumerate(p.curvas):
                ci = QTreeWidgetItem([f"Curve: {c.nombre_x}"])
                ci.setData(0, Qt.UserRole, ("curva", i, j))
                it.addChild(ci)
            for j, a in enumerate(p.areas):
                ai = QTreeWidgetItem([f"Area: {a.curva_izq} → {a.curva_der}"])
                ai.setData(0, Qt.UserRole, ("area", i, j))
                it.addChild(ai)
        self.arbol.expandAll()
        self.arbol.setCurrentItem(raiz)
        self.vista_previa()

    def vista_previa(self):
        from .logplot import DatosLogPlot, LogPlot
        t = self.plantilla()
        reg = None
        for p in self.pr.pozos:
            if p.logs:
                reg = p.logs[0]
                pozo = p
                break
        if t is None:
            return
        d = DatosLogPlot(plantilla=t, registro=reg, nombre_pozo=pozo.nombre if reg else "",
                         trayectoria=pozo.trayectoria if reg else None,
                         litologia=pozo.litologias[0] if reg and pozo.litologias else None,
                         completacion=pozo.completaciones[0] if reg and pozo.completaciones else None,
                         base_herr=self.app.base_herr, base_lito=self.app.base_lito)
        self.preview.lienzo.fijar_plot(LogPlot(d))

    # ---------------------------------------------------------------- propiedades
    def _objeto(self):
        it = self.arbol.currentItem()
        if it is None:
            return None, None
        ref = it.data(0, Qt.UserRole)
        t = self.plantilla()
        if ref[0] == "all":
            return ref, t
        if ref[0] == "pista":
            return ref, t.pistas[ref[1]]
        if ref[0] == "curva":
            return ref, t.pistas[ref[1]].curvas[ref[2]]
        return ref, t.pistas[ref[1]].areas[ref[2]]

    CAMPOS = {
        "all": [("x", "PosX", "f"), ("y", "PosY", "f"), ("escala", "Scale", "f"), ("eje_y", "AxisY", "s"),
                ("mostrar_titulo", "ShowTitle", "b"), ("formato_titulo", "TitleFormat", "s"),
                ("borde_visible", "BorderShow", "b"), ("borde_color", "BorderLineColor", "s"),
                ("borde_ancho", "BorderLineWidth", "i"), ("zona_nombre_visible", "ZoneNameShow", "b"),
                ("zona_nombre_posicion", "ZoneNamePosition", "i"), ("zona_nombre_ancho", "ZoneNameWidth", "f")],
        "pista": [("x", "PosX", "f"), ("ancho", "Width", "f"), ("borde_visible", "BorderShow", "b"),
                  ("borde_color", "BorderLineColor", "s"), ("borde_ancho", "BorderLineWidth", "i"),
                  ("borde_tipo", "BorderLineType", "i"), ("tam_fuente_cabecera", "HeaderFontSize", "i"),
                  ("ancho_comp", "WidthComp", "f"), ("ancho_lito", "WidthLitho", "f")],
        "curva": [("nombre_x", "NameX", "s"), ("nombre_y", "NameY", "s"), ("color", "Color", "s"),
                  ("ancho", "LineWidth", "i"), ("tipo_linea", "LineType", "i"), ("logaritmica", "Logaritmic", "b"),
                  ("invertida", "Reverse", "b"), ("escala_min", "ScaleXMin", "f"),
                  ("escala_max", "ScaleXMax", "f"), ("usar_grupo", "UseGroup", "b"),
                  ("escala_auto", "AutoScale", "b")],
        "area": [("curva_izq", "CurveLeft", "s"), ("curva_der", "CurveRight", "s"), ("color", "Color", "s")],
    }

    def _sel(self, *_):
        while self.form.rowCount():
            self.form.removeRow(0)
        ref, obj = self._objeto()
        if obj is None:
            return
        for attr, etiqueta, tipo in self.CAMPOS[ref[0]]:
            v = getattr(obj, attr)
            if tipo == "b":
                w = QCheckBox()
                w.setChecked(bool(v))
                w.toggled.connect(lambda val, a=attr: self._cambio(a, val))
            elif tipo == "i":
                w = QSpinBox()
                w.setRange(0, 100000)
                w.setValue(int(v))
                w.valueChanged.connect(lambda val, a=attr: self._cambio(a, val))
            elif tipo == "f":
                w = QDoubleSpinBox()
                w.setRange(-1e9, 1e9)
                w.setDecimals(4)
                w.setValue(float(v))
                w.valueChanged.connect(lambda val, a=attr: self._cambio(a, val))
            else:
                w = QLineEdit(str(v))
                w.editingFinished.connect(lambda a=attr, ww=w: self._cambio(a, ww.text()))
            self.form.addRow(etiqueta, w)

    def _cambio(self, attr, valor):
        _, obj = self._objeto()
        setattr(obj, attr, valor)
        self._notificar()
        self.vista_previa()

    def _nueva_pista(self, tipo):
        t = self.plantilla()
        if t is not None:
            t.nueva_pista(tipo)
            self.cargar()
            self._notificar()

    def _nueva_curva(self):
        ref, obj = self._objeto()
        if ref and ref[0] in ("pista", "curva", "area"):
            p = self.plantilla().pistas[ref[1]]
            nombre, ok = QInputDialog.getText(self, tr("Add Curve"), tr("Curve name (NameX)"))
            if ok:
                self.plantilla().nueva_curva(p, nombre.strip())
                self.cargar()
                self._notificar()

    def _nueva_area(self):
        ref, obj = self._objeto()
        if ref and ref[0] in ("pista", "curva", "area"):
            self.plantilla().pistas[ref[1]].areas.append(AreaPlantilla())
            self.cargar()
            self._notificar()

    def _borrar(self):
        ref, obj = self._objeto()
        t = self.plantilla()
        if not ref or ref[0] == "all":
            return
        if ref[0] == "pista":
            del t.pistas[ref[1]]
        elif ref[0] == "curva":
            del t.pistas[ref[1]].curvas[ref[2]]
        else:
            del t.pistas[ref[1]].areas[ref[2]]
        self.cargar()
        self._notificar()
