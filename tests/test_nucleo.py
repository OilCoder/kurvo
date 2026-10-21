"""Pruebas del núcleo: LAS, trayectoria, plantillas, zonas, intervalos y proyecto."""
from pathlib import Path

import numpy as np
import pytest

from kurvo.nucleo.comun import NULO, valor_a_px
from kurvo.nucleo.intervalos import Completacion, Litologia, leer_zonas, lineas_zonas
from kurvo.nucleo.las import ErrorLAS, RegistroLAS, parse_mnemonico
from kurvo.nucleo.plantilla import PISTA_LITOLOGIA, Plantilla
from kurvo.nucleo.proyecto import Proyecto
from kurvo.nucleo.trayectoria import Trayectoria, calc_dtvd, calc_theta

RAIZ = Path(__file__).resolve().parents[1]

LAS_MIN = """~Version Information
VERS. 2.0:
WRAP. NO:
~Well Information
WELL. POZO-X : nombre
NULL. -999.25 :
~Curve Information
DEPT.M :
GR.API : gamma
~A
100 10
101 -999.25
102 30
"""


def test_las_minimo_y_mnemonicos():
    reg = RegistroLAS.desde_lineas(LAS_MIN.splitlines())
    assert reg.nombres() == ["DEPT", "GR"]
    assert reg.nombre_pozo == "POZO-X"
    assert reg.columna("GR").datos.tolist() == [10, NULO, 30]
    assert reg.columna("GR").minimo() == 10 and reg.columna("GR").maximo() == 30
    m = parse_mnemonico("STRT.M  100.0 : inicio")
    assert (m.nombre, m.unidad, m.valor, m.descripcion) == ("STRT", "M", "100.0", "inicio")


def test_las_falta_seccion():
    with pytest.raises(ErrorLAS):
        RegistroLAS.desde_lineas(["~V", "~C", "DEPT. :", "~A", "1"])


def test_las_wrap():
    txt = LAS_MIN.replace("WRAP. NO:", "WRAP. YES:").replace("100 10\n101 -999.25\n102 30\n",
                                                             "100\n10\n101 7\n")
    reg = RegistroLAS.desde_lineas(txt.splitlines())
    assert reg.columna("GR").datos.tolist() == [10, 7]


def test_las_ida_y_vuelta(tmp_path):
    reg = RegistroLAS.desde_lineas(LAS_MIN.splitlines())
    reg.agregar_lineal("LIN", 0, 0.5, 3)
    ruta = tmp_path / "x.las"
    reg.guardar(ruta)
    texto = ruta.read_bytes().decode()
    assert texto.startswith("~Version Information\r\nVERS. 2.0: \r\nWRAP. NO: ")
    assert "      100.00000\t" in texto
    otro = RegistroLAS.abrir(ruta)
    assert otro.nombres() == ["DEPT", "GR", "LIN"]
    np.testing.assert_allclose(otro.columna("LIN").datos, [0, 0.5, 1.0])


def test_valor_en_interpolacion():
    reg = RegistroLAS.desde_lineas(LAS_MIN.splitlines())
    reg.fijar_indices(0, -1)
    assert reg.valor_en(100.5, 0, 0) == 100.5
    assert reg.valor_en(500, 0, 1) == 0.0          # fuera de rango: 0 (fiel)
    assert reg.datos_en_md(102) == [102, 30]


def test_trayectoria_vertical_y_desviada():
    t = Trayectoria.desde_lineas(["#TVD_TO_SS 10", "#MD INC AZIM", "0 0 0", "100 0 0", "200 10 90"])
    assert t.estaciones[1].tvd == 100
    assert t.estaciones[1].tvdss == 90
    e = t.estaciones[2]
    # curvatura mínima: comprobación con fórmula cerrada para arco
    th = calc_theta(0, 10, 0, 90)
    assert th == pytest.approx(10)
    assert e.tvd == pytest.approx(100 + calc_dtvd(100, 200, 0, 10, 0, 90))
    assert e.este > 0 and abs(e.norte) < 1e-9
    assert t.tvd_en(150) == pytest.approx((e.tvd + 100) / 2)
    assert t.md_en(t.tvd_en(150)) == pytest.approx(150)


def test_trayectoria_md_tvd_calcula_inclinacion():
    t = Trayectoria.desde_lineas(["#MD\tTVD", "0\t0", "100\t100", "200\t190"])
    assert t.estaciones[1].inc == pytest.approx(0, abs=1e-3)
    inc = t.estaciones[2].inc
    assert 0 < inc < 90
    assert calc_dtvd(100, 200, 0, inc, 0, 0) == pytest.approx(90, abs=1e-2)


