"""Vistas del gráfico de registros y del corte transversal."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QScrollArea, QSlider, QSpinBox, QSplitter, QVBoxLayout, QWidget)

from ..i18n import tr
from ..nucleo.comun import NULO
from ..nucleo.proyecto import LogPlot as EstadoLogPlot
from ..nucleo.proyecto import PozoCorte
from .dialogos import boton
from .editores import EditorBase
from .logplot import MODO_MD, MODO_TVDSS, NOMBRES_MODO, LogPlot, datos_desde_proyecto, qcolor
from .visor import VisorLogPlot

ESCALA_MIN, ESCALA_MAX = 5, 10000


def declarar_vertical(pozo) -> float:
    """Trayectoria vertical explícita (estaciones en 0 y al fondo, inclinación 0); devuelve el fondo."""
    from ..nucleo.trayectoria import Estacion
    fondo = 0.0
    for x in pozo.logs:
        if x.existe_columna(x.indice_md):
            md = x.columnas[x.indice_md].datos
            if (md != NULO).any():
                fondo = max(fondo, float(md[md != NULO].max()))
    t = pozo.trayectoria
    t.estaciones = [Estacion(md=0.0, inc=0.0), Estacion(md=max(fondo, 1.0), inc=0.0)]
    t.calcular()
    return fondo


def calcular_tvd(app, pozos) -> int:
    """Columna TVD de los registros que no la tienen, con la trayectoria de su pozo (una sola entrada
    de deshacer). Devuelve cuántos registros cambió."""
    from ..nucleo import historial, operaciones
    sin_tvd = [(x, p.trayectoria) for p in pozos if len(p.trayectoria.estaciones) >= 2 for x in p.logs
               if x.existe_columna(x.indice_md) and not x.existe_columna(x.indice_tvd)]
    if sin_tvd:
        with app.operacion("Create TVD from MD"):
            for x, t in sin_tvd:
                historial.aplicar(x, "Create TVD from MD", "depth axis", operaciones.crear_tvd, x, t)
    return len(sin_tvd)


class PaginaLogPlot(EditorBase):
    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.ch_lp = QComboBox()
        self.ch_pozo, self.ch_las, self.ch_lito, self.ch_comp, self.ch_tpl, self.ch_modo = (
            QComboBox() for _ in range(6))
        self.ch_modo.addItems([NOMBRES_MODO[i] for i in range(3)])
        self.ck_prof = QCheckBox(tr("Custom depth"))
        self.sp_tope, self.sp_base = QDoubleSpinBox(), QDoubleSpinBox()
        for s in (self.sp_tope, self.sp_base):
            s.setRange(-1e6, 1e6)
            s.setDecimals(2)
        self.ck_escala = QCheckBox(tr("Custom scale"))
        self.ck_vacias = QCheckBox(tr("Hide empty tracks"))
        self.ck_vacias.setToolTip(tr("Tracks without data in this well are not drawn; the template does not change"))
        self.sp_escala = QSpinBox()
        self.sp_escala.setRange(ESCALA_MIN, ESCALA_MAX)
        self.sld_escala = QSlider(Qt.Horizontal)
        self.sld_escala.setRange(ESCALA_MIN, 2000)
        self.lista_zonas = QListWidget()
        b_add = boton("New", "new", "Create a new log plot")
        b_del = boton("Delete", "delete", "Delete this log plot")
        b_ref = boton("Refresh", "refresh", "Redraw the log plot")
        b_exp = boton("Export...", "export", "Save the log plot as a PNG image")
        b_zin = boton("Zoom In", "zoom_in", "")
        b_zout = boton("Zoom Out", "zoom_out", "")
        b_znorm = boton("Zoom 1:1", "zoom_reset", "")
        # capas opcionales: los resultados de QC, DL y edición vuelven a la vista principal (D56)
        self.ck_qc = QCheckBox(tr("QC flags"))
        self.ck_qc.setToolTip(tr("Mark the samples flagged as doubtful by QC (red dots and ticks)"))
        self.ck_dl = QCheckBox(tr("DL uncertainty"))
        self.ck_dl.setToolTip(tr("Band prediction ± standard deviation around <curve>_DL / _FILL curves"))
        self.ck_orig = QCheckBox(tr("Original (before edits)"))
        self.ck_orig.setToolTip(tr("Dashed gray: the curve before its first edit"))
        g = QGridLayout()
        # la plantilla se edita desde aquí (o con clic derecho en el gráfico), no en una pestaña aparte
        b_tpl = boton("Edit...", "templates", "Edit the template of this log plot: tracks, curves and scales")
        b_tpl.clicked.connect(lambda: self.app.editar_plantilla(max(self.ch_tpl.currentIndex() - 1, 0)))
        fila_tpl = QWidget()
        lay_tpl = QHBoxLayout(fila_tpl)
        lay_tpl.setContentsMargins(0, 0, 0, 0)
        lay_tpl.addWidget(self.ch_tpl, 1)
        lay_tpl.addWidget(b_tpl)
        filas = [("Log plot", self.ch_lp), ("Well", self.ch_pozo), ("Las", self.ch_las),
                 ("Lithology", self.ch_lito), ("Completion", self.ch_comp), ("Template", fila_tpl)]
        for i, (t, w) in enumerate(filas):
            g.addWidget(QLabel(tr(t)), i, 0)
            g.addWidget(w, i, 1)
        n = len(filas)
        g.addWidget(self.ck_prof, n, 0, 1, 2)
        g.addWidget(QLabel(tr("Top")), n + 1, 0)
        g.addWidget(self.sp_tope, n + 1, 1)
        g.addWidget(QLabel(tr("Bottom")), n + 2, 0)
        g.addWidget(self.sp_base, n + 2, 1)
        g.addWidget(self.ck_escala, n + 3, 0, 1, 2)
        g.addWidget(self.sp_escala, n + 4, 0)
        g.addWidget(self.sld_escala, n + 4, 1)
        g.addWidget(self.ck_vacias, n + 5, 0, 1, 2)
        n += 1
        g.addWidget(QLabel(tr("Zones")), n + 5, 0)
        g.addWidget(self.lista_zonas, n + 6, 0, 1, 2)
        g.addWidget(QLabel(f"<b>{tr('Layers')}</b>"), n + 7, 0, 1, 2)
        for k, ck in enumerate((self.ck_qc, self.ck_dl, self.ck_orig)):
            g.addWidget(ck, n + 8 + k, 0, 1, 2)
        bot = QHBoxLayout()
        for b in (b_add, b_del, b_ref, b_exp):
            bot.addWidget(b)
        zoom = QHBoxLayout()
        for b in (b_zin, b_zout, b_znorm):
            zoom.addWidget(b)
        izq = QWidget()
        lay_izq = QVBoxLayout(izq)
        lay_izq.addLayout(g)
        lay_izq.addLayout(bot)
        lay_izq.addLayout(zoom)
        lay_izq.addStretch(1)
        izq.setMaximumWidth(330)
        self.visor = VisorLogPlot()
        # el eje de profundidad se elige sobre el gráfico, como el eje de una hoja de cálculo (D123)
        self.lbl_ref = QLabel()
        barra = QHBoxLayout()
        barra.setContentsMargins(4, 0, 4, 0)
        barra.addWidget(QLabel(f"<b>{tr('Depth axis')}</b>"))
        barra.addWidget(self.ch_modo)
        barra.addWidget(self.lbl_ref)
        barra.addStretch(1)
        der = QWidget()
        lay_der = QVBoxLayout(der)
        lay_der.setContentsMargins(0, 0, 0, 0)
        lay_der.addLayout(barra)
        lay_der.addWidget(self.visor, 1)
        sp = QSplitter()
        sp.addWidget(izq)
        sp.addWidget(der)
        sp.setStretchFactor(1, 4)
        QVBoxLayout(self).addWidget(sp)
        self._cargando = False

        self.ch_lp.currentIndexChanged.connect(self._al_lp)
        self.ch_pozo.currentIndexChanged.connect(self._al_pozo)
        for w in (self.ch_las, self.ch_lito, self.ch_comp, self.ch_tpl):
            w.currentIndexChanged.connect(self._guardar_y_dibujar)
        self.ch_modo.currentIndexChanged.connect(self._al_modo)
        for w in (self.ck_prof, self.ck_escala, self.ck_vacias):
            w.toggled.connect(self._guardar_y_dibujar)
        for w in (self.ck_qc, self.ck_dl, self.ck_orig):
            w.toggled.connect(self.dibujar)
        self.sp_tope.valueChanged.connect(self._guardar_y_dibujar)
        self.sp_base.valueChanged.connect(self._guardar_y_dibujar)
        self.sp_escala.valueChanged.connect(self._escala)
        self.sld_escala.valueChanged.connect(self.sp_escala.setValue)
        self.lista_zonas.itemChanged.connect(self._guardar_y_dibujar)
        b_add.clicked.connect(self.nuevo)
        b_del.clicked.connect(self.borrar)
        b_ref.clicked.connect(self.dibujar)
        b_exp.clicked.connect(self.exportar)
        b_zin.clicked.connect(self.visor.lienzo.acercar)
        b_zout.clicked.connect(self.visor.lienzo.alejar)
        b_znorm.clicked.connect(self.visor.lienzo.zoom_normal)
        self.visor.lienzo.zona_movida.connect(self._zona_movida)
        self.visor.lienzo.setContextMenuPolicy(Qt.CustomContextMenu)
        self.visor.lienzo.customContextMenuRequested.connect(self._menu_grafico)

    def _menu_grafico(self, pos):
        from PySide6.QtWidgets import QMenu
        from . import iconos
        m = QMenu(self)
        m.addAction(iconos.icono("templates"), tr("Configure template..."),
                    lambda: self.app.editar_plantilla(max(self.ch_tpl.currentIndex() - 1, 0)))
        m.addAction(iconos.icono("export"), tr("Export..."), self.exportar)
        m.addAction(iconos.icono("refresh"), tr("Refresh"), self.dibujar)
        m.exec(self.visor.lienzo.mapToGlobal(pos))

    def estado(self) -> EstadoLogPlot | None:
        i = self.ch_lp.currentIndex()
        return self.pr.logplots[i] if 0 <= i < len(self.pr.logplots) else None

    def refrescar(self):
        self._cargando = True
        i = self.ch_lp.currentIndex()
        self.ch_lp.clear()
        self.ch_lp.addItems([lp.nombre for lp in self.pr.logplots])
        if self.pr.logplots:
            i = i if 0 <= i < len(self.pr.logplots) else max(0, self.pr.logplot_actual)
            self.ch_lp.setCurrentIndex(min(i, len(self.pr.logplots) - 1))
        self._cargando = False
        self._al_lp()

    def _al_lp(self, *_):
        if self._cargando:
            return
        lp = self.estado()
        self._cargando = True
        self._combo_pozos(self.ch_pozo, lp.pozo if lp else -1)
        self._llenar_pozo(lp)
        self.ch_tpl.clear()
        self.ch_tpl.addItem(tr("(none)"))
        self.ch_tpl.addItems([t.nombre for t in self.pr.plantillas])
        if lp:
            self.ch_tpl.setCurrentIndex(lp.plantilla + 1)
            self.ch_modo.setCurrentIndex(lp.modo_prof)
            self.ck_prof.setChecked(lp.usar_prof_propia)
            self.sp_tope.setValue(lp.prof_tope)
            self.sp_base.setValue(lp.prof_base)
            self.ck_escala.setChecked(lp.usar_escala_propia)
            self.ck_vacias.setChecked(lp.ocultar_vacias)
            self.sp_escala.setValue(int(lp.escala))
            self.pr.logplot_actual = self.ch_lp.currentIndex()
        self.lista_zonas.clear()
        for k, z in enumerate(self.pr.zonas):
            it = QListWidgetItem(z.nombre)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            vis = lp.zonas_visibles[k] if lp and k < len(lp.zonas_visibles) else True
            it.setCheckState(Qt.Checked if vis else Qt.Unchecked)
            self.lista_zonas.addItem(it)
        self._cargando = False
        self.dibujar()

    def _llenar_pozo(self, lp):
        i = self.ch_pozo.currentIndex()
        pozo = self.pr.pozos[i] if 0 <= i < len(self.pr.pozos) else None
        for ch, lista, sel in ((self.ch_las, pozo.logs if pozo else [], lp.las if lp else -1),
                               (self.ch_lito, pozo.litologias if pozo else [], lp.lito if lp else -1),
                               (self.ch_comp, pozo.completaciones if pozo else [], lp.comp if lp else -1)):
            ch.clear()
            ch.addItem(tr("(none)"))
            ch.addItems([x.nombre for x in lista])
            ch.setCurrentIndex(sel + 1 if sel + 1 < ch.count() else 0)

    def _al_pozo(self, *_):
        if self._cargando:
            return
        lp = self.estado()
        if lp:
            lp.pozo = self.ch_pozo.currentIndex()
            lp.las = lp.lito = lp.comp = 0
        self._cargando = True
        self._llenar_pozo(lp)
        self._cargando = False
        self._guardar_y_dibujar()

    def _escala(self, v):
        self.sld_escala.blockSignals(True)
        self.sld_escala.setValue(min(v, self.sld_escala.maximum()))
        self.sld_escala.blockSignals(False)
        if not self._cargando:
            self.ck_escala.setChecked(True)
            self._guardar_y_dibujar()

    def _guardar_y_dibujar(self, *_):
        if self._cargando:
            return
        lp = self.estado()
        if lp is None:
            return
        lp.pozo = self.ch_pozo.currentIndex()
        lp.las, lp.lito, lp.comp = (self.ch_las.currentIndex() - 1, self.ch_lito.currentIndex() - 1,
                                    self.ch_comp.currentIndex() - 1)
        lp.plantilla = self.ch_tpl.currentIndex() - 1
        lp.modo_prof = self.ch_modo.currentIndex()
        lp.usar_prof_propia = self.ck_prof.isChecked()
        lp.prof_tope, lp.prof_base = self.sp_tope.value(), self.sp_base.value()
        lp.usar_escala_propia = self.ck_escala.isChecked()
        lp.ocultar_vacias = self.ck_vacias.isChecked()
        lp.escala = float(self.sp_escala.value())
        lp.zonas_visibles = [self.lista_zonas.item(k).checkState() == Qt.Checked
                             for k in range(self.lista_zonas.count())]
        self.pr.modificado = True
        self.dibujar()

    # ------------------------------------------------------------ eje de profundidad (D123)
    def _pozo_y_registro(self):
        lp = self.estado()
        if lp is None or not 0 <= lp.pozo < len(self.pr.pozos):
            return None, None
        pozo = self.pr.pozos[lp.pozo]
        reg = pozo.logs[lp.las] if 0 <= lp.las < len(pozo.logs) else None
        return pozo, reg

    def _al_modo(self, *_):
        if self._cargando:
            return
        if self.ch_modo.currentIndex() != MODO_MD and not self.preparar_tvd(self.ch_modo.currentIndex()):
            self._cargando = True
            self.ch_modo.setCurrentIndex(MODO_MD)
            self._cargando = False
        self._guardar_y_dibujar()

    def preparar_tvd(self, modo: int, preguntar=None) -> bool:
        """Deja el pozo listo para verlo en TVD o TVDSS sin pasos intermedios: si no tiene trayectoria
        pregunta si es vertical (y lo anota) o abre la vista Trayectoria; para TVDSS pide la KB si
        falta; y calcula la columna TVD de sus registros. False si el usuario no quiso seguir.
        `preguntar` (pruebas): reemplaza al diálogo y devuelve "vertical", "trajectory" o ""."""
        pozo, reg = self._pozo_y_registro()
        if pozo is None or reg is None:
            return True
        t = pozo.trayectoria
        if len(t.estaciones) < 2:
            if preguntar is not None:
                r = preguntar()
            else:
                caja = QMessageBox(self)
                caja.setIcon(QMessageBox.Question)
                caja.setWindowTitle(tr("Depth axis"))
                caja.setText(tr("{0} has no trajectory, so its TVD is unknown.").format(pozo.nombre))
                caja.setInformativeText(tr("If the well is vertical, TVD equals MD. If it is deviated, load its "
                                           "survey stations in the Trajectory view."))
                b_vert = caja.addButton(tr("The well is vertical"), QMessageBox.AcceptRole)
                b_tray = caja.addButton(tr("Open Trajectory"), QMessageBox.ActionRole)
                caja.addButton(QMessageBox.Cancel)
                caja.exec()
                r = ("vertical" if caja.clickedButton() is b_vert
                     else "trajectory" if caja.clickedButton() is b_tray else "")
            if r == "trajectory":
                self.app.mostrar_vista("tray")
                return False
            if r != "vertical":
                return False
            fondo = declarar_vertical(pozo)
            self.pr.modificado = True
            self.app.registrar(tr("{0}: declared vertical (stations at 0 and {1:g}, inclination 0): TVD = MD")
                               .format(pozo.nombre, fondo))
        if modo == MODO_TVDSS and t.tvd_a_ss == 0.0:
            if preguntar is not None:
                v, ok = 0.0, True
            else:
                v, ok = QInputDialog.getDouble(self, tr("KB elevation"),
                                               tr("Elevation of the depth reference (KB) above sea level for {0}:")
                                               .format(pozo.nombre), 0.0, -1e5, 1e5, 2)
            if not ok:
                return False
            t.tvd_a_ss = v
            t.calcular()
            self.pr.modificado = True
        n = calcular_tvd(self.app, [pozo])
        if n:
            self.pr.modificado = True
            self.app.registrar(tr("{0}: TVD computed for {1} log(s) from its trajectory").format(pozo.nombre, n))
            self.app.refrescar_estado()
        return True

    def _texto_referencia(self):
        pozo, _ = self._pozo_y_registro()
        modo = self.ch_modo.currentIndex()
        if pozo is None or modo == MODO_MD:
            texto = tr("measured along the hole")
        elif modo == MODO_TVDSS:
            texto = tr("TVDSS = TVD − KB {0:g} (below sea level)").format(pozo.trayectoria.tvd_a_ss)
        else:
            texto = tr("vertical depth from the trajectory of {0}").format(pozo.nombre)
        self.lbl_ref.setText(texto)

    def plot_actual(self) -> LogPlot | None:
        i = self.ch_lp.currentIndex()
        if not 0 <= i < len(self.pr.logplots):
            return None
        return LogPlot(datos_desde_proyecto(self.pr, i, self.app.base_lito, self.app.base_herr,
                                            self.app.alias, capas=self.capas()))

    def capas(self) -> set[str]:
        return {k for k, ck in (("qc", self.ck_qc), ("dl", self.ck_dl), ("original", self.ck_orig))
                if ck.isChecked()}

    def seguir_seleccion(self) -> None:
        """El log plot actual muestra el pozo y el log de la selección global (sin marcar el
        proyecto como modificado: es navegación)."""
        s = getattr(self.app, "seleccion", None)
        lp = self.estado()
        if s is None or lp is None or s.pozo < 0 or (lp.pozo, lp.las) == (s.pozo, max(s.log, 0)):
            return
        lp.pozo, lp.las = s.pozo, max(s.log, 0)
        lp.lito = lp.comp = 0
        modificado = self.pr.modificado
        self._al_lp()
        self.pr.modificado = modificado

    def dibujar(self, *_):
        self._texto_referencia()
        plot = self.plot_actual()
        self.visor.lienzo.fijar_plot(plot)
        n = plot.ocultas if plot is not None else 0
        self.ck_vacias.setText(tr("Hide empty tracks") + (f" ({n})" if n else ""))
        if plot is not None and plot.mensajes:
            self.app.registrar("\n".join(plot.mensajes))

    def nuevo(self):
        nombre = self.pr.nombre_libre("logplot-", (lp.nombre for lp in self.pr.logplots))
        self.pr.logplots.append(EstadoLogPlot(nombre=nombre, pozo=0 if self.pr.pozos else -1, las=0, lito=0,
                                              comp=0, plantilla=0 if self.pr.plantillas else -1,
                                              zonas_visibles=[True] * len(self.pr.zonas)))
        self.refrescar()
        self.ch_lp.setCurrentIndex(len(self.pr.logplots) - 1)
        self.app.reconstruir_arbol()

    def borrar(self):
        i = self.ch_lp.currentIndex()
        if 0 <= i < len(self.pr.logplots):
            del self.pr.logplots[i]
            self.refrescar()
            self.app.reconstruir_arbol()

    def exportar(self):
        plot = self.plot_actual()
        if plot is None:
            return
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export"), "", "PNG (*.png)")
        if ruta:
            plot.imagen().save(ruta)

    def _zona_movida(self, zona, md):
        lp = self.estado()
        if lp is not None and 0 <= lp.pozo < len(self.pr.pozos) and md != NULO:
            while len(zona.profundidades) <= lp.pozo:
                zona.profundidades.append(0.0)
            zona.profundidades[lp.pozo] = round(md, 3)
            self.pr.modificado = True
            self.dibujar()
            self.app.refrescar_editores(excepto=self)


class LienzoCorte(QWidget):
    """Varios log plots lado a lado, aplanados en una zona (myCrossSection)."""

    def __init__(self):
        super().__init__()
        self.plots: list[tuple[LogPlot, float]] = []    # (plot, desplazamiento vertical en px)
        self.zoom = 0.5                                  # vista general de varios pozos

    def fijar(self, plots):
        self.plots = plots
        ancho = sum(p.tamano()[0] for p, _ in plots) + 40
        alto = max((p.tamano()[1] + dy for p, dy in plots), default=100)
        self.setFixedSize(int(ancho * self.zoom), int(alto * self.zoom))
        self.update()

    def imagen(self) -> QImage:
        img = QImage(max(1, self.width()), max(1, self.height()), QImage.Format_ARGB32)
        img.fill(Qt.white)
        p = QPainter(img)
        self._pintar(p)
        p.end()
        return img

    def paintEvent(self, ev):
        p = QPainter(self)
        self._pintar(p)
        p.end()

    def _pintar(self, p: QPainter):
        p.fillRect(self.rect(), Qt.white)
        p.scale(self.zoom, self.zoom)
        x = 0.0
        anteriores = []
        for plot, dy in self.plots:
            p.save()
            p.translate(x, dy)
            plot.dibujar(p)
            p.restore()
            anteriores.append((x, dy, plot))
            x += plot.tamano()[0]
        # líneas de correlación entre pozos para cada zona
        for (xa, dya, pa), (xb, dyb, pb) in zip(anteriores, anteriores[1:]):
            for (za, mda), (zb, mdb) in zip(pa.d.zonas, pb.d.zonas):
                ya, yb = pa.a_prof_vista(mda), pb.a_prof_vista(mdb)
                if NULO in (ya, yb):
                    continue
                p.setPen(QPen(qcolor(za.color), 1, Qt.DashLine))
                xa_fin = xa + pa.d.plantilla.mas_a_la_derecha()
                xb_ini = xb + pb.d.plantilla.mas_a_la_izquierda()
                p.drawLine(int(xa_fin), int(pa.prof_a_y(ya) + dya), int(xb_ini), int(pb.prof_a_y(yb) + dyb))


class PaginaCorte(EditorBase):
    def __init__(self, app, parent=None):
        super().__init__(app, parent)
        self.lista = QListWidget()
        self.lista_zonas = QListWidget()         # zonas que dibuja el corte (pendiente 26)
        self.ch_zona = QComboBox()
        self.ch_tpl = QComboBox()
        self.ch_modo = QComboBox()
        self.ch_modo.addItems([NOMBRES_MODO[i] for i in range(3)])
        self.sp_escala = QSpinBox()
        self.sp_escala.setRange(ESCALA_MIN, ESCALA_MAX)
        b_ref = boton("Refresh", "refresh", "Redraw the cross section")
        b_exp = boton("Export...", "export", "Save the cross section as a PNG image")
        b_in, b_out = boton("Zoom In", "zoom_in"), boton("Zoom Out", "zoom_out")
        izq = QWidget()
        g = QVBoxLayout(izq)
        g.addWidget(QLabel(tr("Wells")))
        g.addWidget(self.lista)
        g.addWidget(QLabel(tr("Zones")))
        g.addWidget(self.lista_zonas)
        for t, w in (("Flatten at zone", self.ch_zona), ("Global template", self.ch_tpl),
                     ("Depth mode", self.ch_modo), ("Scale", self.sp_escala)):
            g.addWidget(QLabel(tr(t)))
            g.addWidget(w)
        for b in (b_ref, b_exp, b_in, b_out):
            g.addWidget(b)
        g.addStretch(1)
        izq.setMaximumWidth(260)
        self.lienzo = LienzoCorte()
        sc = QScrollArea()
        sc.setWidget(self.lienzo)
        sp = QSplitter()
        sp.addWidget(izq)
        sp.addWidget(sc)
        sp.setStretchFactor(1, 4)
        QVBoxLayout(self).addWidget(sp)
        b_ref.clicked.connect(self.dibujar)
        b_exp.clicked.connect(self.exportar)
        b_in.clicked.connect(lambda: self._zoom(1.2))
        b_out.clicked.connect(lambda: self._zoom(1 / 1.2))
        for w in (self.ch_zona, self.ch_tpl, self.ch_modo):
            w.currentIndexChanged.connect(self._guardar)
        self.sp_escala.valueChanged.connect(self._guardar)
        self.lista.itemChanged.connect(self._guardar)
        self.lista_zonas.itemChanged.connect(self._guardar)
        self._cargando = False

    def refrescar(self):
        self._cargando = True
        c = self.pr.corte
        self.lista.clear()
        nombres_corte = {pc.pozo for pc in c.pozos}
        for i, p in enumerate(self.pr.pozos):
            it = QListWidgetItem(p.nombre)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if (i in nombres_corte or not c.pozos) else Qt.Unchecked)
            self.lista.addItem(it)
        self.lista_zonas.clear()
        visibles = c.zonas_visibles if len(c.zonas_visibles) == len(self.pr.zonas) else [True] * len(self.pr.zonas)
        for z, ver in zip(self.pr.zonas, visibles):
            it = QListWidgetItem(z.nombre)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if ver else Qt.Unchecked)
            self.lista_zonas.addItem(it)
        self.ch_zona.clear()
        self.ch_zona.addItem(tr("(none)"))
        self.ch_zona.addItems([z.nombre for z in self.pr.zonas])
        self.ch_zona.setCurrentIndex(c.zona_aplanar + 1 if c.zona_aplanar + 1 < self.ch_zona.count() else 0)
        self.ch_tpl.clear()
        self.ch_tpl.addItems([t.nombre for t in self.pr.plantillas])
        self.ch_tpl.setCurrentIndex(c.plantilla_global if c.plantilla_global < len(self.pr.plantillas) else 0)
        self.ch_modo.setCurrentIndex(c.modo_prof_global)
        self.sp_escala.setValue(int(c.escala_global))
        self._cargando = False
        self.dibujar()

    def preparar_tvd(self, modo: int, preguntar=None) -> bool:
        """Para ver el corte en TVD/TVDSS: los pozos marcados sin trayectoria se declaran verticales con una
        sola pregunta (no pozo por pozo) y se calcula la TVD de sus registros. `preguntar` (pruebas)
        reemplaza al diálogo y devuelve True o False."""
        marcados = [self.pr.pozos[i] for i in range(self.lista.count())
                    if self.lista.item(i).checkState() == Qt.Checked and i < len(self.pr.pozos)]
        sin = [p for p in marcados if len(p.trayectoria.estaciones) < 2]
        if sin:
            texto = tr("{0} of the {1} wells have no trajectory, so their TVD is unknown: {2}.").format(
                len(sin), len(marcados), ", ".join(p.nombre for p in sin))
            if preguntar is not None:
                si = preguntar()
            else:
                si = QMessageBox.question(self, tr("Depth mode"), texto + "\n\n" + tr(
                    "Treat them as vertical (TVD = MD)? Deviated wells need their survey stations in the "
                    "Trajectory view first.")) == QMessageBox.Yes
            if not si:
                return False
            for p in sin:
                declarar_vertical(p)
            self.app.registrar(tr("Declared vertical: {0}").format(", ".join(p.nombre for p in sin)))
        if modo == MODO_TVDSS:
            sin_kb = [p.nombre for p in marcados if p.trayectoria.tvd_a_ss == 0.0]
            if sin_kb:
                self.app.registrar(tr("Without KB elevation (TVDSS = TVD): {0}").format(", ".join(sin_kb)))
        if calcular_tvd(self.app, marcados):
            self.app.refrescar_estado()
        self.pr.modificado = True
        return True

    def _guardar(self, *_):
        if self._cargando:
            return
        if self.ch_modo.currentIndex() != MODO_MD and self.ch_modo.currentIndex() != self.pr.corte.modo_prof_global \
                and not self.preparar_tvd(self.ch_modo.currentIndex()):
            self._cargando = True
            self.ch_modo.setCurrentIndex(MODO_MD)
            self._cargando = False
        c = self.pr.corte
        c.zona_aplanar = self.ch_zona.currentIndex() - 1
        c.plantilla_global = self.ch_tpl.currentIndex()
        c.plantilla_global_usar = True
        c.modo_prof_global = self.ch_modo.currentIndex()
        c.escala_global = float(self.sp_escala.value())
        c.escala_global_usar = True
        # pozos y zonas marcados quedan en el proyecto (antes los pozos marcados no se guardaban)
        previos = {pc.pozo: pc for pc in c.pozos}
        c.pozos = [previos.get(i) or PozoCorte(self.pr.pozos[i].nombre, i)
                   for i in range(self.lista.count()) if self.lista.item(i).checkState() == Qt.Checked]
        c.zonas_visibles = [self.lista_zonas.item(k).checkState() == Qt.Checked
                            for k in range(self.lista_zonas.count())]
        self.pr.modificado = True
        self.dibujar()

    def _zoom(self, f):
        self.lienzo.zoom = max(0.1, min(10.0, self.lienzo.zoom * f))
        self.lienzo.fijar(self.lienzo.plots)

    def construir(self) -> list[tuple[LogPlot, float]]:
        from .logplot import DatosLogPlot
        c = self.pr.corte
        if not self.pr.plantillas:
            return []
        tpl = self.pr.plantillas[min(max(c.plantilla_global, 0), len(self.pr.plantillas) - 1)]
        plots = []
        for i, pozo in enumerate(self.pr.pozos):
            it = self.lista.item(i)
            if it is None or it.checkState() != Qt.Checked or not pozo.logs:
                continue
            # zona oculta = sin profundidad (no se dibuja); la de aplanamiento se conserva siempre
            ver = [self.lista_zonas.item(k) is None or self.lista_zonas.item(k).checkState() == Qt.Checked
                   for k in range(len(self.pr.zonas))]
            zonas = [(z, z.prof(i) if ver[k] or k == c.zona_aplanar else NULO) for k, z in enumerate(self.pr.zonas)]
            d = DatosLogPlot(plantilla=tpl, registro=pozo.logs[0], trayectoria=pozo.trayectoria,
                             litologia=pozo.litologias[0] if pozo.litologias else None,
                             completacion=pozo.completaciones[0] if pozo.completaciones else None,
                             zonas=zonas, modo=c.modo_prof_global, escala_propia=c.escala_global,
                             nombre_pozo=pozo.nombre, base_lito=self.app.base_lito,
                             base_herr=self.app.base_herr, alias=self.app.alias)
            plots.append(LogPlot(d))
        # aplanamiento: alinea la profundidad de la zona elegida (FlatAt / CalculateFlattening)
        desplaz = [0.0] * len(plots)
        if 0 <= c.zona_aplanar < len(self.pr.zonas) and plots:
            ys = []
            for pl in plots:
                z, md = pl.d.zonas[c.zona_aplanar]
                pv = pl.a_prof_vista(md)
                ys.append(pl.prof_a_y(pv) if pv != NULO else None)
            ref = max((y for y in ys if y is not None), default=0.0)
            desplaz = [(ref - y) if y is not None else 0.0 for y in ys]
        return list(zip(plots, desplaz))

    def dibujar(self, *_):
        self.lienzo.fijar(self.construir())

    def exportar(self):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export"), "", "PNG (*.png)")
        if ruta:
            self.lienzo.imagen().save(ruta)
