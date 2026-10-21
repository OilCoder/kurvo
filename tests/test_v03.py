"""Pruebas de la versión 0.3: coherencia de la interfaz, panel de QC, preferencias, QC ↔ DL e idioma."""
import numpy as np
import pytest

from kurvo.demo import proyecto_demo
from kurvo.nucleo.comun import NULO


@pytest.fixture()
def ventana(qapp, tmp_path):
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    v.proyecto = proyecto_demo()
    v.refrescar_todo()
    v.resize(1600, 960)
    v.show()
    yield v
    v.proyecto.modificado = False
    v.close()


# ------------------------------------------------------------------ núcleo
def test_preferencias_json():
    from kurvo.nucleo import preferencias
    p = preferencias.Preferencias(idioma="es", nulos_extra=[-9999.0])
    p.qc.nulos_malo = 40.0
    p.dl.epocas = 7
    p.rangos["GR"] = [("GAPI", 0, 300)]
    q = preferencias.Preferencias.desde_json(p.a_json())
    assert q.idioma == "es" and q.nulos_extra == [-9999.0] and q.qc.nulos_malo == 40.0 and q.dl.epocas == 7
    assert q.rangos["GR"] == [("GAPI", 0.0, 300.0)]
    assert preferencias.Preferencias.desde_json("no es json").idioma == "en"


def test_umbrales_de_preferencias_cambian_la_nota():
    from kurvo.nucleo import preferencias, qc
    z = np.arange(200.0)
    gr = 60 + 10 * np.sin(z / 5)
    gr[85:115] = NULO                                 # 15 % de nulos dentro del intervalo registrado (D108)
    previo = preferencias.actual()
    try:
        assert qc.evaluar_curva(gr, z, "GR", "GAPI").nota == "B"
        p = preferencias.Preferencias()
        p.qc.nulos_malo = 10.0
        preferencias.fijar(p)
        assert qc.evaluar_curva(gr, z, "GR", "GAPI").nota == "C"
        p.rangos["GR"] = [("GAPI", 0, 50)]
        assert qc.rango_fisico("GR", "GAPI") == (0, 50)
    finally:
        preferencias.fijar(previo)


def test_analisis_qc():
    from kurvo.nucleo import qc
    pr = proyecto_demo()
    reg = pr.pozos[0].logs[0]
    nombres, m = qc.cobertura(reg)
    assert m.shape == (len(nombres), reg.n_filas) and set(np.unique(m)) <= {0, 1, 2}
    assert (m[nombres.index("GR")] == 0).sum() == (reg.columna("GR").datos == NULO).sum()
    q = qc.caja([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, NULO])
    assert q[2] == pytest.approx(5.5) and q[0] < q[1] < q[3] < q[4]
    x, f = qc.cdf([3.0, 1.0, 2.0, NULO])
    assert list(x) == [1, 2, 3] and f[-1] == 1
    nombres, r = qc.correlacion(reg, ["RHOB", "DT", "GR"])
    assert r[nombres.index("RHOB"), nombres.index("DT")] < -0.9      # el DT del demo sale de la porosidad
    assert np.allclose(np.diag(r), 1)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 2))
    X[10] = (8, -8)
    d2, malas, lim = qc.mahalanobis(X)
    assert malas[10] and malas.sum() < 10 and lim > 0
    medio, paso, mal, tipico = qc.paso_profundidad([0, 0.5, 1.0, 1.5, 2.5, 3.0])
    assert tipico == 0.5 and mal.tolist() == [False, False, False, True, False]
    lineas = qc.lineas_nd(escala_neutron=100.0)
    n, d, f = lineas["Limestone"]
    assert n[0] == 0 and d[0] == pytest.approx(2.71) and lineas["Sandstone"][0][0] < 0 < lineas["Dolomite"][0][0]
    assert qc.escala_neutron("PU") == 100 and qc.escala_densidad("KG/M3") == 1000


