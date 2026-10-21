"""Capturas de la versión 0.3 en docs/capturas (ventana en inglés y en español, panel de QC con cada
pestaña, tablero, diálogos con los iconos nuevos y lámina de iconos). Se revisan a mano."""
import numpy as np
import pytest

from kurvo.demo import proyecto_demo
from kurvo.nucleo.comun import NULO


def proyecto_capturas():
    """Demo con curvas de condición de pozo, una pasada repetida y una curva editada."""
    from kurvo.nucleo import edicion, historial
    pr = proyecto_demo()
    rng = np.random.default_rng(3)
    reg = pr.pozos[0].logs[0]
    md = reg.columna("DEPT").datos
    cali = 8.5 + rng.normal(0, 0.08, len(md))
    cali[(md > 380) & (md < 410)] += 2.2                     # derrumbe
    drho = rng.normal(0, 0.03, len(md))
    drho[(md > 380) & (md < 410)] += 0.2
    reg.columna("DT").datos[(md > 500) & (md < 560)] = NULO       # hueco que reconstruye el DL
    reg.agregar_columna("CALI", np.round(cali, 3), "IN")
    reg.agregar_columna("BS", np.full(len(md), 8.5), "IN")
    reg.agregar_columna("DRHO", np.round(drho, 3), "G/C3")
    rep = reg.copia() if hasattr(reg, "copia") else None
    rep.nombre = "Registro DEMO-1 REP"
    rep.columna("DEPT").datos = md + 0.25
    for n in ("GR", "RHOB", "NPHI"):
        c = rep.columna(n)
        c.datos = np.where(c.datos != NULO, c.datos + rng.normal(0, 2 if n == "GR" else 0.01 if n == "RHOB" else 0.6,
                                                                   len(md)), NULO)
    sel = (md >= 300) & (md < 600)
    for c in rep.columnas:
        c.datos = c.datos[sel]
    pr.pozos[0].logs.append(rep)
    t = pr.plantillas[0]                                         # pista para ver la banda DL
    pista = t.nueva_pista()
    pista.ancho = 130
    c = t.nueva_curva(pista, "DT_FILL")
    c.color, c.escala_min, c.escala_max = "rgb(0, 140, 140)", 40, 120
    gr = reg.columna("GR")
    gr.datos[[200, 420, 610]] = [480.0, 5.0, 900.0]               # picos para el QC
    historial.aplicar(reg, "Despike", "window 11, 4 sigma, median", lambda: setattr(
        gr, "datos", edicion.quitar_picos(gr.datos, md, 11, 4.0, "median")[0]))
    return pr


@pytest.fixture()
def ventana(qapp, tmp_path):
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    v.proyecto = proyecto_capturas()
    v.refrescar_todo()
    v.resize(1600, 960)
    v.show()
    yield v
    v.proyecto.modificado = False
    v.close()


def _reconstruir(v):
    """Reconstrucción DL real (pocas épocas, CPU) para las capas del Log Plot, si hay PyTorch."""
    from kurvo.aprendizaje import redes
    if not redes.torch_disponible():
        return False
    d = v.deep_learning()
    d.sp_epocas.setValue(4)
    d.sp_largo.setValue(64)
    d.sp_mc.setValue(4)
    d.chk_cpu.setChecked(True)
    d.entrenar(sincrono=True)
    d.predecir()
    d.close()
    return True


def _vista_principal(v, qapp, capturas, nombre):
    v.ribbon.setCurrentIndex(1)
    v.pestanas.setCurrentWidget(v.pagina_logplot)
    for ck in (v.pagina_logplot.ck_qc, v.pagina_logplot.ck_dl, v.pagina_logplot.ck_orig):
        ck.setChecked(True)
    v.seleccion.fijar(pozo=0, log=0, curva="GR")
    v.mostrar_panel("qc")
    v.panel_qc.ir_a("summary")
    for _ in range(3):
        qapp.processEvents()
    img = v.grab()
    img.save(str(capturas / nombre))
    return img


