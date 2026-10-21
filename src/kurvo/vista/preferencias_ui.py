"""Diálogo "User Settings": idioma, nulos, umbrales de QC, rangos físicos y opciones por defecto
de deep learning (ver D60–D64). Se guarda en QSettings; el idioma se aplica en caliente."""
from __future__ import annotations

import copy

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QGroupBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..i18n import IDIOMAS, tr
from ..nucleo import preferencias
from ..nucleo.comun import NULO, a_float
from . import iconos
from .dialogos import boton, caja_botones

ARQUITECTURAS = {"unet": "1D U-Net (convolutional)", "bigru": "Bidirectional GRU (recurrent)"}


def _doble(v, lo, hi, dec=3, paso=None):
    w = QDoubleSpinBox()
    w.setDecimals(dec)
    w.setRange(lo, hi)
    w.setValue(v)
    if paso:
        w.setSingleStep(paso)
    return w


def _entero(v, lo, hi, paso=1):
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setValue(v)
    w.setSingleStep(paso)
    return w


class DialogoPreferencias(QDialog):
    def __init__(self, parent, prefs: preferencias.Preferencias, qc_proyecto: preferencias.PreferenciasQC | None = None,
                 nombre_proyecto: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("User Settings"))
        self.setWindowIcon(iconos.icono("settings"))
        self.prefs = copy.deepcopy(prefs)
        # umbrales y rangos: los del usuario y, si el proyecto tiene los suyos, los del proyecto (D87)
        self._qc_usuario = preferencias.PreferenciasQC.de(self.prefs)
        self._qc_proyecto = copy.deepcopy(qc_proyecto)
        self._nombre_proyecto = nombre_proyecto or tr("(unsaved)")
        self._mostrando = "project" if qc_proyecto is not None else "user"
        self.tabs = QTabWidget()
        self.tabs.addTab(self._general(), iconos.icono("settings"), tr("General"))
        self.tabs.addTab(self._qc(), iconos.icono("qc_window"), tr("QC thresholds"))
        self.tabs.addTab(self._rangos(), iconos.icono("clip"), tr("Physical ranges"))
        self.tabs.addTab(self._dl(), iconos.icono("deep_learning"), tr("Deep learning"))
        b_def = boton("Restore Defaults", "restore_original", "Put every setting back to its default value",
                      self.restaurar)
        botones = caja_botones(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        fila = QHBoxLayout()
        fila.addWidget(b_def)
        fila.addStretch(1)
        fila.addWidget(botones)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addLayout(fila)
        self.resize(660, 580)
        self.cargar(self.prefs)
        if self._mostrando == "project":
            self._poner_qc(self._qc_proyecto)
        self._origen()

    # ---------------------------------------------------------------- pestañas
    def _general(self):
        w = QWidget()
        self.ch_idioma = QComboBox()
        for codigo, nombre in IDIOMAS.items():
            self.ch_idioma.addItem(nombre, codigo)
        self.txt_nulos = QLineEdit()
        self.txt_nulos.setPlaceholderText("-9999, -999")
        form = QFormLayout(w)
        form.addRow(tr("Language / Idioma"), self.ch_idioma)
        nota = QLabel(tr("The interface is rebuilt in the new language when you press OK. Curve mnemonics, "
                         "units and file names are never translated."))
        nota.setWordWrap(True)
        nota.setStyleSheet("color: #667;")
        form.addRow("", nota)
        self.ch_tema = QComboBox()
        for codigo, nombre in (("light", "Light"), ("dark", "Dark")):
            self.ch_tema.addItem(tr(nombre), codigo)
        self.ch_tema.setToolTip(tr("Theme of the window, panels and QC plots. The Log Plot, the cross section and the "
                                   "QC report stay on a white background."))
        form.addRow(tr("Theme"), self.ch_tema)
        self.ch_unidad = QComboBox()
        for codigo, nombre in (("M", "Metres (m)"), ("FT", "Feet (ft)")):
            self.ch_unidad.addItem(tr(nombre), codigo)
        self.ch_unidad.setToolTip(tr("Unit given to the depth columns of imported files that have none; shown on "
                                     "the depth axis of the log plots."))
        form.addRow(tr("Default depth unit"), self.ch_unidad)
        form.addRow(tr("Internal null value"), QLabel(f"{NULO:g}"))
        form.addRow(tr("Also treat as null on import"), self.txt_nulos)
        nota2 = QLabel(tr("Comma-separated values converted to the null value when a LAS file is imported "
                          "(the NULL of the file header is always converted)."))
        nota2.setWordWrap(True)
        nota2.setStyleSheet("color: #667;")
        form.addRow("", nota2)
        self.ck_plantilla = QCheckBox(tr("Add new curves to the log plot templates"))
        self.ck_plantilla.setToolTip(tr("Curves created by the tools (_FILL, _NORM, _DL, _QC, calculator...) are added "
                                        "to the templates: next to their source curve with a dashed line, flags in a "
                                        "QC track. Undo removes them again."))
        form.addRow(tr("Templates"), self.ck_plantilla)
        return w

    def _qc(self):
        w = QWidget()
        u = preferencias.UmbralesQC()
        self.sp_qc = {
            "nulos_aviso": _doble(u.nulos_aviso, 0, 100, 1),
            "nulos_malo": _doble(u.nulos_malo, 0, 100, 1),
            "fuera_malo": _doble(u.fuera_malo, 0, 100, 2),
            "saturacion": _doble(u.saturacion, 0, 100, 2),
            "minimo_plano": _entero(u.minimo_plano, 2, 10000),
            "ventana_picos": _entero(u.ventana_picos, 3, 501, 2),
            "sigma_picos": _doble(u.sigma_picos, 0.5, 50, 2, 0.5),
            "derrumbe": _doble(u.derrumbe, 0, 20, 2, 0.25),
            "drho": _doble(u.drho, 0, 2, 3, 0.01),
            "picos_por_mil": _doble(u.picos_por_mil, 0, 1000, 2, 0.5),
            "calibre_cerrado": _doble(u.calibre_cerrado, 0, 20, 2, 0.25),
        }
        etiquetas = {"nulos_aviso": "Null % for a warning (grade B)", "nulos_malo": "Null % for grade C",
                     "fuera_malo": "Out-of-range % for grade C", "saturacion": "Clipped % for a warning",
                     "minimo_plano": "Flat run: equal samples in a row", "ventana_picos": "Spike window (samples)",
                     "sigma_picos": "Spike threshold (robust sigmas)", "derrumbe": "Washout: CALI − BS (in)",
                     "drho": "|DRHO| limit (g/cc)", "picos_por_mil": "Spikes per 1000 samples still grade A",
                     "calibre_cerrado": "Caliper closed or in casing below (in)"}
        g = QGroupBox(tr("Source of the QC thresholds and physical ranges"))
        self.lbl_origen = QLabel()
        self.lbl_origen.setWordWrap(True)
        self.ck_proyecto = QCheckBox(tr("Store them in this project (they override the user settings)"))
        self.ck_proyecto.setChecked(self._mostrando == "project")
        self.ck_proyecto.toggled.connect(self._al_proyecto)
        b_up = boton("User → project", "export", "Copy the user thresholds and ranges into the project",
                     self.usuario_a_proyecto)
        b_pu = boton("Project → user", "import", "Copy the project thresholds and ranges into the user settings",
                     self.proyecto_a_usuario)
        self.b_pu = b_pu
        fila = QHBoxLayout()
        fila.addWidget(b_up)
        fila.addWidget(b_pu)
        fila.addStretch(1)
        lg = QVBoxLayout(g)
        lg.addWidget(self.lbl_origen)
        lg.addWidget(self.ck_proyecto)
        lg.addLayout(fila)
        lay = QVBoxLayout(w)
        lay.addWidget(g)
        form = QFormLayout()
        for k, sp in self.sp_qc.items():
            form.addRow(tr(etiquetas[k]), sp)
        lay.addLayout(form)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- QC del usuario o del proyecto
    def _leer_qc(self) -> preferencias.PreferenciasQC:
        p = self.resultado(_solo_widgets=True)
        return preferencias.PreferenciasQC(p.qc, p.rangos)

    def _poner_qc(self, q: preferencias.PreferenciasQC) -> None:
        for k, sp in self.sp_qc.items():
            sp.setValue(getattr(q.qc, k))
        self.tabla_rangos.setRowCount(0)
        for g, filas in q.rangos.items():
            for unidad, lo, hi in filas:
                self._fila_rango(g, unidad, lo, hi)

    def _guardar_vista(self) -> None:
        """Pasa lo que muestran los controles al juego que se está editando."""
        if self._mostrando == "project":
            self._qc_proyecto = self._leer_qc()
        else:
            self._qc_usuario = self._leer_qc()

    def _origen(self) -> None:
        if self._mostrando == "project":
            texto = tr("Editing the values stored in the project {0}. They are used for this project on any "
                       "computer; the user settings apply to other projects.").format(self._nombre_proyecto)
        else:
            texto = tr("Editing the user settings (this computer). The project has no values of its own.")
        self.lbl_origen.setText(texto)
        self.lbl_origen_rangos.setText(tr("Source: {0}").format(
            tr("project {0}").format(self._nombre_proyecto) if self._mostrando == "project" else tr("user settings")))
        self.b_pu.setEnabled(self._qc_proyecto is not None)

    def _al_proyecto(self, activo: bool) -> None:
        self._guardar_vista()
        if activo:
            if self._qc_proyecto is None:
                self._qc_proyecto = copy.deepcopy(self._qc_usuario)
            self._mostrando = "project"
            self._poner_qc(self._qc_proyecto)
        else:
            self._qc_proyecto = None
            self._mostrando = "user"
            self._poner_qc(self._qc_usuario)
        self._origen()

    def usuario_a_proyecto(self) -> None:
        self._guardar_vista()
        self._qc_proyecto = copy.deepcopy(self._qc_usuario)
        if self.ck_proyecto.isChecked():
            self._poner_qc(self._qc_proyecto)
            self._origen()
        else:
            self.ck_proyecto.setChecked(True)

    def proyecto_a_usuario(self) -> None:
        self._guardar_vista()
        if self._qc_proyecto is not None:
            self._qc_usuario = copy.deepcopy(self._qc_proyecto)
        self._origen()

    def resultado_proyecto(self) -> preferencias.PreferenciasQC | None:
        """Umbrales y rangos que se guardan en el proyecto (None = el proyecto usa los del usuario)."""
        if self._mostrando == "project":
            return self._leer_qc()
        return None

    def _rangos(self):
        w = QWidget()
        self.tabla_rangos = QTableWidget(0, 4)
        self.tabla_rangos.setHorizontalHeaderLabels([tr("Group / mnemonic"), tr("Unit"), tr("Minimum"), tr("Maximum")])
        self.tabla_rangos.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        b_add = boton("Add", "add", "Add a range", lambda: self._fila_rango("", "", 0.0, 1.0))
        b_del = boton("Delete", "delete", "Delete the selected ranges", self._borrar_rangos)
        fila = QHBoxLayout()
        fila.addWidget(b_add)
        fila.addWidget(b_del)
        fila.addStretch(1)
        nota = QLabel(tr("A range applies to the curves of that alias group (or mnemonic) whose unit matches. "
                         "Samples outside it are flagged by QC."))
        nota.setWordWrap(True)
        nota.setStyleSheet("color: #667;")
        self.lbl_origen_rangos = QLabel()
        self.lbl_origen_rangos.setStyleSheet("font-weight: bold;")
        lay = QVBoxLayout(w)
        lay.addWidget(self.lbl_origen_rangos)
        lay.addWidget(nota)
        lay.addWidget(self.tabla_rangos, 1)
        lay.addLayout(fila)
        return w

    def _dl(self):
        w = QWidget()
        d = preferencias.OpcionesDL()
        self.ch_arq = QComboBox()
        for k, v in ARQUITECTURAS.items():
            self.ch_arq.addItem(tr(v), k)
        self.sp_dl = {"largo": _entero(d.largo, 32, 2048, 32), "epocas": _entero(d.epocas, 1, 2000),
                      "lote": _entero(d.lote, 2, 1024), "lr": _doble(d.lr, 1e-5, 1.0, 5, 1e-4),
                      "muestras_mc": _entero(d.muestras_mc, 1, 200)}
        self.ck_cpu = QCheckBox(tr("Force CPU"))
        self.ck_excluir = QCheckBox(tr("Exclude QC-flagged samples from training"))
        form = QFormLayout(w)
        form.addRow(tr("Network"), self.ch_arq)
        for k, t in (("largo", "Window (samples)"), ("epocas", "Max epochs"), ("lote", "Batch size"),
                     ("lr", "Learning rate"), ("muestras_mc", "MC dropout passes (uncertainty)")):
            form.addRow(tr(t), self.sp_dl[k])
        form.addRow("", self.ck_cpu)
        form.addRow("", self.ck_excluir)
        return w

    # ---------------------------------------------------------------- datos
    def _fila_rango(self, grupo, unidad, lo, hi):
        i = self.tabla_rangos.rowCount()
        self.tabla_rangos.insertRow(i)
        for j, v in enumerate((grupo, unidad, f"{lo:g}", f"{hi:g}")):
            self.tabla_rangos.setItem(i, j, QTableWidgetItem(v))

    def _borrar_rangos(self):
        for f in sorted({i.row() for i in self.tabla_rangos.selectedIndexes()}, reverse=True):
            self.tabla_rangos.removeRow(f)

    def cargar(self, p: preferencias.Preferencias):
        self.ch_idioma.setCurrentIndex(max(0, self.ch_idioma.findData(p.idioma)))
        self.txt_nulos.setText(", ".join(f"{x:g}" for x in p.nulos_extra))
        self.ck_plantilla.setChecked(p.plantilla_auto)
        self.ch_tema.setCurrentIndex(max(0, self.ch_tema.findData(p.tema)))
        self.ch_unidad.setCurrentIndex(max(0, self.ch_unidad.findData(p.unidad_prof)))
        for k, sp in self.sp_qc.items():
            sp.setValue(getattr(p.qc, k))
        self.tabla_rangos.setRowCount(0)
        for g, filas in p.rangos.items():
            for unidad, lo, hi in filas:
                self._fila_rango(g, unidad, lo, hi)
        self.ch_arq.setCurrentIndex(max(0, self.ch_arq.findData(p.dl.arquitectura)))
        for k, sp in self.sp_dl.items():
            sp.setValue(getattr(p.dl, k))
        self.ck_cpu.setChecked(p.dl.forzar_cpu)
        self.ck_excluir.setChecked(p.dl.excluir_qc)

    def restaurar(self):
        idioma = self.ch_idioma.currentData()
        self.cargar(preferencias.Preferencias(idioma=idioma))

    def resultado(self, _solo_widgets: bool = False) -> preferencias.Preferencias:
        """Preferencias del usuario. Si se está editando el QC del proyecto, sus umbrales y rangos
        son los del usuario guardados aparte (los del proyecto salen en `resultado_proyecto`)."""
        p = preferencias.Preferencias()
        p.idioma = self.ch_idioma.currentData()
        p.nulos_extra = [a_float(x, None) for x in self.txt_nulos.text().replace(";", ",").split(",") if x.strip()]
        p.nulos_extra = [x for x in p.nulos_extra if x is not None]
        p.plantilla_auto = self.ck_plantilla.isChecked()
        p.tema = self.ch_tema.currentData()
        p.unidad_prof = self.ch_unidad.currentData()
        for k, sp in self.sp_qc.items():
            setattr(p.qc, k, sp.value())
        rangos: dict[str, list] = {}
        for i in range(self.tabla_rangos.rowCount()):
            celdas = [self.tabla_rangos.item(i, j).text().strip() if self.tabla_rangos.item(i, j) else ""
                      for j in range(4)]
            if not celdas[0]:
                continue
            lo, hi = a_float(celdas[2], None), a_float(celdas[3], None)
            if lo is None or hi is None or hi <= lo:
                continue
            rangos.setdefault(celdas[0].upper(), []).append((celdas[1].upper(), lo, hi))
        p.rangos = rangos
        p.dl.arquitectura = self.ch_arq.currentData()
        for k, sp in self.sp_dl.items():
            setattr(p.dl, k, sp.value())
        p.dl.forzar_cpu = self.ck_cpu.isChecked()
        p.dl.excluir_qc = self.ck_excluir.isChecked()
        if not _solo_widgets and self._mostrando == "project":
            p.qc, p.rangos = copy.deepcopy(self._qc_usuario.qc), copy.deepcopy(self._qc_usuario.rangos)
        return p