def test_antes_despues_y_cache():
    from kurvo.nucleo import edicion, historial, qc
    reg = proyecto_demo().pozos[0].logs[0]
    assert qc.antes_despues(reg, "GR") is None
    n1 = qc.notas(reg)
    assert qc.notas(reg) is n1                                   # caché
    p = reg.columna("DEPT").datos
    historial.aplicar(reg, "Set to null", "", lambda: setattr(reg.columna("GR"), "datos",
                                                             edicion.a_nulo(reg.columna("GR").datos, p, 300, 310)))
    assert qc.notas(reg) is not n1                               # la huella cambió con la edición
    prof, orig, actual, dif = qc.antes_despues(reg, "GR")
    sel = (p >= 300) & (p <= 310)
    assert (actual[sel] == NULO).all() and np.isnan(dif[sel]).all() and np.nanmax(np.abs(dif)) == 0


def test_flujo_por_pozo():
    from kurvo.nucleo import flujo, historial
    pr = proyecto_demo()
    pozo = pr.pozos[0]
    estados = {e.clave: e.estado for e in flujo.estado_pozo(pozo)}
    assert [p[0] for p in flujo.PASOS] == list(estados)
    assert estados["prepare"] in (flujo.HECHO, flujo.AVISO) and estados["correct"] in (flujo.OPCIONAL, flujo.PENDIENTE)
    assert estados["deliver"] == flujo.PENDIENTE and estados["check"] == flujo.PENDIENTE
    # recién importado, el siguiente paso es Preparar (si tiene avisos) o Revisar, no Comprobar (D123)
    assert flujo.siguiente(flujo.estado_pozo(pozo)) in (0, 1)
    reg = pozo.logs[0]
    historial.aplicar(reg, "Despike", "", lambda: None)            # sin cambio: no se anota
    historial.aplicar(reg, "Smooth", "", lambda: reg.columna("GR").datos.__setitem__(5, 1.0))
    reg.historial.anotar("Export LAS", "", "x.las")
    estados = {e.clave: e.estado for e in flujo.estado_pozo(pozo)}
    assert estados["correct"] == flujo.HECHO and estados["deliver"] == flujo.HECHO
    assert estados["check"] in (flujo.HECHO, flujo.AVISO)
    vacio = flujo.estado_pozo(type(pozo)("X"))
    assert all(e.estado == flujo.PENDIENTE for e in vacio)


def test_dl_excluye_banderas_qc():
    from kurvo.aprendizaje import datos as D
    from kurvo.nucleo.bases import alias_por_defecto
    reg = proyecto_demo().pozos[0].logs[0]
    reg.columna("DT").datos[100] = 900.0                         # fuera de rango físico
    reg.columna("GR").datos[200] = 5000.0
    alias = alias_por_defecto()
    a = D.extraer(reg, "P", ["GR", "RHOB"], "DT", alias)
    b = D.extraer(reg, "P", ["GR", "RHOB"], "DT", alias, excluir_qc=True)
    assert a.excluidas == 0 and b.excluidas >= 2
    assert np.isfinite(a.y[100]) and np.isnan(b.y[100]) and np.isnan(b.X[0, 200])


# ------------------------------------------------------------------ interfaz
def test_registro_de_acciones_y_ribbon(ventana):
    a = ventana.acciones
    for clave in ("import_las", "validate", "qc_window", "dashboard", "qc_flags", "graphic_edit", "normalize",
                  "deep_learning", "qc_report", "export_las", "settings"):
        assert not a[clave].icon().isNull() and a[clave].toolTip() and a[clave].text()
    # el botón del ribbon muestra la misma QAction
    assert ventana.ribbon.botones["Quality Control"].defaultAction() is a["qc_window"]
    assert a["undo"].shortcut().toString() == "Ctrl+Z"
    titulos = [ventana.ribbon.tabText(i) for i in range(ventana.ribbon.count())]
    assert titulos[0] == "1 · Prepare" and titulos[-1] == "7 · Deliver"           # D123
    grupos = [t for _, t in ventana.ribbon.grupos]
    assert grupos[:3] == ["Import", "Runs", "Structure"] and "Petrophysics" in grupos
    # las acciones de los módulos de interpretación están en el registro
    assert any(k.startswith("mod:Advance Log Analysis/") for k in a.acciones)


