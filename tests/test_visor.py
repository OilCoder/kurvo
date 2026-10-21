"""Pruebas del visor y capturas en docs/capturas."""
import numpy as np
import pytest

from kurvo.demo import proyecto_demo
from kurvo.nucleo.comun import NULO
from kurvo.nucleo.bases import herramientas_por_defecto
from kurvo.vista.logplot import (MODO_MD, MODO_TVD, MODO_TVDSS, LogPlot,
                                        datos_desde_proyecto, poligonos_relleno)


@pytest.fixture()
def pr():
    return proyecto_demo()


def _plot(pr, i=0, **cambios):
    d = datos_desde_proyecto(pr, i, base_herr=herramientas_por_defecto())
    for k, v in cambios.items():
        setattr(d, k, v)
    return LogPlot(d)


def test_rango_automatico_incluye_cero(qapp, pr):
    lp = _plot(pr)
    # completación desde 0 => el mínimo es 0 (regla de PrepareView)
    assert lp.prof_min == 0.0 and lp.prof_max == pytest.approx(649.5)
    assert lp.alto == pytest.approx(649.5 * 500 / 300)


def test_sin_completacion_ni_litologia_empieza_en_el_dato(qapp, pr):
    lp = _plot(pr, completacion=None, litologia=None)
    p = lp.prof_registro()
    assert lp.prof_min == float(p[p != NULO].min())   # lo ausente no cuenta (antes como 0 ft, D127)


def test_profundidad_y_escala_propias(qapp, pr):
    lp = _plot(pr, prof_propia=(200.0, 400.0), escala_propia=100.0)
    assert (lp.prof_min, lp.prof_max) == (200.0, 400.0)
    assert lp.alto == 1000.0
    assert lp.prof_a_y(300) == pytest.approx(lp.y0 + 500)
    assert lp.y_a_prof(lp.y0 + 500) == pytest.approx(300)


def test_modos_de_profundidad(qapp, pr):
    md = _plot(pr, modo=MODO_MD)
    tvd = _plot(pr, modo=MODO_TVD)
    ss = _plot(pr, modo=MODO_TVDSS)
    assert md.col_prof == 0 and tvd.col_prof == 1
    t = pr.pozos[0].trayectoria
    assert tvd.a_prof_vista(450) == pytest.approx(t.tvd_en(450))
    assert ss.a_prof_vista(450) == pytest.approx(t.tvd_en(450) - t.tvd_a_ss)
    np.testing.assert_allclose(ss.prof_registro(), tvd.prof_registro() - t.tvd_a_ss)


def test_falta_columna_de_profundidad(qapp, pr):
    pr.pozos[0].logs[0].indice_tvd = -1
    lp = _plot(pr, modo=MODO_TVD)
    assert not lp.listo and "DEPTH TVD" in lp.mensajes[0]


def test_escala_log_e_invertida(qapp, pr):
    lp = _plot(pr)
    pista = lp.d.plantilla.pistas[1]
    c = pista.curvas[0]
    x = lp.x_curva([0.2, 20, 2000], c, pista.x, pista.ancho)
    np.testing.assert_allclose(x, [pista.x, pista.x + pista.ancho / 2, pista.x + pista.ancho])
    c2 = lp.d.plantilla.pistas[2].curvas[0]           # NPHI invertida 0–60
    p2 = lp.d.plantilla.pistas[2]
    assert lp.x_curva([60], c2, p2.x, p2.ancho)[0] == pytest.approx(p2.x)


def test_relleno_solo_donde_izq_menor_der(qapp):
    ys = np.array([0, 10, 20, 30, 40.0])
    izq = np.array([0, 5, 15, 5, 0.0])
    der = np.array([10, 10, 10, 10, 10.0])
    polis = poligonos_relleno(ys, izq, der)
    assert len(polis) == 2                    # el tramo con izq ≥ der se excluye
    assert polis[0].boundingRect().bottom() < 20


def test_usar_grupo_de_alias(qapp, pr):
    from kurvo.nucleo.bases import BaseAlias, GrupoAlias
    alias = BaseAlias([GrupoAlias("GR", alias=["GR", "GRC"]), GrupoAlias("DEPT", alias=["DEPT"])])
    reg = pr.pozos[0].logs[0]
    reg.agregar_columna("GRC", reg.columna("GR").datos * 1.1)
    pr.plantillas[0].pistas[0].curvas[0].usar_grupo = True
    lp = _plot(pr, alias=alias)
    assert lp.curvas[(0, 0)].columnas == [reg.indice_columna("GR"), reg.indice_columna("GRC")]


