"""Ventana principal: franja general, barra de los siete pasos, vista del centro y paneles.

Desde v0.3: todas las herramientas son QAction de un registro único (vista/acciones.py); la
selección de pozo/log/curva/zona es global (vista/seleccion.py) y se ve en la barra de estado;
el árbol, el flujo de trabajo, el QC y el historial son paneles acoplables cuya disposición se
recuerda; los textos pasan por `tr()` (English/Español)."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PySide6.QtCore import QByteArray, QSettings, QSize, Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QDockWidget, QFileDialog,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QScrollArea, QSizePolicy, QTabWidget, QTextBrowser, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..calculos import formula
from ..i18n import fijar_idioma, idioma, tr, tr_ayuda
from ..modulos.registro import descubrir_modulos
from ..nucleo import bases, operaciones, preferencias, qc
from ..nucleo.comun import NULO, a_float, leer_lineas
from ..nucleo.intervalos import Completacion, Litologia, leer_zonas, lineas_zonas
from ..nucleo.las import ErrorLAS, RegistroLAS
from ..nucleo.plantilla import Plantilla
from ..nucleo.proyecto import ErrorProyecto, Proyecto
from . import iconos
from .acciones import RegistroAcciones
from .dialogos import Campo, aviso, caja_botones, confirmar, pedir
from .editores import (EditorCompletacion, EditorLitologia, EditorLogs, EditorPlantillas,
                       EditorTrayectoria, EditorZonas)
from .paneles import PaginaCorte, PaginaLogPlot
from .seleccion import Seleccion

TITULO = "Kurvo"
FILTRO_PROYECTO = "Project (*.kurvo)"
SUFIJOS_GENERADAS = ("_DL", "_DL_STD", "_FILL", "_QC", "_NORM", "_DS", "_SPL", "_DL_P")
# la disposición de los paneles se guarda con otra clave desde la barra de pasos (D123): la de antes
# reabriría el panel de flujo y las proporciones viejas
CLAVE_DISPOSICION = "ventana/estado_v1"
ACCIONES_PANELES = {"proyecto": "panel_project", "flujo": "panel_workflow", "qc": "panel_qc",
                    "historial": "panel_history", "propiedades": "panel_properties"}


def ajustes() -> QSettings:
    """QSettings de la aplicación. Con KURVO_AJUSTES (pruebas) se usa ese archivo .ini."""
    ruta = os.environ.get("KURVO_AJUSTES")
    if ruta:
        return QSettings(ruta, QSettings.IniFormat)
    s = QSettings("Kurvo", "Kurvo")
    if not s.allKeys():         # primera vez con el nombre Kurvo: trae las preferencias del nombre anterior
        viejo = QSettings("VisorCurvas", "VisorCurvas")
        for k in viejo.allKeys():
            s.setValue(k, viejo.value(k))
    return s


def cargar_preferencias() -> preferencias.Preferencias:
    p = preferencias.Preferencias.desde_json(ajustes().value("preferencias", ""))
    preferencias.fijar(p)
    return p


def guardar_preferencias(p: preferencias.Preferencias) -> None:
    preferencias.fijar(p)
    ajustes().setValue("preferencias", p.a_json())


_traductores: list = []
_VIVAS: list = []           # ventana principal vigente tras reiniciar la interfaz (evita que se libere)


def aplicar_idioma(codigo: str) -> None:
    """Idioma de los textos propios y, en español, de los diálogos estándar de Qt."""
    from PySide6.QtCore import QLibraryInfo, QTranslator
    fijar_idioma(codigo)
    app = QApplication.instance()
    if app is None:
        return
    for t in _traductores:
        app.removeTranslator(t)
    _traductores.clear()
    if codigo == "es":
        t = QTranslator()
        if t.load("qtbase_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(t)
            _traductores.append(t)


_estilo_original: list = []


def aplicar_tema(tema: str) -> None:
    """Tema claro (el estilo del sistema) u oscuro (Fusion con paleta oscura) para la ventana, los
    paneles y las gráficas de pyqtgraph que se creen desde ahora. El Log Plot, el corte y el
    reporte se dibujan siempre sobre blanco (D99)."""
    import pyqtgraph as pg
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QStyleFactory
    app = QApplication.instance()
    if app is None:
        return
    if not _estilo_original:
        _estilo_original.append(app.style().name())
    if tema == "dark":
        app.setStyle(QStyleFactory.create("Fusion"))
        pal = QPalette()
        oscuro, base, texto = QColor(45, 48, 53), QColor(32, 34, 38), QColor(225, 228, 232)
        for rol, color in ((QPalette.Window, oscuro), (QPalette.WindowText, texto), (QPalette.Base, base),
                           (QPalette.AlternateBase, oscuro), (QPalette.ToolTipBase, QColor(60, 63, 68)),
                           (QPalette.ToolTipText, texto), (QPalette.Text, texto), (QPalette.Button, oscuro),
                           (QPalette.ButtonText, texto), (QPalette.BrightText, QColor(255, 90, 90)),
                           (QPalette.Highlight, QColor(42, 130, 218)), (QPalette.HighlightedText, QColor(255, 255, 255)),
                           (QPalette.Link, QColor(90, 160, 255)), (QPalette.PlaceholderText, QColor(140, 145, 150))):
            pal.setColor(rol, color)
        for rol in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
            pal.setColor(QPalette.Disabled, rol, QColor(120, 124, 130))
        app.setPalette(pal)
        pg.setConfigOptions(background=(32, 34, 38), foreground=(220, 222, 226))
    else:
        app.setStyle(QStyleFactory.create(_estilo_original[0]) or QStyleFactory.create("Fusion"))
        app.setPalette(app.style().standardPalette())
        pg.setConfigOptions(background="w", foreground="k")


# ====================================================================== ribbon
class BotonRibbon(QToolButton):
    """Botón del ribbon con la acción del registro y, si la tiene, su etiqueta corta (D96). Qt
    vuelve a poner el texto de la acción cada vez que esta cambia; aquí se repone el corto."""

    def __init__(self, corto: str = ""):
        super().__init__()
        self.corto = corto

    def setDefaultAction(self, accion):
        super().setDefaultAction(accion)
        if self.corto:
            self.setText(self.corto)

    def actionEvent(self, ev):
        super().actionEvent(ev)
        if self.corto and self.text() != self.corto:
            self.setText(self.corto)


class Ribbon(QTabWidget):
    """Páginas con grupos de botones que muestran QAction del registro.

    Un grupo es una lista de elementos: una clave (botón grande), una lista de claves (columna
    de hasta tres botones pequeños) o ("menu", texto, icono, [claves]) (botón con menú)."""

    def __init__(self, acciones: RegistroAcciones, parent=None):
        super().__init__(parent)
        self.acciones = acciones
        self.setFixedHeight(128)
        self.botones: dict[str, QToolButton] = {}
        self.grupos: list[tuple[QGroupBox, str]] = []
        self.titulos: list[str] = []
        self.menus: list[tuple[QToolButton, str]] = []

    def _boton(self, clave: str, grande: bool) -> QToolButton:
        from .acciones import CORTOS
        b = BotonRibbon(tr(CORTOS[clave]) if clave in CORTOS else "")
        b.setDefaultAction(self.acciones[clave])
        b.setAutoRaise(True)
        if grande:
            b.setIconSize(QSize(32, 32))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        else:
            b.setIconSize(QSize(16, 16))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.botones[self.acciones.defs[clave].texto] = b
        return b

    def pagina(self, titulo: str, grupos: list[tuple[str, list]], numero: int = 0):
        """Una página; con `numero` es un paso del trabajo y la pestaña dice "3 · Corregir" (D123)."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)
        for titulo_grupo, elementos in grupos:
            g = QGroupBox(tr(titulo_grupo))
            self.grupos.append((g, titulo_grupo))
            gl = QHBoxLayout(g)
            gl.setContentsMargins(3, 0, 3, 0)
            gl.setSpacing(1)
            for e in elementos:
                if isinstance(e, str):
                    gl.addWidget(self._boton(e, True))
                elif isinstance(e, tuple) and e[0] == "menu":
                    _, texto, icono, claves = e
                    b = QToolButton()
                    b.setText(tr(texto))
                    b.setIcon(iconos.icono(icono))
                    b.setIconSize(QSize(32, 32))
                    b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                    b.setPopupMode(QToolButton.InstantPopup)
                    b.setAutoRaise(True)
                    m = QMenu(b)
                    for k in claves:
                        m.addSeparator() if k == "-" else m.addAction(self.acciones[k])
                    b.setMenu(m)
                    self.menus.append((b, texto))
                    self.botones[texto] = b
                    gl.addWidget(b)
                else:
                    col = QVBoxLayout()
                    col.setSpacing(0)
                    for k in e:
                        col.addWidget(self._boton(k, False))
                    col.addStretch(1)
                    gl.addLayout(col)
            lay.addWidget(g)
        lay.addStretch(1)
        for b in w.findChildren(QToolButton):
            b.setMinimumWidth(b.sizeHint().width())
        area = QScrollArea()
        area.setWidget(w)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.titulos.append((titulo, numero))
        self.addTab(area, self._texto_pestana(titulo, numero))

    @staticmethod
    def _texto_pestana(titulo: str, numero: int) -> str:
        return f"{numero} · {tr(titulo)}" if numero else tr(titulo)

    def retraducir(self):
        for g, t in self.grupos:
            g.setTitle(tr(t))
        for i, (t, n) in enumerate(self.titulos):
            self.setTabText(i, self._texto_pestana(t, n))
        for b, t in self.menus:
            b.setText(tr(t))