def test_menu_contextual_usa_las_mismas_acciones(ventana):
    ed = ventana.editor_logs
    ed.mostrar(0, 0)
    pos = ed.tabla.horizontalHeader().sectionViewportPosition(2)
    from PySide6.QtCore import QPoint
    m = ed.menu_columna(QPoint(pos + 5, 5))

    def todas(menu):
        out = []
        for act in menu.actions():
            out.append(act)
            if act.menu() is not None:
                out += todas(act.menu())
        return out
    acciones = todas(m)
    assert ventana.acciones["qc_window"] in acciones and ventana.acciones["despike"] in acciones
    assert ventana.seleccion.curva == "GR"                       # la columna clicada pasa a la selección


def test_seleccion_global(ventana):
    s = ventana.seleccion
    raiz = ventana.arbol.topLevelItem(0)
    log = raiz.child(1).child(0).child(0)                        # DEMO-2 / Logs / registro
    curva = next(log.child(k) for k in range(log.childCount()) if log.child(k).text(0).startswith("RHOB"))
    ventana.arbol.setCurrentItem(curva)
    assert (s.pozo, s.log, s.curva) == (1, 0, "RHOB")
    assert ventana.editor_logs.indices() == (1, 0)
    assert "RHOB" in ventana.lbl_seleccion.text() and "DEMO-2" in ventana.lbl_seleccion.text()
    assert ventana.panel_qc.ch_pozo.currentIndex() == 1 and ventana.panel_qc.curva() == "RHOB"
    ventana.editor_logs.mostrar(2, 0)
    assert s.pozo == 2
    lp = ventana.pagina_logplot.estado()
    assert lp.pozo == 2


def test_insignias_del_arbol(ventana):
    from kurvo.nucleo import historial
    reg = ventana.proyecto.pozos[0].logs[0]
    historial.aplicar(reg, "Smooth", "", lambda: reg.columna("GR").datos.__setitem__(5, 1.0))
    reg.agregar_columna("GR_DL", reg.columna("GR").datos.copy(), "API")
    ventana.reconstruir_arbol()
    log = ventana.arbol.topLevelItem(0).child(0).child(0).child(0)
    hijos = {log.child(k).text(0).split()[0]: log.child(k) for k in range(log.childCount())}
    assert "QC grade" in hijos["GR"].toolTip(0) and "edited" in hijos["GR"].toolTip(0)
    assert "generated" in hijos["GR_DL"].toolTip(0)
    assert "QC grade of the log" in log.toolTip(0)


def test_panel_qc_recorre_pestanas(ventana, capturas, qapp):
    panel = ventana.ventana_qc()
    ventana.seleccion.fijar(pozo=0, log=0, curva="GR")
    for z in (-1, 0):
        ventana.seleccion.fijar(zona=z)
        for clave in panel.claves:
            panel.ir_a(clave)
            qapp.processEvents()
            assert clave not in panel.sucias
    assert not any("QC panel:" in d for d in ventana.diagnostico)
    assert panel.tabla_resumen.rowCount() == 6
    pozos, curvas, celdas = panel.matriz_dashboard()
    assert len(pozos) == 3 and "GR" in curvas and len(celdas) >= 18
    panel._clic_dashboard(1, curvas.index("DT"))
    assert (ventana.seleccion.pozo, ventana.seleccion.curva) == (1, "DT")
    assert panel.claves[panel.tabs.currentIndex()] == "depth"
    ventana.seleccion.fijar(pozo=0, log=0, curva="NPHI")
    panel.ir_a("crossplot")
    assert panel.ch_x.currentText() == "NPHI" and panel.ch_y.currentText() == "RHOB"
    series, _ = panel.series_pozos("GR")
    assert len(series) == 3


def test_capas_del_logplot(ventana):
    from kurvo.nucleo import historial
    reg = ventana.proyecto.pozos[0].logs[0]
    historial.aplicar(reg, "Smooth", "", lambda: reg.columna("GR").datos.__setitem__(slice(300, 320), 50.0))
    reg.agregar_columna("ILD_DL", reg.columna("ILD").datos.copy(), "OHMM")
    reg.agregar_columna("ILD_DL_STD", np.full(reg.n_filas, 2.0), "OHMM")
    pag = ventana.pagina_logplot
    for ck in (pag.ck_qc, pag.ck_dl, pag.ck_orig):
        ck.setChecked(True)
    assert pag.capas() == {"qc", "dl", "original"}
    plot = pag.plot_actual()
    assert plot.d.capas == frozenset({"qc", "dl", "original"})
    img = plot.imagen()
    assert img.width() > 100


