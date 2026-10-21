"""Panel de control de calidad interactivo (acoplable, D66–D79).

Arriba: pozo, log, zona y curva (la selección global). Pestañas: Dashboard (pozos × curvas),
Summary, Depth view (con la pista de condición de pozo), Coverage, Histogram, Wells comparison
(histogramas, CDF, cajas por pozo y por zona), Crossplot (con líneas de litología N-D y atípicos
de Mahalanobis), Correlation, Before/After y Depth step. Solo se calcula la pestaña visible."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)

from ..i18n import tr
from ..nucleo import preferencias, qc
from ..nucleo.comun import NULO, parse_color
from ..nucleo.edicion import escala_log
from ..nucleo.multipozo import buscar_curva
from . import iconos

NOTA_FONDO = {"A": QColor(200, 236, 209), "B": QColor(255, 226, 179), "C": QColor(246, 196, 196)}
NOTA_TEXTO = {"A": QColor(30, 110, 50), "B": QColor(150, 85, 0), "C": QColor(170, 30, 30)}
PALETA = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40), (148, 103, 189),
          (140, 86, 75), (227, 119, 194), (127, 127, 127), (188, 189, 34), (23, 190, 207)]

PESTANAS = [("dashboard", "Dashboard", "dashboard"), ("summary", "Summary", "summary"),
            ("depth", "Depth view", "depth_view"), ("coverage", "Coverage", "coverage"),
            ("histogram", "Histogram", "histogram"), ("wells", "Wells comparison", "compare_wells"),
            ("crossplot", "Crossplot", "crossplot"), ("correlation", "Correlation", "correlation"),
            ("before_after", "Before/After", "before_after"), ("repeat", "Repeat pass", "compare_original"),
            ("depth_step", "Depth step", "depth_step")]


def _validos(d):
    d = np.asarray(d, float)
    return (d != NULO) & np.isfinite(d)


def _nan(d):
    d = np.asarray(d, float)
    return np.where(_validos(d), d, np.nan)


def color_curva(app, nombre: str, k: int = 0) -> tuple[int, int, int]:
    """Color de la curva en la plantilla del proyecto (el mismo en todas las gráficas); si la curva
    no está en ninguna plantilla, uno de la paleta."""
    alias = app.alias
    g = alias.grupo_de(nombre) if alias is not None else -1
    for t in app.proyecto.plantillas:
        for pista in t.pistas:
            for c in pista.curvas:
                if c.nombre_x.upper() == nombre.upper() or (g >= 0 and alias.grupo_de(c.nombre_x) == g):
                    return tuple(parse_color(c.color)[:3])
    return PALETA[k % len(PALETA)]


PX_POR_ETIQUETA = 42          # ancho mínimo por número del eje X en las pistas de Depth view
ANCHO_MIN_PISTA = 64


def marcas_compactas(vmin: float, vmax: float, maximo: int, log: bool = False) -> list[tuple[float, str]]:
    """Marcas del eje X de una pista estrecha (D97): a lo sumo `maximo`, en pasos 1-2-2,5-5 × 10^k,
    con números de 3 cifras significativas; en escala log, potencias de 10 (posición en log10).
    Se fijan con `setTicks` (una subclase de AxisItem hacía caer PySide al redibujar)."""
    maximo = max(2, int(maximo))
    if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmax < vmin:
        return []
    if vmax == vmin:            # curva constante (BS): una sola marca con su valor
        return [(vmin, f"{10.0 ** vmin:g}" if log else f"{vmin:.3g}")]
    if log:
        a, b = int(np.floor(vmin)), int(np.ceil(vmax))
        paso = max(1, int(np.ceil((b - a + 1) / maximo)))
        return [(float(e), f"{10.0 ** e:g}") for e in range(a, b + 1, paso) if vmin - 1e-9 <= e <= vmax + 1e-9]
    bruto = (vmax - vmin) / maximo
    base = 10 ** np.floor(np.log10(bruto))
    paso = next((f * base for f in (1, 2, 2.5, 5, 10) if f * base >= bruto), 10 * base)
    v = np.ceil(vmin / paso) * paso
    out = []
    while v <= vmax + 1e-9 * paso and len(out) <= maximo:
        out.append((float(v), f"{v:.3g}" if abs(v) > 1e-12 * paso else "0"))
        v += paso
    return out


def _marcas_pista(p, datos, log: bool, maximo: int) -> None:
    d = np.asarray(datos, float)
    d = d[np.isfinite(d)]
    if log:
        d = np.log10(d[d > 0])
    if d.size:
        p.getAxis("bottom").setTicks([marcas_compactas(float(d.min()), float(d.max()), maximo, log)])


def _pista(gl, fila: int, col: int):
    p = gl.addPlot(row=fila, col=col)
    p.setMinimumWidth(ANCHO_MIN_PISTA)
    return p


def _grafico(titulo: str = "") -> pg.PlotWidget:
    g = pg.PlotWidget(title=titulo)
    g.showGrid(x=True, y=True, alpha=0.2)
    g.getPlotItem().getAxis("left").setWidth(48)
    return g


def _caja(plot, x: float, q, color, ancho: float = 0.6):
    """Diagrama de cajas: P25–P75, mediana roja y bigotes P5–P95."""
    p5, p25, p50, p75, p95 = q
    pen = pg.mkPen((60, 60, 60), width=1)
    plot.addItem(pg.BarGraphItem(x=[x], height=[p75 - p25], y0=[p25], width=ancho,
                                 brush=pg.mkBrush(*color, 150), pen=pen))
    plot.plot([x - ancho / 2, x + ancho / 2], [p50, p50], pen=pg.mkPen((200, 30, 30), width=2))
    for a, b in ((p5, p25), (p75, p95)):
        plot.plot([x, x], [a, b], pen=pen)
    for v in (p5, p95):
        plot.plot([x - ancho / 4, x + ancho / 4], [v, v], pen=pen)


class PanelQC(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._sincronizando = False
        self.ch_pozo, self.ch_log, self.ch_zona, self.ch_curva = (QComboBox() for _ in range(4))
        for ch in (self.ch_pozo, self.ch_log, self.ch_zona, self.ch_curva):
            ch.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            ch.setMinimumContentsLength(6)
        fila = QHBoxLayout()
        for texto, ch in (("Well", self.ch_pozo), ("Log", self.ch_log), ("Zone", self.ch_zona),
                          ("Curve", self.ch_curva)):
            fila.addWidget(QLabel(tr(texto)))
            fila.addWidget(ch, 1)
        acciones = QHBoxLayout()
        for clave in ("qc_report", "qc_flags"):
            if clave in getattr(app, "acciones", {}):
                b = QToolButton()
                b.setDefaultAction(app.acciones[clave])
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                b.setIconSize(QSize(18, 18))
                acciones.addWidget(b)
        self.b_ventana = QToolButton()
        self.b_ventana.setText(tr("Open as Window"))
        self.b_ventana.setIcon(iconos.icono("qc_window"))
        self.b_ventana.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_ventana.setToolTip(tr("Detach the QC panel as a separate window (double-click its title to dock it again)"))
        self.b_ventana.clicked.connect(self._flotar)
        self.b_ampliar = QToolButton()
        self.b_ampliar.setText(tr("Expand"))
        self.b_ampliar.setIcon(iconos.icono("zoom_in"))
        self.b_ampliar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_ampliar.setCheckable(True)
        self.b_ampliar.setToolTip(tr("QC over the whole window (hides the project tree and the plot); "
                                     "click again to go back"))
        self.b_ampliar.toggled.connect(lambda v: getattr(self.app, "ampliar_qc", lambda _: None)(v))
        acciones.addWidget(self.b_ampliar)
        acciones.addWidget(self.b_ventana)
        acciones.addStretch(1)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.claves = []
        self.paginas: dict[str, QWidget] = {}
        for clave, titulo, icono in PESTANAS:
            w = getattr(self, f"_crear_{clave}")()
            self.paginas[clave] = w
            self.tabs.addTab(w, iconos.icono(icono), tr(titulo))
            self.claves.append(clave)
        self.tabs.setCurrentIndex(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(fila)
        lay.addLayout(acciones)
        lay.addWidget(self.tabs, 1)
        self.sucias: set[str] = set(self.claves)
        self.ch_pozo.currentIndexChanged.connect(self._al_pozo)
        self.ch_log.currentIndexChanged.connect(self._al_log)
        self.ch_zona.currentIndexChanged.connect(self._al_zona)
        self.ch_curva.currentIndexChanged.connect(self._al_curva)
        self.tabs.currentChanged.connect(lambda *_: self.refrescar())
        self.setMinimumWidth(380)

    # ================================================================ selección
    @property
    def pr(self):
        return self.app.proyecto

    @property
    def sel(self):
        return self.app.seleccion

    def ir_a(self, clave: str):
        if clave in self.claves:
            self.tabs.setCurrentIndex(self.claves.index(clave))

    def _flotar(self):
        dock = self.parent()
        if hasattr(dock, "setFloating"):
            dock.setFloating(True)
            dock.resize(1000, 760)

    def seguir_seleccion(self):
        """Rellena los selectores con la selección global y redibuja la pestaña visible."""
        s = self.sel
        self._sincronizando = True
        try:
            self._llenar(self.ch_pozo, [p.nombre for p in self.pr.pozos], s.pozo)
            p = s.objeto_pozo()
            self._llenar(self.ch_log, [r.nombre for r in p.logs] if p else [], s.log)
            self._llenar(self.ch_zona, [tr("Whole log")] + [z.nombre for z in self.pr.zonas], s.zona + 1)
            reg = s.registro()
            curvas = self._curvas(reg)
            k = curvas.index(s.curva) if s.curva in curvas else (curvas.index("GR") if "GR" in curvas else 0)
            self._llenar(self.ch_curva, curvas, k if curvas else -1)
        finally:
            self._sincronizando = False
        self.sucias = set(self.claves)
        self.refrescar()

    def datos_cambiados(self):
        self.sucias = set(self.claves)
        if self.isVisible():
            self.refrescar()

    @staticmethod
    def _llenar(ch: QComboBox, items, i):
        ch.blockSignals(True)
        if [ch.itemText(k) for k in range(ch.count())] != list(items):
            ch.clear()
            ch.addItems(list(items))
        ch.setCurrentIndex(i if 0 <= i < ch.count() else (0 if ch.count() else -1))
        ch.blockSignals(False)

    @staticmethod
    def _curvas(reg) -> list[str]:
        if reg is None:
            return []
        return [c.nombre for k, c in enumerate(reg.columnas) if k not in (reg.indice_md, reg.indice_tvd)]

    def _al_pozo(self, i):
        if not self._sincronizando:
            self.sel.fijar(pozo=i)

    def _al_log(self, i):
        if not self._sincronizando:
            self.sel.fijar(log=i, curva="")

    def _al_zona(self, i):
        if not self._sincronizando:
            self.sel.fijar(zona=i - 1)

    def _al_curva(self, i):
        if not self._sincronizando:
            self.sel.fijar(curva=self.ch_curva.currentText())

    # ================================================================ utilidades
    def registro(self):
        return self.sel.registro()

    def curva(self) -> str:
        return self.ch_curva.currentText()

    def prof(self, reg):
        return reg.columnas[reg.indice_md].datos if reg.existe_columna(reg.indice_md) else \
            np.arange(reg.n_filas, dtype=float)

    def mascara_zona(self, reg, i_pozo=None, i_zona=None):
        """Muestras de la zona elegida (todo el registro si no hay zona)."""
        from .multipozo_ui import intervalo_zona
        i_pozo = self.sel.pozo if i_pozo is None else i_pozo
        i_zona = self.sel.zona if i_zona is None else i_zona
        if i_zona < 0:
            return np.ones(reg.n_filas, bool)
        t, b = intervalo_zona(self.pr, i_zona, i_pozo)
        return qc.mascara(reg, self.prof(reg), t, b)

    def refrescar(self):
        clave = self.claves[self.tabs.currentIndex()]
        if clave not in self.sucias:
            return
        self.sucias.discard(clave)
        try:
            getattr(self, f"_dibujar_{clave}")()
        except Exception as e:  # noqa: BLE001 - un dato raro no debe tumbar la interfaz
            self.app.registrar(tr("QC panel: {0}").format(f"{type(e).__name__}: {e}"))

    def _aviso_vacio(self, etiqueta: QLabel, reg) -> bool:
        if reg is None:
            etiqueta.setText(tr("Select a log to see its quality control."))
            return True
        return False

    # ================================================================ 0 dashboard
    def _crear_dashboard(self):
        w = QWidget()
        self.lbl_dash = QLabel()
        self.lbl_dash.setWordWrap(True)
        self.tabla_dash = QTableWidget()
        self.tabla_dash.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_dash.cellClicked.connect(self._clic_dashboard)
        lay = QVBoxLayout(w)
        lay.addWidget(self.lbl_dash)
        lay.addWidget(self.tabla_dash, 1)
        return w

    def matriz_dashboard(self):
        """(pozos, curvas, {(i, curva): (j_log, EstadoCurva)}) para todo el proyecto."""
        qc.notas_varios([r for p in self.pr.pozos for r in p.logs], self.app.alias)
        pozos = [p.nombre for p in self.pr.pozos]
        curvas: list[str] = []
        celdas = {}
        for i, p in enumerate(self.pr.pozos):
            for j, r in enumerate(p.logs):
                for nombre, e in qc.notas(r, self.app.alias).items():
                    if nombre not in curvas:
                        curvas.append(nombre)
                    if (i, nombre) not in celdas:
                        celdas[(i, nombre)] = (j, e)
        return pozos, curvas, celdas

    def _dibujar_dashboard(self):
        pozos, curvas, celdas = self.matriz_dashboard()
        t = self.tabla_dash
        t.clear()
        t.setRowCount(len(pozos))
        t.setColumnCount(len(curvas))
        t.setVerticalHeaderLabels(pozos)
        t.setHorizontalHeaderLabels(curvas)
        cuenta = {"A": 0, "B": 0, "C": 0}
        for i in range(len(pozos)):
            for k, nombre in enumerate(curvas):
                dato = celdas.get((i, nombre))
                if dato is None:
                    it = QTableWidgetItem("—")
                    it.setBackground(QBrush(QColor(225, 225, 225)))
                    it.setForeground(QBrush(QColor(140, 140, 140)))
                    it.setToolTip(tr("Curve missing in this well"))
                else:
                    j, e = dato
                    it = QTableWidgetItem(e.nota)
                    it.setBackground(QBrush(NOTA_FONDO[e.nota]))
                    it.setForeground(QBrush(NOTA_TEXTO[e.nota]))
                    it.setToolTip(f"{pozos[i]} / {self.pr.pozos[i].logs[j].nombre} / {nombre}\n"
                                  + ("\n".join(e.avisos) or tr("no issues")))
                    cuenta[e.nota] += 1
                it.setTextAlignment(Qt.AlignCenter)
                t.setItem(i, k, it)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.lbl_dash.setText(tr("{0} well(s) × {1} curve(s): A {2} · B {3} · C {4} · gray = missing. "
                                 "Click a cell to open that well and curve.").format(
            len(pozos), len(curvas), cuenta["A"], cuenta["B"], cuenta["C"]))

    def _clic_dashboard(self, fila, col):
        _, curvas, celdas = self.matriz_dashboard()
        nombre = curvas[col] if col < len(curvas) else ""
        dato = celdas.get((fila, nombre))
        if dato is None:
            return
        self.sel.fijar(pozo=fila, log=dato[0], curva=nombre)
        self.ir_a("depth")

    # ================================================================ 1 summary
    def _crear_summary(self):
        w = QWidget()
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setTextFormat(Qt.RichText)
        self.tabla_resumen = QTableWidget()
        self.tabla_resumen.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_resumen.verticalHeader().setVisible(False)
        self.tabla_resumen.cellClicked.connect(
            lambda f, c: self.sel.fijar(curva=self.tabla_resumen.item(f, 0).text()))
        lay = QVBoxLayout(w)
        lay.addWidget(self.lbl_resumen)
        lay.addWidget(self.tabla_resumen, 1)
        return w

    def estados_zona(self, reg):
        prof = self.prof(reg)
        sel = None if self.sel.zona < 0 else self.mascara_zona(reg)
        return [qc.evaluar_curva(c.datos, prof, c.nombre, c.unidad, self.app.alias, sel)
                for k, c in enumerate(reg.columnas) if k not in (reg.indice_md, reg.indice_tvd)]

    def _dibujar_summary(self):
        from ..nucleo import validacion
        reg = self.registro()
        t = self.tabla_resumen
        if self._aviso_vacio(self.lbl_resumen, reg):
            t.setRowCount(0)
            return
        estados = self.estados_zona(reg)
        cab = ["Curve", "Unit", "Grade", "Null %", "Gaps", "Min", "Max", "Mean", "P10", "P50", "P90",
               "Physical range", "Out", "Spikes", "Flat", "Notes"]
        t.setColumnCount(len(cab))
        t.setHorizontalHeaderLabels([tr(x) for x in cab])
        t.setRowCount(len(estados))
        f = lambda x: "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.4g}"  # noqa: E731
        for i, e in enumerate(estados):
            rango = f"{e.rango[0]:g}–{e.rango[1]:g}" if e.rango else "—"
            valores = (e.nombre, e.unidad, e.nota, f"{e.pct_nulos:g}", str(e.n_huecos), f(e.minimo), f(e.maximo),
                       f(e.media), f(e.p10), f(e.p50), f(e.p90), rango, str(e.fuera_rango), str(e.picos),
                       str(e.muestras_planas), "; ".join(e.avisos) or "OK")
            for j, v in enumerate(valores):
                it = QTableWidgetItem(v)
                if j == 2:
                    it.setBackground(QBrush(NOTA_FONDO[e.nota]))
                    it.setForeground(QBrush(NOTA_TEXTO[e.nota]))
                    it.setTextAlignment(Qt.AlignCenter)
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        problemas = validacion.validar(reg)
        notas = [e.nota for e in estados]
        mal = qc.condicion_pozo(reg, self.app.alias)
        self.lbl_resumen.setText(
            f"<b>{self.sel.objeto_pozo().nombre} / {reg.nombre}</b> · {self.sel.nombre_zona()} · "
            + tr("{0} curve(s): A {1} · B {2} · C {3}").format(len(notas), notas.count("A"), notas.count("B"),
                                                               notas.count("C"))
            + f"<br><b>{tr('LAS validation')}:</b> {validacion.resumen(problemas) if problemas else tr('no problems')}"
            + (f"<br><b>{tr('Borehole condition')}:</b> " + "; ".join(mal) if mal else ""))

    # ================================================================ 2 depth view
    def _crear_depth(self):
        w = QWidget()
        self.lbl_prof = QLabel()
        self.ck_pozo = QCheckBox(tr("Borehole condition track"))
        self.ck_pozo.setChecked(True)
        self.ck_maha = QCheckBox(tr("Multivariate outliers (Mahalanobis)"))
        for ck in (self.ck_pozo, self.ck_maha):
            ck.toggled.connect(lambda *_: (self.sucias.add("depth"), self.refrescar()))
        fila = QHBoxLayout()
        fila.addWidget(self.ck_pozo)
        fila.addWidget(self.ck_maha)
        fila.addStretch(1)
        self.vista_prof = pg.GraphicsLayoutWidget()
        lay = QVBoxLayout(w)
        lay.addLayout(fila)
        lay.addWidget(self.vista_prof, 1)
        lay.addWidget(self.lbl_prof)
        return w

    def atipicos_mahalanobis(self, reg, nombres=None):
        """Máscara de atípicos multivariados sobre las curvas con dato (resistividad en log10)."""
        idx = [k for k, c in enumerate(reg.columnas) if k not in (reg.indice_md, reg.indice_tvd)
               and (nombres is None or c.nombre in nombres) and _validos(c.datos).mean() > 0.5
               and not c.nombre.upper().endswith(("_QC", "_STD"))]
        if len(idx) < 2:
            return np.zeros(reg.n_filas, bool), idx
        cols = []
        for k in idx:
            d = _nan(reg.columnas[k].datos)
            if escala_log(reg.columnas[k].unidad):
                with np.errstate(all="ignore"):
                    d = np.log10(np.where(d > 0, d, np.nan))
            cols.append(d)
        _, malas, _ = qc.mahalanobis(np.column_stack(cols))
        return malas, idx

    def _dibujar_depth(self):
        reg = self.registro()
        gl = self.vista_prof
        gl.clear()
        if self._aviso_vacio(self.lbl_prof, reg):
            return
        prof = self.prof(reg)
        ok_z = _validos(prof)
        sel = self.mascara_zona(reg)
        curvas = [k for k, c in enumerate(reg.columnas) if k not in (reg.indice_md, reg.indice_tvd)
                  and not c.nombre.upper().endswith(("_QC", "_STD", "_P"))][:10]
        maha = self.atipicos_mahalanobis(reg)[0] if self.ck_maha.isChecked() else None
        n_pistas = len(curvas) + (2 if self.ck_pozo.isChecked() else 0)
        self._marcas_por_pista = max(2, int((max(gl.width(), 300) - 60) / max(n_pistas, 1) / PX_POR_ETIQUETA))
        zonas = [(z.nombre, z.prof(self.sel.pozo)) for z in self.pr.zonas]
        primero = None
        n_malas = 0
        for n, k in enumerate(curvas):
            c = reg.columnas[k]
            p = _pista(gl, 0, n)
            p.invertY(True)
            p.showGrid(x=True, y=True, alpha=0.2)
            p.setTitle(f"<span style='font-size:8pt'>{c.nombre}</span>")
            if n:
                p.hideAxis("left")
                p.setYLink(primero)
            else:
                p.getAxis("left").setWidth(44)
                primero = p
            d = _nan(c.datos)
            log = escala_log(c.unidad)
            if log:
                d = np.where(d > 0, d, np.nan)
                p.setLogMode(x=True, y=False)
            m = ok_z & sel
            p.plot(np.where(m, d, np.nan), np.where(m, prof, np.nan), pen=pg.mkPen(color_curva(self.app, c.nombre, n),
                                                                                   width=1.2), connect="finite")
            _marcas_pista(p, np.where(m, d, np.nan), log, self._marcas_por_pista)
            malas = qc.dudosas(reg, k, self.app.alias) & m
            n_malas += int(malas.sum())
            if malas.any():
                xs = d[malas]
                p.plot(np.log10(xs) if log else xs, prof[malas], pen=None, symbol="o", symbolSize=4,
                       symbolBrush=(220, 30, 30), symbolPen=None)
            if maha is not None and (maha & m).any():
                mm = maha & m & np.isfinite(d)
                xs = d[mm]
                p.plot(np.log10(xs) if log else xs, prof[mm], pen=None, symbol="x", symbolSize=6,
                       symbolPen=pg.mkPen((120, 40, 200), width=1.5))
            for nombre, z in zonas:
                p.addItem(pg.InfiniteLine(z, angle=0, pen=pg.mkPen((0, 120, 0), width=1, style=Qt.DashLine),
                                          label=nombre if n == 0 else None,
                                          labelOpts={"position": 0.05, "color": (0, 110, 0), "anchors": [(0, 1), (0, 1)]}))
        if self.ck_pozo.isChecked():
            self._pista_condicion(gl, reg, prof, ok_z & sel, len(curvas), primero)
        if primero is not None and sel.any():
            v = prof[ok_z & sel]
            primero.setYRange(float(v.min()), float(v.max()), padding=0.01)
        self.lbl_prof.setText(tr("{0} doubtful sample(s) in red (null excluded); dashed green: zone tops").format(n_malas)
                              + (tr("; purple ×: multivariate outliers") if maha is not None else ""))

    def _pista_condicion(self, gl, reg, prof, m, col, enlace):
        """CALI contra BS con el derrumbe sombreado y DRHO con su umbral (borehole condition)."""
        u = preferencias.actual().qc
        cc = qc.curvas_condicion(reg, self.app.alias)
        if cc["cali"] is None and cc["drho"] is None:
            return
        if cc["cali"] is not None:
            p = _pista(gl, 0, col)
            p.invertY(True)
            p.hideAxis("left")
            if enlace is not None:
                p.setYLink(enlace)
            p.setTitle("<span style='font-size:8pt'>CALI / BS</span>")
            cal = np.where(m, _nan(cc["cali"]), np.nan)
            p.plot(cal, np.where(m, prof, np.nan), pen=pg.mkPen((90, 60, 20), width=1.2), connect="finite")
            valores = [cal]
            if cc["bs"] is not None:
                bs = np.where(m, _nan(cc["bs"]), np.nan)
                valores.append(bs)
                ok = np.isfinite(cal) & np.isfinite(bs)
                p.plot(np.where(ok, bs, np.nan), np.where(ok, prof, np.nan), pen=pg.mkPen((0, 0, 0), width=1,
                                                                                      style=Qt.DashLine))
                # derrumbe sombreado: franjas horizontales entre BS y CALI donde CALI − BS supera el umbral
                lav = ok & ((cal - bs) > u.derrumbe)
                if lav.any():
                    alto = abs(float(np.nanmedian(np.diff(prof[np.isfinite(prof)])))) or 1.0
                    p.addItem(pg.BarGraphItem(x0=bs[lav], x1=cal[lav], y=prof[lav], height=alto,
                                              brush=pg.mkBrush(230, 60, 60, 120), pen=None))
            todos = np.concatenate([v[np.isfinite(v)] for v in valores])
            if todos.size:
                p.setXRange(float(todos.min()) - 0.5, float(todos.max()) + 0.5, padding=0)
                _marcas_pista(p, todos, False, getattr(self, "_marcas_por_pista", 3))
        if cc["drho"] is not None:
            p = _pista(gl, 0, col + 1)
            p.invertY(True)
            p.hideAxis("left")
            if enlace is not None:
                p.setYLink(enlace)
            p.setTitle("<span style='font-size:8pt'>DRHO</span>")
            dr = np.where(m, _nan(cc["drho"]), np.nan)
            p.plot(dr, np.where(m, prof, np.nan), pen=pg.mkPen((180, 0, 120), width=1.2), connect="finite")
            _marcas_pista(p, np.concatenate([dr, [-u.drho, u.drho]]), False, getattr(self, "_marcas_por_pista", 3))
            for v in (-u.drho, u.drho):
                p.addItem(pg.InfiniteLine(v, angle=90, pen=pg.mkPen((220, 30, 30), style=Qt.DashLine)))

    # ================================================================ 3 coverage
    def _crear_coverage(self):
        w = QWidget()
        self.g_cob = _grafico()
        self.g_cob.invertY(True)
        self.lbl_cob = QLabel()
        self.lbl_cob.setWordWrap(True)
        lay = QVBoxLayout(w)
        lay.addWidget(self.g_cob, 1)
        lay.addWidget(self.lbl_cob)
        return w

    def _dibujar_coverage(self):
        reg = self.registro()
        g = self.g_cob
        g.clear()
        if self._aviso_vacio(self.lbl_cob, reg):
            return
        nombres, m = qc.cobertura(reg, self.app.alias)
        if not nombres:
            return
        prof = self.prof(reg)
        sel = self.mascara_zona(reg)
        colores = np.array([[255, 255, 255], [70, 170, 90], [240, 150, 30]], np.ubyte)
        rgb = colores[m.T]                                  # (muestras, curvas, 3)
        rgb[~sel] = (rgb[~sel] * 0.35 + 165).astype(np.ubyte)
        img = pg.ImageItem(np.transpose(rgb, (1, 0, 2)))    # x = curva, y = muestra
        pv = prof[_validos(prof)]
        z0, z1 = (float(pv.min()), float(pv.max())) if pv.size else (0.0, float(reg.n_filas))
        from PySide6.QtCore import QRectF
        img.setRect(QRectF(0, z0, len(nombres), z1 - z0 or 1))
        g.addItem(img)
        eje = g.getPlotItem().getAxis("bottom")
        eje.setTicks([[(k + 0.5, n) for k, n in enumerate(nombres)]])
        g.setXRange(0, len(nombres), padding=0)
        pct = [100 * (fila == 1)[sel].mean() if sel.any() else 0 for fila in m]
        self.lbl_cob.setText(tr("Green: data · orange: doubtful · white: null. Valid % in {0}: ").format(
            self.sel.nombre_zona()) + ", ".join(f"{n} {p:.0f}%" for n, p in zip(nombres, pct)))

    # ================================================================ 4 histogram
    def _crear_histogram(self):
        w = QWidget()
        self.g_hist = _grafico()
        self.lbl_hist = QLabel()
        lay = QVBoxLayout(w)
        lay.addWidget(self.g_hist, 1)
        lay.addWidget(self.lbl_hist)
        return w

    def _dibujar_histogram(self):
        reg = self.registro()
        g = self.g_hist
        g.clear()
        if self._aviso_vacio(self.lbl_hist, reg):
            return
        k = reg.indice_columna(self.curva())
        if k < 0:
            self.lbl_hist.setText(tr("Choose a curve."))
            return
        c = reg.columnas[k]
        log = escala_log(c.unidad)
        datos = np.where(self.mascara_zona(reg), c.datos, NULO)
        v = qc.valores_log(datos, log)
        if v.size < 2:
            self.lbl_hist.setText(tr("Not enough data."))
            return
        h, bordes = np.histogram(v, 40)
        color = color_curva(self.app, c.nombre)
        g.plot(bordes, h / h.sum() * 100, stepMode="center", fillLevel=0, brush=(*color, 110),
               pen=pg.mkPen(color, width=1.5))
        p10, p50, p90 = np.percentile(v, [10, 50, 90])
        for valor, nombre in ((p10, "P10"), (p50, "P50"), (p90, "P90")):
            g.addItem(pg.InfiniteLine(valor, angle=90, pen=pg.mkPen((40, 40, 40), style=Qt.DashLine),
                                      label=nombre, labelOpts={"position": 0.92}))
        r = qc.rango_fisico(c.nombre, c.unidad, self.app.alias)
        if r is not None:
            for valor in r:
                if not log or valor > 0:
                    g.addItem(pg.InfiniteLine(np.log10(valor) if log else valor, angle=90,
                                              pen=pg.mkPen((220, 30, 30), width=2)))
        g.setLabel("bottom", f"{'log10 ' if log else ''}{c.nombre} {c.unidad}")
        g.setLabel("left", tr("Percentage"))
        fmt = (lambda x: f"{10 ** x:.4g}") if log else (lambda x: f"{x:.4g}")
        self.lbl_hist.setText(tr("{0} samples · P10 {1} · P50 {2} · P90 {3}").format(v.size, fmt(p10), fmt(p50), fmt(p90))
                              + (tr(" · red: physical range {0}–{1}").format(f"{r[0]:g}", f"{r[1]:g}") if r else ""))

    # ================================================================ 5 wells comparison
    def _crear_wells(self):
        w = QWidget()
        self.g_wh, self.g_wcdf = _grafico(tr("Histograms by well")), _grafico(tr("Cumulative (CDF) by well"))
        self.g_wbox, self.g_zbox = _grafico(tr("Boxplot by well (P5–P25–P50–P75–P95)")), _grafico(tr("Boxplot by zone"))
        for g in (self.g_wh, self.g_wcdf):
            g.addLegend(offset=(-5, 5))
        arriba, abajo = QSplitter(), QSplitter()
        arriba.addWidget(self.g_wh)
        arriba.addWidget(self.g_wcdf)
        abajo.addWidget(self.g_wbox)
        abajo.addWidget(self.g_zbox)
        v = QSplitter(Qt.Vertical)
        v.addWidget(arriba)
        v.addWidget(abajo)
        self.lbl_wells = QLabel()
        self.lbl_wells.setWordWrap(True)
        lay = QVBoxLayout(w)
        lay.addWidget(v, 1)
        lay.addWidget(self.lbl_wells)
        return w

    def series_pozos(self, curva: str, i_zona: int | None = None):
        """[(pozo, valores)] de la curva (por nombre o alias) en cada pozo, en la zona indicada."""
        i_zona = self.sel.zona if i_zona is None else i_zona
        out = []
        unidad = ""
        for i, p in enumerate(self.pr.pozos):
            for r in p.logs:
                k = buscar_curva(r, curva, self.app.alias)
                if k >= 0:
                    unidad = unidad or r.columnas[k].unidad
                    m = self.mascara_zona(r, i, i_zona)
                    d = r.columnas[k].datos[m]
                    out.append((p.nombre, d[_validos(d)]))
                    break
        return out, unidad

    def _dibujar_wells(self):
        curva = self.curva()
        for g in (self.g_wh, self.g_wcdf, self.g_wbox, self.g_zbox):
            g.clear()
        if not curva:
            self.lbl_wells.setText(tr("Choose a curve."))
            return
        series, unidad = self.series_pozos(curva)
        log = escala_log(unidad)
        series = [(n, np.log10(v[v > 0]) if log else v) for n, v in series]
        series = [(n, v) for n, v in series if v.size > 1]
        if not series:
            self.lbl_wells.setText(tr("No well has data of {0}.").format(curva))
            return
        todos = np.concatenate([v for _, v in series])
        bordes = np.linspace(*np.percentile(todos, [0.5, 99.5]), 41)
        etiqueta = f"{'log10 ' if log else ''}{curva} {unidad}"
        for k, (n, v) in enumerate(series):
            color = PALETA[k % len(PALETA)]
            h, _ = np.histogram(v, bordes)
            self.g_wh.plot(bordes, h / max(h.sum(), 1) * 100, stepMode="center", pen=pg.mkPen(color, width=2), name=n)
            x, f = qc.cdf(v)
            self.g_wcdf.plot(x, f, pen=pg.mkPen(color, width=2), name=n)
            q = qc.caja(v)
            if q is not None:
                _caja(self.g_wbox, k, q, color)
        self.g_wbox.getPlotItem().getAxis("bottom").setTicks([[(k, n) for k, (n, _) in enumerate(series)]])
        for g, eje in ((self.g_wh, "bottom"), (self.g_wcdf, "bottom"), (self.g_wbox, "left"), (self.g_zbox, "left")):
            g.setLabel(eje, etiqueta)
        self.g_wh.setLabel("left", tr("Percentage"))
        self.g_wcdf.setLabel("left", tr("Fraction"))
        # cajas por zona: la misma zona (por nombre) en cada pozo
        ticks = []
        ancho = 0.8 / max(len(self.pr.pozos), 1)
        for z in range(len(self.pr.zonas)):
            sz, _ = self.series_pozos(curva, z)
            for k, (n, v) in enumerate(sz):
                v = np.log10(v[v > 0]) if log else v
                q = qc.caja(v)
                if q is not None:
                    _caja(self.g_zbox, z + (k - (len(sz) - 1) / 2) * ancho, q, PALETA[k % len(PALETA)], ancho * 0.9)
            ticks.append((z, self.pr.zonas[z].nombre))
        self.g_zbox.getPlotItem().getAxis("bottom").setTicks([ticks])
        p5 = ", ".join(f"{n}: P5 {np.percentile(v, 5):.3g} / P95 {np.percentile(v, 95):.3g}" for n, v in series)
        self.lbl_wells.setText(tr("{0} in {1} ({2}). Colors are wells (same order in every chart). ").format(
            curva, self.sel.nombre_zona(), tr("log10") if log else tr("linear")) + p5)

    # ================================================================ 6 crossplot
    def _crear_crossplot(self):
        w = QWidget()
        self.ch_x, self.ch_y = QComboBox(), QComboBox()
        self.ck_lito = QCheckBox(tr("Lithology lines (neutron-density)"))
        self.ck_lito.setChecked(True)
        self.ck_maha_x = QCheckBox(tr("Mahalanobis outliers"))
        fila = QHBoxLayout()
        for t, wd in (("X", self.ch_x), ("Y", self.ch_y)):
            fila.addWidget(QLabel(t))
            fila.addWidget(wd, 1)
        fila.addWidget(self.ck_lito)
        fila.addWidget(self.ck_maha_x)
        for wd in (self.ch_x, self.ch_y):
            wd.currentIndexChanged.connect(lambda *_: (self.sucias.add("crossplot"), self.refrescar()))
        for wd in (self.ck_lito, self.ck_maha_x):
            wd.toggled.connect(lambda *_: (self.sucias.add("crossplot"), self.refrescar()))
        self.g_cross = _grafico()
        self.g_cross.addLegend(offset=(-5, 5))
        self.lbl_cross = QLabel()
        self.lbl_cross.setWordWrap(True)
        lay = QVBoxLayout(w)
        lay.addLayout(fila)
        lay.addWidget(self.g_cross, 1)
        lay.addWidget(self.lbl_cross)
        return w

    def _ejes_crossplot(self, reg):
        nombres = self._curvas(reg)
        a = self.app.alias

        def grupo(n):
            g = a.grupo_de(n) if a is not None else -1
            return a.grupos[g].nombre.upper() if g >= 0 else n.upper()
        for k, (ch, grupo_pref) in enumerate(((self.ch_x, "PHIN"), (self.ch_y, "RHOB"))):
            if [ch.itemText(i) for i in range(ch.count())] == nombres:
                continue
            ch.blockSignals(True)
            ch.clear()
            ch.addItems(nombres)
            elegido = next((n for n in nombres if grupo(n) == grupo_pref or n.upper() == grupo_pref),
                           nombres[min(k, len(nombres) - 1)] if nombres else "")
            ch.setCurrentText(elegido)
            ch.blockSignals(False)

    def _dibujar_crossplot(self):
        reg = self.registro()
        g = self.g_cross
        g.clear()
        if self._aviso_vacio(self.lbl_cross, reg):
            return
        self._ejes_crossplot(reg)
        kx, ky = reg.indice_columna(self.ch_x.currentText()), reg.indice_columna(self.ch_y.currentText())
        if kx < 0 or ky < 0:
            return
        cx, cy = reg.columnas[kx], reg.columnas[ky]
        x, y = _nan(cx.datos), _nan(cy.datos)
        sel = self.mascara_zona(reg) & np.isfinite(x) & np.isfinite(y)
        malas = (qc.dudosas(reg, kx, self.app.alias) | qc.dudosas(reg, ky, self.app.alias)) & sel
        buenas = sel & ~malas
        logx, logy = escala_log(cx.unidad), escala_log(cy.unidad)
        g.setLogMode(x=logx, y=logy)
        tx = (lambda v: np.log10(np.where(v > 0, v, np.nan))) if logx else (lambda v: v)
        ty = (lambda v: np.log10(np.where(v > 0, v, np.nan))) if logy else (lambda v: v)
        g.plot(tx(x[buenas]), ty(y[buenas]), pen=None, symbol="o", symbolSize=4, symbolPen=None,
               symbolBrush=(*color_curva(self.app, cx.nombre), 140), name=tr("data"))
        if malas.any():
            g.plot(tx(x[malas]), ty(y[malas]), pen=None, symbol="o", symbolSize=5, symbolPen=None,
                   symbolBrush=(220, 30, 30, 220), name=tr("doubtful (QC)"))
        n_maha = 0
        if self.ck_maha_x.isChecked():
            maha, _ = self.atipicos_mahalanobis(reg, [cx.nombre, cy.nombre])
            maha &= sel
            n_maha = int(maha.sum())
            if maha.any():
                g.plot(tx(x[maha]), ty(y[maha]), pen=None, symbol="x", symbolSize=8,
                       symbolPen=pg.mkPen((120, 40, 200), width=1.5), name=tr("Mahalanobis outlier"))
        texto_lito = ""
        if self.ck_lito.isChecked() and self._es_nd(cx, cy):
            lineas = qc.lineas_nd(1.0, qc.escala_neutron(cx.unidad), qc.escala_densidad(cy.unidad))
            colores = {"Sandstone": (200, 160, 0), "Limestone": (40, 120, 220), "Dolomite": (150, 60, 170)}
            for nombre, (n, d, f) in lineas.items():
                g.plot(n, d, pen=pg.mkPen(colores[nombre], width=2), symbol="t", symbolSize=5,
                       symbolBrush=colores[nombre], name=tr(nombre))
                for k in (2, 4, 6):
                    t = pg.TextItem(f"{f[k] * 100:.0f}", color=colores[nombre], anchor=(0, 1))
                    t.setPos(n[k], d[k])
                    g.addItem(t)
            g.invertY(True)
            texto_lito = tr(" · Lithology lines: approximate standard chart, fresh water, limestone-calibrated "
                            "neutron; labels are porosity %.")
        else:
            g.invertY(False)
        g.setLabel("bottom", f"{cx.nombre} {cx.unidad}")
        g.setLabel("left", f"{cy.nombre} {cy.unidad}")
        self.lbl_cross.setText(tr("{0} points · {1} doubtful in red").format(int(sel.sum()), int(malas.sum()))
                               + (tr(" · {0} Mahalanobis outlier(s)").format(n_maha) if self.ck_maha_x.isChecked() else "")
                               + texto_lito)

    def _es_nd(self, cx, cy) -> bool:
        a = self.app.alias

        def grupo(n):
            g = a.grupo_de(n) if a is not None else -1
            return a.grupos[g].nombre.upper() if g >= 0 else n.upper()
        return grupo(cx.nombre) in ("PHIN", "NPHI") and grupo(cy.nombre) in ("RHOB",)

    # ================================================================ 7 correlation
    def _crear_correlation(self):
        w = QWidget()
        self.g_corr = _grafico()
        self.g_corr.invertY(True)
        self.g_corr.setAspectLocked(True)
        self.lbl_corr = QLabel()
        lay = QVBoxLayout(w)
        lay.addWidget(self.g_corr, 1)
        lay.addWidget(self.lbl_corr)
        return w

    def _dibujar_correlation(self):
        reg = self.registro()
        g = self.g_corr
        g.clear()
        if self._aviso_vacio(self.lbl_corr, reg):
            return
        nombres = [n for n in self._curvas(reg) if not n.upper().endswith(("_QC", "_STD"))]
        nombres, m = qc.correlacion(reg, nombres, self.mascara_zona(reg))
        if not nombres:
            return
        mapa = pg.ColorMap([0.0, 0.5, 1.0], [(33, 102, 172), (255, 255, 255), (178, 24, 43)])
        img = pg.ImageItem(np.nan_to_num(m.T, nan=0.0))
        img.setLookupTable(mapa.getLookupTable(0.0, 1.0, 256))
        img.setLevels((-1, 1))
        g.addItem(img)
        for i in range(len(nombres)):
            for j in range(len(nombres)):
                v = m[i, j]
                t = pg.TextItem("—" if not np.isfinite(v) else f"{v:.2f}",
                                color=(255, 255, 255) if np.isfinite(v) and abs(v) > 0.6 else (30, 30, 30),
                                anchor=(0.5, 0.5))
                t.setPos(j + 0.5, i + 0.5)
                g.addItem(t)
        ticks = [(k + 0.5, n) for k, n in enumerate(nombres)]
        g.getPlotItem().getAxis("bottom").setTicks([ticks])
        g.getPlotItem().getAxis("left").setTicks([ticks])
        self.lbl_corr.setText(tr("Pearson r between curves ({0}); resistivity in log10. Blue −1 · white 0 · red +1.")
                              .format(self.sel.nombre_zona()))

    # ================================================================ 8 before/after
    def _crear_before_after(self):
        w = QWidget()
        self.g_ba, self.g_dif = _grafico(tr("Original vs edited")), _grafico(tr("Difference (edited − original)"))
        for g in (self.g_ba, self.g_dif):
            g.invertY(True)
        self.g_dif.setYLink(self.g_ba)
        self.g_ba.addLegend(offset=(-5, 5))
        sp = QSplitter()
        sp.addWidget(self.g_ba)
        sp.addWidget(self.g_dif)
        sp.setSizes([600, 300])
        self.lbl_ba = QLabel()
        self.lbl_ba.setWordWrap(True)
        lay = QVBoxLayout(w)
        lay.addWidget(sp, 1)
        lay.addWidget(self.lbl_ba)
        return w

    def _dibujar_before_after(self):
        reg = self.registro()
        for g in (self.g_ba, self.g_dif):
            g.clear()
        if self._aviso_vacio(self.lbl_ba, reg):
            return
        nombre = self.curva()
        res = qc.antes_despues(reg, nombre) if nombre else None
        if res is None:
            from ..nucleo import historial
            editadas = [c.nombre for c in reg.columnas if historial.original(reg, c.nombre) is not None]
            self.lbl_ba.setText(tr("{0} has not been edited. Edited curves of this log: {1}").format(
                nombre or "—", ", ".join(editadas) or tr("(none)")))
            return
        prof, orig, actual, dif = res
        sel = self.mascara_zona(reg)
        color = color_curva(self.app, nombre)
        self.g_ba.plot(np.where(sel, _nan(orig), np.nan), prof, pen=pg.mkPen((150, 150, 150), width=2.5),
                       connect="finite", name=tr("original"))
        self.g_ba.plot(np.where(sel, _nan(actual), np.nan), prof, pen=pg.mkPen(color, width=1.2), connect="finite",
                       name=tr("edited"))
        self.g_dif.plot(np.where(sel, dif, np.nan), prof, pen=pg.mkPen((214, 110, 0), width=1.2), connect="finite")
        self.g_dif.addItem(pg.InfiniteLine(0, angle=90, pen=pg.mkPen((90, 90, 90), style=Qt.DashLine)))
        cambiadas = int(np.count_nonzero(~((_nan(orig) == _nan(actual)) | (np.isnan(_nan(orig)) & np.isnan(_nan(actual))))))
        d = dif[np.isfinite(dif)]
        self.lbl_ba.setText(tr("{0}: {1} sample(s) differ from the original; mean change {2}, max |change| {3}.").format(
            nombre, cambiadas, f"{d.mean():.4g}" if d.size else "—", f"{np.abs(d).max():.4g}" if d.size else "—"))

    # ================================================================ 9 depth step
    def _crear_depth_step(self):
        w = QWidget()
        self.g_paso = _grafico()
        self.g_paso.invertY(True)
        self.lbl_paso = QLabel()
        self.lbl_paso.setWordWrap(True)
        lay = QVBoxLayout(w)
        lay.addWidget(self.g_paso, 1)
        lay.addWidget(self.lbl_paso)
        return w

    def _dibujar_depth_step(self):
        reg = self.registro()
        g = self.g_paso
        g.clear()
        if self._aviso_vacio(self.lbl_paso, reg):
            return
        medio, paso, mal, tipico = qc.paso_profundidad(self.prof(reg))
        if not paso.size:
            return
        g.plot(paso, medio, pen=pg.mkPen((30, 90, 180), width=1.2))
        if mal.any():
            g.plot(paso[mal], medio[mal], pen=None, symbol="o", symbolSize=6, symbolBrush=(220, 30, 30), symbolPen=None)
        g.addItem(pg.InfiniteLine(tipico, angle=90, pen=pg.mkPen((0, 140, 0), style=Qt.DashLine)))
        g.setLabel("bottom", tr("Depth step"))
        g.setLabel("left", tr("Depth"))
        self.lbl_paso.setText(tr("Typical step {0} · {1} irregular interval(s) in red (> 1% from the typical step, "
                                 "or not increasing). Use Resample to make it constant.").format(
            f"{tipico:.4g}", int(mal.sum())))

    # ================================================================ 10 repeat pass
    def _crear_repeat(self):
        w = QWidget()
        self.ch_rep = QComboBox()
        self.ch_rep.currentIndexChanged.connect(lambda *_: (self.sucias.add("repeat"), self.refrescar()))
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("Repeat pass log")))
        fila.addWidget(self.ch_rep, 1)
        self.g_rep, self.g_rep_dif = _grafico(tr("Main vs repeat pass")), _grafico(tr("Difference (repeat − main)"))
        for g in (self.g_rep, self.g_rep_dif):
            g.invertY(True)
        self.g_rep_dif.setYLink(self.g_rep)
        self.g_rep.addLegend(offset=(-5, 5))
        sp = QSplitter()
        sp.addWidget(self.g_rep)
        sp.addWidget(self.g_rep_dif)
        sp.setSizes([600, 300])
        self.lbl_rep = QLabel()
        self.lbl_rep.setWordWrap(True)
        lay = QVBoxLayout(w)
        lay.addLayout(fila)
        lay.addWidget(sp, 1)
        lay.addWidget(self.lbl_rep)
        return w

    def _dibujar_repeat(self):
        reg = self.registro()
        for g in (self.g_rep, self.g_rep_dif):
            g.clear()
        if self._aviso_vacio(self.lbl_rep, reg):
            return
        pozo = self.sel.objeto_pozo()
        otros = [r for r in pozo.logs if r is not reg]
        nombres = [r.nombre for r in otros]
        actual = self.ch_rep.currentText()
        self.ch_rep.blockSignals(True)
        if [self.ch_rep.itemText(k) for k in range(self.ch_rep.count())] != nombres:
            self.ch_rep.clear()
            self.ch_rep.addItems(nombres)
            pref = next((n for n in nombres if "REP" in n.upper()), nombres[0] if nombres else "")
            self.ch_rep.setCurrentText(actual if actual in nombres else pref)
        self.ch_rep.blockSignals(False)
        if not otros:
            self.lbl_rep.setText(tr("The well has only one log: import the repeat pass as another log of the same well."))
            return
        rep = otros[self.ch_rep.currentIndex()]
        nombre = self.curva()
        k, kr = reg.indice_columna(nombre), buscar_curva(rep, nombre, self.app.alias)
        if k < 0 or kr < 0 or not rep.existe_columna(rep.indice_md):
            self.lbl_rep.setText(tr("{0} is not in the repeat pass {1}.").format(nombre or "—", rep.nombre))
            return
        prof = self.prof(reg)
        res = qc.repetibilidad(prof, reg.columnas[k].datos, rep.columnas[rep.indice_md].datos, rep.columnas[kr].datos)
        if res is None:
            self.lbl_rep.setText(tr("The main and repeat passes do not overlap."))
            return
        sel = self.mascara_zona(reg)
        self.g_rep.plot(np.where(sel, _nan(reg.columnas[k].datos), np.nan), prof,
                        pen=pg.mkPen(color_curva(self.app, nombre), width=1.4), connect="finite", name=tr("main"))
        self.g_rep.plot(np.where(sel, res["repetida"], np.nan), prof, pen=pg.mkPen((120, 120, 120), width=1.2,
                        style=Qt.DashLine), connect="finite", name=tr("repeat"))
        self.g_rep_dif.plot(np.where(sel, res["diferencia"], np.nan), prof, pen=pg.mkPen((214, 110, 0), width=1.2),
                            connect="finite")
        for v in (-res["tolerancia"], 0, res["tolerancia"]):
            self.g_rep_dif.addItem(pg.InfiniteLine(v, angle=90, pen=pg.mkPen((90, 90, 90) if v == 0 else (220, 30, 30),
                                                                             style=Qt.DashLine)))
        self.lbl_rep.setText(tr("{0} vs {1}: {2} samples · mean difference {3} · std {4} · r = {5} · {6}% within "
                                "±{7} (5% of P10–P90)").format(
            reg.nombre, rep.nombre, res["muestras"], f"{res['media']:.4g}", f"{res['desv']:.4g}", f"{res['r']:.3f}",
            f"{res['dentro']:.0f}", f"{res['tolerancia']:.3g}"))
