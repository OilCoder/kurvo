"""Capturas de la versión 0.4 en docs/capturas (gui_v04_*), en inglés y en español: curvas nuevas en
la plantilla, panel de propiedades, deshacer de varios pozos, configuración (tema oscuro, unidad,
QC del proyecto), ribbon a 1600 px, Depth view con datos realistas, tema oscuro y los diálogos con
iconos. Se revisan a mano."""
from pathlib import Path

import pytest

from kurvo.demo import proyecto_demo

REALISTAS = Path(__file__).resolve().parents[1] / "datos" / "realistas"


def _ventana(qapp, tmp_path, idioma="en", tema="light"):
    import pyqtgraph as pg
    from kurvo.nucleo import preferencias
    from kurvo.vista.ventana import VentanaPrincipal, guardar_preferencias
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    guardar_preferencias(preferencias.Preferencias(idioma=idioma, tema=tema))
    v = VentanaPrincipal()
    v.proyecto = proyecto_demo()
    v.refrescar_todo()
    v.resize(1600, 960)
    v.show()
    qapp.processEvents()
    return v


def _cerrar(v):
    from kurvo.nucleo import preferencias
    from kurvo.vista.ventana import aplicar_idioma, aplicar_tema, guardar_preferencias
    v.proyecto.modificado = False
    v.close()
    guardar_preferencias(preferencias.Preferencias())
    aplicar_idioma("en")
    aplicar_tema("light")


def _esperar(qapp, n=6):
    for _ in range(n):
        qapp.processEvents()


def _normalizar_y_banderas(v):
    from kurvo.vista.multipozo_ui import DialogoNormalizacion
    d = DialogoNormalizacion(v)
    d.ch_curva.setCurrentText("GR")
    d.ch_ref.setCurrentIndex(1)
    d.calcular()
    d.aplicar()
    d.close()
    v.seleccion.fijar(pozo=0, log=0, curva="GR")
    v.acciones["qc_flags"].trigger()


@pytest.mark.parametrize("idioma", ["en", "es"])
def test_capturas_v04(qapp, tmp_path, capturas, idioma):
    v = _ventana(qapp, tmp_path, idioma)
    try:
        # ------------------------------------------------ curvas nuevas en la plantilla y propiedades
        _normalizar_y_banderas(v)
        v.pestanas.setCurrentWidget(v.pagina_logplot)
        v.pagina_logplot.ck_escala.setChecked(True)
        v.pagina_logplot.sp_escala.setValue(600)
        v.mostrar_panel("propiedades")
        v.seleccion.fijar(pozo=0, log=0, curva="GR_NORM")
        _esperar(qapp)
        v.grab().save(str(capturas / f"gui_v04_principal_{idioma}.png"))
        img = v.pagina_logplot.plot_actual().imagen()       # el log plot entero, con la pista de banderas
        assert img.save(str(capturas / f"gui_v04_plantilla_curvas_nuevas_{idioma}.png"))
        v.docks["propiedades"].grab().save(str(capturas / f"gui_v04_propiedades_{idioma}.png"))
        # ------------------------------------------------ deshacer de una vez en los tres pozos
        v.mostrar_panel("historial")
        v.seleccion.fijar(pozo=0, log=0, curva="GR")
        v.acciones["undo"].trigger()                        # la bandera QC del pozo 0
        v.seleccion.fijar(pozo=2, log=0, curva="GR")
        v.acciones["undo"].trigger()                        # la normalización, en los tres pozos de una vez
        _esperar(qapp)
        assert not any(n.endswith("_NORM") for p in v.proyecto.pozos for r in p.logs for n in r.nombres())
        v.grab().save(str(capturas / f"gui_v04_deshacer_varios_{idioma}.png"))
        # ------------------------------------------------ ribbon de Mantenimiento a 1600 px
        v.ribbon.setCurrentIndex(1)
        _esperar(qapp)
        v.ribbon.grab().save(str(capturas / f"gui_v04_ribbon_mantenimiento_{idioma}.png"))
        # ------------------------------------------------ configuración
        from kurvo.nucleo import preferencias
        from kurvo.vista.preferencias_ui import DialogoPreferencias
        d = DialogoPreferencias(v, preferencias.Preferencias(idioma=idioma, tema="dark", unidad_prof="FT"))
        d.show()
        _esperar(qapp)
        d.grab().save(str(capturas / f"gui_v04_preferencias_{idioma}.png"))
        d.tabs.setCurrentIndex(1)
        d.usuario_a_proyecto()
        _esperar(qapp)
        d.grab().save(str(capturas / f"gui_v04_preferencias_qc_proyecto_{idioma}.png"))
        d.close()
        # ------------------------------------------------ Depth view con datos realistas
        from kurvo.vista import ventana as V
        pedir = V.pedir
        V.pedir = lambda titulo, campos, *a, **k: {"md": campos[0].defecto, "tvd": "(none)"}
        try:
            v.importar_las(None, str(REALISTAS / "PZ-101_main.las"))
        finally:
            V.pedir = pedir
        v.seleccion.fijar(curva="GRC")
        dock = v.docks["qc"]
        dock.setFloating(True)
        dock.resize(1200, 820)
        v.panel_qc.ir_a("depth")
        v.panel_qc.seguir_seleccion()
        _esperar(qapp)
        dock.grab().save(str(capturas / f"gui_v04_qc_depth_realista_{idioma}.png"))
        dock.setFloating(False)
    finally:
        _cerrar(v)