def test_dialogo_parametros_vista_previa(qapp):
    from kurvo.vista.dialogos import Campo, DialogoParametros
    datos = np.arange(10.0)
    d = DialogoParametros("Smooth", [Campo("k", "Value", "float", 2.0)], None,
                          vista_previa=lambda v: (np.arange(10.0), datos, datos * v["k"], "X"))
    assert d.previsualizar() == 9 and d.barra.b_aplicar is not None and d.barra.b_vista is not None


def test_preferencias_y_flujo_en_la_ventana(ventana, monkeypatch):
    from kurvo.nucleo import preferencias
    from kurvo.vista.preferencias_ui import DialogoPreferencias
    d = DialogoPreferencias(ventana, ventana.prefs)
    d.sp_qc["nulos_malo"].setValue(33)
    d.txt_nulos.setText("-9999, -999")
    p = d.resultado()
    assert p.qc.nulos_malo == 33 and p.nulos_extra == [-9999.0, -999.0] and "GR" in p.rangos
    monkeypatch.setattr(DialogoPreferencias, "exec", lambda self: 1)
    monkeypatch.setattr(DialogoPreferencias, "resultado", lambda self: p)
    assert ventana.preferencias_usuario() is ventana            # sin cambio de idioma: misma ventana
    assert preferencias.actual().qc.nulos_malo == 33
    from kurvo.vista.ventana import ajustes
    assert "33" in ajustes().value("preferencias")
    from kurvo.vista.ventana import guardar_preferencias
    guardar_preferencias(preferencias.Preferencias())
    ventana.prefs = preferencias.actual()
    pasos = ventana.panel_flujo.pasos
    assert len(pasos) == 7 and pasos[0].estado in ("done", "warning")


def test_disposicion_de_paneles(ventana):
    assert set(ventana.docks) >= {"proyecto", "flujo", "qc", "historial"}      # v0.4 agrega "propiedades"
    ventana.acciones["panel_workflow"].setChecked(False)
    assert ventana.docks["flujo"].isHidden()
    ventana.acciones["panel_workflow"].setChecked(True)
    ventana.guardar_disposicion()
    from kurvo.vista.ventana import ajustes
    assert ajustes().value("ventana/estado_v1") is not None


def test_ayuda_how_to(ventana):
    d = ventana.ayuda(mostrar=False)
    from PySide6.QtWidgets import QTextBrowser
    texto = d.findChild(QTextBrowser).toPlainText()
    assert "Import" in texto and "Reconstruct" in texto and "Workflow" in texto
    d.close()


# ------------------------------------------------------------------ idioma
NO_TRADUCIR = {"Rt", "Rt^(-1/m)", "Sin nombre", "_QC", "DEPT", "Merged", "WellName", "NewZone", "_SPL", "_DS",
               "logplot-", " copy1", " copy", "CALC"}


def test_todos_los_textos_tienen_traduccion():
    import re
    import textos_ui
    from kurvo.i18n.es import ES
    faltan = {k: f for k, f in textos_ui.textos().items()
              if k not in ES and k not in NO_TRADUCIR and not re.fullmatch(r"[a-z_0-9]+", k)}
    assert not faltan, faltan
    # los marcadores {0}, {1}... se conservan en la traducción
    for k, v in ES.items():
        assert sorted(re.findall(r"\{\d\}", k)) == sorted(re.findall(r"\{\d\}", v)), k


