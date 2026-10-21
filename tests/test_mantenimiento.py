"""Mantenimiento de curvas: historial (deshacer/rehacer, bitácora, originales) y edición."""
import numpy as np
import pytest

from kurvo.nucleo import edicion, historial
from kurvo.nucleo.comun import NULO
from kurvo.nucleo.las import RegistroLAS


def _reg(n=50):
    r = RegistroLAS("R")
    r.agregar_columna("DEPT", 1000 + 0.5 * np.arange(n), "M")
    r.agregar_columna("GR", np.linspace(20, 120, n), "GAPI")
    r.fijar_indices(0, -1)
    return r


# ------------------------------------------------------------------ historial
def test_deshacer_rehacer_y_bitacora():
    r = _reg()
    gr0 = r.columna("GR").datos.copy()
    historial.aplicar(r, "Set to null", "1005-1010", lambda: r.columna("GR").datos.__setitem__(slice(10, 21), NULO))
    assert (r.columna("GR").datos == NULO).sum() == 11
    c = r.historial.bitacora[-1]
    assert (c.operacion, c.columnas, c.muestras) == ("Set to null", "GR", 11)
    assert historial.deshacer(r) == "Set to null"
    np.testing.assert_array_equal(r.columna("GR").datos, gr0)
    assert historial.rehacer(r) == "Set to null"
    assert (r.columna("GR").datos == NULO).sum() == 11
    assert [x.operacion for x in r.historial.bitacora] == ["Set to null", "Undo", "Redo"]


def test_sin_cambios_no_anota_y_nueva_edicion_vacia_rehacer():
    r = _reg()
    historial.aplicar(r, "Nada", "", lambda: None)
    assert not r.historial.bitacora and not r.historial.puede_deshacer
    historial.aplicar(r, "A", "", lambda: r.columna("GR").datos.__setitem__(0, 1.0))
    historial.deshacer(r)
    historial.aplicar(r, "B", "", lambda: r.columna("GR").datos.__setitem__(1, 1.0))
    assert not r.historial.puede_rehacer


def test_original_se_conserva_y_se_restaura():
    r = _reg()
    gr0 = r.columna("GR").datos.copy()
    historial.aplicar(r, "A", "", lambda: setattr(r.columna("GR"), "datos", gr0 * 2))
    historial.aplicar(r, "B", "", lambda: setattr(r.columna("GR"), "datos", gr0 * 3))
    np.testing.assert_array_equal(historial.original(r, "GR").datos, gr0)   # la primera, no la intermedia
    assert historial.restaurar_original(r, "GR")
    np.testing.assert_array_equal(r.columna("GR").datos, gr0)


def test_restaurar_original_tras_cambiar_filas():
    r = _reg()
    gr0 = r.columna("GR").datos.copy()
    historial.aplicar(r, "Edit", "", lambda: r.columna("GR").datos.__setitem__(3, 999.0))
    historial.aplicar(r, "Delete rows", "", lambda: [setattr(c, "datos", c.datos[::2]) for c in r.columnas])
    historial.restaurar_original(r, "GR")
    np.testing.assert_allclose(r.columna("GR").datos, gr0[::2])


def test_borrar_y_renombrar_columna_quedan_en_bitacora():
    r = _reg()
    historial.aplicar(r, "Rename", "", lambda: (setattr(r.columna("GR"), "nombre", "GR2"),
                                                historial.renombrar_original(r, "GR", "GR2")))
    historial.aplicar(r, "Delete", "", r.borrar_columna, 1)
    assert r.nombres() == ["DEPT"]
    historial.deshacer(r)
    historial.deshacer(r)
    assert r.nombres() == ["DEPT", "GR"]


def test_limite_de_pasos():
    r = _reg()
    for k in range(historial.LIMITE + 10):
        historial.aplicar(r, f"e{k}", "", lambda k=k: r.columna("GR").datos.__setitem__(0, float(k)))
    assert len(r.historial.deshacer) == historial.LIMITE


