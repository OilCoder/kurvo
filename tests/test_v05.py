"""v0.5: lo que salió de probar con los LAS reales del Kansas Geological Survey (data/, D104–D109).
Las pruebas pequeñas usan LAS escritos aquí con la forma de los del KGS; la última recorre data/
entera si existe (no está en el repositorio)."""
from pathlib import Path

import numpy as np
import pytest

from kurvo.nucleo import bases, cabecera_pozo, edicion, preferencias, qc, unidades, validacion
from kurvo.nucleo.comun import NULO
from kurvo.nucleo.las import RegistroLAS
from kurvo.nucleo.proyecto import Proyecto

DATA = Path(__file__).resolve().parents[1] / "data"


def _las(well="1-28", lease="Katie 1-28", uwi="15-081-21195", curvas=("GR.GAPI",), n=200, otros="", extra_w="",
         datos=None, nulo="-999.25"):
    filas = []
    for i in range(n):
        vals = [f"{3000 + 0.5 * i:.1f}"] + [f"{(datos[k][i] if datos else 50 + 10 * np.sin(i / 7 + k)):.4f}"
                                           for k in range(len(curvas))]
        filas.append(" ".join(vals))
    return "\n".join([
        "~Version", "VERS. 2.0 :", "WRAP. NO :",
        "~Well",
        "STRT.FT 3000.0 :", f"STOP.FT {3000 + 0.5 * (n - 1):.1f} :", "STEP.FT 0.5 :", f"NULL. {nulo} :",
        f"WELL. {well} : WELL_NAME", f"LEASE. {lease} : LEASE", f"UWI. {uwi} : API",
        "LAT. 37.3810947 : NAD27_LATITUDE", "LONG. -101.0721631 : NAD27_LONGITUDE", extra_w,
        "~Curve", "DEPT.FT :"] + [f"{c} :" for c in curvas] + ["~Other", otros, "~ASCII"] + filas) + "\n"


def _reg(texto, tmp_path, nombre="a.las"):
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    reg = RegistroLAS.abrir(ruta)
    reg.fijar_indices(0, -1)
    return reg, ruta


TOPES = "BASE,TOP,FORMATION\nnan,3020.0,Heebner Shale Member\nnan,3050.5,Lansing Group\n3070,3060.0,Kansas City Group"


# ------------------------------------------------------------------ identidad del pozo (D104)
@pytest.mark.parametrize("well,lease,esperado", [
    ("1-28", "Katie 1-28", "Katie 1-28"),            # LEASE ya trae el número
    ("2", "REIN 'A'", "REIN 'A' 2"),                  # archivos antiguos: LEAS sin el número
    ("PZ-101", "", "PZ-101"),                         # sin LEASE: WELL
    ("Smith 4", "Smith", "Smith 4"),                  # WELL ya trae el nombre completo
    ("#2-31", "Kt Schaben #2-31", "Kt Schaben #2-31"),
])
def test_nombre_del_pozo(tmp_path, well, lease, esperado):
    reg, _ = _reg(_las(well=well, lease=lease), tmp_path)
    assert cabecera_pozo.nombre_pozo(reg, "archivo") == esperado


def test_pozo_por_uwi_coordenadas_y_topes(tmp_path):
    pr = Proyecto.vacio()
    pr.nueva_zona("Mi zona")                                          # zona del usuario, antes de importar
    a, _ = _reg(_las(otros=TOPES), tmp_path, "a.las")
    b, _ = _reg(_las(lease="KATIE 1-28", curvas=("RHOB.G/CC",)), tmp_path, "b.las")   # mismo UWI, otras mayúsculas
    c, _ = _reg(_las(well="3", lease="Other 3", uwi="15-081-99999"), tmp_path, "c.las")
    i, nuevo = cabecera_pozo.ubicar_pozo(pr, a)
    assert nuevo and pr.pozos[i].nombre == "Katie 1-28"
    assert (pr.pozos[i].x, pr.pozos[i].y) == pytest.approx((-101.0721631, 37.3810947))
    assert pr.zonas[0].prof(i) == NULO                                # el pozo nuevo no tiene el tope del usuario
    pr.pozos[i].logs.append(a)
    assert cabecera_pozo.topes(a) == [("Heebner Shale Member", 3020.0), ("Lansing Group", 3050.5),
                                      ("Kansas City Group", 3060.0)]
    assert cabecera_pozo.asignar_topes(pr, i, cabecera_pozo.topes(a)) == 3
    assert cabecera_pozo.ubicar_pozo(pr, b) == (i, False)
    j, nuevo = cabecera_pozo.ubicar_pozo(pr, c)
    assert nuevo and j != i
    assert all(z.prof(j) == NULO for z in pr.zonas)                   # el otro pozo no tiene esos topes
    assert [n for n, _, _ in qc.zonas_de_pozo(pr, i)] == ["Heebner Shale Member", "Lansing Group",
                                                           "Kansas City Group"]
    assert qc.zonas_de_pozo(pr, j) == []
    from kurvo.vista.multipozo_ui import intervalo_zona
    assert intervalo_zona(pr, 1, i) == (3020.0, 3050.5)
    t, b2 = intervalo_zona(pr, 1, j)                                  # la zona no está en ese pozo: vacío
    assert not qc.mascara(c, c.columnas[0].datos, t, b2).any()


