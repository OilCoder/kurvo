"""Flujo completo con los archivos realistas de datos/realistas/ (v0.4, punto 6; D92–D95):
Import → Validate → QC → Edit → Normalize/Depth shift → DL → QC final → Export, más DLIS.
Si el usuario deja LAS/DLIS reales en datos/reales/, la última prueba los recorre también."""
from pathlib import Path

import numpy as np
import pytest

from kurvo.nucleo import historial, lote, mnemonicos, qc, unidades, validacion
from kurvo.nucleo.comun import NULO

RAIZ = Path(__file__).resolve().parents[1]
REALISTAS = RAIZ / "datos" / "realistas"
REALES = RAIZ / "datos" / "reales"


@pytest.fixture()
def ventana(qapp, tmp_path, monkeypatch):
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    from kurvo.vista import ventana as V
    # el diálogo de columnas de profundidad: la primera como MD, sin TVD
    monkeypatch.setattr(V, "pedir", lambda titulo, campos, *a, **k: {"md": campos[0].defecto, "tvd": "(none)"})
    v = V.VentanaPrincipal()
    v.resize(1600, 960)
    v.show()
    yield v
    v.proyecto.modificado = False
    v.close()


def _importar(v, nombre):
    reg = v.importar_las(None, str(REALISTAS / nombre))
    assert reg is not None, nombre
    return reg