def test_historial_se_guarda_en_el_proyecto(tmp_path):
    from kurvo.demo import proyecto_demo
    from kurvo.nucleo.proyecto import Proyecto
    pr = proyecto_demo()
    r = pr.pozos[0].logs[0]
    gr0 = r.columna("GR").datos.copy()
    historial.aplicar(r, "Despike", "window 11", lambda: r.columna("GR").datos.__setitem__(slice(0, 5), 1.0))
    pr.guardar(tmp_path / "h.kurvo")
    r2 = Proyecto.abrir(tmp_path / "h.kurvo").pozos[0].logs[0]
    assert [c.operacion for c in r2.historial.bitacora] == ["Despike"]
    o = historial.original(r2, "GR")
    np.testing.assert_allclose(o.datos, gr0, atol=1e-6)
    assert o.prof is not None and len(o.prof) == len(gr0)


# ------------------------------------------------------------------ edición
P = np.arange(0.0, 20.0, 1.0)


def test_a_nulo_y_constante():
    d = np.ones(20)
    np.testing.assert_array_equal(np.where(edicion.a_nulo(d, P, 5, 7) == NULO)[0], [5, 6, 7])
    assert edicion.poner_constante(d, P, 7, 5, 3.0)[6] == 3.0          # tope/base invertidos


def test_interpolar_huecos():
    d = P * 2.0
    d[5:8] = NULO
    d[0] = NULO                         # hueco en el borde: no se extrapola
    out = edicion.interpolar_huecos(d, P)
    np.testing.assert_allclose(out[5:8], [10, 12, 14])
    assert out[0] == NULO
    assert (edicion.interpolar_huecos(d, P, max_hueco=2.0)[5:8] == NULO).all()   # hueco de 4 > 2
    np.testing.assert_allclose(edicion.interpolar_huecos(d, P, metodo="pchip")[5:8], [10, 12, 14])


def test_despike():
    rng = np.random.default_rng(1)
    d = 50 + rng.normal(0, 1, 200)
    d[[30, 100, 150]] = [500, -300, 400]
    d[60] = NULO
    out, n = edicion.quitar_picos(d, np.arange(200.0), 11, 4.0, "median")
    assert n == 3 and np.all(np.abs(out[[30, 100, 150]] - 50) < 5)
    assert out[60] == NULO
    out, _ = edicion.quitar_picos(d, np.arange(200.0), 11, 4.0, "null")
    assert (out[[30, 100, 150]] == NULO).all()


def test_suavizar_conserva_nulos_y_constante():
    d = np.full(20, 7.0)
    d[4] = NULO
    s = edicion.suavizar(d, P, 5, "mean")
    assert s[4] == NULO and np.allclose(s[s != NULO], 7.0)
    escalon = np.r_[np.zeros(10), np.ones(10)]
    g = edicion.suavizar(escalon, P, 5, "gaussian")
    assert 0 < g[9] < 1 and 0 < g[10] < 1


def test_recortar():
    d = np.array([-5, 0, 5, 10, 15, NULO])
    c, n = edicion.recortar(d, 0, 10, "clip")
    assert list(c) == [0, 0, 5, 10, 10, NULO] and n == 2
    z, _ = edicion.recortar(d, 0, 10, "null")
    assert list(z) == [NULO, 0, 5, 10, NULO, NULO]


def test_empalmar():
    a, b = np.full(20, 1.0), np.full(20, 3.0)
    out = edicion.empalmar(P, a, b, 10.0)
    assert (out[:10] == 1).all() and (out[10:] == 3).all()
    suave = edicion.empalmar(P, a, b, 10.0, transicion=4.0)
    assert suave[8] == 1.0 and 1 < suave[10] < 3 and suave[12] == 3.0
    nivel = edicion.empalmar(P, a, b, 10.0, transicion=4.0, ajustar_nivel=True)
    assert np.allclose(nivel, 1.0)
    b2 = b.copy()
    b2[:15] = NULO                     # corrida inferior empieza más abajo: se usa la superior
    assert (edicion.empalmar(P, a, b2, 10.0)[10:15] == NULO).all()


