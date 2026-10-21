"""Pruebas de la versión 0.4: curvas nuevas en la plantilla, operaciones compuestas (deshacer de
una vez en varios pozos), panel de propiedades, preferencias de QC por proyecto, rendimiento,
interfaz (unidad, tema, ribbon) y pendientes heredados."""
import numpy as np
import pytest

from kurvo.demo import proyecto_demo
from kurvo.nucleo import historial
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


def _curvas_plantilla(t):
    return [[c.nombre_x for c in p.curvas] for p in t.pistas]


# ------------------------------------------------------------------ plantilla automática (núcleo)
def test_origen_de_curva_generada():
    from kurvo.nucleo.plantilla_auto import origen
    cols = ["DEPT", "GR", "RHOB", "RHOB_DL"]
    assert origen("GR_NORM", cols) == "GR"
    assert origen("RHOB_DL_STD", cols) == "RHOB_DL"
    assert origen("CALC", cols) == ""


def test_agregar_curvas_nuevas_a_la_plantilla():
    from kurvo.nucleo import plantilla_auto as pa
    pr = proyecto_demo()
    reg = pr.pozos[0].logs[0]
    t = pr.plantillas[0]
    n_pistas = len(t.pistas)
    gr = reg.columna("GR")
    reg.agregar_columna("GR_NORM", gr.datos * 1.1, gr.unidad)
    reg.agregar_columna("GR_QC", np.zeros(reg.n_filas))
    reg.agregar_columna("GR_DL_STD", np.ones(reg.n_filas))
    reg.agregar_columna("CALC", np.linspace(0.1, 0.35, reg.n_filas))
    cambios = pa.agregar_nuevas(pr, reg, ["GR_NORM", "GR_QC", "GR_DL_STD", "CALC"])
    curvas = _curvas_plantilla(t)
    assert "GR_NORM" in curvas[0]                                  # misma pista que GR
    ref = next(c for c in t.pistas[0].curvas if c.nombre_x == "GR")
    norm = next(c for c in t.pistas[0].curvas if c.nombre_x == "GR_NORM")
    assert (norm.escala_min, norm.escala_max, norm.color) == (ref.escala_min, ref.escala_max, ref.color)
    assert norm.tipo_linea == pa.LINEA_DISCONTINUA
    assert not any("GR_DL_STD" in p for p in curvas)              # se ve como banda, no como curva
    assert len(t.pistas) == n_pistas + 2                           # pista de banderas y pista de CALC
    qc_pista = next(p for p in t.pistas if any(c.nombre_x == "GR_QC" for c in p.curvas))
    assert qc_pista.curvas[0].escala_max == 1.0
    calc = next(c for p in t.pistas for c in p.curvas if c.nombre_x == "CALC")
    assert calc.escala_min <= 0.1 and calc.escala_max >= 0.35
    assert pa.agregar_nuevas(pr, reg, ["GR_NORM"]) == []           # no se repite
    for c in reversed(cambios):
        c.deshacer()
    assert len(t.pistas) == n_pistas and "GR_NORM" not in _curvas_plantilla(t)[0]