def test_titulo_y_captura(qapp, pr, capturas):
    lp = _plot(pr)
    img = lp.imagen()
    assert img.width() > 600 and img.height() > 1000
    img.save(str(capturas / "logplot_md.png"))
    _plot(pr, 1, modo=MODO_TVDSS, prof_propia=(200.0, 500.0)).imagen().save(
        str(capturas / "logplot_tvdss_200_500.png"))


def test_widget_zoom_y_cursor(qapp, pr, capturas):
    from PySide6.QtCore import QPoint
    from kurvo.vista.visor import VisorLogPlot
    v = VisorLogPlot()
    v.resize(900, 700)
    lp = _plot(pr)
    v.lienzo.fijar_plot(lp)
    w0 = v.lienzo.width()
    v.lienzo.acercar()
    assert v.lienzo.zoom == pytest.approx(1.2) and v.lienzo.width() == int(lp.tamano()[0] * 1.2)
    for _ in range(30):
        v.lienzo.acercar()
    assert v.lienzo.zoom <= 10 * 1.2
    v.lienzo.zoom_normal()
    assert v.lienzo.width() == w0
    assert not v.lienzo.fijar_zoom(0.05)
    y = int(lp.prof_a_y(pr.zonas[0].prof(0)))
    assert v.lienzo.texto_cursor(QPoint(100, y)).startswith("Zone=Tope A")
    assert v.lienzo.texto_cursor(QPoint(100, int(lp.prof_a_y(300)))) == "Depth=300"
    movidas = []
    v.lienzo.zona_movida.connect(lambda z, md: movidas.append((z.nombre, md)))
    v.show()
    v.grab().save(str(capturas / "visor_widget.png"))


def test_rejilla_log_y_lineal(qapp, pr):
    from kurvo.vista.logplot import siguiente_macro_log, siguiente_micro_log
    assert siguiente_macro_log(0.2) == 1 and siguiente_macro_log(1) == 10
    assert siguiente_micro_log(0.2) == pytest.approx(0.3) and siguiente_micro_log(9) == pytest.approx(10)
    lp = _plot(pr)
    c = lp.d.plantilla.pistas[1].curvas[0]                # ILD 0.2–2000
    assert lp._ticks_x(c, 0.2, 2000, False) == [1, 10, 100, 1000]
    micro = lp._ticks_x(c, 0.2, 2000, True)
    assert micro[0] == pytest.approx(0.3) and micro[-1] < 2000
    g = lp.d.plantilla.pistas[0].curvas[0]                # GR 0–150, macro 50
    assert lp._ticks_x(g, 0, 150, False) == [50, 100]     # sin los bordes


@pytest.mark.parametrize("nombre, esperado", [
    ("Sandstone", ("sand", ())), ("Silty clay", ("clay", ("silty",))),
    ("Diamicton with sandy", ("diamicton", ("sandy",))), ("Calcareous", ("limestone", ())),
    ("Nannofossil chalk", ("chalk", ("nannofossil",))), ("Arenisca arcillosa", ("sand", ("clayey",))),
    ("Conglomerate", ("conglomerate", ())), ("Shaly sandstone", ("sand", ("shaly",))),
    ("Desconocida", ("default", ())),
])
def test_clasificacion_litologia(nombre, esperado):
    from kurvo.vista.patrones_lito import clasificar
    assert clasificar(nombre) == esperado


def test_muestrario_patrones_litologia(qapp, capturas):
    """Todos los tipos de la base por defecto, en una lámina."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QFont, QImage, QPainter, QPen

    from kurvo.nucleo.bases import litologias_por_defecto
    from kurvo.vista.patrones_lito import brocha_patron, clasificar
    nombres = [t.nombre for t in litologias_por_defecto().tipos] + [
        "Nannofossil ooze", "Foraminifer chalk", "Clayey sand", "Silty clay", "Foraminifer ooze",
        "Diamicton with silt", "Calcareous", "Sandy silt", "Diatom ooze", "Radiolarian ooze",
        "Nannofossil chalk", "Silty sand", "Sandy clay"]
    cols, w, h = 4, 230, 70
    img = QImage(cols * w, -(-len(nombres) // cols) * h, QImage.Format_RGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.setFont(QFont("Arial", 8))
    for k, n in enumerate(nombres):
        x, y = (k % cols) * w + 6, (k // cols) * h + 6
        p.setPen(QPen(Qt.black, 1))
        p.setBrush(brocha_patron(n))
        p.drawRect(QRectF(x, y, 96, h - 12))
        p.setBrush(Qt.NoBrush)
        prim, mods = clasificar(n)
        p.drawText(QRectF(x + 102, y, w - 110, h - 12), Qt.AlignVCenter | Qt.TextWordWrap,
                   f"{n}\n[{prim}{' + ' + ', '.join(mods) if mods else ''}]")
        assert brocha_patron(n).textureImage().width() > 0
    p.end()
    assert img.save(str(capturas / "patrones_litologia.png"))