def test_pintar():
    d = np.zeros(20)
    out = edicion.pintar(d, P, [(5.0, 4.0), (9.0, 8.0)])      # (valor, profundidad)
    np.testing.assert_allclose(out[4:9], [5, 6, 7, 8, 9])
    assert out[3] == 0 and out[9] == 0


# ------------------------------------------------------------------ interfaz
@pytest.fixture()
def ventana(qapp, tmp_path):
    from kurvo.demo import proyecto_demo
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    v.proyecto = proyecto_demo()
    v.refrescar_todo()
    yield v
    v.proyecto.modificado = False
    v.close()


def test_editor_logs_deshacer_desde_la_interfaz(ventana, monkeypatch):
    from kurvo.vista import edicion_curvas
    ed = ventana.editor_logs
    ed.mostrar(0, 0)
    reg = ed.registro()
    ed.columna_clic = reg.indice_columna("GR")
    gr0 = reg.columna("GR").datos.copy()
    assert not ed.b_undo.isEnabled()
    monkeypatch.setattr(edicion_curvas, "pedir", lambda *a, **k: {"tope": 300.0, "base": 310.0})
    edicion_curvas.a_nulo(ed)
    assert ed.b_undo.isEnabled() and (reg.columna("GR").datos == NULO).sum() > (gr0 == NULO).sum()
    ed.modelo.setData(ed.modelo.index(0, reg.indice_columna("GR")), "42")
    assert reg.columna("GR").datos[0] == 42
    ed.deshacer()
    ed.deshacer()
    np.testing.assert_array_equal(reg.columna("GR").datos, gr0)
    ed.rehacer()
    assert ed.b_redo.isEnabled()


def test_edicion_grafica_trazo(ventana):
    from kurvo.vista.edicion_curvas import edicion_grafica
    ed = ventana.editor_logs
    ed.mostrar(0, 0)
    reg = ed.registro()
    ed.columna_clic = reg.indice_columna("GR")
    d = edicion_grafica(ed)
    d.aplicar_trazo([(77.0, 300.0), (77.0, 305.0)])
    md = reg.columnas[reg.indice_md].datos
    sel = (md >= 300) & (md <= 305)
    assert np.allclose(reg.columna("GR").datos[sel], 77.0)
    d.region.setRegion((300, 305))
    d._intervalo("Set to null", lambda x, p, a, b: edicion.a_nulo(x, p, a, b))
    assert (reg.columna("GR").datos[sel] == NULO).all()
    assert [c.operacion for c in reg.historial.bitacora][-2:] == ["Manual edit", "Set to null"]
    d.close()


# ------------------------------------------------------------------ validación
LAS_MALO = """~Version Information
VERS. 2.0:
WRAP. NO:
~Well Information
STRT.M 90 : start
NULL. -9999 :
~Curve Information
DEPT.M :
GR.API :
GR.API :
~A
100 10 1
101 -9999 2
101 30 3
99 40 4
"""


def test_validar_detecta_y_corrige():
    from kurvo.nucleo import validacion as v
    r = RegistroLAS.desde_lineas(LAS_MALO.splitlines())
    r.fijar_indices(0, -1)
    codigos = {p.codigo for p in v.validar(r)}
    assert {"DUPLICATE_DEPTH", "NOT_MONOTONIC", "FILE_NULL", "DUPLICATE_CURVE", "HEADER_MISSING",
            "HEADER_STRT"} <= codigos
    historial.aplicar(r, "Fix all", "", v.corregir_todo, r)
    restantes = {p.codigo for p in v.validar(r) if p.nivel != v.INFO}
    assert restantes == set(), restantes
    assert r.columnas[0].datos.tolist() == [99, 100, 101]
    assert r.nombres() == ["DEPT", "GR", "GR_1"]
    assert r.columna("GR").datos.tolist() == [40, 10, NULO]          # se conserva la primera fila de 101
    assert v._w(r, "STRT").valor == "99" and v._w(r, "STEP").valor == "1"
    historial.deshacer(r)
    assert r.n_filas == 4 and r.nulo_archivo == -9999


