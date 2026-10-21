"""Módulo "Quality Control": reporte de QC, columna de bandera y comparación entre pozos
(lógica en nucleo/qc.py; reporte en vista/reporte_qc.py; panel interactivo en vista/qc_ui.py).
Desde v0.3 sus entradas son acciones del registro único (Quality Control, Add QC Flags, QC Report)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QListWidget, QListWidgetItem, QVBoxLayout)

from ..i18n import tr
from ..nucleo import qc
from ..vista.dialogos import aviso, caja_botones
from .base import Modulo, contexto


def informes_de(app, objetivos):
    """`objetivos`: lista de (i_pozo, registro) → lista de (InformeRegistro, registro)."""
    pr = app.proyecto
    return [(qc.informe(r, pr.pozos[i].nombre, qc.zonas_de_pozo(pr, i), app.alias), r) for i, r in objetivos]


class DialogoReporteQC(QDialog):
    def __init__(self, app, preseleccion=None):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(tr("QC Report"))
        self.lista = QListWidget()
        for i, p in enumerate(app.proyecto.pozos):
            for r in p.logs:
                it = QListWidgetItem(f"{p.nombre} / {r.nombre}")
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if preseleccion is None or r is preseleccion else Qt.Unchecked)
                it.setData(Qt.UserRole, (i, r))
                self.lista.addItem(it)
        self.ch_formato = QComboBox()
        self.ch_formato.addItems(["HTML (.html)", "PDF (.pdf)"])
        form = QFormLayout()
        form.addRow(tr("Format"), self.ch_formato)
        b = caja_botones(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        b.accepted.connect(self.guardar)
        b.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lista)
        lay.addLayout(form)
        lay.addWidget(b)
        self.resize(460, 420)

    def objetivos(self):
        return [self.lista.item(k).data(Qt.UserRole) for k in range(self.lista.count())
                if self.lista.item(k).checkState() == Qt.Checked]

    def guardar(self, ruta: str | None = None):
        from ..vista import reporte_qc
        objetivos = self.objetivos()
        if not objetivos:
            aviso(self, tr("Select at least one log."))
            return None
        pdf = self.ch_formato.currentIndex() == 1
        if ruta is None:
            ruta, _ = QFileDialog.getSaveFileName(self, tr("Save QC Report"), "qc_report." + ("pdf" if pdf else "html"),
                                                  "PDF (*.pdf)" if pdf else "HTML (*.html)")
            if not ruta:
                return None
        informes = informes_de(self.app, objetivos)
        (reporte_qc.guardar_pdf if pdf else reporte_qc.guardar_html)(ruta, informes, self.app.alias)
        self.app.registrar(tr("QC report saved: {0}").format(ruta))
        self.accept()
        return ruta


class ControlCalidad(Modulo):
    nombre = "Quality Control"
    descripcion = "Curve QC report (HTML/PDF), QC flag column and multi-well histogram comparison"

    def acciones_editor_logs(self, app):
        return []           # están en el registro de acciones (qc_window, qc_flags, qc_report)

    def reporte(self, app, solo_activo=False):
        _, reg, _ = contexto(app)
        d = DialogoReporteQC(app, reg if solo_activo else None)
        d.exec()
        return d

    def bandera(self, app):
        _, reg, c = contexto(app)
        if reg is None or not reg.existe_columna(c):
            aviso(app, tr("Select a curve first: click its column in the Basic Log Editor or its node in the "
                          "project tree."))
            return
        nombre = reg.columnas[c].nombre + "_QC"
        datos = qc.bandera(reg, c, app.alias)

        def poner():
            i = reg.indice_columna(nombre)
            if i >= 0:
                reg.columnas[i].datos = datos
            else:
                reg.agregar_columna(nombre, datos, "", f"QC flag of {reg.columnas[c].nombre} (1 = doubtful)")
        app.editor_logs.editar("QC flag", f"{nombre}: {int(datos.sum())} doubtful sample(s)", poner)

    def comparar(self, app):
        """Comparación de la curva entre pozos: pestaña "Wells comparison" del panel de QC."""
        _, reg, c = contexto(app)
        if reg is None or not reg.existe_columna(c):
            aviso(app, tr("Select a curve first: click its column in the Basic Log Editor or its node in the "
                          "project tree."))
            return None
        app.seleccion.fijar(curva=reg.columnas[c].nombre)
        return app.ventana_qc("wells")
