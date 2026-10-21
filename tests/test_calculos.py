"""Pruebas de los cálculos petrofísicos, con valores esperados calculados a mano."""
import math

import numpy as np
import pytest

from kurvo.calculos import formula, graficos, petrofisica as pf
from kurvo.nucleo.comun import NULO


def test_vshale():
    np.testing.assert_allclose(pf.vsh_indice([50, 150, NULO], 0, 100), [0.5, 1.0, NULO])
    np.testing.assert_allclose(pf.vsh_indice([150], 0, 100, limitar=False), [1.5])
    np.testing.assert_allclose(pf.vsh_neutron([0.25], 0.5), [0.5])
    np.testing.assert_allclose(pf.vsh_neutron_densidad([0.3], [0.1], 0.5, 0.2), [2 / 3])
    with pytest.raises(ValueError):
        pf.vsh_neutron_densidad([0.3], [0.1], 0.2, 0.2)


def test_porosidad():
    np.testing.assert_allclose(pf.porosidad_densidad([2.3], 2.65, 1.0), [(2.65 - 2.3) / 1.65])
    np.testing.assert_allclose(pf.porosidad_sonico([80], 55, 189), [25 / 134])
    assert pf.MATRIZ_DENSIDAD["Calcite"] == 2.71 and pf.MATRIZ_SONICO["Salt"] == 67


def test_archie():
    sw = pf.sw_archie([0.2], [10], 1, 2, 2, 0.1)[0]
    assert sw == pytest.approx(math.sqrt(0.1 / (10 * 0.04)))
    assert pf.sw_archie([0.0], [10])[0] == NULO


def test_simandoux_n2_y_newton():
    phi, rt, vsh, a, m, rw, rsh = 0.2, 10.0, 0.3, 1.0, 2.0, 0.1, 2.0
    x = phi ** m / (a * rw)
    y = vsh / rsh
    esperado = (math.sqrt(y * y + 4 * x / rt) - y) / (2 * x)
    assert pf.sw_simandoux([phi], [rt], [vsh], a, m, 2, rw, rsh)[0] == pytest.approx(esperado)
    # n≠2: resuelve 1/Rt = x·Sw^n + y·Sw
    s = pf.sw_simandoux([phi], [rt], [vsh], a, m, 2.2, rw, rsh, limitar=False)[0]
    assert x * s ** 2.2 + y * s == pytest.approx(1 / rt, rel=0.01)
    mod = pf.sw_simandoux([phi], [rt], [vsh], a, m, 2, rw, rsh, modificado=True, limitar=False)[0]
    x2 = x / (1 - vsh)
    assert mod == pytest.approx((math.sqrt(y * y + 4 * x2 / rt) - y) / (2 * x2))


def test_indonesia():
    phi, rt, vsh, a, m, n, rw, rsh = 0.2, 10.0, 0.3, 1.0, 2.0, 2.0, 0.1, 2.0
    den = vsh ** (1 - vsh / 2) / math.sqrt(rsh) + math.sqrt(phi ** m / (a * rw))
    assert pf.sw_indonesia([phi], [rt], [vsh], a, m, n, rw, rsh)[0] == pytest.approx(
        ((1 / math.sqrt(rt)) / den) ** (2 / n))
    den2 = vsh ** ((1 - vsh) / 2) / math.sqrt(rsh) + math.sqrt(phi ** m / (a * rw))
    assert pf.sw_indonesia([phi], [rt], [vsh], a, m, n, rw, rsh, modificado=True)[0] == pytest.approx(
        ((1 / math.sqrt(rt)) / den2) ** (2 / n))


def test_arcilla_dispersa():
    phid, phis, rt, rw = 0.15, 0.25, 20.0, 0.1
    q = (phis - phid) / phis
    t = 0.8 * rw / (phis ** 2 * rt)
    assert pf.sw_arcilla_dispersa([phid], [phis], [rt], rw)[0] == pytest.approx(
        (math.sqrt(t + (q / 2) ** 2) - q / 2) / (1 - q))


def test_pickett_y_hingle():
    (rt1, p1), (rt2, p2) = graficos.linea_pickett(0.5, 1, 2, 2, 0.1)
    assert (p1, p2) == (0.01, 1.0)
    assert rt2 == pytest.approx(0.1 / 0.25) and rt1 == pytest.approx(0.1 / (0.01 ** 2 * 0.25))
    k = graficos.pendiente_hingle(0.5, 1, 2, 2, 0.1)
    assert graficos.linea_hingle(0.5, 1, 2, 2, 0.1)[1] == pytest.approx((0.46, 0.46 * k))
    # un punto de Archie con Sw=0.5 cae sobre la recta de Hingle
    phi = 0.2
    rt = 0.1 / (phi ** 2 * 0.25)
    assert graficos.y_hingle([rt], 2)[0] == pytest.approx(phi * k)


def test_analisis_texto_ida_y_vuelta():
    txt = ("0.6; 1.8; 2; 3.1\nDATASW|0.1|0.2\nDATASWX|TRUE|FALSE\n"
           "DATA|D1|1547|1563|W|L|PORE|ILD|220|225|FALSE\n220.084; 0.21; 12.266\n")
    an = graficos.AnalisisSw.desde_texto(txt)
    assert (an.a, an.m, an.n, an.rw) == (0.6, 1.8, 2, 3.1)
    assert an.sw_visible == [True, False] and an.conjuntos[0].rt == [12.266]
    assert graficos.AnalisisSw.desde_texto(an.a_texto()).conjuntos[0].col_rt == "ILD"
    with pytest.raises(ValueError):
        an.agregar_sw(0.1)


def test_histograma_division_entera():
    v = [1, 2, 3, 4, NULO, NULO]
    centros, pct, (lo, hi) = graficos.histograma(v, 20)
    assert len(centros) == 20 and lo == pytest.approx(0.999) and hi == pytest.approx(4.004)
    assert pct.sum() == 4 * (100 // 6)


def test_desplazar():
    np.testing.assert_allclose(graficos.desplazar([1, NULO, 3], 2.5), [3.5, NULO, 5.5])


def test_formula():
    txt = "RhoBulk:=X1;\nRhoMatrix:=2.65;\nRhoFluid:=1;\nPorosity:=(RhoMatrix-RhoBulk)/(RhoMatrix-RhoFluid);\nPorosity"
    assert formula.variables_entrada(txt) == ["X1"]
    r = formula.evaluar(txt, {"X1": np.array([2.3, NULO])})
    assert r[0] == pytest.approx(0.35 / 1.65) and r[1] == NULO
    r = formula.evaluar("if(X1=0, 2, 6) + 2^3 + log10(100)", {"X1": np.array([0.0, 1.0])})
    np.testing.assert_allclose(r, [12, 16])
    with pytest.raises(formula.ErrorFormula):
        formula.evaluar("foo(X1)", {"X1": np.array([1.0])})
    with pytest.raises(formula.ErrorFormula):
        formula.evaluar("(X1", {"X1": np.array([1.0])})