def test_duplicados_promedio_y_paso():
    from kurvo.nucleo import validacion as v
    r = _reg(6)
    r.columnas[0].datos[3] = r.columnas[0].datos[2]
    r.columna("GR").datos[2:4] = [10, 20]
    assert v.quitar_duplicados(r, "mean") == 1
    assert r.columna("GR").datos[2] == 15
    assert v.paso_regular([0, 0.5, 1.0, 1.5]) == 0.5 and v.paso_regular([0, 0.5, 1.2]) == 0


def test_las_guardado_con_cabecera_completa(tmp_path):
    from kurvo.nucleo import validacion as v
    r = _reg(5)
    r.guardar(tmp_path / "a.las", pozo="POZO-9")
    otro = RegistroLAS.abrir(tmp_path / "a.las")
    otro.fijar_indices(0, -1)
    assert otro.nombre_pozo == "POZO-9"
    assert [p for p in v.validar(otro) if p.nivel != v.INFO] == []


def test_dialogo_validacion(qapp):
    from kurvo.vista.validacion_ui import DialogoValidacion

    class Ed:                                   # editor mínimo
        def actualizar_tabla(self):
            pass
    from PySide6.QtWidgets import QWidget
    r = RegistroLAS.desde_lineas(LAS_MALO.splitlines())
    r.fijar_indices(0, -1)
    padre = QWidget()
    d = DialogoValidacion.__new__(DialogoValidacion)
    DialogoValidacion.__init__(d, padre, r)
    d.ed = Ed()
    assert d.tabla.rowCount() >= 6 and d.b_todo.isEnabled()
    d.corregir_todo()
    assert all(p.nivel == "INFO" for p in d.problemas)


# ------------------------------------------------------------------ remuestreo, unidades, mnemónicos
def test_remuestreo_lineal_y_promedio():
    from kurvo.nucleo import remuestreo
    r = RegistroLAS("R")
    r.agregar_columna("DEPT", [100.1, 100.6, 101.2, 101.6, 102.1], "M")
    r.agregar_columna("X", [0.0, 1.0, NULO, 3.0, 4.0])
    r.fijar_indices(0, -1)
    n = remuestreo.remuestrear(r, 0.5, metodo="linear")
    assert n == 4 and r.columnas[0].datos.tolist() == [100.5, 101.0, 101.5, 102.0]
    assert r.columna("X").datos[0] == pytest.approx(0.8)
    assert r.columna("X").datos[1] == NULO and r.columna("X").datos[2] == NULO   # no cruza el nulo
    r2 = _reg(41)                                     # 1000..1020 cada 0.5
    remuestreo.remuestrear(r2, 2.0, metodo="auto")    # paso 4 veces mayor -> promedio por bloque
    assert r2.columnas[0].datos[0] == 1000 and r2.columnas[0].datos[-1] == 1020
    gr = np.linspace(20, 120, 41)
    assert r2.columna("GR").datos[1] == pytest.approx(gr[2:6].mean())     # [1001, 1003)


def test_malla_alineada():
    from kurvo.nucleo.remuestreo import malla
    assert malla(100.13, 101.0, 0.25).tolist() == [100.25, 100.5, 100.75, 101.0]
    with pytest.raises(ValueError):
        malla(0, 1, 0)


def test_unidades():
    from kurvo.nucleo import unidades as u
    np.testing.assert_allclose(u.convertir([1.0, NULO], "ft", "M"), [0.3048, NULO])
    np.testing.assert_allclose(u.convertir([100.0], "US/F", "US/M"), [328.0839895])
    np.testing.assert_allclose(u.convertir([2.65], "G/C3", "KG/M3"), [2650.0])
    np.testing.assert_allclose(u.convertir([212.0], "DEGF", "DEGC"), [100.0])
    np.testing.assert_allclose(u.convertir([25.0], "PU", "V/V"), [0.25])
    assert "US/M" in u.destinos("USEC/FT") and u.destinos("OHMM") == []
    with pytest.raises(ValueError):
        u.convertir([1.0], "M", "G/CC")
    r = _reg(3)
    r.agregar_columna("TVD", r.columnas[0].datos.copy(), "M")
    r.indice_tvd = 2
    assert u.convertir_profundidad(r, "FT") == ["DEPT", "TVD"]
    assert r.columnas[0].unidad == "FT" and r.columnas[0].datos[0] == pytest.approx(1000 / 0.3048)