# ------------------------------------------------------------------ alias y unidades (D106)
def test_alias_y_unidades_de_los_las_reales():
    a = bases.alias_por_defecto()
    grupo = lambda n: a.grupos[a.grupo_de(n)].nombre  # noqa: E731
    assert grupo("RILD") == "RESD" and grupo("RILM") == "RESM" and grupo("RLL3") == "RESS"
    assert grupo("CNLS") == "PHIN" and grupo("DPOR") == "PHID" and grupo("RHOC") == "DRHO"
    assert grupo("DCAL") == "CAL" and grupo("CILD") == "COND" and grupo("NEUT") == "NEUT"
    assert grupo("PHID") == "PHID" and grupo("PHIE") == "POR"
    assert unidades.canonica("DECP") == "V/V" and unidades.canonica("BARNS/E") == "B/E"
    assert unidades.canonica("MMO/M") == "MMHO/M" and unidades.canonica("OHM-M") == "OHMM"
    assert qc.rango_fisico("DPOR", "PU", a) == (-15, 100)


def test_rangos_guardados_antes_reciben_los_grupos_nuevos():
    viejo = preferencias.Preferencias()
    viejo.rangos = {"GR": [("GAPI", 0, 300)]}
    import json
    d = json.loads(viejo.a_json())
    del d["version_rangos"]                                           # como lo guardaba v0.4
    p = preferencias.Preferencias.desde_json(json.dumps(d))
    assert p.rangos["GR"] == [("GAPI", 0, 300)] and "PHID" in p.rangos
    p.rangos.pop("PHID")                                              # el usuario lo quita: queda quitado
    assert "PHID" not in preferencias.Preferencias.desde_json(p.a_json()).rangos


# ------------------------------------------------------------------ validación (D107)
def test_nulos_no_declarados_y_unidades_que_no_cuadran(tmp_path):
    n = 200
    gr = 50 + 10 * np.sin(np.arange(n) / 7)
    phin = 0.12 + 0.05 * np.sin(np.arange(n) / 5)                     # V/V rotulado PU
    dcal = 8 + 0.3 * np.sin(np.arange(n) / 9)                         # pulgadas rotuladas GAPI
    dga = 2.7 + 0.05 * np.sin(np.arange(n) / 3)
    dga[50:60] = -999.0                                               # nulo de otro sistema
    reg, _ = _reg(_las(curvas=("GR.", "CNLS.PU", "DCAL.GAPI", "DGA.G/CC"), datos=[gr, phin, dcal, dga]), tmp_path)
    p = {x.codigo: x for x in validacion.validar(reg)}
    assert "DGA (10)" in p["UNDECLARED_NULL"].mensaje
    textos = " ".join(x.mensaje for x in validacion.validar(reg))
    assert "CNLS" in textos and "V/V" in textos and "DCAL" in textos and "GAPI" in p["NO_UNIT"].mensaje
    from kurvo.nucleo import historial
    historial.aplicar(reg, "Fix all (validation)", "", validacion.corregir_todo, reg)
    assert [c.unidad for c in reg.columnas] == ["FT", "GAPI", "V/V", "IN", "G/CC"]
    assert (reg.columna("DGA").datos[50:60] == NULO).all()
    assert not {"UNDECLARED_NULL", "UNIT_MISMATCH"} & {x.codigo for x in validacion.validar(reg)}
    historial.deshacer(reg)                                           # se deshace como cualquier corrección
    assert reg.columna("CNLS").unidad == "PU"


