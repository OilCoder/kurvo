"""Pruebas de la ventana principal con capturas en docs/capturas."""
import numpy as np
import pytest

from kurvo.demo import proyecto_demo


@pytest.fixture()
def ventana(qapp, tmp_path):
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    v.proyecto = proyecto_demo()
    v.proyecto.ruta = str(tmp_path / "demo.kurvo")
    v.refrescar_todo()
    v.resize(1400, 900)
    v.show()
    yield v
    v.proyecto.modificado = False
    v.close()


def test_estructura_ribbon_y_pestanas(ventana):
    # siete pasos del trabajo arriba (D123); lo demás, en la franja general
    assert [ventana.ribbon.tabText(i) for i in range(ventana.ribbon.count())] == [
        "1 · Prepare", "2 · Review", "3 · Correct", "4 · Align and Compare", "5 · Reconstruct", "6 · Check",
        "7 · Deliver"]
    for b in ("Import LAS", "Composite Well Log", "Validate LAS", "Quality Control", "Despike", "Advance Calculator",
              "Trajectory", "Normalize Wells", "Deep Learning", "QC Report", "Export LAS", "Print"):
        assert b in ventana.ribbon.botones
    en_franja = {a.objectName() for b, _ in ventana.franja.menus for a in b.menu().actions()}
    for clave in ("open", "save_as", "close_project", "exit", "settings", "grouping",
                  "plugins", "help", "about", "diagnostic", "examples", "start_page", "view_templates"):
        assert f"accion_{clave}" in en_franja
    nombres = [ventana.pestanas.tabText(i) for i in range(ventana.pestanas.count())]
    assert nombres[:7] == ["Log Plot", "Cross Section", "Data Table", "Trajectory", "Formation Tops", "Lithology",
                           "Completion"]
    assert "Templates" not in nombres          # la plantilla se edita desde el gráfico, en su ventana
    assert "Pickett Plot" in nombres and "Hingle Plot" in nombres
    assert {m.nombre for m in ventana.modulos} >= {"Advance Log Analysis", "Depth Shifting", "Quick Plot",
                                                   "Pickett Plot", "Hingle Plot", "Deep Learning",
                                                   "Quality Control"}


def test_arbol_y_operaciones(ventana):
    raiz = ventana.arbol.topLevelItem(0)
    assert raiz.childCount() == 3 and raiz.child(0).text(0) == "DEMO-1"
    pr = ventana.proyecto
    prof = pr.zonas[0].profundidades[:]
    ventana._mover(("pozo", 0), 1)
    assert pr.pozos[1].nombre == "DEMO-1" and pr.zonas[0].profundidades == [prof[1], prof[0], prof[2]]
    ventana._duplicar(("plantilla", 0))
    assert len(pr.plantillas) == 2 and pr.plantillas[1].nombre != pr.plantillas[0].nombre
    assert ventana.arbol.topLevelItem(2).childCount() == 2


def test_editor_logs_crear_tvd_y_calculos(ventana):
    ed = ventana.editor_logs
    ed.mostrar(0, 0)
    reg = ed.registro()
    n = reg.n_columnas
    ed.crear_tvd()
    assert reg.n_columnas == n + 1 and reg.indice_tvd == n
    t = ventana.proyecto.pozos[0].trayectoria
    assert reg.columnas[n].datos[100] == pytest.approx(t.tvd_en(reg.columnas[0].datos[100]))
    from kurvo.modulos.base import agregar_resultado
    agregar_resultado(ventana, "X", np.ones(reg.n_filas))
    assert ed.modelo.columnCount() == n + 2


def test_guardar_y_abrir(ventana, tmp_path):
    assert ventana.guardar()
    from kurvo.nucleo.proyecto import Proyecto
    assert len(Proyecto.abrir(ventana.proyecto.ruta).pozos) == 3
    assert ventana.abrir(ventana.proyecto.ruta)


def test_capturas_de_pestanas(ventana, capturas, qapp):
    nombres = {"Trajectory": "gui_trayectoria", "Data Table": "gui_editor_logs",
               "Formation Tops": "gui_zonas", "Templates": "gui_plantillas", "Log Plot": "gui_logplot",
               "Cross Section": "gui_corte", "Pickett Plot": "gui_pickett"}
    ventana.pagina_corte.ch_zona.setCurrentIndex(2)
    for i in range(ventana.pestanas.count()):
        t = ventana.pestanas.tabText(i)
        if t in nombres:
            ventana.mostrar_vista(next(k for k, w in ventana.vistas.items() if w is ventana.pestanas.widget(i)))
            qapp.processEvents()
            img = ventana.grab()
            assert img.width() > 1000
            img.save(str(capturas / f"{nombres[t]}.png"))
    d = ventana.editar_plantilla()
    qapp.processEvents()
    d.grab().save(str(capturas / "gui_plantillas.png"))
    d.close()


def test_modulos_desde_editor_de_logs(ventana, monkeypatch):
    from kurvo.calculos import petrofisica as pf
    from kurvo.modulos import calculator, varios
    ed = ventana.editor_logs
    ed.mostrar(0, 0)
    reg = ed.registro()
    ed.columna_clic = reg.indice_columna("GR")
    mod = next(m for m in ventana.modulos if m.nombre == "Advance Log Analysis")
    menu = dict(mod.acciones_editor_logs(ventana))
    assert [t for t, _ in menu["Sw"]][0] == "Archie Formula"
    monkeypatch.setattr(calculator, "pedir", lambda *a, **k: {
        "x": reg.indice_columna("GR"), "lim": 30.0, "sh": 100.0, "nombre": "VSH_GR", "limitar": True})
    mod._ejecutar(ventana, "gr")
    np.testing.assert_allclose(reg.columna("VSH_GR").datos,
                               pf.vsh_indice(reg.columna("GR").datos, 30, 100, True))
    monkeypatch.setattr(varios, "pedir", lambda *a, **k: {
        "col": 0, "shift": 2.5, "nueva": True, "nombre": "DEPT_SH"})
    next(m for m in ventana.modulos if m.nombre == "Depth Shifting").ejecutar(ventana)
    np.testing.assert_allclose(reg.columna("DEPT_SH").datos, reg.columna("DEPT").datos + 2.5)
