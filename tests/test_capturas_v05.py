"""Capturas de la versión 0.5 en docs/capturas (gui_v05_*), en inglés y en español, con los LAS reales
del campo El Dorado (data/, no versionada): importación de la carpeta, plantilla Standard con los
topes de formación, validación de unidades y nulos, y el tablero de QC del campo. Se revisan a mano."""
from pathlib import Path

import pytest

CAMPO = Path(__file__).resolve().parents[1] / "data" / "El Dorado"
POZO = "Bloir 'A' 32"


def _esperar(qapp, n=6):
    for _ in range(n):
        qapp.processEvents()


@pytest.mark.skipif(not CAMPO.exists(), reason="data/El Dorado (LAS reales del KGS) no está")
@pytest.mark.parametrize("idioma", ["en", "es"])
def test_capturas_v05(qapp, tmp_path, capturas, idioma, monkeypatch):
    import pyqtgraph as pg
    from kurvo.nucleo import preferencias
    from kurvo.vista import ventana as V
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    V.guardar_preferencias(preferencias.Preferencias(idioma=idioma))
    monkeypatch.setattr(V, "aviso", lambda *a, **k: None)
    v = V.VentanaPrincipal()
    v.resize(1600, 960)
    v.show()
    try:
        v.importar_carpeta_las(str(CAMPO))
        pr = v.proyecto
        i = pr.indice_pozo(POZO)
        assert i >= 0 and pr.plantillas and pr.plantillas[0].nombre == "Standard"
        # ------------------------------------------------ ventana principal: árbol, log plot y propiedades
        v.seleccion.fijar(pozo=i, log=0, curva="DCAL")
        v.pestanas.setCurrentWidget(v.pagina_logplot)
        v.pagina_logplot.seguir_seleccion()
        v.mostrar_panel("propiedades")
        _esperar(qapp)
        v.grab().save(str(capturas / f"gui_v05_principal_{idioma}.png"))
        img = v.pagina_logplot.plot_actual().imagen()
        assert img.save(str(capturas / f"gui_v05_logplot_topes_{idioma}.png"))
        # ------------------------------------------------ ribbon con Import LAS Folder
        v.ribbon.setCurrentIndex(1)
        _esperar(qapp)
        v.ribbon.grab().save(str(capturas / f"gui_v05_ribbon_importar_{idioma}.png"))
        # ------------------------------------------------ validación: nulos no declarados y unidades
        from kurvo.vista.validacion_ui import DialogoValidacion
        d = DialogoValidacion(v.editor_logs, pr.pozos[i].logs[0])
        d.resize(1000, 520)
        d.show()
        _esperar(qapp, 4)
        d.grab().save(str(capturas / f"gui_v05_validacion_{idioma}.png"))
        d.close()
        # ------------------------------------------------ tablero de QC del campo
        dock = v.docks["qc"]
        v.mostrar_panel("qc")
        dock.setFloating(True)
        dock.resize(1400, 820)
        v.panel_qc.ir_a("dashboard")
        _esperar(qapp)
        dock.grab().save(str(capturas / f"gui_v05_dashboard_campo_{idioma}.png"))
        dock.setFloating(False)
    finally:
        v.proyecto.modificado = False
        v.close()
        V.guardar_preferencias(preferencias.Preferencias())
        V.aplicar_idioma("en")


CUTTER = Path(__file__).resolve().parents[1] / "data" / "Cutter"


@pytest.mark.skipif(not CUTTER.exists(), reason="data/Cutter (LAS reales del KGS) no está")
@pytest.mark.parametrize("idioma", ["en", "es"])
def test_capturas_v05_compuesto(qapp, tmp_path, capturas, idioma, monkeypatch):
    """Composite Well Log (D110): Katie 1-28 llega en 5 archivos (ILD, RHOB, ILD, DT+GR, DT); el compuesto
    las muestra juntas en la plantilla Standard, con las dos pasadas de DT."""
    import pyqtgraph as pg
    from kurvo.nucleo import operaciones, preferencias
    from kurvo.vista import ventana as V
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    V.guardar_preferencias(preferencias.Preferencias(idioma=idioma))
    monkeypatch.setattr(V, "aviso", lambda *a, **k: None)
    v = V.VentanaPrincipal()
    v.resize(1600, 960)
    v.show()
    try:
        v.importar_varios_las(sorted(str(p) for p in CUTTER.rglob("Katie_1-28*.las")))
        pr = v.proyecto
        i = pr.indice_pozo("Katie 1-28")
        assert i >= 0 and len(pr.pozos[i].logs) == 5
        pr.pozos[i].logs.append(operaciones.componer(pr.pozos[i].logs))
        v._tras_cambio()
        v.seleccion.fijar(pozo=i, log=5, curva="DT_2")
        v.pestanas.setCurrentWidget(v.pagina_logplot)
        v.pagina_logplot.seguir_seleccion()
        lp = v.pagina_logplot.estado()                   # el log plot empieza en 0 (pendiente 23): el tramo con datos
        lp.usar_prof_propia, lp.prof_tope, lp.prof_base = True, 3800.0, 4700.0
        v.pagina_logplot._al_lp()
        v.mostrar_panel("propiedades")
        v.ribbon.setCurrentIndex(2)
        _esperar(qapp)
        v.grab().save(str(capturas / f"gui_v05_compuesto_{idioma}.png"))
    finally:
        v.proyecto.modificado = False
        v.close()
        V.guardar_preferencias(preferencias.Preferencias())
        V.aplicar_idioma("en")