# ------------------------------------------------------------------ QC (D108)
def test_nulos_fuera_del_intervalo_registrado_no_bajan_la_nota():
    z = np.arange(1000.0)
    gr = 60 + 10 * np.sin(z / 5)
    gr[:600] = NULO                                                   # la curva empieza más abajo
    e = qc.evaluar_curva(gr, z, "GR", "GAPI")
    assert e.pct_nulos == 0 and e.nota == "A" and e.intervalo == (600.0, 999.0)
    gr[700:800] = NULO                                                # hueco interior: sí cuenta
    e = qc.evaluar_curva(gr, z, "GR", "GAPI")
    assert e.pct_nulos == 25 and e.n_huecos == 1


def test_picos_no_marca_cambios_de_capa():
    d = np.r_[np.full(100, 30.0), np.full(100, 120.0), np.full(100, 40.0)] + np.sin(np.arange(300) / 3)
    d[99:101] = [55.0, 95.0]                                          # muestras de transición digitalizadas
    d[199:202] = [100.0, 70.0, 45.0]
    assert not edicion.detectar_picos(d, 11, 4.0).any()
    d[50], d[150] = 200.0, 10.0                                       # picos de una muestra
    d[250:252] = 150.0                                                # pico de dos muestras
    assert np.flatnonzero(edicion.detectar_picos(d, 11, 4.0)).tolist() == [50, 150, 250, 251]


# ------------------------------------------------------------------ importación (D105)
def test_importar_varios_sin_dialogos(qapp, tmp_path, monkeypatch):
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    from kurvo.vista import ventana as V

    def no_preguntar(*a, **k):
        raise AssertionError("la importación múltiple no debe preguntar")
    monkeypatch.setattr(V, "pedir", no_preguntar)
    carpeta = tmp_path / "campo" / "sub"
    carpeta.mkdir(parents=True)
    (carpeta / "Katie_1-28.las").write_text(_las(otros=TOPES), encoding="utf-8")
    (carpeta / "Katie_1-28_part1.LAS").write_text(_las(lease="KATIE 1-28", curvas=("RHOB.G/CC",)), encoding="utf-8")
    (tmp_path / "campo" / "Other_3.las").write_text(_las(well="3", lease="Other 3", uwi="15-081-9"), encoding="utf-8")
    (tmp_path / "campo" / "roto.las").write_text("no es un LAS", encoding="utf-8")
    v = V.VentanaPrincipal()
    avisos = []
    monkeypatch.setattr(V, "aviso", lambda w, t, *a: avisos.append(t))
    try:
        nuevos = v.importar_carpeta_las(str(tmp_path / "campo"))
        pr = v.proyecto
        assert len(nuevos) == 3 and [p.nombre for p in pr.pozos] == ["Other 3", "Katie 1-28"]
        assert len(pr.pozos[1].logs) == 2 and [z.nombre for z in pr.zonas][:2] == ["Heebner Shale Member",
                                                                                     "Lansing Group"]
        assert pr.zonas[0].prof(0) == NULO and pr.zonas[0].prof(1) == 3020.0
        assert len(avisos) == 1 and "1" in avisos[0]                  # el archivo roto, informado al final
        assert v.acciones["import_las_folder"].text()
    finally:
        v.proyecto.modificado = False
        v.close()


# ------------------------------------------------------------------ D110
def test_mismo_nombre_otro_uwi_es_otro_pozo(tmp_path):
    pr = Proyecto.vacio()
    a, _ = _reg(_las(well="1", lease="Borger 1", uwi="15-135-19010"), tmp_path, "a.las")
    b, _ = _reg(_las(well="1", lease="Borger 1", uwi="15-135-19009"), tmp_path, "b.las")
    s, _ = _reg(_las(well="1", lease="Borger 1", uwi=""), tmp_path, "c.las")
    i, _ = cabecera_pozo.ubicar_pozo(pr, a)
    pr.pozos[i].logs.append(a)
    j, nuevo = cabecera_pozo.ubicar_pozo(pr, b)
    assert nuevo and j != i and pr.pozos[j].nombre == "Borger 1 (15-135-19009)"
    assert cabecera_pozo.ubicar_pozo(pr, s) == (i, False)            # sin UWI: por el nombre