# ------------------------------------------------------------------ operaciones compuestas (núcleo)
def test_operacion_compuesta_deshace_y_rehace_en_todos_los_registros():
    pr = proyecto_demo()
    hp = pr.historial_ops
    regs = [p.logs[0] for p in pr.pozos]
    antes = [r.columna("GR").datos.copy() for r in regs]
    op = hp.iniciar("Normalize wells")
    for r in regs:
        historial.aplicar(r, "Normalize", "", lambda r=r: r.agregar_columna("GR_NORM", r.columna("GR").datos * 2))
        historial.aplicar(r, "Edit", "", lambda r=r: setattr(r.columna("GR"), "datos", r.columna("GR").datos + 1))
    hecha = hp.terminar(op, pr, plantillas=True)
    assert hecha is not None and hecha.n_registros == 3
    assert "GR_NORM" in _curvas_plantilla(pr.plantillas[0])[0]
    assert hp.deshacer_en(regs[1])[1] is hecha                    # Ctrl+Z en cualquiera deshace todo
    for r, a in zip(regs, antes):
        assert r.indice_columna("GR_NORM") < 0 and np.array_equal(r.columna("GR").datos, a)
        assert [c.operacion for c in r.historial.bitacora[-2:]] == ["Undo", "Undo"]
    assert "GR_NORM" not in _curvas_plantilla(pr.plantillas[0])[0]
    assert hp.ultima(deshecha=True) is hecha
    hp.rehacer(hecha)
    assert all(r.indice_columna("GR_NORM") >= 0 for r in regs)
    assert "GR_NORM" in _curvas_plantilla(pr.plantillas[0])[0]
    # si un registro cambió después, la operación no se deshace a medias
    historial.aplicar(regs[0], "Edit", "", lambda: setattr(regs[0].columna("SP"), "datos", regs[0].columna("SP").datos + 1))
    from kurvo.nucleo.historial_proyecto import ErrorOperacion
    with pytest.raises(ErrorOperacion):
        hp.deshacer(hecha)
    assert hp.deshacer_en(regs[0])[1] is None                      # deshace solo la edición suelta


def test_operacion_anidada_y_sin_cambios():
    pr = proyecto_demo()
    hp = pr.historial_ops
    op = hp.iniciar("outer")
    assert hp.iniciar("inner") is None
    hp.terminar(None)
    assert hp.terminar(op, pr) is None                             # nada cambió: no se registra
    assert historial._compuesta is None


# ------------------------------------------------------------------ interfaz
def test_bandera_qc_va_a_la_plantilla_y_ctrl_z_la_quita(ventana):
    v = ventana
    t = v.proyecto.plantillas[0]
    n = len(t.pistas)
    v.seleccion.fijar(pozo=0, log=0, curva="GR")
    v.acciones["qc_flags"].trigger()
    assert any(c.nombre_x == "GR_QC" for p in t.pistas for c in p.curvas) and len(t.pistas) == n + 1
    v.deshacer()
    reg = v.seleccion.registro()
    assert reg.indice_columna("GR_QC") < 0 and len(t.pistas) == n
    v.rehacer()
    assert reg.indice_columna("GR_QC") >= 0 and len(t.pistas) == n + 1


def test_preferencia_plantilla_auto_desactivada(ventana):
    v = ventana
    v.prefs.plantilla_auto = False
    t = v.proyecto.plantillas[0]
    v.seleccion.fijar(pozo=0, log=0, curva="GR")
    v.acciones["qc_flags"].trigger()
    assert not any(c.nombre_x == "GR_QC" for p in t.pistas for c in p.curvas)
    v.prefs.plantilla_auto = True


def test_normalizacion_de_varios_pozos_se_deshace_de_una_vez(ventana):
    from kurvo.vista.multipozo_ui import DialogoNormalizacion
    v = ventana
    d = DialogoNormalizacion(v)
    d.ch_curva.setCurrentText("GR")
    d.calcular()
    d.aplicar()
    regs = [p.logs[0] for p in v.proyecto.pozos]
    nuevas = [r for r in regs if any(n.endswith("_NORM") for n in r.nombres())]
    assert len(nuevas) >= 2
    v.seleccion.fijar(pozo=0, log=0, curva="")
    v.deshacer()
    assert not any(n.endswith("_NORM") for r in regs for n in r.nombres())
    v.rehacer()
    assert sum(any(n.endswith("_NORM") for n in r.nombres()) for r in regs) == len(nuevas)