def _textos_visibles(w):
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QGroupBox, QLabel, QTabWidget, QTableWidget,
                                   QTreeWidget)
    out = []
    for h in [w] + w.findChildren(object):
        if isinstance(h, QAbstractButton):
            out += [h.text(), h.toolTip()]
        elif isinstance(h, QLabel):
            out.append(h.text())
        elif isinstance(h, QGroupBox):
            out.append(h.title())
        elif isinstance(h, QTabWidget):
            out += [h.tabText(i) for i in range(h.count())]
        elif isinstance(h, QComboBox):
            out += [h.itemText(i) for i in range(h.count())]
        elif isinstance(h, QTableWidget):
            out += [h.horizontalHeaderItem(j).text() for j in range(h.columnCount()) if h.horizontalHeaderItem(j)]
        elif isinstance(h, QTreeWidget):
            it = h.topLevelItem(0)
            if it is not None:
                out.append(it.text(0))
    return [t for t in out if t]


def test_ventana_en_espanol_sin_textos_en_ingles(qapp, tmp_path):
    from kurvo.i18n.es import ES
    from kurvo.nucleo import preferencias
    from kurvo.vista.ventana import VentanaPrincipal, aplicar_idioma, guardar_preferencias
    guardar_preferencias(preferencias.Preferencias(idioma="es"))
    try:
        v = VentanaPrincipal()
        v.proyecto = proyecto_demo()
        v.refrescar_todo()
        v.seleccion.fijar(pozo=0, log=0, curva="GR")
        assert v.ribbon.tabText(1) == "2 · Revisar" and v.acciones["qc_window"].text() == "Control de calidad"
        assert v.docks["flujo"].windowTitle() == "Flujo de trabajo"
        for clave in v.panel_qc.claves:
            v.panel_qc.ir_a(clave)
        from kurvo.vista.multipozo_ui import DialogoNormalizacion
        from kurvo.vista.preferencias_ui import DialogoPreferencias
        dialogos = [DialogoNormalizacion(v), DialogoPreferencias(v, v.prefs), v.deep_learning()]
        sin_traducir = set()
        for w in [v] + [d for d in dialogos if d is not None]:
            for t in _textos_visibles(w):
                for linea in t.replace("<b>", "").replace("</b>", "").split("<br>"):
                    linea = linea.strip()
                    # "Scale" también es una propiedad del formato de plantilla (PosX, ShowTitle...),
                    # que se muestra sin traducir a propósito
                    if linea in ES and ES[linea] != linea and linea != "Scale":
                        sin_traducir.add(linea)
        assert not sin_traducir, sin_traducir
        texto_ayuda = v.ayuda(mostrar=False).findChild(__import__("PySide6.QtWidgets", fromlist=["QTextBrowser"])
                                                       .QTextBrowser).toPlainText()
        assert "Cómo hacer el mantenimiento" in texto_ayuda
        from kurvo.nucleo import qc
        reg = v.proyecto.pozos[0].logs[0]
        reg.columna("GR").datos[300:600] = -999.25      # dentro del intervalo registrado (D108)
        assert "nulos" in " ".join(qc.evaluar_curva(reg.columna("GR").datos, None, "GR", "API").avisos)
        for d in dialogos:
            if d is not None:
                d.close()
        v.proyecto.modificado = False
        v.close()
    finally:
        guardar_preferencias(preferencias.Preferencias())
        aplicar_idioma("en")


def test_cambio_de_idioma_en_caliente(ventana, monkeypatch):
    from kurvo.nucleo import preferencias
    from kurvo.vista.preferencias_ui import DialogoPreferencias
    from kurvo.vista.ventana import aplicar_idioma, guardar_preferencias
    ventana.seleccion.fijar(pozo=1, log=0, curva="RHOB")
    p = preferencias.Preferencias(idioma="es")
    monkeypatch.setattr(DialogoPreferencias, "exec", lambda self: 1)
    monkeypatch.setattr(DialogoPreferencias, "resultado", lambda self: p)
    try:
        nueva = ventana.preferencias_usuario()
        assert nueva is not ventana and nueva.proyecto is not None
        assert nueva.ribbon.tabText(0) == "1 · Preparar" and nueva.ribbon.tabText(1) == "2 · Revisar"
        assert (nueva.seleccion.pozo, nueva.seleccion.curva) == (1, "RHOB")
        assert len(nueva.proyecto.pozos) == 3
        nueva.proyecto.modificado = False
        nueva.close()
    finally:
        guardar_preferencias(preferencias.Preferencias())
        aplicar_idioma("en")