def test_mnemonicos():
    from kurvo.nucleo import mnemonicos
    from kurvo.nucleo.bases import alias_por_defecto
    r = _reg(3)
    for n in ("ILD", "LLD", "NPHI", "XYZ"):
        r.agregar_columna(n, np.ones(3))
    props = mnemonicos.proponer(r, alias_por_defecto())
    d = {p.actual: p for p in props}
    assert d["ILD"].nuevo == "RESD" and d["ILD"].aplicable
    assert not d["LLD"].aplicable and "already" in d["LLD"].motivo        # segunda curva al mismo grupo
    assert d["NPHI"].nuevo == "PHIN" and "XYZ" not in d and "DEPT" not in d
    historial.aplicar(r, "Std", "", mnemonicos.aplicar, r, props)
    assert r.nombres() == ["DEPT", "GR", "RESD", "LLD", "PHIN", "XYZ"]


def test_mnemonicos_de_las_cargas_de_la_kcc():
    """D122: el 31 % de 1500 LAS de la KCC (6 condados de Kansas) tenía alguna curva clave con nombres de
    compañía que la base no reconocía (GAMMA, DEN(CDL), POR(NEU), RES(DI)...)."""
    from kurvo.nucleo.bases import alias_por_defecto
    a = alias_por_defecto()
    esperado = {"GAMMA": "GR", "DEN(CDL)": "RHOB", "POR(NEU)": "PHIN", "POR(DEN)": "PHID", "RES(DI)": "RESD",
                "RES(DG)": "RESD", "RES(MI)": "RESM", "COND(DI)": "COND", "CALIPER": "CAL", "COMP": "DRHO",
                "PDPE": "PE", "DELTAT": "DTC"}
    assert {m: a.grupos[a.grupo_de(m)].nombre for m in esperado} == esperado


# ------------------------------------------------------------------ varios pozos
def _senal(z):
    return 60 + 30 * np.sin(z / 7.0) + 15 * np.sin(z / 2.3) + 10 * np.cos(z / 1.1)


def test_desfase_por_correlacion_recupera_desplazamiento():
    from kurvo.nucleo import multipozo
    z = np.arange(1000.0, 1200.0, 0.5)
    ref = _senal(z)
    obj = _senal(z - 3.2)                       # lo mismo, 3.2 m más abajo
    res = multipozo.desfase_por_correlacion(z, ref, z, obj, 10.0)
    assert res.desfase == pytest.approx(-3.2, abs=0.1) and res.correlacion > 0.99
    assert res.correlacion_cero < res.correlacion
    corregida = multipozo.desplazar_curva(z, obj, res.desfase)
    ok = corregida != NULO
    assert np.corrcoef(corregida[ok], ref[ok])[0, 1] > 0.99
    r = RegistroLAS("O")
    r.agregar_columna("DEPT", z.copy(), "M")
    r.agregar_columna("GR", obj)
    r.fijar_indices(0, -1)
    multipozo.desplazar_registro(r, res.desfase)
    assert r.columnas[0].datos[0] == pytest.approx(1000 + res.desfase)


def test_normalizacion_percentiles():
    from kurvo.nucleo import multipozo
    rng = np.random.default_rng(3)
    ref = rng.normal(75, 20, 2000)
    otro = ref * 1.3 + 12                         # mismo GR con otra calibración
    rb, ra, _ = multipozo.percentiles(ref)
    pb, pa, n = multipozo.percentiles(otro)
    norm = multipozo.normalizar(otro, pb, pa, rb, ra)
    np.testing.assert_allclose(norm, ref, atol=1e-9)
    z = np.arange(2000.0)
    b, a, n = multipozo.percentiles(ref, z, 0, 99)
    assert n == 100
    with pytest.raises(ValueError):
        multipozo.percentiles(ref[:5])