def test_plantilla_ida_y_vuelta(tmp_path):
    t = Plantilla(nombre="t")
    p = t.nueva_pista()
    c = t.nueva_curva(p, "GR")
    c.logaritmica = True
    t.nueva_pista(PISTA_LITOLOGIA)
    assert t.pistas[1].x == p.x + p.ancho + 30
    ruta = tmp_path / "a.kvplantilla"
    t.guardar(ruta)
    u = Plantilla.abrir(ruta)
    assert len(u.pistas) == 2 and u.pistas[1].tipo == PISTA_LITOLOGIA
    assert u.pistas[0].curvas[0].nombre_x == "GR" and u.pistas[0].curvas[0].logaritmica
    assert u.pistas[0].curvas[0].rejilla_x.macro_paso == 100


def test_zonas():
    pozos, zonas = leer_zonas(["#WELLTOPS, A, B", "Z1, 10, 20", "Z2, 30"])
    assert pozos == ["A", "B"] and zonas[1].profundidades == [30, 0]
    assert lineas_zonas(pozos, zonas)[1] == "Z1, 10, 20"


def test_completacion_y_litologia():
    c = Completacion.desde_lineas(["#COMPLETION", "#P", "#N", "#fecha",
                                   "Casing|Casing 7\"|0|600"], "N")
    assert c.herramientas[0].base == 600 and c.prof_max() == 600
    l = Litologia.desde_lineas([Litologia.CABECERA, "10\t20\t3\tArcilla"])
    assert l.intervalos[0].tipo == 3 and l.lineas()[1] == "10\t20\t3\tArcilla"


def test_valor_a_px():
    assert valor_a_px(50, 0, 100, 200, 10) == 110
    assert valor_a_px(10, 1, 100, 200, 0, log=True) == pytest.approx(100)
    assert valor_a_px(NULO, 0, 100, 200, 0) < 0          # el nulo no se filtra (fiel)


def test_proyecto_ida_y_vuelta(tmp_path):
    pr = Proyecto()
    p = pr.nuevo_pozo()
    assert p.nombre == "WellName1"
    p.logs.append(RegistroLAS.desde_lineas(LAS_MIN.splitlines()))
    p.logs[0].nombre = "log"
    pr.nueva_zona()
    pr.zonas[0].profundidades[0] = 101.5
    pr.plantillas.append(Plantilla(nombre="tpl"))
    ruta = tmp_path / "p.kurvo"
    pr.guardar(ruta)
    q = Proyecto.abrir(ruta)
    assert q.pozos[0].nombre == "WellName1"
    assert q.pozos[0].logs[0].columna("GR").datos[2] == 30
    assert q.zonas[0].nombre == "NewZone1" and q.zonas[0].profundidades == [101.5]
    assert q.plantillas[0].nombre == "tpl"


def test_operaciones_parcial_filtro_combinar():
    from kurvo.nucleo import operaciones as op
    reg = RegistroLAS.desde_lineas(LAS_MIN.splitlines())
    reg.fijar_indices(0, -1)
    p = op.log_parcial(reg, 2, 3, "parcial")
    assert p.columna("DEPT").datos.tolist() == [101, 102] and reg.n_filas == 3
    with pytest.raises(ValueError):
        op.log_parcial(reg, 1, 2, " ")
    q = reg.copia()
    assert op.filtrar(q, 1, "is null", 0) == 1 and q.n_filas == 2
    q = reg.copia()
    op.filtrar(q, 1, ">=", 20, accion="Set to null")
    assert q.columna("GR").datos.tolist() == [10, NULO, NULO]
    b = RegistroLAS.desde_lineas(LAS_MIN.replace("GR.API", "RHOB.G").replace("100 10\n", "100.5 2\n")
                                 .replace("101 -999.25", "101 2.5").replace("102 30", "101.5 3").splitlines())
    b.fijar_indices(0, -1)
    m = op.combinar(reg, b)
    assert m.nombres() == ["DEPT", "GR", "RHOB"]
    assert m.columna("RHOB").datos[0] == NULO          # 100 queda fuera del rango de b
    assert m.columna("RHOB").datos[1] == 2.5 and m.columna("RHOB").datos[2] == NULO


def test_crear_tvd_y_md():
    from kurvo.nucleo import operaciones as op
    reg = RegistroLAS.desde_lineas(LAS_MIN.splitlines())
    reg.fijar_indices(0, -1)
    t = Trayectoria.desde_lineas(["#MD INC AZIM", "0 0 0", "100 0 0", "200 20 0"])
    i = op.crear_tvd(reg, t)
    assert reg.indice_tvd == i and reg.columnas[i].datos[0] == pytest.approx(100)
    j = op.crear_md(reg, t)
    np.testing.assert_allclose(reg.columnas[j].datos, reg.columnas[0].datos)