# ====================================================================== panel de flujo
class PanelFlujo(QWidget):
    """Estado de cada paso del flujo de mantenimiento para el pozo seleccionado; cada paso abre
    su herramienta (ver nucleo/flujo.py)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.lbl = QLabel()
        self.lbl.setStyleSheet("font-weight: bold;")
        self.contenido = QWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.lbl)
        lay.addWidget(self.contenido)
        lay.addStretch(1)
        self.leyenda = QLabel()
        self.leyenda.setWordWrap(True)
        self.leyenda.setStyleSheet("color: #667; font-size: 8pt;")
        lay.addWidget(self.leyenda)
        self.pasos = []

    def refrescar(self):
        from ..nucleo import flujo
        nuevo = QWidget()
        self.rejilla = QGridLayout(nuevo)
        self.rejilla.setContentsMargins(0, 0, 0, 0)
        self.rejilla.setVerticalSpacing(1)
        self.rejilla.setColumnStretch(1, 1)
        self.layout().replaceWidget(self.contenido, nuevo)
        self.contenido.setParent(None)
        self.contenido.deleteLater()
        self.contenido = nuevo
        pozo = self.app.seleccion.objeto_pozo()
        self.leyenda.setText(tr("✓ done · ! with warnings · ○ pending (red) or optional (gray). "
                                "Click a step to open its tool."))
        if pozo is None:
            self.lbl.setText(tr("No well selected."))
            self.pasos = []
            return
        self.lbl.setText(tr("Workflow — {0}").format(pozo.nombre))
        self.pasos = flujo.estado_pozo(pozo, self.app.alias)
        for i, p in enumerate(self.pasos):
            b = QToolButton()
            b.setIcon(iconos.icono_estado(p.estado))
            b.setText(f"{i + 1}. {p.titulo}")
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setAutoRaise(True)
            b.setToolTip(f"<b>{p.titulo}</b>: {tr(p.estado)}" + (f"<br>{p.detalle}" if p.detalle else ""))
            if p.accion in self.app.acciones:
                b.clicked.connect(lambda *_, k=p.accion: self.app.acciones[k].trigger())
            self.rejilla.addWidget(b, 2 * i, 0)
            if p.detalle:
                det = QLabel(p.detalle)
                det.setStyleSheet("color: #556; font-size: 8pt; margin-left: 26px;")
                det.setWordWrap(True)
                self.rejilla.addWidget(det, 2 * i + 1, 0)


# ====================================================================== franja general (D123)
class FranjaGeneral(QWidget):
    """Utilidades que no son pasos del trabajo, en una franja compacta sobre la barra de pasos:
    proyecto, guardar, deshacer, vistas, configuración y ayuda; a la derecha, el siguiente paso del
    pozo seleccionado y un buscador de herramientas."""

    MENUS = [("Project", "open", ["open", "save", "save_as", "close_project", "-", "start_page", "-", "exit"]),
             ("View", "logplot", ["view_logplot", "view_cross_section", "view_table", "view_trajectory", "view_zones",
                                  "view_lithology", "view_completion", "view_templates", "-",
                                  "panel_project", "panel_workflow", "panel_qc", "panel_history",
                                  "panel_properties"]),
             ("Settings", "settings", ["settings", "-", "grouping", "plugins"]),
             ("Help", "help", ["manual", "help", "examples", "start_page", "-", "about", "diagnostic"])]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(2)
        self.menus: list[tuple[QToolButton, str]] = []
        for i, (texto, icono, claves) in enumerate(self.MENUS):
            b = QToolButton()
            b.setText(tr(texto))
            b.setIcon(iconos.icono(icono))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setPopupMode(QToolButton.InstantPopup)
            b.setAutoRaise(True)
            m = QMenu(b)
            for k in claves:
                m.addSeparator() if k == "-" else m.addAction(app.acciones[k])
            b.setMenu(m)
            self.menus.append((b, texto))
            lay.addWidget(b)
            if i == 0:
                for k in ("save", "undo", "redo"):
                    lay.addWidget(self._boton(k))
        lay.addStretch(1)
        self.lbl_siguiente = QLabel()
        self.lbl_siguiente.setTextFormat(Qt.RichText)
        self.b_siguiente = QToolButton()
        self.b_siguiente.setText(tr("Go"))
        self.b_siguiente.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.b_siguiente.clicked.connect(self._ir_al_siguiente)
        lay.addWidget(self.lbl_siguiente)
        lay.addWidget(self.b_siguiente)
        lay.addSpacing(12)
        from PySide6.QtWidgets import QCompleter, QLineEdit
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText(tr("Search a tool (e.g. tvd, spikes)"))
        self.buscar.setClearButtonEnabled(True)
        self.buscar.setMinimumWidth(240)
        self.completar = QCompleter([], self.buscar)
        self.completar.setCaseSensitivity(Qt.CaseInsensitive)
        self.completar.setFilterMode(Qt.MatchContains)
        self.buscar.setCompleter(self.completar)
        self.completar.activated.connect(self._buscar)
        self.buscar.returnPressed.connect(lambda: self._buscar(self.buscar.text()))
        lay.addWidget(self.buscar)
        self._paso = -1
        self.b_siguiente.hide()

    def _boton(self, clave: str) -> QToolButton:
        b = QToolButton()
        b.setDefaultAction(self.app.acciones[clave])
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setAutoRaise(True)
        return b

    def herramientas(self) -> dict[str, str]:
        """{nombre visible: clave de la acción} de todo lo que se puede buscar."""
        out = {}
        for clave, a in self.app.acciones.acciones.items():
            t = a.text().replace("&", "")
            if t and not clave.startswith("panel_"):
                out.setdefault(t, clave)
        return out

    def actualizar_busqueda(self):
        from PySide6.QtCore import QStringListModel
        self.completar.setModel(QStringListModel(sorted(self.herramientas()), self.completar))

    def _buscar(self, texto: str):
        nombres = self.herramientas()
        clave = nombres.get(texto)
        if clave is None:          # sin elegir de la lista: la primera herramienta que contiene el texto
            t = texto.strip().lower()
            clave = next((k for n, k in sorted(nombres.items()) if t and t in n.lower()), None)
        if clave is None:
            self.app.statusBar().showMessage(tr("No tool matches \"{0}\"").format(texto), 4000)
            return
        self.buscar.clear()
        self.app.acciones[clave].trigger()

    def fijar_siguiente(self, pozo_nombre: str, paso: int, titulo: str, detalle: str):
        """Siguiente paso del pozo seleccionado; paso < 0 sin pozo o con todo hecho."""
        self._paso = paso
        if not pozo_nombre:
            self.lbl_siguiente.setText("")
            self.b_siguiente.hide()
        elif paso < 0:
            self.lbl_siguiente.setText(tr("<b>{0}</b>: every step done").format(pozo_nombre))
            self.b_siguiente.hide()
        else:
            extra = f" — {detalle}" if detalle else ""
            self.lbl_siguiente.setText(tr("<b>{0}</b> · next step: <b>{1} · {2}</b>{3}").format(
                pozo_nombre, paso + 1, titulo, extra))
            self.b_siguiente.show()

    def _ir_al_siguiente(self):
        if 0 <= self._paso < self.app.ribbon.count():
            self.app.ribbon.setCurrentIndex(self._paso)

    def retraducir(self):
        for b, t in self.menus:
            b.setText(tr(t))
        self.b_siguiente.setText(tr("Go"))
        self.buscar.setPlaceholderText(tr("Search a tool (e.g. tvd, spikes)"))
        self.actualizar_busqueda()


# ====================================================================== pantalla de inicio (D123)
class PaginaInicio(QWidget):
    """Lo primero que se ve sin proyecto: qué se puede hacer y en qué orden se trabaja."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        externo = QVBoxLayout(self)
        externo.addStretch(1)
        fila = QHBoxLayout()
        fila.addStretch(1)
        caja = QWidget()
        caja.setMaximumWidth(1000)
        lay = QVBoxLayout(caja)
        lay.setSpacing(14)
        titulo = QLabel(tr("What do you want to do?"))
        titulo.setStyleSheet("font-size: 22pt; font-weight: 600;")
        lay.addWidget(titulo)
        sub = QLabel(tr("If it is your first time, start with an example: it loads real wells and opens a "
                        "step-by-step guide."))
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 11pt;")
        lay.addWidget(sub)
        botones = QHBoxLayout()
        botones.setSpacing(18)
        for clave, texto, detalle in (
                ("import_las_folder", "Import my wells",
                 "LAS files of a folder; the runs of a well are kept together."),
                ("open", "Open a project", "Continue where you left off (.kurvo)."),
                ("examples", "Try an example",
                 "El Dorado (oil in carbonates, 12 wells) or Cutter (gas in sandstones, 10 wells), with a guide.")):
            tarjeta = QVBoxLayout()
            b = QToolButton()
            b.setIcon(app.acciones[clave].icon())
            b.setIconSize(QSize(40, 40))
            b.setText(tr(texto))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setMinimumSize(260, 110)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setStyleSheet("QToolButton { font-size: 12pt; font-weight: 600; padding: 10px; }")
            b.clicked.connect(lambda *_, k=clave: app.acciones[k].trigger())
            det = QLabel(tr(detalle))
            det.setWordWrap(True)
            det.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            tarjeta.addWidget(b)
            tarjeta.addWidget(det)
            botones.addLayout(tarjeta, 1)
        lay.addLayout(botones)
        orden = QLabel(tr("How you work, always in this order:") + "<br><b>1 · " + tr("Prepare") + "</b> → 2 · "
                       + tr("Review") + " → 3 · " + tr("Correct") + " → 4 · " + tr("Align and Compare") + " → 5 · "
                       + tr("Reconstruct") + " → 6 · " + tr("Check") + " → 7 · " + tr("Deliver") + "<br>"
                       + tr("Each step is a tab of the bar above. Search finds any tool by its name."))
        orden.setTextFormat(Qt.RichText)
        orden.setWordWrap(True)
        orden.setStyleSheet("font-size: 10.5pt; margin-top: 12px;")
        lay.addWidget(orden)
        fila.addWidget(caja, 10)
        fila.addStretch(1)
        externo.addLayout(fila)
        externo.addStretch(2)