def test_buscar_curva_por_alias():
    from kurvo.nucleo.bases import alias_por_defecto
    from kurvo.nucleo.multipozo import buscar_curva
    r = _reg(3)
    r.agregar_columna("ILD", np.ones(3))
    assert buscar_curva(r, "LLD", alias_por_defecto()) == 2 and buscar_curva(r, "LLD") == -1


def test_lote_sobre_varios_registros():
    from kurvo.demo import proyecto_demo
    from kurvo.nucleo import lote
    pr = proyecto_demo()
    objetivos = [(p.nombre, r) for p in pr.pozos for r in p.logs]
    res = lote.ejecutar("despike", objetivos, {"ventana": 11, "umbral": 4.0}, curva="GR")
    assert all(r.ok for r in res) and len(res) == 3
    res = lote.ejecutar("resample", objetivos, {"paso": 1.0})
    assert all(r.ok for r in res)
    assert all(r.n_filas < 1000 for _, r in objetivos)
    res = lote.ejecutar("despike", objetivos, curva="NOEXISTE")
    assert not any(r.ok for r in res) and "not found" in res[0].mensaje
    assert [c.operacion for c in objetivos[0][1].historial.bitacora] == ["Despike curve (batch)",
                                                                          "Resample (batch)"]


def test_dialogos_multipozo(ventana):
    from kurvo.vista.multipozo_ui import DialogoDesfaseAuto, DialogoLote, DialogoNormalizacion
    pr = ventana.proyecto
    d = DialogoNormalizacion(ventana)
    assert d.calcular() and len(d.resultados) == 3
    d.aplicar()
    assert pr.pozos[1].logs[0].indice_columna("GR_NORM") >= 0
    d = DialogoDesfaseAuto(ventana)
    res = d.calcular()
    assert res is not None and np.isfinite(res.correlacion)
    md0 = pr.pozos[1].logs[0].columnas[0].datos[0]
    d.aplicar()
    assert pr.pozos[1].logs[0].columnas[0].datos[0] == pytest.approx(md0 + res.desfase)
    d = DialogoLote(ventana)
    d.ch_op.setCurrentIndex(d.ch_op.findData("validate"))
    res = d.ejecutar(params={})
    assert len(res) == 3 and d.resultados.rowCount() == 3


# ------------------------------------------------------------------ DLIS, CSV, Excel
class _Canal:
    def __init__(self, nombre, unidad, largo=""):
        self.name, self.units, self.long_name = nombre, unidad, largo


class _Frame:
    def __init__(self):
        self.name = "60B"
        self.channels = [_Canal("TDEP", "0.1 in"), _Canal("GR", "gAPI", "Gamma Ray"), _Canal("IMG", "")]

    def curves(self):
        dt = np.dtype([("FRAMENO", "i4"), ("TDEP", "f8"), ("GR", "f4"), ("IMG", "f4", (3,))])
        a = np.zeros(4, dt)
        a["TDEP"] = [12000, 12006, 12012, 12018]
        a["GR"] = [50, np.nan, 70, 80]
        return a


class _Archivo:
    origins = [type("O", (), {"well_name": "POZO-D"})()]
    frames = [_Frame()]


class _Carga(list):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_leer_dlis_con_modulo_simulado():
    from kurvo.nucleo import intercambio
    falso = type("M", (), {"load": staticmethod(lambda ruta: _Carga([_Archivo()]))})
    frames = intercambio.leer_dlis("x.dlis", falso)
    assert len(frames) == 1
    r = frames[0].registro
    assert r.nombre_pozo == "POZO-D" and r.nombres() == ["DEPT", "GR"]
    np.testing.assert_allclose(r.columnas[0].datos, [100, 100.05, 100.1, 100.15])
    assert r.columnas[0].unidad == "FT" and r.columna("GR").datos[1] == NULO
    assert frames[0].omitidos == ["IMG (3,)"]


