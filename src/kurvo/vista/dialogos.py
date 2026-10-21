"""Diálogos reutilizables (parámetros genéricos, renombrar, listas) y el patrón común de las
herramientas que modifican datos: vista previa → Apply → queda en el historial, con los mismos
botones, iconos y orden en todos los diálogos (ver D55)."""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from ..i18n import tr
from . import iconos

TITULO_APP = "Kurvo"
NOTA_HISTORIAL = "Applied changes are recorded in the Change Log and can be undone (Ctrl+Z)."


@dataclass
class Campo:
    clave: str
    etiqueta: str
    tipo: str = "float"          # float | int | texto | bool | opcion | columna
    defecto: object = None
    opciones: list = field(default_factory=list)
    minimo: float = -1e12
    maximo: float = 1e12
    decimales: int = 4
    traducir_opciones: bool = False   # las opciones son palabras (no mnemónicos) y se traducen


def boton(texto: str, icono: str, ayuda: str = "", slot=None, traducir: bool = True) -> QPushButton:
    """Botón con icono propio y texto (traducido) al lado; la ayuda queda como tooltip."""
    b = QPushButton(iconos.icono(icono), tr(texto) if traducir else texto)
    b.setIconSize(QSize(18, 18))
    if ayuda:
        b.setToolTip(tr(ayuda))
    if slot is not None:
        b.clicked.connect(slot)
    return b


ICONOS_ESTANDAR = {QDialogButtonBox.Ok: ("OK", "apply"), QDialogButtonBox.Cancel: ("Cancel", "close"),
                   QDialogButtonBox.Close: ("Close", "close"), QDialogButtonBox.Save: ("Save", "save"),
                   QDialogButtonBox.Apply: ("Apply", "apply"), QDialogButtonBox.Yes: ("Yes", "apply"),
                   QDialogButtonBox.No: ("No", "close")}


def caja_botones(botones, parent=None) -> QDialogButtonBox:
    """QDialogButtonBox con iconos propios y textos traducidos."""
    b = QDialogButtonBox(botones, parent)
    for estandar, (texto, icono) in ICONOS_ESTANDAR.items():
        w = b.button(estandar)
        if w is not None:
            w.setText(tr(texto))
            w.setIcon(iconos.icono(icono))
    return b


class BarraAplicar(QWidget):
    """[Preview] [Apply] … nota … [Close]: botonera común de las herramientas que cambian datos."""

    def __init__(self, dialogo: QDialog, vista_previa=None, aplicar=None, texto_aplicar: str = "Apply",
                 texto_vista: str = "Preview", nota: bool = True):
        super().__init__(dialogo)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.b_vista = boton(texto_vista, "preview", "Compute and show the result without changing the data",
                             vista_previa) if vista_previa else None
        self.b_aplicar = boton(texto_aplicar, "apply", "Write the result (recorded in the Change Log)",
                               aplicar) if aplicar else None
        self.b_cerrar = boton("Close", "close", "", dialogo.reject)
        for b in (self.b_vista, self.b_aplicar):
            if b is not None:
                lay.addWidget(b)
        self.nota = QLabel(tr(NOTA_HISTORIAL) if nota else "")
        self.nota.setStyleSheet("color: #667;")
        lay.addWidget(self.nota, 1)
        lay.addWidget(self.b_cerrar)
        if self.b_aplicar is not None:
            self.b_aplicar.setDefault(True)


