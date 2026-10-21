"""Widget interactivo del gráfico de registros: zoom, desplazamiento y arrastre de topes."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QMessageBox, QScrollArea, QToolTip, QWidget

from ..i18n import tr
from ..nucleo.comun import NULO
from .logplot import LogPlot

ZOOM_MIN, ZOOM_MAX, PASO_ZOOM = 0.1, 10.0, 1.2
TOLERANCIA_ZONA = 2.0


class LienzoLogPlot(QWidget):
    zona_movida = Signal(object, float)      # (Zona, nueva profundidad MD)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot: LogPlot | None = None
        self.zoom = 1.0
        self.solo_lectura = False
        self._arrastrando = None
        self.setMouseTracking(True)
        self.setAutoFillBackground(False)

    # ------------------------------------------------------------ datos
    def fijar_plot(self, plot: LogPlot | None) -> None:
        self.plot = plot
        self._ajustar()
        self.update()

    def _ajustar(self) -> None:
        if self.plot is None:
            self.setMinimumSize(10, 10)
            self.resize(10, 10)
            return
        w, h = self.plot.tamano()
        self.setFixedSize(max(10, int(w * self.zoom)), max(10, int(h * self.zoom)))

    def fijar_zoom(self, z: float) -> bool:
        """Zoom; ignora valores menores que 0.1."""
        if z < ZOOM_MIN:
            return False
        self.zoom = z
        self._ajustar()
        self.update()
        return True

    def acercar(self) -> None:
        if self.zoom < ZOOM_MAX:
            self.fijar_zoom(self.zoom * PASO_ZOOM)

    def alejar(self) -> None:
        if self.zoom > ZOOM_MIN:
            self.fijar_zoom(self.zoom / PASO_ZOOM)

    def zoom_normal(self) -> None:
        self.fijar_zoom(1.0)

    # ------------------------------------------------------------ pintura
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.white)
        if self.plot is not None:
            p.scale(self.zoom, self.zoom)
            self.plot.dibujar(p)
        p.end()

    # ------------------------------------------------------------ mouse
    def _prof_en(self, pos: QPoint) -> float:
        return self.plot.y_a_prof(pos.y() / self.zoom)

    def zona_cercana(self, prof: float):
        for z, md in self.plot.d.zonas:
            pv = self.plot.a_prof_vista(md)
            if pv != NULO and pv - TOLERANCIA_ZONA < prof < pv + TOLERANCIA_ZONA:
                return z, pv
        return None

    def texto_cursor(self, pos: QPoint) -> str:
        prof = self._prof_en(pos)
        cerca = self.zona_cercana(prof)
        if cerca is not None:
            return tr("Zone={0} ({1})").format(cerca[0].nombre, f"{cerca[1]:g}")
        return tr("Depth={0}").format(f"{prof:g}")

    def mouseMoveEvent(self, ev):
        if self.plot is None or not self.plot.listo:
            return
        pos = ev.position().toPoint()
        if self._arrastrando is not None:
            self.setCursor(Qt.SizeVerCursor)
            return
        if self.zoom == 1.0 and not self.solo_lectura:
            cerca = self.zona_cercana(self._prof_en(pos))
            self.setCursor(Qt.SizeVerCursor if cerca else Qt.CrossCursor)
        texto = self.texto_cursor(pos)
        self.setToolTip(texto)
        QToolTip.showText(ev.globalPosition().toPoint(), texto, self)

    def mousePressEvent(self, ev):
        if (self.plot is None or self.zoom != 1.0 or self.solo_lectura
                or ev.button() != Qt.LeftButton):
            return
        cerca = self.zona_cercana(self._prof_en(ev.position().toPoint()))
        if cerca is not None:
            self._arrastrando = cerca[0]

    def mouseReleaseEvent(self, ev):
        if self._arrastrando is None or self.plot is None:
            return
        z = self._arrastrando
        self._arrastrando = None
        prof_vista = self._prof_en(ev.position().toPoint())
        md = prof_vista
        t = self.plot.d.trayectoria
        if self.plot.d.modo != 2 and t is not None:
            if self.plot.d.modo == 1:
                prof_vista += t.tvd_a_ss
            md = t.md_en(prof_vista)
        self.zona_movida.emit(z, md)

    def mouseDoubleClickEvent(self, ev):
        if self.plot is None or self.plot.d.registro is None:
            return
        prof = self._prof_en(ev.position().toPoint())
        reg = self.plot.d.registro
        valores = reg.datos_en_md(prof)
        lineas = [f"{n} = {v:g}" for n, v in zip(reg.nombres(), valores)]
        QMessageBox.information(self, tr("Depth"), tr("Depth = {0}").format(f"{prof:g}") + "\n\n" + "\n".join(lineas))


class VisorLogPlot(QScrollArea):
    """Lienzo con barras de desplazamiento (unidad 20 px)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lienzo = LienzoLogPlot()
        self.setWidget(self.lienzo)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.verticalScrollBar().setSingleStep(20)
        self.horizontalScrollBar().setSingleStep(20)