def test_exportar_csv_y_excel(tmp_path):
    import pandas as pd
    from kurvo.nucleo import intercambio
    r = _reg(4)
    r.columna("GR").datos[1] = NULO
    intercambio.exportar_csv(r, tmp_path / "a.csv")
    lineas = (tmp_path / "a.csv").read_text(encoding="utf-8").splitlines()
    assert lineas[0] == "DEPT,GR" and lineas[1] == "M,GAPI" and lineas[3].endswith(",")
    hojas = intercambio.exportar_excel([("P1", r), ("P1", r)], tmp_path / "a.xlsx")
    assert len(set(hojas)) == 2
    libro = pd.read_excel(tmp_path / "a.xlsx", sheet_name=None)
    assert "Curves" in libro and list(libro[hojas[0]].columns) == ["DEPT [M]", "GR [GAPI]"]
    assert np.isnan(libro[hojas[0]]["GR [GAPI]"][1])


# ------------------------------------------------------------------ control de calidad
def test_qc_curva():
    from kurvo.nucleo import qc
    z = np.arange(0, 100, 0.5)
    gr = 60 + 10 * np.sin(z)
    gr[10:15] = NULO
    gr[50:65] = 77.0                      # tramo plano
    gr[100] = 900.0                       # fuera de rango físico y pico
    e = qc.evaluar_curva(gr, z, "GR", "GAPI")
    assert e.n_huecos == 1 and e.hueco_max == pytest.approx(3.0)
    assert e.fuera_rango == 1 and e.tramos_planos == 1 and e.picos >= 1
    assert e.nota == "B" and any("flat" in a for a in e.avisos)
    r = _reg(200)
    r.columnas[0].datos = z
    r.columna("GR").datos = gr
    f = qc.bandera(r, 1)
    assert f[12] == 1 and f[100] == 1 and f[55] == 1 and f[30] == 0
    assert qc.rango_fisico("NPHI", "PU") is None              # sin alias no sabe que es PHIN
    from kurvo.nucleo.bases import alias_por_defecto
    assert qc.rango_fisico("NPHI", "PU", alias_por_defecto()) == (-15, 100)


def test_qc_informe_y_reporte(tmp_path, qapp):
    from kurvo.demo import proyecto_demo
    from kurvo.nucleo import qc
    from kurvo.nucleo.bases import alias_por_defecto
    from kurvo.vista import reporte_qc
    pr = proyecto_demo()
    alias = alias_por_defecto()
    informes = [(qc.informe(r, p.nombre, qc.zonas_de_pozo(pr, i), alias), r)
                for i, p in enumerate(pr.pozos) for r in p.logs]
    assert len(informes[0][0].zonas) == len(pr.zonas)
    reporte_qc.guardar_html(tmp_path / "qc.html", informes, alias)
    texto = (tmp_path / "qc.html").read_text(encoding="utf-8")
    assert "Log Quality Control Report" in texto and texto.count("data:image/png;base64,") >= 12
    reporte_qc.guardar_pdf(tmp_path / "qc.pdf", informes[:1], alias)
    assert (tmp_path / "qc.pdf").read_bytes()[:4] == b"%PDF"


def test_modulo_qc_en_la_ventana(ventana, tmp_path):
    ed = ventana.editor_logs
    ed.mostrar(0, 0)
    reg = ed.registro()
    ed.columna_clic = reg.indice_columna("GR")
    mod = next(m for m in ventana.modulos if m.nombre == "Quality Control")
    mod.bandera(ventana)
    assert reg.indice_columna("GR_QC") >= 0 and ed.b_undo.isEnabled()
    assert mod.comparar(ventana) is not None
    from kurvo.modulos.control_calidad import DialogoReporteQC
    d = DialogoReporteQC(ventana, reg)
    assert len(d.objetivos()) == 1
    assert d.guardar(str(tmp_path / "r.html"))
    assert ventana.exportar_csv(0, 0, ruta=str(tmp_path / "x.csv"))
    assert ventana.exportar_excel(ruta=str(tmp_path / "x.xlsx"))
