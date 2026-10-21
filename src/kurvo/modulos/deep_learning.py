"""Módulo "Deep Learning": reconstrucción de curvas y clasificación de litofacies con redes 1D
entrenadas con varios pozos (reemplaza al módulo de Random Forest). Lógica en aprendizaje/."""
from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QProgressBar, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..aprendizaje import datos as D
from ..aprendizaje import redes
from ..i18n import tr
from ..nucleo import historial, preferencias, qc
from ..nucleo.comun import NULO, UID
from ..nucleo.intervalos import IntervaloLito, Litologia
from ..nucleo.multipozo import buscar_curva
from ..vista.dialogos import aviso, boton
from .base import Modulo

ROLES = ["Train", "Validate", "Predict", "Ignore"]
TIPO_ANALISIS = "dlmodel"
ENTRADAS_TIPICAS = ("GR", "RHOB", "NPHI", "DT", "ILD", "PE", "SP", "CALI", "RT", "DTC", "PEF", "LLD")


def _curvas_proyecto(pr) -> list[str]:
    from ..vista.multipozo_ui import nombres_curvas
    return nombres_curvas(pr)


def facies_a_intervalos(prof, clases, nombre: str) -> Litologia:
    """Tramos contiguos de la misma clase → interpretación de litología (para el Log Plot)."""
    lit = Litologia(nombre)
    p, c = np.asarray(prof, float), np.asarray(clases, float)
    ok = np.isfinite(p) & np.isfinite(c) & (p != NULO)
    idx = np.where(ok)[0]
    if not idx.size:
        return lit
    ini = idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if c[b] != c[ini] or b != a + 1:
            lit.intervalos.append(IntervaloLito(float(p[ini]), float(p[a]), int(c[ini]), "DL"))
            ini = b
    lit.intervalos.append(IntervaloLito(float(p[ini]), float(p[idx[-1]]), int(c[ini]), "DL"))
    return lit


class _Trabajador(QObject):
    progreso = Signal(int, int, float, float)
    terminado = Signal(object)
    error = Signal(str)

    def __init__(self, modelo, ent, val, cpu):
        super().__init__()
        self.modelo, self.ent, self.val, self.cpu = modelo, ent, val, cpu
        self.parar = False

    def ejecutar(self):
        try:
            res = self.modelo.entrenar(self.ent, self.val, self.cpu, lambda *a: self.progreso.emit(*a),
                                       lambda: self.parar)
            self.terminado.emit(res)
        except Exception as e:  # noqa: BLE001 - se informa en la interfaz
            self.error.emit(f"{type(e).__name__}: {e}")