def test_registro_compuesto_de_las_partes(tmp_path):
    from kurvo.nucleo import operaciones
    n = 200
    seno = 50 + 10 * np.sin(np.arange(n) / 7)
    p1, _ = _reg(_las(curvas=("GR.GAPI", "DT.US/F"), datos=[seno, seno + 30]), tmp_path, "p1.las")
    p2, _ = _reg(_las(curvas=("GR.GAPI", "DT.US/F", "ILD.OHMM"), datos=[seno, seno + 35, seno / 10]), tmp_path, "p2.las")
    p3, _ = _reg(_las(curvas=("RHOB.G/CC",), n=100, datos=[np.full(100, 2.5)]), tmp_path, "p3.las")
    p3.columnas[0].datos = p3.columnas[0].datos + 120.0              # más abajo, con solape parcial
    c = operaciones.componer([p1, p2, p3])
    assert c.nombres() == ["DEPT", "GR", "DT", "DT_2", "ILD", "RHOB"]  # GR igual: una; DT distinto: las dos
    assert c.n_filas == 340 and c.columnas[0].datos[[0, -1]].tolist() == [3000.0, 3169.5]
    assert "[p2]" in c.columna("DT_2").descripcion and c.indice_md == 0
    rhob = c.columna("RHOB").datos
    assert (rhob[:240] == NULO).all() and (rhob[240:] == 2.5).all()
    assert len(p1.columnas) == 3                                     # los originales no cambian
    with pytest.raises(ValueError):
        operaciones.componer([p1])


def test_calibre_cerrado_y_picos_por_mil():
    a = bases.alias_por_defecto()
    z = np.arange(3000.0)
    dcal = 8 + 0.3 * np.sin(z / 9)
    dcal[:1800] = -2.9                                               # sube con el brazo cerrado
    e = qc.evaluar_curva(dcal, z, "DCAL", "IN", a)
    assert e.cerradas == 1800 and e.fuera_rango == 0 and e.nota == "B"
    assert any("1800" in x and "0–1799" in x for x in e.avisos)
    gr = 60 + 10 * np.sin(z / 5)
    gr[[500, 1500, 2500]] = 300.0                                    # 1 pico cada 1000 muestras
    e = qc.evaluar_curva(gr, z, "GR", "GAPI", a)
    assert e.picos == 3 and e.nota == "A"
    gr[50:3000:150] = 300.0                                          # ~7 picos cada 1000 muestras
    assert qc.evaluar_curva(gr, z, "GR", "GAPI", a).nota == "B"
    assert validacion.unidad_sugerida("DCAL", "GAPI", dcal) == "IN"  # por el tramo abierto
    assert validacion.unidad_sugerida("C1", "units", dcal + 100) == ""  # gas de lodo: no es calibre


# ------------------------------------------------------------------ los LAS reales (si están)
@pytest.mark.skipif(not DATA.exists(), reason="data/ (LAS reales del KGS) no está")
# ------------------------------------------------------------------ D111
def test_plantilla_standard_con_sp_y_registros_antiguos(qapp, tmp_path):
    from kurvo.nucleo import plantilla_auto
    from kurvo.nucleo.plantilla import Plantilla
    from kurvo.vista.logplot import DatosLogPlot, LogPlot
    a = bases.alias_por_defecto()
    grupo = lambda n: a.grupos[a.grupo_de(n)].nombre  # noqa: E731
    assert [grupo(n) for n in ("RES", "LL8", "GUARD", "SON", "DTC1", "NPRL", "GRSG", "TSS1")] == [
        "RESD", "RESS", "RESS", "DTC", "DTC", "PHIN", "GR", "TENS"]
    n = 400
    z = np.arange(n)
    sp = -480 + 40 * np.sin(z / 9)                                    # línea base de El Dorado (~ −500 mV)
    sp[:100] = 200.0                                                  # tramo entubado, plano y lejos
    neu = 300 + 150 * np.sin(z / 11)                                  # neutrón en cuentas (API)
    reg, _ = _reg(_las(curvas=("GR.GAPI", "SP.MV", "RES.OHMM", "NEU.NAPI"),
                       datos=[60 + 0 * sp, sp, 10 + 5 * np.sin(z / 4), neu], n=n), tmp_path)
    pr = Proyecto.vacio()
    i, _ = cabecera_pozo.ubicar_pozo(pr, reg)
    pr.pozos[i].logs.append(reg)
    t = plantilla_auto.plantilla_estandar(pr, a)
    pistas = [[c.nombre_x for c in p.curvas] for p in t.pistas]
    assert pistas[0] == ["GR", "CAL", "SP"] and ["NEUT"] in pistas
    from kurvo.nucleo.plantilla import PISTA_LITOLOGIA
    assert t.pistas[1].tipo == PISTA_LITOLOGIA and t.pistas[1].x > t.pistas[0].x + t.pistas[0].ancho
    assert not any("RMIC" in p for p in pistas)                       # sin microlog en el proyecto: sin su pista
    sp_t = t.pistas[0].curvas[2]
    assert sp_t.escala_auto and not t.pistas[0].curvas[0].escala_auto
    t.guardar(tmp_path / "x.kvplantilla")                              # la escala automática se guarda
    assert Plantilla.abrir(tmp_path / "x.kvplantilla").pistas[0].curvas[2].escala_auto
    lp = LogPlot(DatosLogPlot(t, reg, alias=a, prof_propia=(3050.0, 3199.5)))   # sin el tramo entubado
    lo, hi = lp.escala(sp_t)
    assert lo <= -510 and -450 <= hi <= -400 and hi - lo <= 200
    assert lp.curvas[(2, 0)].columnas == [reg.indice_columna("RES")]  # RES en la pista de resistividad
    lo, hi = lp.escala(t.pistas[-1].curvas[0])
    assert lo <= 160 and 440 <= hi <= 600


