"""Capturas de la 1.0 en docs/capturas (gui_v10_*), en inglés y en español, para el manual y las guías de
los dos ejemplos: pantalla de inicio, barra de cada paso, gráficos y cortes de El Dorado y Cutter. Los
proyectos se arman con los archivos de docs/ejemplos (tests/ejemplos_docs.py). Se revisan a mano."""
import pytest

from ejemplos_docs import armar


def _esperar(qapp, n=6):
    for _ in range(n):
        qapp.processEvents()


def _ventana(idioma, monkeypatch):
    import pyqtgraph as pg
    from kurvo.nucleo import preferencias
    from kurvo.vista import ventana as V
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    V.guardar_preferencias(preferencias.Preferencias(idioma=idioma))
    monkeypatch.setattr(V, "aviso", lambda *a, **k: None)
    v = V.VentanaPrincipal()
    v.resize(1600, 960)
    v.show()
    return v


def _cerrar(v):
    from kurvo.nucleo import preferencias
    from kurvo.vista import ventana as V
    v.proyecto.modificado = False
    v.close()
    V.guardar_preferencias(preferencias.Preferencias())
    V.aplicar_idioma("en")


def _grafico(v, qapp, pozo, tope, base, archivo, log=0):
    pr = v.proyecto
    i = pr.indice_pozo(pozo)
    v.seleccion.fijar(pozo=i, log=log, curva="")
    v.mostrar_vista("logplot")
    v.pagina_logplot.seguir_seleccion()
    lp = v.pagina_logplot.estado()
    p = pr.pozos[i]
    lp.lito = 0 if p.litologias else -1
    lp.comp = 0 if p.completaciones else -1
    lp.usar_prof_propia, lp.prof_tope, lp.prof_base = True, tope, base
    v.pagina_logplot._al_lp()
    _esperar(qapp)
    assert v.pagina_logplot.plot_actual().imagen().save(archivo)


def _plantilla_con_completacion(pr):
    from kurvo.nucleo.plantilla import PISTA_COMPLETACION
    t = pr.plantillas[0]
    if not any(p.tipo == PISTA_COMPLETACION for p in t.pistas):
        c = t.nueva_pista(PISTA_COMPLETACION)
        c.ancho, c.ancho_comp = 110.0, 90.0


@pytest.mark.parametrize("idioma", ["en", "es"])
def test_capturas_v10_inicio_y_pasos(qapp, tmp_path, capturas, idioma, monkeypatch):
    v = _ventana(idioma, monkeypatch)
    try:
        _esperar(qapp)
        v.grab().save(str(capturas / f"gui_v10_inicio_{idioma}.png"))
        armar(v, "el_dorado", tmp_path / "las", monkeypatch)
        for paso in range(v.ribbon.count()):
            v.ribbon.setCurrentIndex(paso)
            _esperar(qapp, 3)
            v.menuWidget().grab().save(str(capturas / f"gui_v10_paso{paso + 1}_{idioma}.png"))
        v.ribbon.setCurrentIndex(0)
        v.seleccion.fijar(pozo=v.proyecto.indice_pozo("Barnhill 'A' 31"), log=0, curva="")
        v.mostrar_vista("logplot")
        _esperar(qapp)
        v.grab().save(str(capturas / f"gui_v10_principal_{idioma}.png"))
        v.ribbon.setCurrentIndex(1)
        v.acciones["qc_window"].trigger()
        _esperar(qapp)
        v.grab().save(str(capturas / f"gui_v10_qc_{idioma}.png"))
        v.ribbon.setCurrentIndex(3)
        v.seleccion.fijar(pozo=v.proyecto.indice_pozo("Bloir 'A' 33"), log=0, curva="")
        v.editor_tray.ch_pozo.setCurrentIndex(v.proyecto.indice_pozo("Bloir 'A' 33"))
        v.mostrar_vista("tray")
        _esperar(qapp)
        v.grab().save(str(capturas / f"gui_v10_trayectoria_{idioma}.png"))
    finally:
        _cerrar(v)


@pytest.mark.parametrize("idioma", ["en", "es"])
def test_capturas_v10_el_dorado(qapp, tmp_path, capturas, idioma, monkeypatch):
    v = _ventana(idioma, monkeypatch)
    try:
        pr = armar(v, "el_dorado", tmp_path / "las", monkeypatch)
        _plantilla_con_completacion(pr)
        _grafico(v, qapp, "Barnhill 'A' 31", 2280.0, 2490.0, str(capturas / f"gui_v10_eldorado_barnhill_{idioma}.png"))
        _grafico(v, qapp, "Hess 'A' 34", 2450.0, 2730.0, str(capturas / f"gui_v10_eldorado_hess34_{idioma}.png"))
        # corte en TVDSS con todos los pozos: los que no tienen trayectoria se declaran verticales de una vez
        v.ribbon.setCurrentIndex(3)
        v.mostrar_vista("corte")
        pc = v.pagina_corte
        from kurvo.nucleo.proyecto import PozoCorte
        linea = ["Hull Higgins 'A' 28", "Enyart 'A' 115", "Bloir 'A' 33", "Bloir 'A' 32", "Hess 'A' 34", "Koogler 'A' 301"]
        pr.corte.pozos = [PozoCorte(n, pr.indice_pozo(n)) for n in linea]      # de norte a sur
        pc.refrescar()
        assert pc.preparar_tvd(1, preguntar=lambda: True)
        pr.corte.modo_prof_global = 1
        pr.corte.zona_aplanar = -1
        pr.corte.zonas_visibles = [z.nombre in ("Heebner", "Lansing", "Kansas City", "Cherokee", "Viola", "Simpson",
                                                "Arbuckle") for z in pr.zonas]
        pc.refrescar()
        _esperar(qapp)
        assert pc.lienzo.imagen().save(str(capturas / f"gui_v10_eldorado_corte_{idioma}.png"))
    finally:
        _cerrar(v)


@pytest.mark.parametrize("idioma", ["en", "es"])
def test_capturas_v10_cutter(qapp, tmp_path, capturas, idioma, monkeypatch):
    from kurvo.nucleo import operaciones
    v = _ventana(idioma, monkeypatch)
    try:
        pr = armar(v, "cutter", tmp_path / "las", monkeypatch)
        _plantilla_con_completacion(pr)
        sara = pr.pozos[pr.indice_pozo("Sara 1-28")]
        sara.logs.insert(0, operaciones.componer(sara.logs, "Composite"))     # 1 · Preparar › Compuesto
        v.refrescar_todo()
        _grafico(v, qapp, "Sara 1-28", 5350.0, 5750.0, str(capturas / f"gui_v10_cutter_sara_{idioma}.png"))
        wiu = "CUTTER W I UNIT (CUTTER KGS 1) 9"
        log = next(k for k, r in enumerate(pr.pozos[pr.indice_pozo(wiu)].logs) if "triple" in r.nombre.lower())
        _grafico(v, qapp, wiu, 7200.0, 7740.0, str(capturas / f"gui_v10_cutter_basamento_{idioma}.png"), log=log)
    finally:
        _cerrar(v)