class DialogoDeepLearning(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        pr = app.proyecto
        self.setWindowTitle(tr("Deep Learning — curve reconstruction and lithofacies"))
        opciones = preferencias.actual().dl
        self.modelo: redes.ModeloCurvas | None = None
        self.hilo = None
        curvas = _curvas_proyecto(pr)

        # ---------------------------------------------------------- configuración
        self.ch_tarea = QComboBox()
        for k, v in redes.TAREAS.items():
            self.ch_tarea.addItem(tr(v), k)
        self.ch_arq = QComboBox()
        for k, v in redes.ARQUITECTURAS.items():
            self.ch_arq.addItem(tr(v), k)
        self.ch_arq.setCurrentIndex(max(0, self.ch_arq.findData(opciones.arquitectura)))
        self.ch_obj = QComboBox()
        self.ch_obj.setEditable(True)
        self.ch_obj.addItems(curvas)
        self.lista_ent = QListWidget()
        for n in curvas:
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n.upper() in ENTRADAS_TIPICAS else Qt.Unchecked)
            self.lista_ent.addItem(it)
        self.sp_largo, self.sp_epocas, self.sp_lote, self.sp_mc = QSpinBox(), QSpinBox(), QSpinBox(), QSpinBox()
        for sp, lo, hi, v in ((self.sp_largo, 32, 2048, opciones.largo), (self.sp_epocas, 1, 2000, opciones.epocas),
                              (self.sp_lote, 2, 1024, opciones.lote), (self.sp_mc, 1, 200, opciones.muestras_mc)):
            sp.setRange(lo, hi)
            sp.setValue(v)
        self.sp_largo.setSingleStep(32)
        self.sp_largo.setToolTip(tr("Samples per depth window (multiple of 8); context the network sees"))
        self.sp_lr = QDoubleSpinBox()
        self.sp_lr.setDecimals(5)
        self.sp_lr.setRange(1e-5, 1.0)
        self.sp_lr.setValue(opciones.lr)
        self.chk_cpu = QCheckBox(tr("Force CPU"))
        self.chk_cpu.setChecked(opciones.forzar_cpu)
        self.chk_qc = QCheckBox(tr("Exclude QC-flagged samples from training"))
        self.chk_qc.setChecked(opciones.excluir_qc)
        self.chk_qc.setToolTip(tr("Samples flagged by QC (out of physical range, spikes, flat runs) are not used to "
                                  "train; QC grades are recomputed after writing the prediction"))
        self.chk_relleno = QCheckBox(tr("Also write <curve>_FILL (original + prediction in gaps)"))
        self.chk_relleno.setChecked(True)
        self.chk_lito = QCheckBox(tr("Also create a lithology interpretation 'DL facies'"))
        self.chk_lito.setChecked(True)
        self.lbl_disp = QLabel()
        form = QFormLayout()
        form.addRow(tr("Task"), self.ch_tarea)
        form.addRow(tr("Network"), self.ch_arq)
        self.lbl_obj = QLabel(tr("Target curve"))
        form.addRow(self.lbl_obj, self.ch_obj)
        form.addRow(tr("Window (samples)"), self.sp_largo)
        form.addRow(tr("Max epochs"), self.sp_epocas)
        form.addRow(tr("Batch size"), self.sp_lote)
        form.addRow(tr("Learning rate"), self.sp_lr)
        form.addRow(tr("MC dropout passes (uncertainty)"), self.sp_mc)
        form.addRow(tr("Device"), self.lbl_disp)
        form.addRow("", self.chk_cpu)
        form.addRow("", self.chk_qc)
        form.addRow("", self.chk_relleno)
        form.addRow("", self.chk_lito)
        g_conf = QGroupBox(tr("Model"))
        g_conf.setLayout(form)
        g_ent = QGroupBox(tr("Input curves (by name or alias group)"))
        QVBoxLayout(g_ent).addWidget(self.lista_ent)

        # ---------------------------------------------------------- pozos
        self.tabla_pozos = QTableWidget(len(pr.pozos), 3)
        self.tabla_pozos.setHorizontalHeaderLabels([tr("Well / log"), tr("Target data"), tr("Role")])
        self.tabla_pozos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.combos_rol = []
        for i, p in enumerate(pr.pozos):
            it = QTableWidgetItem(f"{p.nombre} / {p.logs[0].nombre}" if p.logs else f"{p.nombre} ({tr('no logs')})")
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.tabla_pozos.setItem(i, 0, it)
            self.tabla_pozos.setItem(i, 1, QTableWidgetItem(""))
            ch = QComboBox()
            for rol in ROLES:
                ch.addItem(tr(rol), rol)
            self.tabla_pozos.setCellWidget(i, 2, ch)
            self.combos_rol.append(ch)
        g_pozos = QGroupBox(tr("Wells (first log of each well)"))
        QVBoxLayout(g_pozos).addWidget(self.tabla_pozos)

        # ---------------------------------------------------------- resultados
        self.b_entrenar = boton("Train", "train", "Train the network and show the validation metrics "
                                "(the data are not changed)")
        self.b_parar = boton("Stop", "stop", "Stop training after the current epoch")
        self.b_predecir = boton("Predict && Write", "predict", "Write the prediction in every well that is not "
                                "'Ignore' (recorded in the Change Log)")
        self.b_guardar = boton("Save Model in Project", "save_model", "Keep the trained model inside the project")
        self.b_cargar = boton("Load Model...", "load_model", "Use a model stored in the project")
        self.b_cerrar = boton("Close", "close", "", self.close)
        self.b_parar.setEnabled(False)
        self.b_predecir.setEnabled(False)
        self.b_guardar.setEnabled(False)
        self.barra = QProgressBar()
        self.lbl_estado = QLabel(tr("Configure the model and press Train."))
        self.lbl_estado.setWordWrap(True)
        self.g_perdida = pg.PlotWidget(title=tr("Loss"))
        self.g_perdida.addLegend()
        self.g_perdida.setLabel("bottom", tr("Epoch"))
        self.c_ent = self.g_perdida.plot([], [], pen=pg.mkPen("b", width=2), name=tr("train"))
        self.c_val = self.g_perdida.plot([], [], pen=pg.mkPen("r", width=2), name=tr("validation"))
        self.tabla_met = QTableWidget(0, 5)
        self.tabla_met.setHorizontalHeaderLabels([tr("Validation well"), tr("Samples"), "R²", "RMSE", tr("Accuracy")])
        self.tabla_met.horizontalHeader().setStretchLastSection(True)

        botones = QHBoxLayout()
        for b in (self.b_entrenar, self.b_parar, self.b_predecir, self.b_guardar, self.b_cargar):
            botones.addWidget(b)
        botones.addStretch(1)
        botones.addWidget(self.b_cerrar)
        izq = QWidget()
        li = QVBoxLayout(izq)
        li.addWidget(g_conf)
        li.addWidget(g_ent, 1)
        der = QWidget()
        ld = QVBoxLayout(der)
        ld.addWidget(g_pozos, 1)
        ld.addLayout(botones)
        ld.addWidget(self.barra)
        ld.addWidget(self.lbl_estado)
        ld.addWidget(self.g_perdida, 2)
        ld.addWidget(self.tabla_met, 1)
        sp = QSplitter()
        sp.addWidget(izq)
        sp.addWidget(der)
        sp.setSizes([420, 700])
        QVBoxLayout(self).addWidget(sp)

        self.ch_tarea.currentIndexChanged.connect(self._tarea)
        self.ch_obj.currentTextChanged.connect(self._roles_por_defecto)
        self.chk_cpu.toggled.connect(self._dispositivo)
        self.b_entrenar.clicked.connect(self.entrenar)
        self.b_parar.clicked.connect(self.parar)
        self.b_predecir.clicked.connect(self.predecir)
        self.b_guardar.clicked.connect(self.guardar_modelo)
        self.b_cargar.clicked.connect(self.cargar_modelo)
        if self.ch_obj.findText("DT") >= 0:
            self.ch_obj.setCurrentText("DT")
        self._tarea()
        self._dispositivo()
        self.resize(1200, 820)

    # ---------------------------------------------------------------- estado
    @property
    def regresion(self) -> bool:
        return self.ch_tarea.currentData() == "regresion"

    def _tarea(self, *_):
        self.ch_obj.setEnabled(self.regresion)
        self.chk_relleno.setVisible(self.regresion)
        self.chk_lito.setVisible(not self.regresion)
        self.lbl_obj.setText(tr("Target curve") if self.regresion else tr("Labels: first lithology interpretation"))
        self._roles_por_defecto()

    def _dispositivo(self, *_):
        if not redes.torch_disponible():
            self.lbl_disp.setText(tr("PyTorch is not installed (pip install torch)"))
            self.b_entrenar.setEnabled(False)
            return
        _, texto = redes.elegir_dispositivo(self.chk_cpu.isChecked())
        self.lbl_disp.setText(texto)

    def _tiene_objetivo(self, p) -> int:
        if not p.logs:
            return 0
        if not self.regresion:
            return sum(len(l.intervalos) for l in p.litologias[:1])
        k = buscar_curva(p.logs[0], self.ch_obj.currentText().strip(), self.app.alias)
        if k < 0:
            return 0
        d = p.logs[0].columnas[k].datos
        return int(((d != NULO) & np.isfinite(d)).sum())

    def _roles_por_defecto(self, *_):
        pr = self.app.proyecto
        con = [i for i, p in enumerate(pr.pozos) if self._tiene_objetivo(p) > 0]
        for i, p in enumerate(pr.pozos):
            n = self._tiene_objetivo(p)
            self.tabla_pozos.item(i, 1).setText((tr("{0} samples").format(n) if self.regresion
                                                 else tr("{0} intervals").format(n)) if n else "—")
            rol = "Ignore" if not p.logs else ("Train" if i in con else "Predict")
            if len(con) >= 2 and i == con[-1]:
                rol = "Validate"
            self.combos_rol[i].setCurrentIndex(ROLES.index(rol))

    def roles(self) -> dict[str, list[int]]:
        out = {r: [] for r in ROLES}
        for i, ch in enumerate(self.combos_rol):
            out[ch.currentData()].append(i)
        return out

    def entradas(self) -> list[str]:
        obj = self.ch_obj.currentText().strip().upper() if self.regresion else ""
        return [self.lista_ent.item(k).text() for k in range(self.lista_ent.count())
                if self.lista_ent.item(k).checkState() == Qt.Checked and self.lista_ent.item(k).text().upper() != obj]

    def _pozo(self, i, entradas) -> D.Pozo:
        p = self.app.proyecto.pozos[i]
        lit = (p.litologias[0] if p.litologias else Litologia()) if not self.regresion else None
        return D.extraer(p.logs[0], p.nombre, entradas, self.ch_obj.currentText().strip() if self.regresion else None,
                         self.app.alias, lit, excluir_qc=self.chk_qc.isChecked())

    # ---------------------------------------------------------------- entrenamiento
    def preparar(self):
        """Construye configuración, normalizador y conjuntos; devuelve (modelo, ent, val) o None."""
        entradas = self.entradas()
        roles = self.roles()
        if not entradas:
            aviso(self, tr("Select at least one input curve."))
            return None
        if not roles["Train"]:
            aviso(self, tr("Assign the role 'Train' to at least one well with target data."))
            return None
        try:
            ent = [self._pozo(i, entradas) for i in roles["Train"]]
            val = [self._pozo(i, entradas) for i in roles["Validate"]]
        except ValueError as e:
            aviso(self, str(e))
            return None
        if not val and len(ent) == 1:            # un solo pozo: valida con el último 20 % en profundidad
            p = ent[0]
            corte = int(len(p.prof) * 0.8)
            val = [D.Pozo(p.nombre + " (last 20%)", p.prof[corte:], p.X[:, corte:], p.y[corte:], p.curvas)]
            ent = [D.Pozo(p.nombre, p.prof[:corte], p.X[:, :corte], p.y[:corte], p.curvas)]
        unidades = []
        for n in entradas:
            u = ""
            for p in self.app.proyecto.pozos:
                if p.logs and (k := buscar_curva(p.logs[0], n, self.app.alias)) >= 0:
                    u = p.logs[0].columnas[k].unidad
                    break
            unidades.append(u)
        largo = max(32, self.sp_largo.value() // 8 * 8)
        cfg = redes.Configuracion(self.ch_tarea.currentData(), self.ch_arq.currentData(), entradas, unidades,
                                  self.ch_obj.currentText().strip() if self.regresion else "LITHO",
                                  largo=largo, epocas=self.sp_epocas.value(), lote=self.sp_lote.value(),
                                  lr=self.sp_lr.value(), muestras_mc=self.sp_mc.value())
        try:
            if self.regresion:
                pref = self.app.proyecto.pozos[roles["Train"][0]].logs[0]
                k = buscar_curva(pref, cfg.objetivo, self.app.alias)
                log_obj = D.es_log(cfg.objetivo, pref.columnas[k].unidad if k >= 0 else "", self.app.alias)
            else:
                log_obj = False
                cfg.clases = sorted({int(v) for p in ent for v in p.y if v >= 0})
                if len(cfg.clases) < 2:
                    raise ValueError(tr("Lithofacies needs at least two lithology types in the training wells."))
            norm = D.ajustar_normalizador(ent, entradas, unidades, log_obj, True, self.app.alias, self.regresion)
        except ValueError as e:
            aviso(self, str(e))
            return None
        return redes.ModeloCurvas(cfg, norm), ent, val

    def entrenar(self, sincrono: bool = False):
        prep = self.preparar()
        if prep is None:
            return None
        self.modelo, ent, val = prep
        self.h_ent, self.h_val = [], []
        self.barra.setMaximum(self.modelo.cfg.epocas)
        self.barra.setValue(0)
        self.excluidas = sum(p.excluidas for p in ent + val)
        self.lbl_estado.setText(tr("Training on {0} …").format(self.lbl_disp.text())
                                + (tr(" ({0} QC-flagged samples excluded)").format(self.excluidas)
                                   if self.excluidas else ""))
        self.trabajador = _Trabajador(self.modelo, ent, val, self.chk_cpu.isChecked())
        self.trabajador.progreso.connect(self._progreso)
        self.trabajador.terminado.connect(self._fin)
        self.trabajador.error.connect(self._error)
        for b, v in ((self.b_entrenar, False), (self.b_parar, True), (self.b_predecir, False), (self.b_guardar, False)):
            b.setEnabled(v)
        if sincrono:                              # pruebas: sin hilo
            self.trabajador.ejecutar()
            return self.modelo
        self.hilo = QThread(self)
        self.trabajador.moveToThread(self.hilo)
        self.hilo.started.connect(self.trabajador.ejecutar)
        self.trabajador.terminado.connect(self.hilo.quit)
        self.trabajador.error.connect(self.hilo.quit)
        self.hilo.start()
        return self.modelo

    def parar(self):
        if getattr(self, "trabajador", None) is not None:
            self.trabajador.parar = True
            self.lbl_estado.setText(tr("Stopping after this epoch …"))

    def _progreso(self, ep, total, le, lv):
        self.h_ent.append(le)
        self.h_val.append(lv)
        self.c_ent.setData(range(1, len(self.h_ent) + 1), self.h_ent)
        self.c_val.setData(range(1, len(self.h_val) + 1), self.h_val)
        self.barra.setValue(ep)
        self.lbl_estado.setText(tr("Epoch {0}/{1} · train {2} · validation {3}").format(ep, total, f"{le:.4f}", f"{lv:.4f}"))

    def _fin(self, res: redes.Resultado):
        self.resultado = res
        self.barra.setValue(self.barra.maximum())
        self.tabla_met.setRowCount(len(res.metricas))
        for i, m in enumerate(res.metricas):
            for j, v in enumerate((m.pozo, str(m.muestras), m.r2, m.rmse, m.exactitud)):
                self.tabla_met.setItem(i, j, QTableWidgetItem(v if isinstance(v, str) else
                                                              ("—" if math.isnan(v) else f"{v:.3f}")))
        self.lbl_estado.setText(tr("Trained {0} epoch(s) in {1} s on {2}").format(res.epocas, f"{res.segundos:.1f}",
                                                                                 res.dispositivo)
                                + (tr(" · batch reduced to {0}").format(res.lote_final)
                                   if res.lote_final != self.modelo.cfg.lote else "")
                                + (tr(" · {0} QC-flagged samples excluded").format(self.excluidas)
                                   if getattr(self, "excluidas", 0) else "")
                                + self._texto_calibracion(res))
        for b, v in ((self.b_entrenar, True), (self.b_parar, False), (self.b_predecir, True), (self.b_guardar, True)):
            b.setEnabled(v)
        self.app.registrar(self.lbl_estado.text())

    def _texto_calibracion(self, res: redes.Resultado) -> str:
        """La banda de incertidumbre se calibra con los pozos de validación (D121); sin ellos no es fiable."""
        if not self.regresion:
            return ""
        if res.calibracion > 0:
            return tr(" · uncertainty calibrated on the validation wells (×{0})").format(f"{res.calibracion:.1f}")
        return tr(" · uncertainty NOT calibrated: assign a 'Validate' well; the band underestimates the error")

    def _error(self, texto):
        for b, v in ((self.b_entrenar, True), (self.b_parar, False)):
            b.setEnabled(v)
        self.lbl_estado.setText(tr("Training failed: ") + texto)
        aviso(self, tr("Training failed: ") + "\n" + texto)

    # ---------------------------------------------------------------- predicción
    def predecir(self):
        if self.modelo is None:
            return 0
        pr, cfg = self.app.proyecto, self.modelo.cfg
        destino = [i for i, p in enumerate(pr.pozos) if p.logs and self.combos_rol[i].currentData() != "Ignore"]
        hechos = 0
        notas_nuevas = []
        with self.app.operacion("Deep learning prediction"):
            for i in destino:
                p = pr.pozos[i]
                reg = p.logs[0]
                try:
                    pozo = D.extraer(reg, p.nombre, cfg.entradas, cfg.objetivo if self.regresion else None, self.app.alias)
                    a, b = self.modelo.predecir(pozo)
                except ValueError as e:
                    self.app.registrar(f"{p.nombre}: {e}")
                    continue
                a = np.where(np.isfinite(a), a, NULO)
                b = np.where(np.isfinite(b), b, NULO)
                if self.regresion:
                    nombre = cfg.objetivo
                    cols = [(f"{nombre}_DL", a, "Deep learning prediction"),
                            (f"{nombre}_DL_STD", b, "Prediction uncertainty (MC dropout std"
                             + (f", calibrated x{cfg.calibracion:.1f} on validation wells)" if cfg.calibracion > 0
                                else ", NOT calibrated)"))]
                    if self.chk_relleno.isChecked():
                        k = buscar_curva(reg, nombre, self.app.alias)
                        if k >= 0:
                            orig = reg.columnas[k].datos
                            cols.append((f"{nombre}_FILL", np.where(orig != NULO, orig, a), "Original + DL in gaps"))
                    unidad = ""
                    k = buscar_curva(reg, nombre, self.app.alias)
                    if k >= 0:
                        unidad = reg.columnas[k].unidad
                else:
                    cols = [("LITHO_DL", a, "Deep learning lithofacies (lithology id)"),
                            ("LITHO_DL_P", b, "Probability of the predicted facies")]
                    unidad = ""

                def poner(reg=reg, cols=cols, unidad=unidad):
                    for n, d, desc in cols:
                        j = reg.indice_columna(n)
                        if j >= 0:
                            reg.columnas[j].datos = d
                        else:
                            reg.agregar_columna(n, d, unidad if not n.endswith("_P") else "", desc)
                historial.aplicar(reg, "Deep learning", f"{redes.ARQUITECTURAS[cfg.arquitectura]} · "
                                  f"{redes.TAREAS[cfg.tarea]} · inputs {', '.join(cfg.entradas)}", poner)
                qc.invalidar(reg)            # QC ↔ DL: la nota se recalcula con las curvas nuevas
                estados = qc.notas(reg, self.app.alias)
                notas_nuevas += [f"{p.nombre} {n} {estados[n].nota}" for n, *_ in cols if n in estados
                                 and not n.endswith(("_STD", "_P"))]
                if not self.regresion and self.chk_lito.isChecked():
                    md = reg.columnas[reg.indice_md].datos
                    p.litologias = [l for l in p.litologias if l.nombre != "DL facies"]
                    p.litologias.append(facies_a_intervalos(md, np.where(a == NULO, np.nan, a), "DL facies"))
                hechos += 1
        pr.modificado = True
        self.app.refrescar_todo()
        self.notas_qc = notas_nuevas
        resumen = tr("QC grades after reconstruction: {0}").format(", ".join(notas_nuevas)) if notas_nuevas else ""
        self.app.registrar(tr("Deep learning prediction written in {0} well(s)").format(hechos)
                           + (". " + resumen if resumen else ""))
        self.lbl_estado.setText(tr("Prediction written in {0} well(s).").format(hechos) + (" " + resumen if resumen else ""))
        return hechos

    # ---------------------------------------------------------------- persistencia
    def guardar_modelo(self, nombre: str | None = None):
        from ..nucleo.proyecto import Analisis
        if self.modelo is None:
            return None
        cfg = self.modelo.cfg
        nombre = nombre or f"{cfg.objetivo} {cfg.arquitectura} ({', '.join(cfg.entradas)})"
        a = Analisis(TIPO_ANALISIS, UID.nuevo(), nombre, cfg.tarea, self.modelo.a_texto())
        self.app.proyecto.analisis.append(a)
        self.app.proyecto.modificado = True
        self.app.registrar(tr("Model '{0}' stored in the project (saved with the project)").format(nombre))
        return a

    def cargar_modelo(self, indice: int | None = None):
        modelos = [a for a in self.app.proyecto.analisis if a.tipo == TIPO_ANALISIS]
        if not modelos:
            aviso(self, tr("The project has no stored models."))
            return None
        if indice is None:
            from PySide6.QtWidgets import QInputDialog
            nombre, ok = QInputDialog.getItem(self, tr("Load Model"), tr("Model"), [a.nombre for a in modelos], 0, False)
            if not ok:
                return None
            indice = [a.nombre for a in modelos].index(nombre)
        try:
            self.modelo = redes.ModeloCurvas.desde_texto(modelos[indice].contenido)
        except Exception as e:  # noqa: BLE001
            aviso(self, tr("Unable to load the model: {0}").format(e))
            return None
        cfg = self.modelo.cfg
        self.ch_tarea.setCurrentIndex(self.ch_tarea.findData(cfg.tarea))
        self.ch_arq.setCurrentIndex(self.ch_arq.findData(cfg.arquitectura))
        if self.regresion:
            self.ch_obj.setCurrentText(cfg.objetivo)
        for k in range(self.lista_ent.count()):
            it = self.lista_ent.item(k)
            it.setCheckState(Qt.Checked if it.text() in cfg.entradas else Qt.Unchecked)
        self.b_predecir.setEnabled(True)
        self.lbl_estado.setText(tr("Model '{0}' loaded. Press Predict to apply it.").format(modelos[indice].nombre))
        return self.modelo

    def closeEvent(self, ev):
        if self.hilo is not None and self.hilo.isRunning():
            if QMessageBox.question(self, tr("Deep Learning"), tr("Training is running. Stop it and close?")) != QMessageBox.Yes:
                ev.ignore()
                return
            self.parar()
            self.hilo.quit()
            self.hilo.wait(30000)
        super().closeEvent(ev)


class DeepLearning(Modulo):
    nombre = "Deep Learning"
    descripcion = ("Curve reconstruction and lithofacies classification with 1D neural networks "
                   "(U-Net / BiGRU) trained on several wells; uses the GPU when available")

    def acciones_editor_logs(self, app):
        return []           # es la acción "deep_learning" del registro (ribbon y menús)

    def abrir(self, app):
        d = DialogoDeepLearning(app)
        d.show()
        app._ventanas.append(d)
        return d