# ------------------------------------------------------------------ panel de propiedades
def test_panel_propiedades_muestra_y_edita_la_curva(ventana):
    v = ventana
    p = v.panel_propiedades
    v.seleccion.fijar(pozo=0, log=0, curva="GR")
    assert p.txt_nombre.text() == "GR" and p.lbl["nota"].text() and p.lbl["rango"].text()
    assert "GR" in p.lbl_titulo.text() and p.lbl["grupo"].text() == "GR"
    p.txt_nombre.setText("GR_EDIT")
    p.txt_unidad.setText("API")
    assert p.aplicar()
    reg = v.seleccion.registro()
    assert reg.indice_columna("GR_EDIT") >= 0 and reg.columna("GR_EDIT").unidad == "API"
    assert v.seleccion.curva == "GR_EDIT" and reg.historial.bitacora[-1].operacion == "Curve properties"
    p.txt_nombre.setText("SP")
    from unittest import mock
    with mock.patch("kurvo.vista.propiedades_ui.aviso") as av:
        assert not p.aplicar() and av.called                     # nombre repetido
    v.deshacer()
    assert reg.indice_columna("GR") >= 0 and reg.indice_columna("GR_EDIT") < 0
    v.seleccion.fijar(curva="GR")
    v.acciones["qc_flags"].trigger()
    v.seleccion.fijar(curva="GR_QC")
    assert "QC flag" in p.lbl["tipo"].text() or "Bandera" in p.lbl["tipo"].text()
    assert v.docks["propiedades"].objectName() == "Panel_propiedades"
    v.acciones["panel_properties"].setChecked(False)
    assert v.docks["propiedades"].isHidden()


# ------------------------------------------------------------------ QC por proyecto
def test_preferencias_qc_del_proyecto_mandan_y_se_guardan(tmp_path):
    from kurvo.nucleo import preferencias, qc
    from kurvo.nucleo.proyecto import Proyecto
    pr = proyecto_demo()
    q = preferencias.PreferenciasQC()
    q.qc.nulos_malo = 1.0
    q.rangos["GR"] = [("API", 0, 80)]
    pr.qc_ajustes = q.a_json()
    ruta = tmp_path / "p.kurvo"
    pr.guardar(ruta)
    pr2 = Proyecto.abrir(ruta)
    q2 = preferencias.PreferenciasQC.desde_json(pr2.qc_ajustes)
    assert q2.qc.nulos_malo == 1.0 and q2.rangos["GR"] == [("API", 0.0, 80.0)]
    usuario = preferencias.usuario()
    try:
        preferencias.fijar_proyecto(q2)
        assert preferencias.origen_qc() == "project" and preferencias.actual().qc.nulos_malo == 1.0
        assert qc.rango_fisico("GR", "API") == (0, 80)
        assert preferencias.actual().idioma == usuario.idioma          # el resto sigue siendo del usuario
    finally:
        preferencias.fijar_proyecto(None)
    assert preferencias.actual() is usuario and preferencias.origen_qc() == "user"
    assert preferencias.PreferenciasQC.desde_json("{roto") is None
    # un proyecto sin ajustes propios no los crea al guardar
    pr3 = proyecto_demo()
    pr3.guardar(tmp_path / "q.kurvo")
    assert Proyecto.abrir(tmp_path / "q.kurvo").qc_ajustes == ""


def test_dialogo_copia_usuario_proyecto(ventana, monkeypatch):
    from kurvo.nucleo import preferencias
    from kurvo.vista.preferencias_ui import DialogoPreferencias
    v = ventana
    d = DialogoPreferencias(v, v.prefs)
    assert not d.ck_proyecto.isChecked() and d.resultado_proyecto() is None
    d.usuario_a_proyecto()
    assert d.ck_proyecto.isChecked()
    d.sp_qc["nulos_malo"].setValue(7)
    assert d.resultado_proyecto().qc.nulos_malo == 7 and d.resultado().qc.nulos_malo == v.prefs.qc.nulos_malo
    d.proyecto_a_usuario()
    assert d.resultado().qc.nulos_malo == 7
    monkeypatch.setattr(DialogoPreferencias, "exec", lambda self: 1)
    monkeypatch.setattr(DialogoPreferencias, "resultado_proyecto", lambda self: preferencias.PreferenciasQC(
        preferencias.UmbralesQC(nulos_malo=3.0)))
    v.preferencias_usuario()
    try:
        assert v.proyecto.qc_ajustes and v.proyecto.modificado
        assert preferencias.origen_qc() == "project" and preferencias.actual().qc.nulos_malo == 3.0
        d2 = DialogoPreferencias(v, v.prefs, preferencias.proyecto(), "demo.kurvo")
        assert d2.ck_proyecto.isChecked() and d2.sp_qc["nulos_malo"].value() == 3.0
        assert "demo.kurvo" in d2.lbl_origen.text()
    finally:
        v.proyecto.qc_ajustes = ""
        v.sincronizar_qc_proyecto()
    assert preferencias.origen_qc() == "user"


