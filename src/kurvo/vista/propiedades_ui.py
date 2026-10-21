"""Panel acoplable "Curve Properties" (v0.4, D86): la curva de la selección global con su nombre,
unidad, descripción, grupo de alias, nota de QC con sus avisos, origen (medida, editada o generada
y por qué operación), estadística y rango físico aplicado. Nombre, unidad y descripción se editan
con Apply y quedan en la bitácora (deshacibles). Botones a Before/After, Graphic Edit y QC."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QVBoxLayout, QWidget)

from ..i18n import tr
from ..nucleo import historial, qc
from .dialogos import aviso, boton

COLORES_NOTA = {"A": "#2e9e5b", "B": "#e07b00", "C": "#d23f3f"}


def _num(v) -> str:
    try:
        return "—" if v != v else f"{v:.4g}"
    except TypeError:
        return "—"


def creacion(reg, nombre: str):
    """Primer cambio de la bitácora que menciona la curva, si la creó (agregar, empalmar, DL...)."""
    for c in reg.historial.bitacora:
        if nombre in [x.strip() for x in c.columnas.split(",")]:
            return c
    return None


class PanelPropiedades(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.reg = None
        self.nombre = ""
        self.lbl_titulo = QLabel()
        self.lbl_titulo.setStyleSheet("font-weight: bold;")
        self.lbl_titulo.setWordWrap(True)
        self.txt_nombre, self.txt_unidad, self.txt_desc = QLineEdit(), QLineEdit(), QLineEdit()
        self.b_aplicar = boton("Apply", "apply", "Rename the curve or change its unit or description "
                               "(kept in the change log, can be undone)", self.aplicar)
        g_edit = QGroupBox(tr("Curve"))
        f = QFormLayout(g_edit)
        f.addRow(tr("Name"), self.txt_nombre)
        f.addRow(tr("Unit"), self.txt_unidad)
        f.addRow(tr("Description"), self.txt_desc)
        f.addRow("", self.b_aplicar)
        self.lbl = {k: QLabel() for k in ("grupo", "tipo", "nota", "avisos", "muestras", "nulos", "minmax",
                                          "media", "pct", "rango")}
        for w in self.lbl.values():
            w.setWordWrap(True)
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)
        g_info = QGroupBox(tr("Status"))
        fi = QFormLayout(g_info)
        # "etiquetas": nombre que la prueba de traducciones (tests/textos_ui.py) revisa
        etiquetas = (("grupo", "Alias group"), ("tipo", "Origin"), ("nota", "QC grade"), ("avisos", "QC warnings"))
        for k, t in etiquetas:
            fi.addRow(tr(t), self.lbl[k])
        g_est = QGroupBox(tr("Statistics"))
        fe = QFormLayout(g_est)
        etiquetas = (("muestras", "Samples (valid)"), ("nulos", "Nulls"), ("minmax", "Min / Max"),
                     ("media", "Mean / Std"), ("pct", "P10 / P50 / P90"), ("rango", "Physical range"))
        for k, t in etiquetas:
            fe.addRow(tr(t), self.lbl[k])
        self.b_antes = boton("Before/After", "before_after", "Original against the current curve (QC panel)",
                             lambda: self.app.ventana_qc("before_after"))
        self.b_grafica = boton("Graphic Edit", "graphic_edit", "Edit the curve on a depth plot",
                               lambda: self.app.acciones["graphic_edit"].trigger())
        self.b_qc = boton("QC", "qc_window", "Depth view of the curve with the doubtful samples (QC panel)",
                          lambda: self.app.ventana_qc("depth"))
        fila = QHBoxLayout()
        for b in (self.b_antes, self.b_grafica, self.b_qc):
            fila.addWidget(b)
        cuerpo = QWidget()
        lay = QVBoxLayout(cuerpo)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.lbl_titulo)
        lay.addWidget(g_edit)
        lay.addWidget(g_info)
        lay.addWidget(g_est)
        lay.addLayout(fila)
        lay.addStretch(1)
        area = QScrollArea()
        area.setWidget(cuerpo)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        QVBoxLayout(self).setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(area)
        self.refrescar()

    # ---------------------------------------------------------------- datos
    def refrescar(self) -> None:
        s = self.app.seleccion
        reg = s.registro()
        k = s.indice_curva()
        activo = reg is not None and k >= 0
        for w in (self.txt_nombre, self.txt_unidad, self.txt_desc, self.b_aplicar, self.b_antes, self.b_grafica,
                  self.b_qc):
            w.setEnabled(activo)
        if not activo:
            self.reg, self.nombre = None, ""
            self.lbl_titulo.setText(tr("Select a curve in the project tree, the Basic Log Editor or the QC panel."))
            for w in (self.txt_nombre, self.txt_unidad, self.txt_desc):
                w.clear()
            for w in self.lbl.values():
                w.setText("")
            return
        c = reg.columnas[k]
        self.reg, self.nombre = reg, c.nombre
        pozo = s.objeto_pozo()
        self.lbl_titulo.setText(f"{c.nombre}   ·   {pozo.nombre if pozo else ''} / {reg.nombre}")
        self.txt_nombre.setText(c.nombre)
        self.txt_unidad.setText(c.unidad)
        self.txt_desc.setText(c.descripcion)
        alias = self.app.alias
        g = alias.grupo_de(c.nombre) if alias is not None else -1
        self.lbl["grupo"].setText(alias.grupos[g].nombre if g >= 0 else tr("(none)"))
        self.lbl["tipo"].setText(self._origen(reg, c))
        estados = qc.notas(reg, alias)
        e = estados.get(c.nombre)
        if e is None:        # columna de profundidad
            self.lbl["nota"].setText(tr("depth column (not graded)"))
            self.lbl["avisos"].setText("")
            e = qc.evaluar_curva(c.datos, None, c.nombre, c.unidad, alias)
        else:
            color = COLORES_NOTA.get(e.nota, "#667")
            self.lbl["nota"].setText(f"<span style='color:white; background-color:{color}; font-weight:bold;'>"
                                     f"&nbsp;{e.nota}&nbsp;</span>")
            self.lbl["avisos"].setText("<br>".join(e.avisos) if e.avisos else tr("no warnings"))
        self.lbl["muestras"].setText(f"{e.muestras} ({e.validas})")
        self.lbl["nulos"].setText(f"{e.pct_nulos:g} %  ·  " + tr("{0} gap(s)").format(e.n_huecos) + (
            "<br>" + tr("logged from {0} to {1}").format(f"{e.intervalo[0]:g}", f"{e.intervalo[1]:g}")
            if e.intervalo else ""))
        self.lbl["minmax"].setText(f"{_num(e.minimo)} / {_num(e.maximo)}")
        self.lbl["media"].setText(f"{_num(e.media)} / {_num(e.desv)}")
        self.lbl["pct"].setText(f"{_num(e.p10)} / {_num(e.p50)} / {_num(e.p90)}")
        rango = qc.rango_fisico(c.nombre, c.unidad, alias)
        self.lbl["rango"].setText(f"{rango[0]:g} – {rango[1]:g} {c.unidad}" if rango else
                                  tr("none for this group and unit"))
        self.b_antes.setEnabled(historial.original(reg, c.nombre) is not None)

    def _origen(self, reg, c) -> str:
        from .ventana import SUFIJOS_GENERADAS
        if c.nombre.upper().endswith(SUFIJOS_GENERADAS):
            cambio = creacion(reg, c.nombre)
            if cambio is not None:
                return tr("generated by {0} ({1})").format(tr(cambio.operacion), cambio.fecha) + \
                    (f"<br><span style='color:#667'>{cambio.detalle}</span>" if cambio.detalle else "")
            return tr("generated curve") + (f": {c.descripcion}" if c.descripcion else "")
        if historial.original(reg, c.nombre) is not None:
            n = sum(1 for x in reg.historial.bitacora if c.nombre in [y.strip() for y in x.columnas.split(",")])
            return tr("edited (original version kept)") + " · " + tr("{0} change(s)").format(n)
        return tr("measured (not edited)")

    # ---------------------------------------------------------------- edición
    def aplicar(self) -> bool:
        reg, viejo = self.reg, self.nombre
        if reg is None or reg.indice_columna(viejo) < 0:
            return False
        nuevo = self.txt_nombre.text().strip()
        unidad, desc = self.txt_unidad.text().strip(), self.txt_desc.text().strip()
        if not nuevo:
            aviso(self, tr("Empty name is not allowed! Please set new name."))
            return False
        if nuevo.upper() != viejo.upper() and reg.indice_columna(nuevo) >= 0:
            aviso(self, tr("Name is already used! Please use a different name."))
            return False
        col = reg.columnas[reg.indice_columna(viejo)]
        if (nuevo, unidad, desc) == (col.nombre, col.unidad, col.descripcion):
            return False
        cambios = [f"{viejo} -> {nuevo}"] if nuevo != viejo else []
        if unidad != col.unidad:
            cambios.append(f"unit {col.unidad or '-'} -> {unidad or '-'}")
        if desc != col.descripcion:
            cambios.append("description")

        def poner():
            col.nombre, col.unidad, col.descripcion = nuevo, unidad, desc
            if nuevo != viejo:
                historial.renombrar_original(reg, viejo, nuevo)
        with self.app.operacion("Curve properties"):
            historial.aplicar(reg, "Curve properties", "; ".join(cambios), poner)
        self.app.proyecto.modificado = True
        self.app.seleccion.fijar(curva=nuevo)
        self.app.editor_logs.actualizar_tabla()
        self.refrescar()
        return True