def test_capturas_tema_oscuro(qapp, tmp_path, capturas):
    for idioma in ("en", "es"):
        v = _ventana(qapp, tmp_path, idioma, "dark")
        try:
            v.seleccion.fijar(pozo=0, log=0, curva="GR")
            v.pestanas.setCurrentWidget(v.pagina_logplot)
            v.panel_qc.ir_a("depth")
            v.panel_qc.seguir_seleccion()
            _esperar(qapp)
            v.grab().save(str(capturas / f"gui_v04_tema_oscuro_{idioma}.png"))
        finally:
            _cerrar(v)


def test_capturas_dialogos_con_iconos(qapp, tmp_path, capturas):
    """Los diálogos con los iconos de v0.3 (las capturas que quedaron fuera de docs/capturas)."""
    from kurvo.modulos.control_calidad import DialogoReporteQC
    from kurvo.vista.edicion_curvas import DialogoHistorial
    from kurvo.vista.multipozo_ui import DialogoDesfaseAuto, DialogoLote, DialogoNormalizacion
    from kurvo.vista.validacion_ui import DialogoValidacion
    from kurvo.vista.ventana import DialogoCalculadora
    for idioma in ("en", "es"):
        v = _ventana(qapp, tmp_path, idioma)
        try:
            _normalizar_y_banderas(v)
            reg = v.seleccion.registro()
            dialogos = {"validacion": DialogoValidacion(v.editor_logs, reg), "normalizacion": DialogoNormalizacion(v),
                        "desfase": DialogoDesfaseAuto(v), "lote": DialogoLote(v), "reporte_qc": DialogoReporteQC(v),
                        "calculadora": DialogoCalculadora(reg, v), "bitacora": DialogoHistorial(v.editor_logs, reg)}
            dialogos["normalizacion"].calcular()
            dialogos["desfase"].calcular()
            for nombre, d in dialogos.items():
                d.show()
                _esperar(qapp, 4)
                d.grab().save(str(capturas / f"gui_v04_dialogo_{nombre}_{idioma}.png"))
                d.close()
            dl = v.deep_learning()
            if dl is not None:
                w = dl.window() if hasattr(dl, "window") else dl
                _esperar(qapp, 4)
                w.grab().save(str(capturas / f"gui_v04_dialogo_deep_learning_{idioma}.png"))
                w.close()
        finally:
            _cerrar(v)