# ------------------------------------------------------------------ rendimiento
def test_mediana_rapida_igual_a_numpy():
    import warnings
    from kurvo.nucleo.edicion import nanmediana_filas
    rng = np.random.default_rng(0)
    for forma in ((500, 11), (300, 55), (40, 4), (1, 7)):
        v = rng.normal(size=forma).round(1)
        v[rng.random(forma) < 0.15] = np.nan
        v[:1] = np.nan
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            esperado = np.nanmedian(v, axis=1)
        assert np.array_equal(nanmediana_filas(v), esperado, equal_nan=True)


def test_tramos_vectorizados():
    from kurvo.nucleo import qc
    from kurvo.nucleo.edicion import huecos
    d = np.array([1, 1, 1, NULO, NULO, 2, 2, 3, 3, 3, 3, NULO, 5], float)
    assert huecos(d) == [(3, 4), (11, 11)]
    assert qc.tramos_planos(d, 3) == [(0, 2), (7, 10)]
    assert qc.tramos_planos(d, 1) == [(0, 2), (5, 6), (7, 10), (12, 12)]


def test_rendimiento_proyecto_grande(qapp, tmp_path):
    """12 pozos × 20 000 muestras × 15 curvas (la medición completa de 50 pozos está en
    tests/medir_rendimiento.py (D89–D91)."""
    import time
    from kurvo.demo import proyecto_grande
    from kurvo.nucleo import qc
    from kurvo.nucleo.proyecto import Proyecto
    from kurvo.vista.ventana import VentanaPrincipal
    pr = proyecto_grande(12, 20000, 15)
    t0 = time.perf_counter()
    pr.guardar(tmp_path / "g.kurvo")
    pr = Proyecto.abrir(tmp_path / "g.kurvo")
    assert time.perf_counter() - t0 < 8
    assert pr.pozos[3].logs[0].n_filas == 20000 and pr.pozos[3].logs[0].n_columnas == 15
    v = VentanaPrincipal()
    try:
        v.proyecto = pr
        qc.invalidar()
        t0 = time.perf_counter()
        v.refrescar_todo()
        assert time.perf_counter() - t0 < 8
        otro = v._buscar_nodo(("log", 7, 0))
        hijos = [otro.child(k) for k in range(otro.childCount())]
        v.seleccion.fijar(pozo=2, log=0, curva="GR")
        v.pestanas.setCurrentWidget(v.editor_logs)
        m = v.editor_logs.modelo
        t0 = time.perf_counter()
        m.setData(m.index(5, 2), "77")
        assert time.perf_counter() - t0 < 2
        assert pr.pozos[2].logs[0].columnas[2].datos[5] == 77
        # solo se rehízo el nodo del registro editado: los demás nodos son los mismos objetos
        assert v._buscar_nodo(("log", 7, 0)) is otro and [otro.child(k) for k in range(otro.childCount())] == hijos
        editado = v._buscar_nodo(("log", 2, 0))
        assert any("curve_edited" in str(editado.child(k).toolTip(0)) or "edited" in editado.child(k).toolTip(0)
                   for k in range(editado.childCount()))
    finally:
        v.proyecto.modificado = False
        v.close()