def test_porosidad_en_otra_unidad_y_gases_no_salen_de_la_pista(qapp, tmp_path):
    """D112: al dibujar, la porosidad en PU sobre una escala de V/V se pasa a V/V, y los gases C1/C2
    de un registro de lodo ("units") no van a la pista del calibre."""
    from kurvo.nucleo import plantilla_auto
    from kurvo.vista.logplot import DatosLogPlot, LogPlot
    a = bases.alias_por_defecto()
    z = np.arange(200)
    reg, _ = _reg(_las(curvas=("NPHI.%", "DPHI.DECP", "CALI.IN", "C1.units"),
                       datos=[20 + 5 * np.sin(z / 5), 0.15 + 0.05 * np.sin(z / 7), 8 + 0 * z, 50 + 40 * np.sin(z / 3)]),
                  tmp_path)
    pr = Proyecto.vacio()
    i, _ = cabecera_pozo.ubicar_pozo(pr, reg)
    pr.pozos[i].logs.append(reg)
    t = plantilla_auto.plantilla_estandar(pr, a)                      # mediana de las medianas (20; 0,15): PU
    lp = LogPlot(DatosLogPlot(t, reg, alias=a))
    pistas = {c.nombre_x: (i, j) for i, p in enumerate(t.pistas) for j, c in enumerate(p.curvas)}
    phin, phid, cal = (lp.curvas[pistas[g]] for g in ("PHIN", "PHID", "CAL"))
    assert lp.escala(phin.plantilla) == (-15, 45)
    k = reg.indice_columna("NPHI")
    assert lp.datos_dibujo(k, phin.plantilla) is reg.columnas[k].datos                     # ya en %
    k = reg.indice_columna("DPHI")
    assert np.allclose(lp.datos_dibujo(k, phid.plantilla), reg.columnas[k].datos * 100)   # V/V → PU
    assert reg.columnas[k].datos.max() < 1                                                 # los datos no cambian
    assert cal.columnas == [reg.indice_columna("CALI")]