def test_flujo_completo_con_datos_realistas(ventana, tmp_path):
    v = ventana
    # ---------------------------------------------------------------- 1 Import
    main = _importar(v, "PZ-101_main.las")
    rep = _importar(v, "PZ-101_repeat.las")
    vec = _importar(v, "PZ-102.las")
    v.prefs.nulos_extra = [-999.0]                                     # nulo de otro sistema (preferencia)
    prob = _importar(v, "PZ-103.las")
    v.prefs.nulos_extra = []
    pr = v.proyecto
    assert [p.nombre for p in pr.pozos] == ["PZ-101", "PZ-102", "PZ-103"]
    assert len(pr.pozos[0].logs) == 2                                  # la pasada repetida, en el mismo pozo
    assert main.columna("DEPT").unidad == "F" and main.n_filas == 2801
    assert (main.columna("GRC").datos[:20] == NULO).all()              # -9999 del archivo → nulo interno
    assert not (main.columna("GRC").datos == -9999).any()
    assert main.historial.bitacora[0].operacion == "Import: convert nulls"
    # ---------------------------------------------------------------- 2 Validate
    problemas = validacion.validar(prob)
    codigos = {p.codigo for p in problemas}
    assert {"DUPLICATE_DEPTH", "HEADER_STEP"} <= codigos, codigos
    historial.aplicar(prob, "Fix all (validation)", "", validacion.corregir_todo, prob)
    assert not any(p.nivel == validacion.ERROR for p in validacion.validar(prob))
    assert all(np.diff(prob.columna("DEPT").datos) > 0)
    # el nulo "extra" -999 se convirtió al importar, con la preferencia del usuario
    assert not (prob.columna("GR").datos == -999.0).any()
    assert any(c.detalle.startswith("extra nulls") for c in prob.historial.bitacora)
    # mnemónicos de compañía → estándar del grupo de alias
    props = mnemonicos.proponer(main, v.alias)
    actuales = {p.actual: p.nuevo for p in props if p.aplicable}
    assert actuales.get("GRC") == "GR" and actuales.get("AT90") == "RESD" and actuales.get("RHOZ") == "RHOB"
    historial.aplicar(main, "Standardize mnemonics", "", mnemonicos.aplicar, main, props)
    assert main.indice_columna("RESD") >= 0 and main.indice_columna("PHIN") >= 0
    # unidades de PZ-102 a las de PZ-101
    for nombre, destino in (("RHOB", "G/C3"), ("NPHI", "V/V"), ("DT", "US/F")):
        k = vec.indice_columna(nombre)
        historial.aplicar(vec, "Convert units", nombre, unidades.convertir_columna, vec, k, destino)
    assert 1.8 < np.median(vec.columna("RHOB").datos) < 2.8 and np.median(vec.columna("NPHI").datos) < 1
    # ---------------------------------------------------------------- 3 QC
    estados = qc.notas(main, v.alias)
    assert estados["GR"].picos >= 8                                     # los picos sembrados
    assert estados["RHOB"].tramos_planos >= 1                           # herramienta trabada
    assert estados["BS"].tramos_planos == 0                             # BS constante no es "plano" (D70)
    cond = qc.condicion_pozo(main, v.alias)
    assert any("CALI" in t for t in cond) and any("DRHO" in t for t in cond), cond
    rep_res = qc.repetibilidad(main.columna("DEPT").datos, main.columna("GR").datos,
                               rep.columna("DEPT").datos, rep.columna("GRC").datos)
    assert rep_res is not None and rep_res["r"] > 0.9
    # ---------------------------------------------------------------- 4 Edit / Repair
    r = lote.ejecutar("despike", [("PZ-101", main)], {"ventana": 11, "umbral": 4.0}, "GR", v.alias)
    assert r[0].ok
    assert qc.notas(main, v.alias)["GR"].picos < estados["GR"].picos
    # ---------------------------------------------------------------- 5 Normalize / depth shift
    from kurvo.nucleo import multipozo
    res = multipozo.desfase_por_correlacion(multipozo.profundidad(main), main.columna("GR").datos,
                                            multipozo.profundidad(vec), vec.columna("GR").datos, 10.0)
    assert abs(abs(res.desfase) - 3.0) < 0.6, res.desfase                # las capas de PZ-102 están 3 ft arriba
    from kurvo.vista.multipozo_ui import DialogoNormalizacion
    d = DialogoNormalizacion(v)
    d.ch_curva.setCurrentText("GR")
    d.ch_ref.setCurrentIndex(0)
    d.calcular()
    d.aplicar()
    norm = vec.columna("GR_NORM").datos
    v_ok = norm[norm != NULO]
    ref = main.columna("GR").datos[main.columna("GR").datos != NULO]
    assert np.allclose(np.percentile(v_ok, [5, 95]), np.percentile(ref, [5, 95]), atol=1.0)
    assert abs(np.percentile(vec.columna("GR").datos[vec.columna("GR").datos != NULO], 95) - np.percentile(ref, 95)) > 8
    # ---------------------------------------------------------------- 6 Reconstruct (DL) en otra prueba
    # ---------------------------------------------------------------- 7 QC final y 8 Export
    from kurvo.modulos.control_calidad import DialogoReporteQC
    dlg = DialogoReporteQC(v)
    ruta_html = dlg.guardar(str(tmp_path / "qc.html"))
    assert ruta_html and "PZ-101" in Path(ruta_html).read_text(encoding="utf-8")
    ruta_las = v.exportar_las(0, 0, str(tmp_path / "PZ-101_out.las"))
    v.exportar_csv(0, 0, str(tmp_path / "PZ-101_out.csv"))
    v.exportar_excel(None, str(tmp_path / "todo.xlsx"))
    import lasio
    l = lasio.read(ruta_las)
    assert "RESD" in l.keys() and l.well.WELL.value == "PZ-101" and float(l.well.NULL.value) == NULO
    assert abs(l.well.STRT.value - 4800) < 1e-6 and l.well.STRT.unit == "F"
    otro = v.importar_las(None, ruta_las)                                # ida y vuelta
    assert otro.n_filas == main.n_filas and np.allclose(otro.columna("RHOB").datos, main.columna("RHOB").datos)
    ruta_pro = tmp_path / "realista.kurvo"
    pr.guardar(ruta_pro)
    from kurvo.nucleo.proyecto import Proyecto
    pr2 = Proyecto.abrir(ruta_pro)
    assert pr2.pozos[0].logs[0].historial.bitacora[-1].operacion.startswith("Export")