# ------------------------------------------------------------------ interfaz (punto 7)
def test_ribbon_en_espanol_cabe_a_1600(qapp, tmp_path):
    from kurvo.nucleo import preferencias
    from kurvo.vista.ventana import VentanaPrincipal, aplicar_idioma, guardar_preferencias
    guardar_preferencias(preferencias.Preferencias(idioma="es"))
    try:
        v = VentanaPrincipal()
        v.resize(1600, 960)
        v.show()
        qapp.processEvents()
        for i in range(v.ribbon.count()):
            area = v.ribbon.widget(i)
            assert area.widget().sizeHint().width() <= 1590, v.ribbon.tabText(i)
        b = v.ribbon.botones["Standardize Mnemonics"]
        assert b.text() == "Mnemónicos" and "Estandarizar" in b.toolTip()       # corto en el botón, completo en la ayuda
        v.acciones["mnemonics"].setEnabled(False)
        assert b.text() == "Mnemónicos"
        v.close()
    finally:
        guardar_preferencias(preferencias.Preferencias())
        aplicar_idioma("en")


def test_marcas_compactas_no_superponen_numeros():
    from kurvo.vista.qc_ui import marcas_compactas
    m = marcas_compactas(-3.2, 351.0, 2)
    assert 2 <= len(m) <= 3 and all(-3.2 <= v <= 351 for v, _ in m)
    assert [t for _, t in marcas_compactas(0.0, 1.0, 3)] == ["0", "0.5", "1"]
    assert [t for _, t in marcas_compactas(-0.7, 3.3, 3, log=True)] == ["10", "1000"]
    assert marcas_compactas(8.5, 8.5, 3) == [(8.5, "8.5")] and marcas_compactas(2.0, 1.0, 3) == []


def test_unidad_de_profundidad_por_defecto(ventana, tmp_path, monkeypatch):
    from kurvo.vista import ventana as V
    ruta = tmp_path / "sin_unidad.las"
    ruta.write_text("~V\nVERS. 2.0:\nWRAP. NO:\n~W\nWELL. X1:\n~C\nDEPT. :\nGR.API :\n~A\n100 50\n100.5 55\n101 60\n",
                    encoding="ascii")
    monkeypatch.setattr(V, "pedir", lambda t, campos, *a, **k: {"md": campos[0].defecto, "tvd": "(none)"})
    ventana.prefs.unidad_prof = "FT"
    try:
        reg = ventana.importar_las(None, str(ruta))
    finally:
        ventana.prefs.unidad_prof = "M"
    assert reg.columna("DEPT").unidad == "FT"
    assert reg.historial.bitacora[-1].operacion == "Import: default depth unit"


def test_tema_oscuro_y_claro(qapp):
    import pyqtgraph as pg
    from PySide6.QtGui import QPalette
    from kurvo.nucleo import preferencias
    from kurvo.vista.ventana import aplicar_tema
    assert preferencias.Preferencias.desde_json(preferencias.Preferencias(tema="dark", unidad_prof="FT").a_json()).tema == "dark"
    try:
        aplicar_tema("dark")
        assert qapp.palette().color(QPalette.Window).lightness() < 80
        assert pg.getConfigOption("background") != "w"
    finally:
        aplicar_tema("light")
        pg.setConfigOptions(background="w", foreground="k")
    assert qapp.palette().color(QPalette.Window).lightness() > 180


# ------------------------------------------------------------------ pendientes heredados (punto 8)
def test_desfase_automatico_recalcula_la_tvd():
    from kurvo.nucleo import multipozo
    pr = proyecto_demo()
    pozo = pr.pozos[2]
    reg = pozo.logs[0]
    md0 = reg.columna("DEPT").datos.copy()
    assert multipozo.desplazar_registro(reg, 2.5, pozo.trayectoria)
    md = reg.columna("DEPT").datos
    assert np.allclose(md, md0 + 2.5)
    tvd = reg.columnas[reg.indice_tvd].datos
    assert np.allclose(tvd[::50], [pozo.trayectoria.tvd_en(x) for x in md[::50]])
    otro = proyecto_demo().pozos[0].logs[0]
    antes = otro.columnas[otro.indice_tvd].datos.copy()
    assert not multipozo.desplazar_registro(otro, 1.0)              # sin trayectoria la TVD no se toca
    assert np.array_equal(otro.columnas[otro.indice_tvd].datos, antes)