@pytest.mark.skipif(not DATA.exists(), reason="data/ (LAS reales del KGS) no está")
def test_campos_reales_del_kgs(qapp, tmp_path, monkeypatch):
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    from kurvo.vista import ventana as V
    avisos = []
    monkeypatch.setattr(V, "aviso", lambda w, t, *a: avisos.append(t))
    campos = (p for p in DATA.iterdir() if p.is_dir() and p.name not in ("proyectos", "DLIS", "banco_dl") and any(p.rglob("*.las")))
    for campo in sorted(campos):                                  # proyectos/ guarda LAS exportados (D115); banco_dl/, el banco de DL
        v = V.VentanaPrincipal()
        try:
            archivos = {p.resolve() for p in campo.rglob("*") if p.suffix.lower() == ".las"}
            nuevos = v.importar_carpeta_las(str(campo))
            assert len(nuevos) == len(archivos) and not avisos, (campo.name, avisos)
            pr = v.proyecto
            assert len(pr.pozos) < len(archivos)                      # las partes de un pozo van juntas
            assert not any(p.nombre.strip().isdigit() for p in pr.pozos)  # no hay pozos "1", "2"...
            assert pr.zonas                                           # coordenadas en todo pozo cuyo LAS las trae
            assert all(p.x != 0 for p in pr.pozos if any(cabecera_pozo.coordenadas(r) for r in p.logs))
            notas = [e.nota for p in pr.pozos for r in p.logs for e in qc.notas(r, v.alias).values()]
            assert notas.count("C") < 0.1 * len(notas), campo.name
            en_plantilla = {v.alias.grupo_de(c.nombre_x) for p in pr.plantillas[0].pistas for c in p.curvas}
            sin_curvas = [p.nombre for p in pr.pozos              # ningún pozo queda vacío en la plantilla (D111)
                          if not any(v.alias.grupo_de(c.nombre) in en_plantilla for r in p.logs for c in r.columnas[1:])]
            assert not sin_curvas, (campo.name, sin_curvas)
            for p in pr.pozos:
                for r in p.logs:
                    validacion.corregir_todo(r)
                    assert not any(x.nivel == validacion.ERROR for x in validacion.validar(r)), (p.nombre, r.nombre)
        finally:
            v.proyecto.modificado = False
            v.close()


def test_tvdss_en_pozo_de_tierra(tmp_path):
    """Pendiente 24: con KB mayor que el tope del registro, la TVDSS de arriba es negativa; antes el
    abs() del intervalo la doblaba (Sara 1-28: 1240–2910 en vez de −1240 a 2896)."""
    from kurvo.nucleo import operaciones
    from kurvo.nucleo.plantilla import Plantilla
    from kurvo.nucleo.trayectoria import Estacion, Trayectoria
    from kurvo.vista.logplot import DatosLogPlot, LogPlot
    reg, _ = _reg(_las(n=4001), tmp_path)                 # 3000–5000 ft MD
    t = Trayectoria(estaciones=[Estacion(0.0, inc=0.0), Estacion(6000.0, inc=0.0)], tvd_a_ss=3500.0)
    t.calcular()
    operaciones.crear_tvd(reg, t)
    tpl = Plantilla()
    tpl.nueva_curva(tpl.nueva_pista(), "GR")
    lp = LogPlot(DatosLogPlot(plantilla=tpl, registro=reg, trayectoria=t, modo=1))
    assert (lp.prof_min, lp.prof_max) == (-500.0, 1500.0) and not lp.mensajes
    md = LogPlot(DatosLogPlot(plantilla=tpl, registro=reg, trayectoria=t, modo=2))
    assert (md.prof_min, md.prof_max) == (3000.0, 5000.0)  # MD: desde el primer dato (D127)


def test_corte_zonas_visibles_y_pozos_guardados(qapp, tmp_path, monkeypatch):
    """Pendiente 26: el corte dibuja solo las zonas marcadas (la de aplanamiento siempre) y guarda en el
    proyecto los pozos y zonas marcados."""
    from PySide6.QtCore import Qt
    from kurvo.vista import ventana as V
    monkeypatch.setattr(V, "aviso", lambda *a, **k: None)
    rutas = []
    for k, (lease, uwi) in enumerate((("Katie 1-28", "15-081-21195"), ("Sara 1-28", "15-081-21142"))):
        ruta = tmp_path / f"{k}.las"
        ruta.write_text(_las(lease=lease, uwi=uwi, otros=TOPES), encoding="utf-8")
        rutas.append(str(ruta))
    v = V.VentanaPrincipal()
    try:
        v.importar_varios_las(rutas)
        pc, pr = v.pagina_corte, v.proyecto
        pc.refrescar()
        assert pc.lista_zonas.count() == len(pr.zonas) == 3
        pc.ch_zona.setCurrentIndex(2)                          # aplanar en la zona 1
        pc.lista_zonas.item(0).setCheckState(Qt.Unchecked)
        pc.lista_zonas.item(1).setCheckState(Qt.Unchecked)
        pc.lista.item(1).setCheckState(Qt.Unchecked)
        assert pr.corte.zonas_visibles == [False, False, True]
        assert [p.pozo for p in pr.corte.pozos] == [0]
        (plot, _), = pc.construir()
        profs = [d for _, d in plot.d.zonas]
        assert profs[0] == NULO and profs[1] == 3050.5 and profs[2] == 3060.0
    finally:
        v.proyecto.modificado = False
        v.close()