class DialogoParametros(QDialog):
    """Formulario a partir de una lista de Campo; `valores()` devuelve un dict.

    Con `vista_previa(valores) -> (prof, antes, después, etiqueta)` el diálogo muestra la curva
    antes y después sin tocar los datos, y el botón de aceptar se llama "Apply"."""

    def __init__(self, titulo: str, campos: list[Campo], parent=None, al_cambiar_opcion=None,
                 vista_previa=None):
        super().__init__(parent)
        self.setWindowTitle(tr(titulo))
        self.campos = campos
        self.widgets = {}
        self.vista_previa = vista_previa
        form = QFormLayout()
        for c in campos:
            if c.tipo in ("opcion", "columna"):
                w = QComboBox()
                for o in c.opciones:
                    w.addItem(tr(str(o)) if c.traducir_opciones else str(o), o)
                if c.defecto is not None and str(c.defecto) in [str(o) for o in c.opciones]:
                    w.setCurrentIndex([str(o) for o in c.opciones].index(str(c.defecto)))
                elif c.tipo == "columna":
                    w.setCurrentIndex(-1 if c.defecto is None else 0)
            elif c.tipo == "bool":
                w = QCheckBox()
                w.setChecked(bool(c.defecto))
            elif c.tipo == "int":
                w = QSpinBox()
                w.setRange(int(max(c.minimo, -2**31 + 1)), int(min(c.maximo, 2**31 - 1)))
                w.setValue(int(c.defecto or 0))
            elif c.tipo == "texto":
                w = QLineEdit(str(c.defecto or ""))
            else:
                w = QDoubleSpinBox()
                w.setDecimals(c.decimales)
                w.setRange(c.minimo, c.maximo)
                w.setValue(float(c.defecto or 0.0))
            self.widgets[c.clave] = w
            form.addRow(tr(c.etiqueta), w)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        self.grafico = None
        if vista_previa is not None:
            import pyqtgraph as pg
            self.grafico = pg.PlotWidget()
            self.grafico.invertY(True)
            self.grafico.addLegend()
            self.grafico.setMinimumHeight(320)
            self.lbl_vista = QLabel(tr("Press Preview to see the result before applying it."))
            lay.addWidget(self.grafico, 1)
            lay.addWidget(self.lbl_vista)
            self.barra = BarraAplicar(self, self.previsualizar, self.accept)
            self.barra.b_cerrar.setText(tr("Cancel"))
            lay.addWidget(self.barra)
            self.resize(520, 680)
        else:
            botones = caja_botones(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            botones.accepted.connect(self.accept)
            botones.rejected.connect(self.reject)
            lay.addWidget(botones)
        if al_cambiar_opcion:
            for c in campos:
                if c.tipo == "opcion":
                    self.widgets[c.clave].currentTextChanged.connect(
                        lambda t, k=c.clave: al_cambiar_opcion(self, k, self.valores()[k]))

    def previsualizar(self):
        """Dibuja la curva antes (gris) y después (color) con los parámetros actuales."""
        import numpy as np
        import pyqtgraph as pg
        try:
            prof, antes, despues, etiqueta = self.vista_previa(self.valores())
        except ValueError as e:
            self.lbl_vista.setText(str(e))
            return None
        from .edicion_curvas import _trazar
        g = self.grafico
        g.clear()
        _trazar(g, antes, prof, pg.mkPen((165, 165, 165), width=2), tr("before"))
        _trazar(g, despues, prof, pg.mkPen((214, 110, 0), width=1.4), tr("after"))
        g.setLabel("bottom", etiqueta)
        a, d = np.asarray(antes, float), np.asarray(despues, float)
        n = int(np.count_nonzero(~((a == d) | (np.isnan(a) & np.isnan(d)))))
        self.lbl_vista.setText(tr("{0} sample(s) would change.").format(n))
        return n

    def valores(self) -> dict:
        out = {}
        for c in self.campos:
            w = self.widgets[c.clave]
            if c.tipo == "columna":
                out[c.clave] = w.currentIndex()
            elif c.tipo == "opcion":
                dato = w.currentData()
                out[c.clave] = str(dato) if dato is not None else w.currentText()
            elif c.tipo == "bool":
                out[c.clave] = w.isChecked()
            elif c.tipo == "texto":
                out[c.clave] = w.text().strip()
            else:
                out[c.clave] = w.value()
        return out

    def fijar(self, clave: str, valor) -> None:
        w = self.widgets[clave]
        if isinstance(w, (QDoubleSpinBox, QSpinBox)):
            w.setValue(valor)
        elif isinstance(w, QLineEdit):
            w.setText(str(valor))


def pedir(titulo: str, campos: list[Campo], parent=None, **kw) -> dict | None:
    d = DialogoParametros(titulo, campos, parent, **kw)
    return d.valores() if d.exec() == QDialog.Accepted else None


def aviso(parent, texto: str) -> None:
    QMessageBox.warning(parent, TITULO_APP, texto)


def confirmar(parent, texto: str) -> bool:
    return QMessageBox.question(parent, TITULO_APP, texto) == QMessageBox.Yes