def test_dlis_realista(ventana):
    pytest.importorskip("dlisio")
    v = ventana
    nuevos = v.importar_dlis(None, str(REALISTAS / "PZ-104.dlis"))
    assert len(nuevos) == 1
    reg = nuevos[0]
    assert v.proyecto.pozos[0].nombre == "PZ-104"
    assert reg.nombres() == ["DEPT", "GR", "RHOB", "NPHI", "DT", "CALI"]
    prof = reg.columna("DEPT").datos
    assert reg.columna("DEPT").unidad == "FT" and prof[0] == pytest.approx(5000.0) and prof[1] == pytest.approx(5000.5)
    assert (reg.columna("GR").datos[:20] == NULO).all()
    assert "WF1" in reg.historial.bitacora[-1].detalle                     # canal 2D omitido y anotado
    estados = qc.notas(reg, v.alias)
    # unidades del DLIS (g/cm3, m3/m3, gAPI) reconocidas para el rango físico
    assert estados["RHOB"].rango is not None and estados["NPHI"].rango is not None and estados["GR"].rango is not None
    assert all(e.nota in "AB" for n, e in estados.items() if n != "GR")


def test_deep_learning_rellena_el_hueco_del_sonico(ventana):
    pytest.importorskip("torch")
    from kurvo.aprendizaje import datos as D
    from kurvo.aprendizaje import redes
    v = ventana
    main = _importar(v, "PZ-101_main.las")
    vec = _importar(v, "PZ-102.las")
    for reg in (main, vec):
        historial.aplicar(reg, "Standardize mnemonics", "", mnemonicos.aplicar, reg, mnemonicos.proponer(reg, v.alias))
    k = vec.indice_columna("DTC")
    historial.aplicar(vec, "Convert units", "", unidades.convertir_columna, vec, k, "US/F")
    entradas = ["GR", "RESD", "RHOB", "PHIN"]
    for reg in (main, vec):
        for nombre, destino in (("RHOB", "G/C3"), ("PHIN", "V/V")):
            j = reg.indice_columna(nombre)
            if reg.columnas[j].unidad.upper() != destino:
                historial.aplicar(reg, "Convert units", "", unidades.convertir_columna, reg, j, destino)
    pozos = [D.extraer(r, n, entradas, "DTC", v.alias) for r, n in ((vec, "PZ-102"), (main, "PZ-101"))]
    cfg = redes.Configuracion("regresion", "unet", entradas, ["GAPI", "OHMM", "G/C3", "V/V"], "DTC",
                              largo=64, canales=8, epocas=12, lote=16, lr=5e-3, muestras_mc=3, paciencia=12)
    norm = D.ajustar_normalizador(pozos[:1], entradas, cfg.unidades, False, True, v.alias)
    modelo = redes.ModeloCurvas(cfg, norm)
    modelo.entrenar(pozos[:1], pozos[1:], forzar_cpu=True)
    a, _ = modelo.predecir(pozos[1])
    md = main.columna("DEPT").datos
    hueco = (md > 5650) & (md < 5700)
    assert np.isfinite(a[hueco]).all()
    vecinos = main.columna("DTC").datos[(md > 5600) & (md < 5750) & (main.columna("DTC").datos != NULO)]
    assert vecinos.min() - 25 < np.median(a[hueco]) < vecinos.max() + 25


@pytest.mark.parametrize("carpeta", [REALES], ids=["datos_reales"])
def test_archivos_reales_si_existen(ventana, carpeta):
    archivos = sorted(carpeta.glob("*.las")) + sorted(carpeta.glob("*.LAS")) if carpeta.exists() else []
    dlis = sorted(carpeta.glob("*.dlis")) + sorted(carpeta.glob("*.DLIS")) if carpeta.exists() else []
    if not archivos and not dlis:
        pytest.skip(f"no hay archivos en {carpeta}")
    v = ventana
    for a in archivos:
        reg = v.importar_las(None, str(a))
        assert reg is not None and reg.n_filas > 0, a
        validacion.validar(reg)
        estados = qc.notas(reg, v.alias)
        assert estados, a
        v.exportar_las(len(v.proyecto.pozos) - 1, len(v.proyecto.pozos[-1].logs) - 1,
                       str(Path(v.ajustes.fileName()).parent / (a.stem + "_out.las")))
    if dlis:
        pytest.importorskip("dlisio")
        for a in dlis:
            assert v.importar_dlis(None, str(a)), a
    v.panel_qc.ir_a("dashboard")
    pozos, curvas, celdas = v.panel_qc.matriz_dashboard()
    assert len(pozos) >= 1 and celdas
