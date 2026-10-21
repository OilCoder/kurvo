"""Diálogo "Validate LAS": lista de problemas del registro activo con corrección automática."""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from ..nucleo import historial, validacion
from ..i18n import tr
from .dialogos import BarraAplicar, boton

COLORES = {validacion.ERROR: QColor(200, 40, 40), validacion.AVISO: QColor(190, 120, 0),
           validacion.INFO: QColor(60, 90, 160)}
NOMBRES_CORRECCION = {
    "quitar_filas_sin_profundidad": "Delete rows without depth",
    "ordenar_por_profundidad": "Sort rows by depth",
    "quitar_duplicados": "Remove duplicated depths",
    "convertir_nulos": "Convert nulls to -999.25",
    "renombrar_duplicadas": "Rename duplicated curves",
    "actualizar_cabecera": "Update header (STRT/STOP/STEP/NULL/WELL)",
    "convertir_nulos_comunes": "Convert -999, -9999... to -999.25",
    "corregir_unidades": "Set the units the values indicate (no conversion)",
}


class DialogoValidacion(QDialog):
    def __init__(self, ed, reg):
        super().__init__(ed)
        self.ed, self.reg = ed, reg
        self.setWindowTitle(f"{tr('Validate LAS')} — {reg.nombre}")
        self.lbl = QLabel()
        self.tabla = QTableWidget(0, 3)
        self.tabla.setHorizontalHeaderLabels([tr("Level"), tr("Problem"), tr("Automatic fix")])
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        # la tabla es la vista previa; los arreglos son el "Apply" (patrón común, D55)
        self.b_uno = boton("Fix Selected", "fix", "Apply the automatic fix of the selected problems")
        self.b_todo = boton("Fix All", "fix_all", "Apply every automatic fix")
        self.barra = BarraAplicar(self)
        self.barra.layout().insertWidget(0, self.b_uno)
        self.barra.layout().insertWidget(1, self.b_todo)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl)
        lay.addWidget(self.tabla)
        lay.addWidget(self.barra)
        self.b_uno.clicked.connect(self.corregir_seleccion)
        self.b_todo.clicked.connect(self.corregir_todo)
        self.tabla.itemSelectionChanged.connect(self._botones)
        self.resize(820, 380)
        self.recargar()

    def recargar(self):
        self.problemas = validacion.validar(self.reg)
        self.tabla.setRowCount(len(self.problemas))
        for i, p in enumerate(self.problemas):
            celdas = (tr(p.nivel), p.mensaje, tr(NOMBRES_CORRECCION.get(p.correccion, "—")))
            for j, v in enumerate(celdas):
                it = QTableWidgetItem(v)
                if j == 0:
                    it.setForeground(COLORES[p.nivel])
                self.tabla.setItem(i, j, it)
        texto = validacion.resumen(self.problemas)
        self.lbl.setText((tr("✔ No problems found.") if not self.problemas else texto) +
                         "   ·   " + tr("{0} rows, {1} curves").format(self.reg.n_filas, self.reg.n_columnas))
        self._botones()

    def _botones(self):
        filas = {i.row() for i in self.tabla.selectedIndexes()}
        self.b_uno.setEnabled(any(self.problemas[f].correccion for f in filas))
        self.b_todo.setEnabled(any(p.correccion for p in self.problemas))

    def corregir_seleccion(self):
        filas = sorted({i.row() for i in self.tabla.selectedIndexes()})
        hechas = []
        for f in filas:
            p = self.problemas[f]
            if p.correccion and p.correccion not in hechas:
                historial.aplicar(self.reg, NOMBRES_CORRECCION[p.correccion], p.codigo,
                                  validacion.corregir, self.reg, p)
                hechas.append(p.correccion)
        self._fin()

    def corregir_todo(self):
        historial.aplicar(self.reg, "Fix all (validation)", "", validacion.corregir_todo, self.reg)
        self._fin()

    def _fin(self):
        self.ed.actualizar_tabla()
        self.recargar()