# ====================================================================== ventana
class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.proyecto = Proyecto()
        self.diagnostico: list[str] = []
        self._ventanas = []
        self.ajustes = ajustes()
        self.prefs = cargar_preferencias()
        if idioma() != self.prefs.idioma:
            aplicar_idioma(self.prefs.idioma)
        if self.prefs.tema == "dark" or _estilo_original:
            aplicar_tema(self.prefs.tema)
        self.cargar_bases()
        self.resize(1400, 900)
        self.setWindowIcon(iconos.icono("app"))
        self.setDockNestingEnabled(True)
        self.seleccion = Seleccion(self)
        self.acciones = RegistroAcciones(self)
        self._titulo()

        self.ribbon = Ribbon(self.acciones)     # sus páginas se arman cuando están los módulos

        self.pestanas = QTabWidget()
        self.editor_tray = EditorTrayectoria(self)
        self.editor_logs = EditorLogs(self)
        self.editor_lito = EditorLitologia(self)
        self.editor_comp = EditorCompletacion(self)
        self.editor_zonas = EditorZonas(self)
        self.editor_tpl = EditorPlantillas(self)
        self.pagina_logplot = PaginaLogPlot(self)
        self.pagina_corte = PaginaCorte(self)
        # el gráfico del pozo primero: es la vista natural del trabajo (D123)
        self.editores = [self.pagina_logplot, self.pagina_corte, self.editor_logs, self.editor_tray,
                         self.editor_zonas, self.editor_lito, self.editor_comp, self.editor_tpl]
        # la plantilla no es una pestaña: configura el gráfico y se abre desde él (Editar..., clic derecho)
        self._nombres_pestanas = ["Log Plot", "Cross Section", "Data Table", "Trajectory", "Formation Tops",
                                  "Lithology", "Completion"]
        self.vistas = dict(zip(("logplot", "corte", "logs", "tray", "zonas", "lito", "comp", "tpl"), self.editores))
        for nombre, icono, ed in zip(self._nombres_pestanas,
                                     ("logplot", "cross_section", "log", "trajectory", "zones", "lithology",
                                      "completion"), self.editores):
            self.pestanas.addTab(ed, iconos.icono(icono), tr(nombre))
            ed.cambiado.connect(lambda e=ed: self._cambiado(e))
        self.editor_tpl.cambiado.connect(self._plantilla_cambiada)
        self.pestanas.tabBar().hide()          # una sola navegación: los botones "Vistas" de cada paso
        self._dialogo_plantilla = None
        self.pestanas.currentChanged.connect(self._pestana)

        # arriba, todo el ancho: la franja general y la barra de los siete pasos (D123)
        self.franja = FranjaGeneral(self)
        arriba = QWidget()
        lay_arriba = QVBoxLayout(arriba)
        lay_arriba.setContentsMargins(0, 0, 0, 0)
        lay_arriba.setSpacing(0)
        lay_arriba.addWidget(self.franja)
        lay_arriba.addWidget(self.ribbon)
        self.setMenuWidget(arriba)
        from PySide6.QtWidgets import QStackedWidget
        self.inicio = PaginaInicio(self)
        self.centro = QStackedWidget()
        self.centro.addWidget(self.inicio)
        self.centro.addWidget(self.pestanas)
        self.setCentralWidget(self.centro)

        # ---------------------------------------------------------------- paneles acoplables
        self.arbol = QTreeWidget()
        self.arbol.setHeaderHidden(True)
        self.arbol.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arbol.customContextMenuRequested.connect(self._menu_arbol)
        self.arbol.itemDoubleClicked.connect(self._abrir_nodo)
        self.arbol.currentItemChanged.connect(self._al_nodo)
        self.arbol.setMinimumWidth(230)
        self.panel_flujo = PanelFlujo(self)
        from .edicion_curvas import TablaHistorial
        from .qc_ui import PanelQC
        self.panel_historial = TablaHistorial(self)
        self.panel_qc = PanelQC(self)
        from .propiedades_ui import PanelPropiedades
        self.panel_propiedades = PanelPropiedades(self)
        self.docks: dict[str, QDockWidget] = {}
        for clave, titulo, widget, area in (("proyecto", "Project", self.arbol, Qt.LeftDockWidgetArea),
                                            ("flujo", "Workflow", self.panel_flujo, Qt.LeftDockWidgetArea),
                                            ("qc", "Quality Control", self.panel_qc, Qt.RightDockWidgetArea),
                                            ("historial", "Change Log", self.panel_historial,
                                             Qt.RightDockWidgetArea),
                                            ("propiedades", "Curve Properties", self.panel_propiedades,
                                             Qt.RightDockWidgetArea)):
            dock = QDockWidget(tr(titulo), self)
            dock.setObjectName({"proyecto": "PaneData"}.get(clave, f"Panel_{clave}"))
            dock.setWidget(widget)
            dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
                             | QDockWidget.DockWidgetFloatable)
            self.addDockWidget(area, dock)
            self.docks[clave] = dock
            accion = self.acciones[ACCIONES_PANELES[clave]]
            dock.visibilityChanged.connect(lambda v, a=accion, d=dock: self._sync_accion_panel(a, d))
        self._titulos_docks = {"proyecto": "Project", "flujo": "Workflow", "qc": "Quality Control",
                               "historial": "Change Log", "propiedades": "Curve Properties"}
        self.splitDockWidget(self.docks["proyecto"], self.docks["flujo"], Qt.Vertical)
        self.tabifyDockWidget(self.docks["qc"], self.docks["historial"])
        self.tabifyDockWidget(self.docks["historial"], self.docks["propiedades"])
        self.docks["qc"].raise_()
        self.resizeDocks([self.docks["qc"]], [470], Qt.Horizontal)
        self.resizeDocks([self.docks["proyecto"], self.docks["flujo"]], [520, 300], Qt.Vertical)
        # la barra de pasos y "siguiente paso" hacen el trabajo del panel de flujo: arranca cerrado, y en
        # pantallas chicas también el de propiedades, para que el gráfico y el QC tengan espacio (D123)
        self.docks["flujo"].hide()
        pantalla = self.screen().availableGeometry().width() if self.screen() else 1920
        if pantalla < 1600:
            self.docks["propiedades"].hide()
        self._restaurar_disposicion()

        # ---------------------------------------------------------------- barra de estado
        self.lbl_seleccion = QLabel()
        self.statusBar().addPermanentWidget(self.lbl_seleccion)
        self.seleccion.cambiada.connect(self._al_seleccion)

        self.modulos = descubrir_modulos()
        for m in self.modulos:
            try:
                m.instalar(self)
            except Exception as e:  # noqa: BLE001
                self.registrar(tr("Unable to load plugin: {0} ({1})").format(m.nombre, e))
        self._construir_ribbon(self._acciones_modulos())
        self.ribbon.currentChanged.connect(self._al_paso)
        self._al_paso(self.ribbon.currentIndex())
        self.franja.actualizar_busqueda()
        self.statusBar().showMessage(tr("{0} plugins loaded").format(len(self.modulos)))
        self.refrescar_todo()
        self._sync_todas_acciones_panel()

    # ================================================================ construcción
    def _construir_ribbon(self, modulos: dict[str, tuple]):
        # barra de los siete pasos del trabajo (D123): cada página tiene las herramientas de su paso; lo
        # que no es un paso (proyecto, vistas, configuración, ayuda) está en la franja general.
        # `modulos`: {nombre del módulo: botón con su menú} de _acciones_modulos
        def de_modulos(*nombres):
            return [modulos[n] for n in nombres if n in modulos]
        resto = [g for n, g in modulos.items()
                 if n not in ("Quick Plot", "Depth Shifting", "Advance Log Analysis")]
        # el centro no tiene pestañas: cada paso termina con el grupo "Vistas" (lo que el centro puede
        # mostrar en ese paso), y el botón de la vista que se ve queda marcado
        vistas_modulos = [k for k in self.acciones.acciones if k.startswith("mod:view/")]
        self.ribbon.pagina("Prepare", [
            ("Import", ["import_las", ["import_las_folder", "import_dlis"]]),
            ("Runs", ["composite", ["combine", "partial_log", "splice"]]),
            ("Structure", ["validate", ["mnemonics", "convert_units", "resample"]]),
            ("Views", ["view_logplot", "view_table"])], 1)
        self.ribbon.pagina("Review", [
            ("Inspect", ["qc_window", ["dashboard", "qc_flags"]]),
            ("Contrast", de_modulos("Quick Plot")),
            ("Views", ["view_logplot"])], 2)
        self.ribbon.pagina("Correct", [
            ("Repair", ["despike", "interpolate", "graphic_edit"]),
            ("Transform", ["smooth", ["curve_null", "curve_value", "clip"], "calculator", ["filter"]]),
            ("Compare", ["compare_original", ["restore_original", "history"]]),
            ("Scope", ["batch"]),
            ("Views", ["view_logplot", "view_table"])], 3)
        self.ribbon.pagina("Align and Compare", [
            ("Depth", ["depth_shift"] + de_modulos("Depth Shifting") + [["create_tvd", "create_md"]]),
            ("Neighbors", ["normalize"]),
            ("Views", ["view_logplot", "view_trajectory", "view_cross_section", "view_zones"])], 4)
        self.ribbon.pagina("Reconstruct", [
            ("Reconstruct", ["deep_learning"]),
            ("Views", ["view_logplot"])], 5)
        self.ribbon.pagina("Check", [
            ("Changes and QC", ["qc_window", "history"]),
            ("Petrophysics", de_modulos("Advance Log Analysis") + resto),
            ("Views", ["view_logplot"] + vistas_modulos + ["view_lithology", "view_completion"])], 6)
        self.ribbon.pagina("Deliver", [
            ("Export", ["export_las", ["export_csv", "export_excel"]]),
            ("Report", ["qc_report"]),
            ("Printing", ["print", ["print_setup"]]),
            ("Views", ["view_logplot"])], 7)

    def _acciones_modulos(self) -> dict[str, tuple]:
        """Las entradas de los módulos (interpretación, Quick Plot...) pasan al registro de
        acciones, además del menú del editor de logs. Devuelve {módulo: botón con menú} para que
        cada uno vaya al paso donde se usa."""
        iconos_mod = {"Advance Log Analysis": "calculator", "Pickett Plot": "crossplot", "Hingle Plot": "crossplot",
                      "Depth Shifting": "depth_shift", "Quick Plot": "histogram"}
        grupos = {}
        ayuda = {"Depth Shifting": "Shift a curve by a fixed depth, into a new column or in place",
                 "Quick Plot": "Plot a curve against depth, or its histogram",
                 "Advance Log Analysis": "Vshale, porosity and water saturation of the selected log"}
        for m in self.modulos:
            entradas = m.acciones_editor_logs(self)
            if not entradas:
                continue
            icono = iconos_mod.get(m.nombre, "plugins")
            claves = []
            for texto, func in entradas:
                if texto == "-":
                    claves.append("-")
                elif isinstance(func, list):
                    for t2, f2 in func:
                        k = f"mod:{m.nombre}/{texto}/{t2}"
                        self.acciones.accion(k, t2, icono, ayuda.get(m.nombre, ""), lambda f=f2: self._con_curva(f))
                        claves.append(k)
                    claves.append("-")
                else:
                    k = f"mod:{m.nombre}/{texto}"
                    self.acciones.accion(k, texto, icono, ayuda.get(m.nombre, ""), lambda f=func: self._con_curva(f))
                    claves.append(k)
            self.acciones.modulos[m.nombre] = entradas
            while claves and claves[-1] == "-":
                claves.pop()
            # un módulo con una sola entrada es un botón, no un menú de un elemento
            grupos[m.nombre] = claves[0] if len(claves) == 1 else ("menu", m.nombre, icono, claves)
        return grupos

    def _con_curva(self, funcion):
        """Las acciones de los módulos usan el registro y la curva seleccionados."""
        if self.registro_seleccionado() is None:
            return None
        self.preparar_curva(obligatoria=False)
        return funcion()

    # ================================================================ utilidades
    def cargar_bases(self) -> None:
        """Bases propias; los grupos de alias, los que el usuario editó si los hay."""
        self.base_herr = bases.herramientas_por_defecto()
        self.base_lito = bases.litologias_por_defecto()
        guardados = self.ajustes.value("alias", "")
        self.alias = (bases.BaseAlias.desde_texto(guardados) if guardados else None) or bases.alias_por_defecto()
        from ..nucleo import validacion
        validacion.fijar_alias(self.alias)

    def registrar(self, texto: str) -> None:
        self.diagnostico.append(texto)
        self.statusBar().showMessage(texto.splitlines()[0], 5000)

    def agregar_pestana(self, nombre: str, widget: QWidget, icono: str | None = None) -> None:
        self.vistas[nombre] = widget          # las de los módulos (Pickett, Hingle) también son vistas
        if icono is None and ("Pickett" in nombre or "Hingle" in nombre):
            icono = "crossplot"
        a = self.acciones.accion(f"mod:view/{nombre}", nombre, icono or "plugins",
                                 "Crossplot to find Rw, m and the saturation of the selected interval",
                                 lambda n=nombre: self.mostrar_vista(n))
        self.acciones.agrupar_vista(a, nombre)
        if icono:
            self.pestanas.addTab(widget, iconos.icono(icono), tr(nombre))
        else:
            self.pestanas.addTab(widget, tr(nombre))

    def _titulo(self):
        nombre = Path(self.proyecto.ruta).name if self.proyecto.ruta else tr("(unsaved)")
        self.setWindowTitle(f"{TITULO} - {nombre}{' *' if self.proyecto.modificado else ''}")

    def _cambiado(self, editor):
        self._titulo()
        if editor is self.editor_logs:
            self.panel_historial.fijar(self.seleccion.registro())
            self.refrescar_estado(self.editor_logs.registro())
        if editor is not self.pagina_logplot and self.pestanas.currentWidget() is not self.pagina_logplot:
            return
        self.reconstruir_arbol()

    def _pestana(self, i):
        w = self.pestanas.widget(i)
        if w in (self.pagina_logplot, self.pagina_corte, self.editor_tpl):
            w.refrescar()

    def refrescar_editores(self, excepto=None):
        for ed in self.editores:
            if ed is not excepto:
                ed.refrescar()
        self._titulo()
        self.refrescar_estado()
        self._actualizar_centro()

    def sincronizar_qc_proyecto(self):
        """Umbrales y rangos de QC del proyecto (si los tiene) sobre los del usuario (D87). Solo
        cambia algo, e invalida la caché de QC, si cambió el proyecto o sus ajustes de QC."""
        clave = (id(self.proyecto), self.proyecto.qc_ajustes)
        if clave != getattr(self, "_clave_qc", None):
            self._clave_qc = clave
            preferencias.fijar_proyecto(preferencias.PreferenciasQC.desde_json(self.proyecto.qc_ajustes))
            qc.invalidar()

    def refrescar_todo(self):
        self.sincronizar_qc_proyecto()
        self.seleccion.validar()
        self.refrescar_editores()
        self.reconstruir_arbol()
        for m in self.modulos if hasattr(self, "modulos") else []:
            m.cargar(self.proyecto)
        self._al_seleccion()

    def refrescar_estado(self, reg=None):
        """Tras un cambio de datos: árbol (insignias), flujo, QC e historial. Con `reg` (la edición
        tocó solo ese registro) se rehace solo su nodo del árbol."""
        if not hasattr(self, "panel_qc"):
            return
        if reg is None or not self.actualizar_nodo_registro(reg):
            self.reconstruir_arbol()
        self.panel_flujo.refrescar()
        self._actualizar_siguiente()
        self.panel_historial.fijar(self.seleccion.registro())
        self.panel_qc.datos_cambiados()
        self.panel_propiedades.refrescar()

    # ================================================================ operaciones compuestas
    @contextmanager
    def operacion(self, descripcion: str):
        """Agrupa los cambios de una herramienta (en uno o varios registros) en una sola entrada
        de deshacer; las curvas nuevas se agregan a las plantillas si la preferencia lo pide."""
        hp = self.proyecto.historial_ops
        op = hp.iniciar(descripcion)
        try:
            yield op
        finally:
            hecha = hp.terminar(op, self.proyecto, self.prefs.plantilla_auto, self.alias)
            if hecha is not None and hecha.plantillas:
                nombres = sorted({c.curva.nombre_x for c in hecha.plantillas})
                plantillas = sorted({c.plantilla.nombre for c in hecha.plantillas})
                self.registrar(tr("Added to template {0}: {1}").format(", ".join(plantillas), ", ".join(nombres)))
                self.proyecto.modificado = True
                self.editor_tpl.refrescar()
                self.pagina_logplot.dibujar()

    def _tras_deshacer(self, resultado, rehacer: bool = False):
        if resultado is None:
            return
        texto, op = resultado
        if op is not None:
            self.registrar((tr("Redone in {0} log(s): {1}") if rehacer else tr("Undone in {0} log(s): {1}"))
                           .format(op.n_registros, tr(op.descripcion)))
            self.proyecto.modificado = True
            self.refrescar_editores()
            if op.plantillas:
                self.pagina_logplot.dibujar()
        else:
            self.editor_logs.seguir_seleccion()
            self.editor_logs.actualizar_tabla()

    # ================================================================ selección global
    def _al_seleccion(self):
        s = self.seleccion
        s.validar()
        if s.pozo >= 0 and hasattr(self, "centro") and self.centro.currentWidget() is self.inicio:
            self.centro.setCurrentWidget(self.pestanas)        # elegir un pozo deja la pantalla de inicio
        self.lbl_seleccion.setText(s.texto())
        if not hasattr(self, "panel_qc"):
            return
        self.editor_logs.seguir_seleccion()
        self.pagina_logplot.seguir_seleccion()
        self.panel_qc.seguir_seleccion()
        self.panel_historial.fijar(s.registro())
        self.panel_flujo.refrescar()
        self._actualizar_siguiente()
        self.panel_propiedades.refrescar()
        self._marcar_nodo()

    def registro_seleccionado(self, avisar: bool = True):
        reg = self.seleccion.registro()
        if reg is None and avisar:
            aviso(self, tr("Select a log first (project tree, Basic Log Editor or QC panel)."))
        return reg

    def preparar_curva(self, obligatoria: bool = True) -> bool:
        """Deja el editor de logs en el log seleccionado con la curva seleccionada como columna
        activa (las herramientas de curva trabajan sobre ella)."""
        reg = self.registro_seleccionado()
        if reg is None:
            return False
        self.editor_logs.seguir_seleccion()
        k = self.seleccion.indice_curva()
        if k < 0 and reg.existe_columna(self.editor_logs.columna_clic) and \
                self.editor_logs.columna_clic not in (reg.indice_md, reg.indice_tvd):
            k = self.editor_logs.columna_clic
        if k < 0:
            if obligatoria:
                aviso(self, tr("Select a curve first: click its column in the Basic Log Editor or its node in the "
                               "project tree."))
            return False
        self.editor_logs.columna_clic = k
        return True

    # ================================================================ paneles
    def mostrar_panel(self, clave: str, visible: bool = True):
        dock = self.docks.get(clave) if hasattr(self, "docks") else None
        if dock is None:
            return
        dock.setVisible(visible)
        if visible:
            dock.raise_()

    def _sync_accion_panel(self, accion, dock):
        accion.blockSignals(True)
        accion.setChecked(not dock.isHidden())
        accion.blockSignals(False)

    def _sync_todas_acciones_panel(self):
        for clave, accion in ACCIONES_PANELES.items():
            self._sync_accion_panel(self.acciones[accion], self.docks[clave])

    def _restaurar_disposicion(self):
        estado = self.ajustes.value(CLAVE_DISPOSICION)
        geometria = self.ajustes.value("ventana/geometria")
        if isinstance(geometria, QByteArray):
            self.restoreGeometry(geometria)
        if isinstance(estado, QByteArray):
            self.restoreState(estado)

    def guardar_disposicion(self):
        self.ajustes.setValue(CLAVE_DISPOSICION, self.saveState())
        self.ajustes.setValue("ventana/geometria", self.saveGeometry())

    def ventana_qc(self, pestana: str | None = None):
        """Muestra el panel de QC (en la pestaña indicada) con la selección actual, a pantalla completa:
        revisar la calidad necesita espacio (D123); "Volver al gráfico" lo devuelve al lateral."""
        if self.registro_seleccionado() is None:
            return None
        self.mostrar_panel("qc")
        self.ampliar_qc(True)
        if pestana:
            self.panel_qc.ir_a(pestana)
        self.panel_qc.seguir_seleccion()
        return self.panel_qc

    def dashboard_qc(self):
        if not self._hay_logs():
            return None
        return self.ventana_qc("dashboard")

    def ampliar_qc(self, ampliar: bool):
        """QC a pantalla completa (nota 7 de la prueba manual): oculta el árbol, el flujo y el centro,
        y el panel de QC ocupa la ventana; al desmarcar vuelve todo como estaba."""
        if ampliar == getattr(self, "_qc_ampliado", False):
            return
        self._qc_ampliado = ampliar
        if ampliar:
            self._antes_de_ampliar = {k: not self.docks[k].isHidden() for k in ("proyecto", "flujo")}
            for k in ("proyecto", "flujo"):
                self.docks[k].hide()
            self.centro.hide()
            self.mostrar_panel("qc")
        else:
            self.centro.show()
            for k, visible in getattr(self, "_antes_de_ampliar", {"proyecto": True}).items():
                self.docks[k].setVisible(visible)
            self.resizeDocks([self.docks["qc"]], [470], Qt.Horizontal)
        b = self.panel_qc.b_ampliar
        b.blockSignals(True)
        b.setChecked(ampliar)
        b.setText(tr("Back to the plot") if ampliar else tr("Expand"))
        b.blockSignals(False)

    # ================================================================ centro (D123)
    # vistas del centro de cada paso: el gráfico siempre (el pozo es el centro del trabajo); las demás,
    # solo en el paso donde se usan. Las vistas de un módulo que no está aquí van en Comprobar.
    VISTAS_POR_PASO = [("logplot", "logs"), ("logplot",), ("logplot", "logs"), ("logplot", "tray", "corte", "zonas"),
                       ("logplot",), ("logplot", "Pickett Plot", "Hingle Plot", "lito", "comp"), ("logplot",)]

    def _al_paso(self, paso: int):
        """Al elegir un paso, el centro muestra solo sus vistas y el QC a pantalla completa vuelve al
        lateral fuera de Revisar y Comprobar."""
        if paso not in (1, 5):
            self.ampliar_qc(False)
        if not 0 <= paso < len(self.VISTAS_POR_PASO):
            return
        propias = set(self.VISTAS_POR_PASO[paso])
        conocidas = {v for vs in self.VISTAS_POR_PASO for v in vs}
        if paso == 5:
            propias |= set(self.vistas) - conocidas
        actual = next((k for k, w in self.vistas.items() if w is self.pestanas.currentWidget()), "logplot")
        if actual not in propias and self.centro.currentWidget() is self.pestanas:
            self.mostrar_vista("logplot")

    def mostrar_vista(self, nombre: str):
        """Trae al centro una vista: gráfico, corte, tabla de datos, trayectoria, topes... Si no es del
        paso actual, su pestaña aparece igual: el usuario la pidió (Ver, buscador, otro paso)."""
        if nombre == "tpl":
            return self.editar_plantilla()
        self.ampliar_qc(False)
        w = self.vistas[nombre]
        self.centro.setCurrentWidget(self.pestanas)
        self.pestanas.setCurrentWidget(w)
        self.acciones.marcar_vista(nombre)
        return w

    def editar_plantilla(self, indice: int | None = None):
        """La plantilla del gráfico (pistas, curvas, escalas) en una ventana aparte, no en una pestaña:
        es una configuración del gráfico de registros. Sin índice, la del gráfico actual."""
        if indice is None:
            lp = self.pagina_logplot.estado()
            indice = lp.plantilla if lp is not None and lp.plantilla >= 0 else 0
        if self._dialogo_plantilla is None:
            d = QDialog(self)
            d.setWindowTitle(tr("Template"))
            QVBoxLayout(d).addWidget(self.editor_tpl)
            d.resize(1100, 720)
            self._dialogo_plantilla = d
        self.editor_tpl.refrescar()
        if 0 <= indice < self.editor_tpl.ch_plantilla.count():
            self.editor_tpl.ch_plantilla.setCurrentIndex(indice)
        self._dialogo_plantilla.show()
        self._dialogo_plantilla.raise_()
        return self._dialogo_plantilla

    def _plantilla_cambiada(self):
        self._titulo()
        self.pagina_logplot.dibujar()
        self.reconstruir_arbol()

    def pagina_inicio(self):
        self.centro.setCurrentWidget(self.inicio)

    def _actualizar_centro(self):
        """Sin pozos se ve la pantalla de inicio; al cargar el primer pozo, el gráfico."""
        if not hasattr(self, "centro"):
            return
        vacio = not self.proyecto.pozos
        derecha = ("qc", "historial", "propiedades")      # sin pozos están vacíos: no ocupan la pantalla
        if vacio and not getattr(self, "_vacio", False):
            self.centro.setCurrentWidget(self.inicio)
            self._paneles_antes = {k: not self.docks[k].isHidden() for k in derecha}
            for k in derecha:
                self.docks[k].hide()
        elif not vacio and getattr(self, "_vacio", True):
            self.centro.setCurrentWidget(self.pestanas)
            for k, visible in getattr(self, "_paneles_antes", {}).items():
                self.docks[k].setVisible(visible)
            if getattr(self, "_paneles_antes", None):
                self.docks["qc"].raise_()
        self._vacio = vacio

    def _actualizar_siguiente(self):
        from ..nucleo import flujo
        pozo = self.seleccion.objeto_pozo()
        pasos = self.panel_flujo.pasos if pozo is not None else []
        k = flujo.siguiente(pasos)
        self.franja.fijar_siguiente(pozo.nombre if pozo else "", k, pasos[k].titulo if k >= 0 else "",
                                    pasos[k].detalle if k >= 0 else "")

    # ================================================================ ejemplos (D123)
    # (nombre visible, guía, carpeta de datos, zip de los LAS); datos públicos del Kansas Geological Survey
    EJEMPLOS = [("El Dorado: oil in carbonates (12 wells)", "ejemplo_el_dorado.md", "el_dorado", "las_el_dorado.zip"),
                ("Cutter: gas and oil in sandstones (10 wells)", "ejemplo_cutter.md", "cutter", "las_cutter.zip")]

    @staticmethod
    def carpetas_ejemplos() -> tuple[Path, Path] | None:
        """(carpeta de las guías, carpeta de los datos). En el ejecutable, `ejemplos/` junto al .exe
        (o dentro de _internal); desde el código, docs/ y docs/ejemplos/."""
        import sys
        if getattr(sys, "frozen", False):
            for d in (Path(sys.executable).parent / "ejemplos", Path(getattr(sys, "_MEIPASS", ".")) / "ejemplos"):
                if (d / "el_dorado").is_dir():
                    return d, d
            return None
        docs = Path(__file__).resolve().parents[3] / "docs"
        return (docs, docs / "ejemplos") if (docs / "ejemplos").is_dir() else None

    def abrir_ejemplo(self, nombre: str | None = None):
        """Carga un pozo de ejemplo en un proyecto nuevo (sus LAS ya descomprimidos e importados) y
        abre su guía. Los demás archivos del ejemplo (topes, trayectoria...) quedan en una carpeta
        del usuario, que la guía indica."""
        import shutil
        import zipfile
        from PySide6.QtCore import QStandardPaths
        carpetas = self.carpetas_ejemplos()
        if carpetas is None:
            aviso(self, tr("The example files are not installed."))
            return None
        if nombre is None:
            visibles = [tr(e[0]) for e in self.EJEMPLOS]
            elegido, ok = QInputDialog.getItem(self, tr("Try an Example"), tr("Example"), visibles, 0, False)
            if not ok:
                return None
            nombre = self.EJEMPLOS[visibles.index(elegido)][0]
        if not self._confirmar_guardar():
            return None
        _, guia, sub, zip_las = next(e for e in self.EJEMPLOS if e[0] == nombre or e[2] == nombre)
        guias, datos = carpetas
        base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or Path.home() / "Kurvo")
        destino = base / "ejemplos" / sub
        if destino.exists():
            shutil.rmtree(destino, ignore_errors=True)
        (destino / "las").mkdir(parents=True, exist_ok=True)
        for f in (datos / sub).iterdir():
            if f.is_file() and f.name != zip_las:
                shutil.copy2(f, destino / f.name)
        with zipfile.ZipFile(datos / sub / zip_las) as z:
            z.extractall(destino / "las")
        self.proyecto = Proyecto()
        qc.invalidar()
        self._vacio = True
        nuevos = self.importar_carpeta_las(str(destino / "las"))
        self.mostrar_vista("logplot")
        self.registrar(tr("Example {0} loaded: {1} log(s). Its other files are in {2}").format(
            nombre, len(nuevos), destino))
        self._mostrar_guia(guias / guia, destino)
        return destino

    def abrir_manual(self):
        """El manual (docs/manual.md; en el ejecutable, ejemplos/manual.md) en el visor de las guías."""
        carpetas = self.carpetas_ejemplos()
        if carpetas is None or not (carpetas[0] / "manual.md").exists():
            aviso(self, tr("The manual is not installed."))
            return None
        return self._mostrar_guia(carpetas[0] / "manual.md", None)

    def _mostrar_guia(self, ruta: Path, carpeta_datos: Path | None):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        d = QDialog(self)
        d.setWindowTitle(tr("Guide") + f" — {ruta.stem}")
        t = QTextBrowser()
        t.setOpenExternalLinks(True)
        t.setSearchPaths([str(ruta.parent)])
        t.setMarkdown(ruta.read_text(encoding="utf-8"))
        b_carpeta = QToolButton()
        b_carpeta.setText(tr("Open the example folder"))
        b_carpeta.setIcon(iconos.icono("open"))
        b_carpeta.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b_carpeta.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(carpeta_datos))))
        b_carpeta.setVisible(carpeta_datos is not None)
        botones = caja_botones(QDialogButtonBox.Close)
        botones.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(t)
        fila = QHBoxLayout()
        fila.addWidget(b_carpeta)
        fila.addStretch(1)
        fila.addWidget(botones)
        lay.addLayout(fila)
        d.resize(820, 900)
        d.setModal(False)
        d.show()
        self._ventanas.append(d)
        return d

    # ================================================================ árbol
    def reconstruir_arbol(self):
        """Árbol del proyecto: pozos (logs con sus curvas, completación, litología), zonas, plantillas,
        log plots. Los logs y curvas llevan la nota de QC; las curvas editadas y generadas, su icono."""
        from ..nucleo import historial
        abiertos = self._nodos_abiertos()
        pr = self.proyecto
        qc.notas_varios([r for p in pr.pozos for r in p.logs], self.alias)     # en paralelo (D90)
        self.arbol.blockSignals(True)
        self.arbol.clear()
        raiz_pozos = QTreeWidgetItem([f"{tr('Wells')} ({len(pr.pozos)})"])
        raiz_pozos.setData(0, Qt.UserRole, ("pozos",))
        raiz_pozos.setIcon(0, iconos.icono("wells"))
        for i, p in enumerate(pr.pozos):
            ip = QTreeWidgetItem([p.nombre])
            ip.setData(0, Qt.UserRole, ("pozo", i))
            ip.setIcon(0, iconos.icono("well"))
            for clave, titulo, lista, icono in (("logs", "Logs", p.logs, "log"),
                                                ("comps", "Completion", p.completaciones, "completion"),
                                                ("litos", "Lithology", p.litologias, "lithology")):
                g = QTreeWidgetItem([tr(titulo)])
                g.setData(0, Qt.UserRole, (clave, i))
                g.setIcon(0, iconos.icono(icono))
                for j, x in enumerate(lista):
                    h = QTreeWidgetItem([x.nombre])
                    h.setData(0, Qt.UserRole, (clave[:-1], i, j))
                    h.setIcon(0, iconos.icono(icono))
                    if clave == "logs":
                        self._nodos_curvas(h, x, i, j, historial)
                    g.addChild(h)
                ip.addChild(g)
            raiz_pozos.addChild(ip)
        ramas = [("zonas", "Zones", pr.zonas, "zona", "zones"),
                 ("plantillas", "Templates", pr.plantillas, "plantilla", "templates"),
                 ("logplots", "Log Plots", pr.logplots, "logplot", "logplot")]
        self.arbol.addTopLevelItem(raiz_pozos)
        for clave, titulo, lista, hijo, icono in ramas:
            r = QTreeWidgetItem([f"{tr(titulo)} ({len(lista)})"])
            r.setData(0, Qt.UserRole, (clave,))
            r.setIcon(0, iconos.icono(icono))
            for j, x in enumerate(lista):
                h = QTreeWidgetItem([x.nombre])
                h.setData(0, Qt.UserRole, (hijo, j))
                h.setIcon(0, iconos.icono(icono))
                r.addChild(h)
            self.arbol.addTopLevelItem(r)
        raiz_pozos.setExpanded(True)
        self._reabrir(abiertos)
        self.arbol.blockSignals(False)
        self._marcar_nodo()

    def actualizar_nodo_registro(self, reg) -> bool:
        """Tras editar un registro: rehace solo su nodo (nota, curvas e insignias) en lugar de todo
        el árbol (D91). Devuelve False si el nodo no está (el árbol hay que reconstruirlo)."""
        from ..nucleo import historial
        for i, p in enumerate(self.proyecto.pozos):
            for j, r in enumerate(p.logs):
                if r is reg:
                    break
            else:
                continue
            break
        else:
            return False
        item = self._buscar_nodo(("log", i, j))
        if item is None or item.text(0) != reg.nombre:
            return False
        abiertos = self._nodos_abiertos()
        self.arbol.blockSignals(True)
        try:
            item.takeChildren()
            self._nodos_curvas(item, reg, i, j, historial)
            self._reabrir(abiertos)
        finally:
            self.arbol.blockSignals(False)
        self._marcar_nodo()
        return True

    def _buscar_nodo(self, ref):
        def buscar(it):
            if it.data(0, Qt.UserRole) == ref:
                return it
            for k in range(it.childCount()):
                r = buscar(it.child(k))
                if r is not None:
                    return r
            return None
        for k in range(self.arbol.topLevelItemCount()):
            it = buscar(self.arbol.topLevelItem(k))
            if it is not None:
                return it
        return None

    def _nodos_curvas(self, item_log, reg, i, j, historial):
        try:
            estados = qc.notas(reg, self.alias)
        except Exception:  # noqa: BLE001 - un registro dañado no debe impedir dibujar el árbol
            estados = {}
        peor = qc.peor_nota(estados.values())
        item_log.setIcon(0, iconos.icono_nota("log", peor) if peor else iconos.icono("log"))
        if peor:
            item_log.setToolTip(0, tr("QC grade of the log: {0} (worst curve)").format(peor))
        for k, c in enumerate(reg.columnas):
            marca = " [MD]" if k == reg.indice_md else " [TVD]" if k == reg.indice_tvd else ""
            h = QTreeWidgetItem([f"{c.nombre}{marca}" + (f"  ({c.unidad})" if c.unidad else "")])
            h.setData(0, Qt.UserRole, ("curva", i, j, c.nombre))
            generada = c.nombre.upper().endswith(SUFIJOS_GENERADAS)
            editada = historial.original(reg, c.nombre) is not None
            base = "curve_generated" if generada else "curve_edited" if editada else "curve"
            e = estados.get(c.nombre)
            h.setIcon(0, iconos.icono_nota(base, e.nota) if e is not None else iconos.icono(base))
            partes = []
            if e is not None:
                partes.append(tr("QC grade {0}").format(e.nota) + (": " + "; ".join(e.avisos) if e.avisos else ""))
            if editada:
                partes.append(tr("edited (original version kept)"))
            if generada:
                partes.append(tr("generated curve") + (f": {c.descripcion}" if c.descripcion else ""))
            h.setToolTip(0, "\n".join(partes))
            item_log.addChild(h)

    def _nodos_abiertos(self) -> set:
        abiertos = set()

        def recorrer(it):
            if it.isExpanded():
                abiertos.add(repr(it.data(0, Qt.UserRole)))
            for k in range(it.childCount()):
                recorrer(it.child(k))
        for k in range(self.arbol.topLevelItemCount()):
            recorrer(self.arbol.topLevelItem(k))
        return abiertos

    def _reabrir(self, abiertos: set):
        def recorrer(it):
            if repr(it.data(0, Qt.UserRole)) in abiertos:
                it.setExpanded(True)
            for k in range(it.childCount()):
                recorrer(it.child(k))
        for k in range(self.arbol.topLevelItemCount()):
            recorrer(self.arbol.topLevelItem(k))

    def _marcar_nodo(self):
        """Resalta en el árbol el log (o la curva) seleccionado, sin disparar otra selección."""
        s = self.seleccion
        objetivo = ("curva", s.pozo, s.log, s.curva) if s.curva else ("log", s.pozo, s.log)

        def buscar(it):
            if it.data(0, Qt.UserRole) == objetivo:
                return it
            for k in range(it.childCount()):
                r = buscar(it.child(k))
                if r is not None:
                    return r
            return None
        for k in range(self.arbol.topLevelItemCount()):
            it = buscar(self.arbol.topLevelItem(k))
            if it is not None:
                self.arbol.blockSignals(True)
                self.arbol.setCurrentItem(it)
                self.arbol.blockSignals(False)
                return

    def _al_nodo(self, item, *_):
        if item is None:
            return
        ref = item.data(0, Qt.UserRole)
        if ref[0] == "pozo":
            self.seleccion.fijar(pozo=ref[1])
        elif ref[0] in ("log", "comp", "lito"):
            self.seleccion.fijar(pozo=ref[1], log=ref[2] if ref[0] == "log" else None,
                                 curva="" if ref[0] == "log" else None)
        elif ref[0] == "curva":
            self.seleccion.fijar(pozo=ref[1], log=ref[2], curva=ref[3])
        elif ref[0] == "zona":
            self.seleccion.fijar(zona=ref[1])

    def _abrir_nodo(self, item, *_):
        ref = item.data(0, Qt.UserRole)
        if ref[0] in ("log", "curva"):
            self.editor_logs.mostrar(ref[1], ref[2])
            self.mostrar_vista("logs")
            if ref[0] == "curva":
                k = self.proyecto.pozos[ref[1]].logs[ref[2]].indice_columna(ref[3])
                if k >= 0:
                    self.editor_logs.tabla.selectColumn(k)
        elif ref[0] == "pozo":
            self.editor_tray.ch_pozo.setCurrentIndex(ref[1])
            self.mostrar_vista("tray")
        elif ref[0] in ("comp", "lito"):
            ed = self.editor_comp if ref[0] == "comp" else self.editor_lito
            ed.ch_pozo.setCurrentIndex(ref[1])
            ed.ch_item.setCurrentIndex(ref[2])
            self.mostrar_vista(ref[0])
        elif ref[0] == "zona":
            self.mostrar_vista("zonas")
        elif ref[0] == "plantilla":
            self.editar_plantilla(ref[1])
        elif ref[0] == "logplot":
            self.pagina_logplot.ch_lp.setCurrentIndex(ref[1])
            self.mostrar_vista("logplot")

    def _lista_de(self, ref):
        pr = self.proyecto
        tipo = ref[0]
        if tipo == "pozo":
            return pr.pozos, ref[1]
        if tipo in ("log", "comp", "lito"):
            p = pr.pozos[ref[1]]
            return {"log": p.logs, "comp": p.completaciones, "lito": p.litologias}[tipo], ref[2]
        return {"zona": pr.zonas, "plantilla": pr.plantillas, "logplot": pr.logplots}[tipo], ref[1]

    def _menu_arbol(self, pos):
        """Menús contextuales del árbol (FUN_004062c0) y atajos a las acciones del registro."""
        item = self.arbol.itemAt(pos)
        if item is None:
            return
        self.arbol.setCurrentItem(item)
        ref = item.data(0, Qt.UserRole)
        a = self.acciones
        m = QMenu(self)
        tipo = ref[0]
        if tipo == "curva":
            for k in ("qc_window", "qc_flags", "graphic_edit"):
                m.addAction(a[k])
            sub = m.addMenu(iconos.icono("curve_null"), tr("Curve Editing"))
            from .edicion_curvas import acciones as acciones_edicion
            for k in acciones_edicion(None):
                sub.addSeparator() if k == "-" else sub.addAction(a[k])
            m.addAction(a["convert_units"])
            m.addSeparator()
            m.addAction(iconos.icono("properties"), tr("Curve Properties"), lambda: self.mostrar_panel("propiedades"))
            m.exec(self.arbol.viewport().mapToGlobal(pos))
            return
        if tipo in ("pozo", "log", "comp", "lito", "zona", "plantilla", "logplot"):
            m.addAction(tr("Setting"), lambda: self._renombrar(ref))
            m.addSeparator()
            m.addAction(iconos.icono("up"), tr("Move Up"), lambda: self._mover(ref, -1))
            m.addAction(tr("Move to First"), lambda: self._mover(ref, "first"))
            m.addAction(iconos.icono("down"), tr("Move Down"), lambda: self._mover(ref, 1))
            m.addAction(tr("Move to Last"), lambda: self._mover(ref, "last"))
            m.addSeparator()
            m.addAction(tr("Duplicate"), lambda: self._duplicar(ref))
            m.addAction(iconos.icono("delete"), tr("Delete"), lambda: self._borrar(ref))
        if tipo in ("pozos", "pozo"):
            m.addSeparator()
            m.addAction(iconos.icono("new"), tr("Create New Well"), self.nuevo_pozo)
            m.addAction(iconos.icono("import"), tr("Import Well Header"), self.importar_cabecera)
            m.addAction(iconos.icono("export"), tr("Export Well Header"), self.exportar_cabecera)
        if tipo == "pozo":
            m.addSeparator()
            m.addAction(a["panel_workflow"])
        if tipo == "zonas":
            m.addAction(iconos.icono("new"), tr("Create New Zone"), lambda: (self.proyecto.nueva_zona(),
                                                                              self._tras_cambio()))
            m.addAction(iconos.icono("import"), tr("Import Zone List"), self.importar_zonas)
            m.addAction(iconos.icono("export"), tr("Export Zone List"), self.exportar_zonas)
        if tipo == "plantillas":
            m.addAction(iconos.icono("new"), tr("Create New Template"), self.nueva_plantilla)
            m.addAction(iconos.icono("import"), tr("Import Template"), self.importar_plantilla)
        if tipo == "plantilla":
            m.addAction(iconos.icono("export"), tr("Export Template"), lambda: self.exportar_plantilla(ref[1]))
        if tipo == "logplots":
            m.addAction(iconos.icono("new"), tr("Create New Log Plot"), self.pagina_logplot.nuevo)
        if tipo in ("logs", "log"):
            m.addSeparator()
            m.addAction(a["import_las"])
            m.addAction(a["import_las_folder"])
            m.addAction(a["import_dlis"])
            m.addAction(a["composite"])
            if tipo == "log":
                m.addSeparator()
                for k in ("validate", "qc_window", "history", "-", "export_las", "export_csv"):
                    m.addSeparator() if k == "-" else m.addAction(a[k])
            m.addAction(a["export_excel"])
        if tipo in ("comps", "comp"):
            m.addSeparator()
            m.addAction(iconos.icono("new"), tr("Create New Completion Package"), lambda: self._nuevo_paquete(ref[1]))
            m.addAction(iconos.icono("import"), tr("Import Completion Package"), lambda: self.importar_comp(ref[1]))
            if tipo == "comp":
                m.addAction(iconos.icono("export"), tr("Export Completion Package"),
                            lambda: self.exportar_comp(ref[1], ref[2]))
        if tipo in ("litos", "lito"):
            m.addSeparator()
            m.addAction(iconos.icono("new"), tr("Create New Lithology Interpretation"),
                        lambda: self._nueva_lito(ref[1]))
            m.addAction(iconos.icono("import"), tr("Import Interpretation"), lambda: self.importar_lito(ref[1]))
            if tipo == "lito":
                m.addAction(iconos.icono("export"), tr("Export Interpretation"),
                            lambda: self.exportar_lito(ref[1], ref[2]))
        m.exec(self.arbol.viewport().mapToGlobal(pos))

    def _tras_cambio(self):
        self.proyecto.modificado = True
        self.refrescar_todo()

    def _renombrar(self, ref):
        lista, i = self._lista_de(ref)
        nombre, ok = QInputDialog.getText(self, tr("Setting"), tr("Name"), text=lista[i].nombre)
        if not ok:
            return
        if not nombre.strip():
            aviso(self, tr("Empty name is not allowed! Please set new name."))
            return
        if any(x.nombre == nombre.strip() for k, x in enumerate(lista) if k != i):
            aviso(self, tr("Name is already used! Please use a different name."))
            return
        lista[i].nombre = nombre.strip()
        self._tras_cambio()

    def _mover(self, ref, dest):
        lista, i = self._lista_de(ref)
        j = {"first": 0, "last": len(lista) - 1}.get(dest, i + dest if isinstance(dest, int) else i)
        if not 0 <= j < len(lista) or j == i:
            return
        if ref[0] == "pozo":   # las zonas guardan una profundidad por pozo
            for z in self.proyecto.zonas:
                z.profundidades += [0.0] * (len(lista) - len(z.profundidades))
                Proyecto.mover(z.profundidades, i, j)
        if ref[0] == "zona":
            for lp in self.proyecto.logplots:
                if len(lp.zonas_visibles) == len(lista):
                    Proyecto.mover(lp.zonas_visibles, i, j)
        Proyecto.mover(lista, i, j)
        self._tras_cambio()

    def _duplicar(self, ref):
        import copy
        from ..nucleo.comun import UID
        lista, i = self._lista_de(ref)
        x = copy.deepcopy(lista[i])
        x.nombre = self.proyecto.nombre_libre(x.nombre + " copy", (y.nombre for y in lista)).replace(" copy1", " copy")
        if hasattr(x, "uid"):
            x.uid = UID.nuevo()
        lista.insert(i + 1, x)
        if ref[0] == "pozo":
            for z in self.proyecto.zonas:
                z.profundidades.insert(i + 1, z.prof(i))
        if ref[0] == "zona":
            for lp in self.proyecto.logplots:
                lp.zonas_visibles.insert(i + 1, True)
        self._tras_cambio()

    def _borrar(self, ref):
        lista, i = self._lista_de(ref)
        if not confirmar(self, tr("Delete {0}?").format(lista[i].nombre)):
            return
        if ref[0] == "pozo":
            self.proyecto.borrar_pozo(i)
        else:
            del lista[i]
            if ref[0] == "zona":
                for lp in self.proyecto.logplots:
                    if i < len(lp.zonas_visibles):
                        del lp.zonas_visibles[i]
        self._tras_cambio()

    # ================================================================ proyecto
    def _confirmar_guardar(self) -> bool:
        if not self.proyecto.modificado:
            return True
        r = QMessageBox.question(self, TITULO, tr("Do you want to save the project?"),
                                 QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        return self.guardar() if r == QMessageBox.Yes else True

    def abrir(self, ruta: str) -> bool:
        try:
            pr = Proyecto.abrir(ruta)
        except (ErrorProyecto, OSError, ErrorLAS) as e:
            aviso(self, tr(str(e)))
            return False
        self.proyecto = pr
        qc.invalidar()
        self.seleccion.fijar(pozo=0, log=0, curva="", zona=-1)
        self.refrescar_todo()
        self.mostrar_vista("logplot")
        self.pagina_logplot.refrescar()
        self.registrar(tr("Project {0} opened").format(Path(ruta).name))
        return True

    def abrir_dialogo(self):
        if not self._confirmar_guardar():
            return
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Open File"), "", tr(FILTRO_PROYECTO) + ";;" + tr("All (*.*)"))
        if ruta:
            self.abrir(ruta)

    def guardar(self) -> bool:
        if not self.proyecto.ruta:
            return self.guardar_como()
        for m in self.modulos:
            m.guardar(self.proyecto)
        try:
            self.proyecto.guardar()
        except OSError as e:
            aviso(self, tr("Error! Cannot save project file. {0}").format(e))
            return False
        self._titulo()
        self.registrar(tr("Project saved"))
        return True

    def guardar_como(self) -> bool:
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Save File"), "", tr(FILTRO_PROYECTO))
        if not ruta:
            return False
        if not ruta.endswith(".kurvo"):
            ruta += ".kurvo"
        self.proyecto.ruta = ruta
        return self.guardar()

    def cerrar_proyecto(self):
        if self._confirmar_guardar():
            self.proyecto = Proyecto()
            qc.invalidar()
            self.refrescar_todo()

    def closeEvent(self, ev):
        if self._confirmar_guardar():
            self.guardar_disposicion()
            ev.accept()
        else:
            ev.ignore()

    # ================================================================ pozos/LAS
    def nuevo_pozo(self):
        nombre, ok = QInputDialog.getText(self, tr("Create New Well"), tr("Well name"),
                                          text=self.proyecto.nombre_libre("WellName", (p.nombre for p in self.proyecto.pozos)))
        if ok:
            try:
                self.proyecto.nuevo_pozo(nombre.strip())
            except ErrorProyecto as e:
                aviso(self, str(e))
            self._tras_cambio()

    def importar_las_dialogo(self):
        """Import LAS del ribbon: uno o varios archivos. Con uno se eligen las columnas de profundidad;
        con varios se toman solas (D105)."""
        rutas, _ = QFileDialog.getOpenFileNames(self, tr("Import Las File"), "",
                                                tr("LAS File (*.las)") + ";;" + tr("All (*.*)"))
        if len(rutas) == 1:
            return self.importar_las(None, rutas[0])
        return self.importar_varios_las(rutas) if rutas else None

    def importar_carpeta_las(self, carpeta: str | None = None) -> list:
        """Import LAS Folder: todos los .las de la carpeta y sus subcarpetas (D105)."""
        if carpeta is None:
            carpeta = QFileDialog.getExistingDirectory(self, tr("Import LAS Folder"))
        if not carpeta:
            return []
        rutas = sorted({str(p) for p in Path(carpeta).rglob("*") if p.is_file() and p.suffix.lower() == ".las"})
        if not rutas:
            aviso(self, tr("There are no LAS files in {0}.").format(carpeta))
            return []
        return self.importar_varios_las(rutas)

    def _plantilla_inicial(self) -> None:
        """Proyecto sin plantillas al que se le importan registros: plantilla "Standard" por grupos de
        alias y un log plot que la usa, para que el Log Plot no quede vacío (D109)."""
        pr = self.proyecto
        if pr.plantillas or not pr.pozos:
            return
        from ..nucleo import plantilla_auto
        from ..nucleo.proyecto import LogPlot as EstadoLogPlot
        pr.plantillas.append(plantilla_auto.plantilla_estandar(pr, self.alias))
        if not pr.logplots:
            pr.logplots.append(EstadoLogPlot(nombre="logplot-1", pozo=max(self.seleccion.pozo, 0),
                                             las=max(self.seleccion.log, 0), plantilla=0,
                                             zonas_visibles=[True] * len(pr.zonas)))
            pr.logplot_actual = 0
        else:
            for lp in pr.logplots:
                if lp.plantilla < 0:
                    lp.plantilla = 0
        self.registrar(tr("Template \"{0}\" created from the alias groups (GR/SP, lithology, resistivity, "
                          "density-neutron, sonic).").format(pr.plantillas[0].nombre))

    @staticmethod
    def columnas_profundidad(reg) -> tuple[str, str]:
        """(MD, TVD) por defecto: MD la primera columna (como el diálogo), TVD la que dice TVD."""
        cols = reg.nombres()
        tvd = next((c for c in cols[1:] if "TVD" in c.upper()), "(none)")
        return (cols[0] if cols else ""), tvd

    def importar_varios_las(self, rutas: list[str]) -> list:
        """Importa varios LAS sin preguntar las columnas de profundidad, con barra de progreso. Los
        archivos que no se pueden leer se anotan en el diagnóstico y se informan al final."""
        from PySide6.QtWidgets import QProgressDialog
        progreso = QProgressDialog(tr("Importing LAS files..."), tr("Cancel"), 0, len(rutas), self)
        progreso.setWindowTitle(tr("Import LAS"))
        progreso.setMinimumDuration(400)
        nuevos, fallidos = [], []
        pozos_antes, zonas_antes = len(self.proyecto.pozos), len(self.proyecto.zonas)
        for k, ruta in enumerate(rutas):
            progreso.setValue(k)
            progreso.setLabelText(tr("Importing LAS files...") + f"\n{Path(ruta).name}")
            QApplication.processEvents()
            if progreso.wasCanceled():
                break
            reg = self.importar_las(None, ruta, auto=True)
            (nuevos if reg is not None else fallidos).append(reg if reg is not None else ruta)
        progreso.setValue(len(rutas))
        self.registrar(tr("{0} LAS file(s) imported into {1} new well(s); {2} new zone(s) from formation tops.").format(
            len(nuevos), len(self.proyecto.pozos) - pozos_antes, len(self.proyecto.zonas) - zonas_antes))
        if fallidos:
            self.registrar(tr("Not imported:") + "\n" + "\n".join(fallidos))
            aviso(self, tr("{0} file(s) could not be imported (see the Diagnostic Log).").format(len(fallidos)))
        if nuevos:
            self.seleccion.fijar(pozo=self.proyecto.pozos.index(next(p for p in self.proyecto.pozos
                                                                     if nuevos[0] in p.logs)), log=0, curva="")
            self._plantilla_inicial()
            self._tras_cambio()
        return nuevos

    def importar_las(self, i_pozo: int | None = None, ruta: str | None = None,
                     auto: bool = False) -> RegistroLAS | None:
        """Importa un LAS y elige las columnas de profundidad MD y TVD. Sin pozo indicado, el
        registro va al pozo del mismo UWI o nombre (LEASE + WELL), o a uno nuevo, y los topes de
        formación de ~Other pasan a las zonas (D104). `auto`: sin diálogos (importación múltiple)."""
        if ruta is None:
            ruta, _ = QFileDialog.getOpenFileName(self, tr("Import Las File"), "",
                                                  tr("LAS File (*.las)") + ";;" + tr("All (*.*)"))
        if not ruta:
            return None
        try:
            reg = RegistroLAS.abrir(ruta)
        except (ErrorLAS, OSError, ValueError) as e:
            if auto:
                self.registrar(f"{Path(ruta).name}: {e}")
            else:
                aviso(self, str(e))
            return None
        cols = reg.nombres()
        if not cols:
            if not auto:
                aviso(self, tr("The log has no curves."))
            return None
        md_def, tvd_def = self.columnas_profundidad(reg)
        if auto:
            v = {"md": md_def, "tvd": tvd_def}
        else:
            v = pedir("Depth columns", [Campo("md", "Depth MD", "opcion", md_def, cols),
                                        Campo("tvd", "Depth TVD", "opcion", tvd_def, ["(none)"] + cols)], self)
            if v is None:
                return None
        reg.fijar_indices(reg.indice_columna(v["md"]), reg.indice_columna(v["tvd"]) if v["tvd"] in cols else -1)
        from ..nucleo import cabecera_pozo
        if i_pozo is None:
            i_pozo, _ = cabecera_pozo.ubicar_pozo(self.proyecto, reg, Path(ruta).stem)
        topes = cabecera_pozo.topes(reg)
        if topes:
            n = cabecera_pozo.asignar_topes(self.proyecto, i_pozo, topes)
            if n:
                self.registrar(tr("{0}: {1} formation top(s) from the ~Other section").format(reg.nombre, n))
        from ..nucleo import historial, validacion
        if reg.nulo_archivo != NULO or validacion.convertir_nulos(reg.copia()):
            historial.aplicar(reg, "Import: convert nulls", f"file NULL {reg.nulo_archivo:g} -> -999.25",
                              validacion.convertir_nulos, reg)
        self._unidad_prof_por_defecto(reg)
        extra = [x for x in self.prefs.nulos_extra if x != NULO]
        if extra:
            def nulos_extra():
                for c in reg.columnas:
                    c.datos = np.where(np.isin(c.datos, extra), NULO, c.datos)
            historial.aplicar(reg, "Import: convert nulls", "extra nulls " + ", ".join(f"{x:g}" for x in extra),
                              nulos_extra)
        problemas = validacion.validar(reg)
        if any(p.nivel == validacion.ERROR for p in problemas):
            self.registrar(tr("{0}: {1} — use Validate LAS").format(reg.nombre, validacion.resumen(problemas)) + "\n"
                           + "\n".join(map(str, problemas)))
        pozo = self.proyecto.pozos[i_pozo]
        if cabecera_pozo.fijar_kb(pozo, reg):
            self.registrar(tr("{0}: KB elevation {1:g} taken from the LAS header").format(
                pozo.nombre, pozo.trayectoria.tvd_a_ss))
        if any(r.nombre == reg.nombre for r in pozo.logs):
            reg.nombre = self.proyecto.nombre_libre(reg.nombre + "-", (r.nombre for r in pozo.logs))
        pozo.logs.append(reg)
        if auto:
            return reg
        self.seleccion.fijar(pozo=i_pozo, log=len(pozo.logs) - 1, curva="")
        self._plantilla_inicial()
        self._tras_cambio()
        return reg

    def _unidad_prof_por_defecto(self, reg) -> None:
        """Columnas de profundidad sin unidad: la de User Settings (m o ft), anotada en la bitácora (D98)."""
        from ..nucleo import historial
        sin = [k for k in (reg.indice_md, reg.indice_tvd) if reg.existe_columna(k) and not reg.columnas[k].unidad.strip()]
        if not sin:
            return
        unidad = self.prefs.unidad_prof

        def poner():
            for k in sin:
                reg.columnas[k].unidad = unidad
        historial.aplicar(reg, "Import: default depth unit", f"{', '.join(reg.columnas[k].nombre for k in sin)} "
                          f"-> {unidad} (User Settings)", poner)

    def exportar_las_activo(self):
        if self.registro_seleccionado() is None:
            return None
        return self.exportar_las(self.seleccion.pozo, self.seleccion.log)

    def exportar_las(self, i_pozo: int, i_log: int, ruta: str | None = None):
        reg = self.proyecto.pozos[i_pozo].logs[i_log]
        if ruta is None:
            ruta, _ = QFileDialog.getSaveFileName(self, tr("Export LAS File"), reg.nombre + ".las", tr("LAS File (*.las)"))
        if ruta:
            try:
                reg.guardar(ruta, self.proyecto.pozos[i_pozo].nombre)
            except OSError:
                aviso(self, tr("Unable to export las file. File is being used by other application or "
                               "insufficient privilege."))
                return None
            reg.historial.anotar("Export LAS", ", ".join(reg.nombres()), Path(ruta).name)
            self.registrar(tr("{0} exported to {1}").format(reg.nombre, ruta))
            self.refrescar_estado()
        return ruta

    def importar_cabecera(self):
        """'#WELLNAME, X-COORD, Y-COORD'."""
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Import Well Header"), "", tr("Text delimited files (*.*)"))
        if not ruta:
            return
        for linea in leer_lineas(ruta):
            s = linea.strip()
            if not s or s.startswith("#"):
                continue
            c = [x.strip() for x in s.split(",")]
            i = self.proyecto.indice_pozo(c[0])
            x, y = (a_float(c[1]) if len(c) > 1 else 0.0), (a_float(c[2]) if len(c) > 2 else 0.0)
            if i >= 0:
                self.proyecto.pozos[i].x, self.proyecto.pozos[i].y = x, y
            else:
                self.proyecto.nuevo_pozo(c[0], x, y)
        self._tras_cambio()

    def exportar_cabecera(self):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export wells header"), "", tr("Text delimited files (*.*)"))
        if ruta:
            Path(ruta).write_text("#WELLNAME, X-COORD, Y-COORD\n" + "".join(
                f"{p.nombre}, {p.x:g}, {p.y:g}\n" for p in self.proyecto.pozos), encoding="utf-8")

    # ================================================================ zonas/plantillas
    def importar_zonas(self):
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Import well tops"), "", tr("Text delimited files (*.*)"))
        if not ruta:
            return
        pozos, zonas = leer_zonas(leer_lineas(ruta))
        pr = self.proyecto
        for z in zonas:
            existente = next((x for x in pr.zonas if x.nombre == z.nombre), None) or pr.nueva_zona(z.nombre)
            for k, nombre in enumerate(pozos):
                i = pr.indice_pozo(nombre)
                if i >= 0:
                    existente.profundidades += [0.0] * (len(pr.pozos) - len(existente.profundidades))
                    existente.profundidades[i] = z.prof(k)
        self._tras_cambio()

    def exportar_zonas(self):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export well tops"), "", tr("Text delimited files (*.*)"))
        if ruta:
            Path(ruta).write_text("\n".join(lineas_zonas([p.nombre for p in self.proyecto.pozos],
                                                         self.proyecto.zonas)) + "\n", encoding="utf-8")

    def nueva_plantilla(self):
        nombre, ok = QInputDialog.getText(self, tr("Create New Template"), tr("Template Name"))
        if ok:
            if not nombre.strip():
                aviso(self, tr("Empty template name is not allowed."))
                return
            t = Plantilla(nombre=nombre.strip())
            t.nueva_curva(t.nueva_pista())
            self.proyecto.plantillas.append(t)
            self._tras_cambio()

    def importar_plantilla(self):
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Import Template File"), "",
                                              tr("Template (*.kvplantilla)") + ";;" + tr("All (*.*)"))
        if ruta:
            from ..nucleo.comun import UID
            t = Plantilla.abrir(ruta)
            t.uid = UID.nuevo()                 # puede venir de otro proyecto con el mismo número
            self.proyecto.plantillas.append(t)
            self._tras_cambio()

    def exportar_plantilla(self, i):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export Template File"), "", tr("Template (*.kvplantilla)"))
        if ruta:
            if not ruta.endswith(".kvplantilla"):
                ruta += ".kvplantilla"
            self.proyecto.plantillas[i].guardar(ruta)

    # ================================================================ completación/litología
    def _nuevo_paquete(self, i):
        nombre, ok = QInputDialog.getText(self, tr("Create New Completion Package"), tr("Name"))
        if ok and nombre.strip():
            self.proyecto.pozos[i].completaciones.append(Completacion(nombre.strip()))
            self._tras_cambio()

    def importar_comp(self, i):
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Import Completion Package"), "", tr("Text delimited files (*.*)"))
        if ruta:
            self.proyecto.pozos[i].completaciones.append(Completacion.abrir(ruta))
            self._tras_cambio()

    def exportar_comp(self, i, j):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export Completion tops"), "", tr("Text delimited files (*.*)"))
        if ruta:
            self.proyecto.pozos[i].completaciones[j].guardar(ruta, self.proyecto.pozos[i].nombre)

    def _nueva_lito(self, i):
        nombre, ok = QInputDialog.getText(self, tr("Create New Lithology Interpretation"), tr("Name"))
        if ok and nombre.strip():
            self.proyecto.pozos[i].litologias.append(Litologia(nombre.strip()))
            self._tras_cambio()

    def importar_lito(self, i):
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Import Lithology Interpretation"), "",
                                              "*.txt;;" + tr("All (*.*)"))
        if ruta:
            self.proyecto.pozos[i].litologias.append(Litologia.abrir(ruta))
            self._tras_cambio()

    def exportar_lito(self, i, j):
        ruta, _ = QFileDialog.getSaveFileName(self, tr("Export Lithology Log"), "", "*.txt")
        if ruta:
            self.proyecto.pozos[i].litologias[j].guardar(ruta)

    # ================================================================ Maintenance
    def deshacer(self):
        """Ctrl+Z: último cambio del registro seleccionado; si es parte de una operación de varios
        pozos, la deshace entera. Sin nada que deshacer en el registro, la última operación
        compuesta del proyecto."""
        from ..nucleo.historial_proyecto import ErrorOperacion
        hp = self.proyecto.historial_ops
        reg = self.registro_seleccionado(avisar=False)
        try:
            if reg is not None and reg.historial.deshacer:
                return self._tras_deshacer(hp.deshacer_en(reg))
            op = hp.ultima()
            if op is not None:
                hp.deshacer(op)
                return self._tras_deshacer((op.descripcion, op))
        except ErrorOperacion as e:
            aviso(self, tr("This operation cannot be undone at once: these logs were edited afterwards: {0}. "
                           "Undo their later changes first.").format(e))
        return None

    def rehacer(self):
        from ..nucleo.historial_proyecto import ErrorOperacion
        hp = self.proyecto.historial_ops
        reg = self.registro_seleccionado(avisar=False)
        try:
            if reg is not None and reg.historial.rehacer:
                return self._tras_deshacer(hp.rehacer_en(reg), True)
            op = hp.ultima(deshecha=True)
            if op is not None:
                hp.rehacer(op)
                return self._tras_deshacer((op.descripcion, op), True)
        except ErrorOperacion as e:
            aviso(self, tr("This operation cannot be redone at once: these logs changed afterwards: {0}.").format(e))
        return None

    def banderas_qc(self):
        if not self.preparar_curva():
            return None
        modulo = next((m for m in self.modulos if m.nombre == "Quality Control"), None)
        return modulo.bandera(self) if modulo is not None else None

    def _hay_logs(self) -> bool:
        if not any(p.logs for p in self.proyecto.pozos):
            aviso(self, tr("The project has no logs. Import LAS files first."))
            return False
        return True

    def lote(self):
        if self._hay_logs():
            from .multipozo_ui import DialogoLote
            DialogoLote(self).exec()

    def normalizar_pozos(self):
        if self._hay_logs():
            from .multipozo_ui import DialogoNormalizacion
            DialogoNormalizacion(self).exec()

    def desfase_automatico(self):
        if self._hay_logs():
            from .multipozo_ui import DialogoDesfaseAuto
            DialogoDesfaseAuto(self).exec()

    def deep_learning(self):
        if self._hay_logs():
            modulo = next((m for m in self.modulos if m.nombre == "Deep Learning"), None)
            if modulo is not None:
                return modulo.abrir(self)
        return None

    def reporte_qc(self):
        if self._hay_logs():
            from ..modulos.control_calidad import DialogoReporteQC
            DialogoReporteQC(self, self.seleccion.registro()).exec()

    def importar_dlis_dialogo(self):
        return self.importar_dlis(None)

    def importar_dlis(self, i_pozo: int | None = None, ruta: str | None = None) -> list:
        """Cada frame del DLIS entra como un registro del pozo (el del archivo, o el elegido)."""
        from ..nucleo import intercambio
        if not intercambio.dlis_disponible():
            aviso(self, tr("DLIS support needs the 'dlisio' package (pip install dlisio)."))
            return []
        if ruta is None:
            ruta, _ = QFileDialog.getOpenFileName(self, tr("Import DLIS File"), "",
                                                  "DLIS (*.dlis *.DLIS);;" + tr("All (*.*)"))
        if not ruta:
            return []
        try:
            frames = intercambio.leer_dlis(ruta)
        except Exception as e:  # noqa: BLE001 - dlisio lanza varios tipos según el daño del archivo
            aviso(self, tr("Unable to read DLIS file: {0}").format(e))
            return []
        nuevos = []
        for fr in frames:
            reg = fr.registro
            i = i_pozo
            if i is None:
                nombre = reg.nombre_pozo.strip() or Path(ruta).stem
                i = self.proyecto.indice_pozo(nombre)
                if i < 0:
                    self.proyecto.nuevo_pozo(nombre)
                    i = len(self.proyecto.pozos) - 1
            pozo = self.proyecto.pozos[i]
            if any(r.nombre == reg.nombre for r in pozo.logs):
                reg.nombre = self.proyecto.nombre_libre(reg.nombre + "-", (r.nombre for r in pozo.logs))
            reg.historial.anotar("Import DLIS", ", ".join(reg.nombres()),
                                 f"{Path(ruta).name} file {fr.archivo_logico} frame {fr.frame}"
                                 + (f"; skipped array channels: {', '.join(fr.omitidos)}" if fr.omitidos else ""))
            self._unidad_prof_por_defecto(reg)
            pozo.logs.append(reg)
            nuevos.append(reg)
            if fr.omitidos:
                self.registrar(tr("{0}: array channels skipped: {1}").format(reg.nombre, ", ".join(fr.omitidos)))
        self.registrar(tr("DLIS {0}: {1} frame(s) imported").format(Path(ruta).name, len(nuevos)))
        self._plantilla_inicial()
        self._tras_cambio()
        return nuevos

    def exportar_csv(self, i_pozo: int | None = None, i_log: int | None = None, ruta: str | None = None):
        from ..nucleo import intercambio
        if i_pozo is None:
            reg = self.registro_seleccionado()
            if reg is None:
                return None
        else:
            reg = self.proyecto.pozos[i_pozo].logs[i_log]
        if ruta is None:
            ruta, _ = QFileDialog.getSaveFileName(self, tr("Export CSV"), reg.nombre + ".csv", "CSV (*.csv)")
        if ruta:
            intercambio.exportar_csv(reg, ruta)
            reg.historial.anotar("Export CSV", ", ".join(reg.nombres()), Path(ruta).name)
            self.registrar(tr("{0} exported to {1}").format(reg.nombre, ruta))
        return ruta

    def exportar_excel(self, i_pozo: int | None = None, ruta: str | None = None):
        """Todos los registros del pozo indicado o, sin pozo, de todo el proyecto."""
        from ..nucleo import intercambio
        pozos = self.proyecto.pozos if i_pozo is None else [self.proyecto.pozos[i_pozo]]
        regs = [(p.nombre, r) for p in pozos for r in p.logs]
        if not regs:
            aviso(self, tr("There are no logs to export."))
            return None
        if ruta is None:
            ruta, _ = QFileDialog.getSaveFileName(self, tr("Export Excel"), "logs.xlsx", "Excel (*.xlsx)")
        if ruta:
            try:
                intercambio.exportar_excel(regs, ruta)
            except (OSError, ImportError) as e:
                aviso(self, tr("Unable to export: {0}").format(e))
                return None
            for _, r in regs:
                r.historial.anotar("Export Excel", "", Path(ruta).name)
            self.registrar(tr("{0} log(s) exported to {1}").format(len(regs), ruta))
        return ruta

    # ================================================================ Advance
    def _registro_activo(self):
        return self.registro_seleccionado()

    def log_parcial(self):
        """Registro parcial: filas inicio–fin en un LAS nuevo."""
        reg, pozo = self.registro_seleccionado(), self.seleccion.objeto_pozo()
        if reg is None:
            return
        v = pedir("Create Partial Log", [Campo("ini", "Row start", "int", 1, minimo=1, maximo=reg.n_filas),
                                         Campo("fin", "Row end", "int", reg.n_filas, minimo=1, maximo=reg.n_filas),
                                         Campo("nombre", "Name", "texto", reg.nombre + " (partial)")], self)
        if v is None:
            return
        try:
            pozo.logs.append(operaciones.log_parcial(reg, v["ini"], v["fin"], v["nombre"]))
        except ValueError as e:
            aviso(self, str(e))
            return
        self._tras_cambio()

    def calculadora(self):
        """Advance Calculator: fórmula con X1..Xn sobre columnas del LAS activo."""
        reg = self.registro_seleccionado()
        if reg is None:
            return
        self.editor_logs.seguir_seleccion()
        dlg = DialogoCalculadora(reg, self)
        if dlg.exec() == QDialog.Accepted and dlg.resultado is not None:
            from ..modulos.base import agregar_resultado
            agregar_resultado(self, dlg.nombre, dlg.resultado)

    def combinar_las(self):
        """Combinar: une dos LAS del pozo por la profundidad MD."""
        pozo = self.seleccion.objeto_pozo()
        if pozo is None or len(pozo.logs) < 2:
            aviso(self, tr("The well needs at least two logs."))
            return
        nombres = [r.nombre for r in pozo.logs]
        v = pedir("Combine Las Files", [Campo("a", "Las 1", "opcion", nombres[0], nombres),
                                        Campo("b", "Las 2", "opcion", nombres[1], nombres),
                                        Campo("nombre", "Result name", "texto", "Merged")], self)
        if v is None:
            return
        a, b = pozo.logs[nombres.index(v["a"])], pozo.logs[nombres.index(v["b"])]
        try:
            pozo.logs.append(operaciones.combinar(a, b, v["nombre"]))
        except ValueError as e:
            aviso(self, str(e))
            return
        self._tras_cambio()

    def componer_pozo(self):
        """Composite Well Log (D110): un registro con todas las curvas de los registros del pozo
        seleccionado o de todos los pozos; los registros originales quedan como estaban."""
        pozo = self.seleccion.objeto_pozo()
        varios = [p for p in self.proyecto.pozos if len(p.logs) >= 2]
        if not varios:
            aviso(self, tr("The well needs at least two logs."))
            return
        alcance = [tr("Selected well"), tr("All wells with two or more logs")]
        v = pedir("Composite Well Log", [
            Campo("alcance", "Wells", "opcion", alcance[0] if pozo is not None and len(pozo.logs) >= 2 else alcance[1],
                  alcance),
            Campo("nombre", "Result name", "texto", "Composite"),
            Campo("paso", "Depth step (0 = finest of the logs)", "float", 0.0, minimo=0.0, maximo=1000.0, decimales=4)],
            self)
        if v is None:
            return
        pozos = varios if v["alcance"] == alcance[1] else [pozo] if pozo is not None else []
        hechos, fallos = 0, []
        for p in pozos:
            try:
                p.logs.append(operaciones.componer(p.logs, v["nombre"], v["paso"] or None))
                hechos += 1
            except ValueError as e:
                fallos.append(f"{p.nombre}: {tr(str(e))}")
        if fallos:
            aviso(self, "\n".join(fallos))
        if hechos:
            self.registrar(tr("Composite log created in {0} well(s).").format(hechos))
            self._tras_cambio()

    def agrupacion_logs(self):
        """Log Grouping: edita grupos y alias de la base de alias."""
        texto = "\n".join(f"{g.nombre}: {', '.join(g.alias)}" for g in self.alias.grupos)
        nuevo, ok = QInputDialog.getMultiLineText(self, tr("Log Grouping"), tr("GROUP: alias1, alias2, ..."), texto)
        if not ok:
            return
        grupos = []
        for linea in nuevo.splitlines():
            if ":" in linea:
                g, resto = linea.split(":", 1)
                grupos.append(bases.GrupoAlias(g.strip(), alias=[a.strip() for a in resto.split(",") if a.strip()]))
        self.alias.grupos = grupos
        qc.invalidar()
        self.ajustes.setValue("alias", self.alias.a_texto())       # se recuerdan para las próximas sesiones

    def gestor_modulos(self):
        d = QDialog(self)
        d.setWindowTitle(tr("Plugin Manager"))
        lista = QListWidget()
        for m in self.modulos:
            lista.addItem(f"{tr(m.nombre)} — {tr(m.descripcion)}")
        b = caja_botones(QDialogButtonBox.Close)
        b.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(lista)
        lay.addWidget(b)
        d.resize(600, 300)
        d.exec()

    # ================================================================ preferencias e idioma
    def preferencias_usuario(self):
        from .preferencias_ui import DialogoPreferencias
        pr = self.proyecto
        d = DialogoPreferencias(self, self.prefs, preferencias.PreferenciasQC.desde_json(pr.qc_ajustes),
                                Path(pr.ruta).name if pr.ruta else "")
        if d.exec() != QDialog.Accepted:
            return None
        nuevas = d.resultado()
        cambia_idioma = nuevas.idioma != self.prefs.idioma or nuevas.tema != self.prefs.tema
        self.prefs = nuevas
        guardar_preferencias(nuevas)
        qc_proyecto = d.resultado_proyecto() if hasattr(d, "resultado_proyecto") else None
        texto_qc = qc_proyecto.a_json() if qc_proyecto is not None else ""
        if texto_qc != pr.qc_ajustes:
            pr.qc_ajustes = texto_qc
            pr.modificado = True
            self._titulo()
        self._clave_qc = None
        self.sincronizar_qc_proyecto()
        self.registrar(tr("User settings saved"))
        if cambia_idioma:
            aplicar_idioma(nuevas.idioma)
            return self.reiniciar_interfaz()
        self.refrescar_todo()
        return self

    def reiniciar_interfaz(self):
        """Aplica el idioma en caliente: crea una ventana nueva con el mismo proyecto, la misma
        selección y la misma disposición de paneles, y cierra esta."""
        self.guardar_disposicion()
        nueva = VentanaPrincipal()
        nueva.proyecto = self.proyecto
        nueva.alias, nueva.base_lito, nueva.base_herr = self.alias, self.base_lito, self.base_herr
        nueva.diagnostico = self.diagnostico
        s = self.seleccion
        nueva.refrescar_todo()
        nueva.seleccion.fijar(pozo=s.pozo, log=s.log, curva=s.curva, zona=s.zona)
        nueva.pestanas.setCurrentIndex(self.pestanas.currentIndex())
        nueva.ribbon.setCurrentIndex(self.ribbon.currentIndex())
        nueva.setGeometry(self.geometry())
        nueva.show()
        _VIVAS[:] = [nueva]
        self.proyecto = Proyecto()          # para que no pregunte si se guarda al cerrar esta
        self.close()
        return nueva

    # ================================================================ ayuda / impresión
    def imprimir(self):
        from PySide6.QtGui import QPainter
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        plot = self.pagina_logplot.plot_actual()
        if plot is None:
            return
        if not hasattr(self, "impresora"):
            self.impresora = QPrinter(QPrinter.HighResolution)
        impresora = self.impresora
        if QPrintDialog(impresora, self).exec() != QDialog.Accepted:
            return
        img = plot.imagen()
        p = QPainter(impresora)
        r = p.viewport()
        tam = img.size().scaled(r.size(), Qt.KeepAspectRatio)
        p.setViewport(r.x(), r.y(), tam.width(), tam.height())
        p.setWindow(img.rect())
        p.drawImage(0, 0, img)
        p.end()

    def ver_diagnostico(self):
        d = QDialog(self)
        d.setWindowTitle(tr("Diagnostic Log"))
        t = QPlainTextEdit("\n".join(self.diagnostico) or tr("(empty)"))
        t.setReadOnly(True)
        QVBoxLayout(d).addWidget(t)
        d.resize(600, 400)
        d.exec()

    def ayuda(self, mostrar: bool = True):
        """How To: el flujo de mantenimiento paso a paso, en el idioma de la interfaz."""
        d = QDialog(self)
        d.setWindowTitle(tr("How To"))
        t = QTextBrowser()
        t.setOpenExternalLinks(False)
        t.setHtml(tr_ayuda("howto"))
        b = caja_botones(QDialogButtonBox.Close)
        b.rejected.connect(d.reject)
        lay = QVBoxLayout(d)
        lay.addWidget(t)
        lay.addWidget(b)
        d.resize(760, 680)
        self._ventanas.append(d)
        if mostrar:
            d.show()
        return d

    def configurar_impresion(self):
        from PySide6.QtPrintSupport import QPageSetupDialog, QPrinter
        if not hasattr(self, "impresora"):
            self.impresora = QPrinter(QPrinter.HighResolution)
        QPageSetupDialog(self.impresora, self).exec()

    def acerca(self):
        QMessageBox.about(self, tr("About"), f"<b>{TITULO}</b> {__version__}<br>" + tr(
            "Well log curve maintenance: editing with undo and change log, LAS validation, resampling, units, "
            "mnemonics, batch operations, multi-well normalization, depth shift, quality control and deep "
            "learning.<br><br>Non-commercial software (PolyForm Noncommercial 1.0.0)."))