def test_quitar_picos_deja_al_qc_sin_picos():
    """Un solo criterio: con los parámetros del QC, después de "Quitar picos" el QC no cuenta ninguno
    (antes una pasada dejaba picos menores: la escala robusta se achica al quitar los grandes)."""
    rng = np.random.default_rng(7)
    d = 60 + 8 * np.sin(np.arange(3000) / 40) + rng.normal(0, 0.5, 3000)
    idx = rng.choice(np.arange(5, 2995), 120, replace=False)
    d[idx] += rng.choice([-1, 1], 120) * rng.uniform(3, 60, 120)   # picos de tamaños muy distintos
    u = preferencias.actual().qc
    assert edicion.detectar_picos(d, u.ventana_picos, u.sigma_picos).sum() > 0
    out, n = edicion.quitar_picos(d, np.arange(3000.0), u.ventana_picos, u.sigma_picos, "median")
    assert n >= 1 and edicion.detectar_picos(out, u.ventana_picos, u.sigma_picos).sum() == 0
    st = qc.evaluar_curva(out, np.arange(3000.0), "GR", "GAPI")
    assert st.picos == 0


DLIS_REAL = DATA / "DLIS" / "Fallon_FORGE_21-31" / "DM9E-00185_Ormat_Carson_Forge-21-31_TCOM_ConCu_R02_L002Up.dlis"


@pytest.mark.skipif(not DLIS_REAL.exists(), reason="el DLIS de Fallon FORGE 21-31 (data/, no versionada) no está")
def test_dlis_real_de_compania_de_servicio(qapp, tmp_path, monkeypatch):
    """Pendiente A2: DLIS real (Schlumberger, triple combo de Fallon FORGE 21-31, DOE, CC-BY). Los 6 frames
    se leen; las curvas del LAS que la compañía entregó junto al DLIS dan los mismos valores; la pasada
    de subida se detecta y "Corregir todo" la ordena."""
    pytest.importorskip("dlisio")
    from kurvo.nucleo import intercambio, lote
    from kurvo.vista import ventana as V
    frames = {f.frame: f for f in intercambio.leer_dlis(DLIS_REAL)}
    assert len(frames) == 6 and all(f.registro.nombre_pozo == "Forge 21-31" for f in frames.values())
    assert any(o.startswith("HLSP") for o in frames["10B"].omitidos)          # arreglos: omitidos y anotados
    las = RegistroLAS.abrir(DLIS_REAL.with_suffix(".las"))
    pl = las.columnas[0].datos

    def igual(nombre, r):                     # la misma curva puede estar en varios frames con otro muestreo
        k, pd = r.indice_columna(nombre), r.columnas[0].datos
        a = las.columnas[las.indice_columna(nombre)].datos
        orden = np.argsort(pd)
        y = np.interp(pl, pd[orden], r.columnas[k].datos[orden])
        m = (a != NULO) & np.isfinite(y) & (y != NULO)
        return m.sum() > 100 and np.median(np.abs(y[m] - a[m])) <= 1e-3 * (np.median(np.abs(a[m])) + 1e-9)
    comunes = [n for n in las.nombres()[1:] if any(f.registro.indice_columna(n) >= 0 for f in frames.values())]
    iguales = [n for n in comunes if any(igual(n, f.registro) for f in frames.values()
                                         if f.registro.indice_columna(n) >= 0)]
    assert len(comunes) >= 50 and iguales == comunes
    monkeypatch.setattr(V, "aviso", lambda *a, **k: None)
    v = V.VentanaPrincipal()
    try:
        assert len(v.importar_dlis(None, str(DLIS_REAL))) == 6
        reg = next(x for x in v.proyecto.pozos[0].logs if x.nombre.endswith("60B"))
        assert any("bottom-up" in str(x) for x in validacion.validar(reg))
        lote.ejecutar_uno("fix", reg, {})
        prof = reg.columnas[reg.indice_md].datos
        assert np.all(np.diff(prof) > 0) and not any("bottom-up" in str(x) for x in validacion.validar(reg))
    finally:
        v.proyecto.modificado = False
        v.close()