def test_capturas_principal_y_qc(ventana, capturas, qapp):
    v = ventana
    _reconstruir(v)
    _vista_principal(v, qapp, capturas, "gui_v03_principal_en.png")
    plot = v.pagina_logplot.plot_actual()
    assert plot.d.capas == frozenset({"qc", "dl", "original"})
    plot.imagen(0.8).save(str(capturas / "gui_v03_logplot_capas.png"))
    # panel de QC como ventana flotante, una captura por pestaña
    dock = v.docks["qc"]
    dock.setFloating(True)
    dock.resize(1150, 800)
    v.seleccion.fijar(pozo=0, log=0, curva="GR")
    for clave in v.panel_qc.claves:
        if clave == "crossplot":
            v.seleccion.fijar(curva="NPHI")
        elif clave == "before_after":
            v.seleccion.fijar(curva="GR")
        v.panel_qc.ir_a(clave)
        if clave == "depth":
            v.panel_qc.ck_maha.setChecked(True)
        for _ in range(3):
            qapp.processEvents()
        img = dock.grab()
        assert img.width() > 900
        img.save(str(capturas / f"gui_v03_qc_{clave}.png"))
    assert not any("QC panel:" in d for d in v.diagnostico), v.diagnostico
    dock.setFloating(False)


def test_capturas_dialogos(ventana, capturas, qapp):
    from kurvo.vista.dialogos import Campo, DialogoParametros
    from kurvo.vista.multipozo_ui import DialogoDesfaseAuto, DialogoNormalizacion
    from kurvo.vista.preferencias_ui import DialogoPreferencias
    from kurvo.nucleo import edicion
    v = ventana
    d = DialogoNormalizacion(v)
    d.calcular()
    d.resize(980, 760)
    d.show()
    qapp.processEvents()
    d.grab().save(str(capturas / "gui_v03_dialogo_normalizacion.png"))
    d.close()
    d = DialogoDesfaseAuto(v)
    d.calcular()
    d.show()
    qapp.processEvents()
    d.grab().save(str(capturas / "gui_v03_dialogo_desfase.png"))
    d.close()
    reg = v.proyecto.pozos[1].logs[0]
    p = reg.columna("DEPT").datos
    gr = reg.columna("GR").datos

    def vista(val):
        return p, gr, edicion.suavizar(gr, p, val["ven"], "mean", 300, 400), "GR API"
    d = DialogoParametros("Smooth", [Campo("ven", "Window (samples)", "int", 9)], v, vista_previa=vista)
    d.previsualizar()
    d.show()
    qapp.processEvents()
    d.grab().save(str(capturas / "gui_v03_dialogo_vista_previa.png"))
    d.close()
    d = DialogoPreferencias(v, v.prefs)
    d.show()
    for i, nombre in enumerate(("general", "qc", "rangos", "dl")):
        d.tabs.setCurrentIndex(i)
        qapp.processEvents()
        if nombre in ("general", "rangos"):
            d.grab().save(str(capturas / f"gui_v03_preferencias_{nombre}.png"))
    d.close()


def test_capturas_espanol(qapp, tmp_path, capturas):
    from kurvo.nucleo import preferencias
    from kurvo.vista.ventana import VentanaPrincipal, aplicar_idioma, guardar_preferencias
    guardar_preferencias(preferencias.Preferencias(idioma="es"))
    try:
        v = VentanaPrincipal()
        v.proyecto = proyecto_capturas()
        v.refrescar_todo()
        v.resize(1600, 960)
        v.show()
        _reconstruir(v)
        _vista_principal(v, qapp, capturas, "gui_v03_principal_es.png")
        v.ribbon.setCurrentIndex(0)
        qapp.processEvents()
        v.grab().save(str(capturas / "gui_v03_ribbon_general_es.png"))
        dock = v.docks["qc"]
        dock.setFloating(True)
        dock.resize(1150, 800)
        v.panel_qc.ir_a("dashboard")
        qapp.processEvents()
        dock.grab().save(str(capturas / "gui_v03_qc_dashboard_es.png"))
        a = v.ayuda(mostrar=False)
        a.show()
        qapp.processEvents()
        a.grab().save(str(capturas / "gui_v03_ayuda_es.png"))
        a.close()
        v.proyecto.modificado = False
        v.close()
    finally:
        guardar_preferencias(preferencias.Preferencias())
        aplicar_idioma("en")


def test_lamina_de_iconos(qapp, capturas):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QFont, QImage, QPainter
    from kurvo.vista import iconos
    nombres = list(iconos.ICONOS)
    col, lado, cw, ch = 10, 48, 120, 80
    filas = (len(nombres) + col - 1) // col
    img = QImage(col * cw, filas * ch, QImage.Format_ARGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.setFont(QFont("Arial", 8))
    for i, n in enumerate(nombres):
        x, y = (i % col) * cw, (i // col) * ch
        p.drawPixmap(x + (cw - lado) // 2, y + 4, iconos.pixmap(n, lado))
        p.drawText(QRectF(x, y + 56, cw, 20), Qt.AlignCenter, n)
    p.end()
    assert img.save(str(capturas / "iconos.png"))