class DialogoCalculadora(QDialog):
    def __init__(self, reg, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Advance Calculator"))
        self.reg = reg
        self.resultado = None
        self.nombre = ""
        self.texto = QPlainTextEdit("X1 * 1")
        self.cols = QListWidget()
        self.cols.addItems(reg.nombres())
        self.cols.setSelectionMode(QListWidget.MultiSelection)
        from PySide6.QtWidgets import QLineEdit
        from .dialogos import boton
        self.txt_nombre = QLineEdit("CALC")
        b_abrir = boton("Load formula...", "open", "", self._abrir)
        botones = caja_botones(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self._ejecutar)
        botones.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Formula (Var := expr; ...; result). X1..Xn = selected columns in order:")))
        lay.addWidget(self.texto)
        lay.addWidget(b_abrir)
        lay.addWidget(QLabel(tr("Columns (X1, X2, ... in selection order)")))
        lay.addWidget(self.cols)
        lay.addWidget(QLabel(tr("Result column")))
        lay.addWidget(self.txt_nombre)
        lay.addWidget(botones)
        self.orden: list[int] = []
        self.cols.itemSelectionChanged.connect(self._orden)

    def _orden(self):
        sel = {self.cols.row(i) for i in self.cols.selectedItems()}
        self.orden = [i for i in self.orden if i in sel] + [i for i in sorted(sel) if i not in self.orden]

    def _abrir(self):
        ruta, _ = QFileDialog.getOpenFileName(self, tr("Formula"), "", tr("Formula (*.formula)") + ";;" + tr("All (*.*)"))
        if ruta:
            self.texto.setPlainText("\n".join(leer_lineas(ruta)))

    def _ejecutar(self):
        texto = self.texto.toPlainText()
        try:
            variables = formula.variables_entrada(texto)
            if len(variables) > len(self.orden):
                raise formula.ErrorFormula(tr("Select {0} column(s) for {1}").format(len(variables),
                                                                                    ", ".join(variables)))
            entradas = {f"X{k + 1}": self.reg.columnas[c].datos for k, c in enumerate(self.orden)}
            if not entradas:
                entradas = {"X1": np.zeros(self.reg.n_filas)}
            self.resultado = formula.evaluar(texto, entradas)
        except formula.ErrorFormula as e:
            aviso(self, str(e))
            return
        self.nombre = self.txt_nombre.text().strip() or "CALC"
        self.accept()
