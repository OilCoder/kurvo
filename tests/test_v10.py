"""1.0: navegación por los siete pasos del trabajo, pantalla de inicio, ejemplos y eje de profundidad
sobre el gráfico (D123), que salieron de la prueba manual del 20 de octubre (docs/prueba_manual_1.0.md)."""
from pathlib import Path

from kurvo.nucleo import cabecera_pozo, flujo
from kurvo.nucleo.comun import NULO
from kurvo.nucleo.las import RegistroLAS
from kurvo.nucleo.trayectoria import Trayectoria

LAS_KGS = """~Version
VERS. 2.0 :
WRAP. NO :
~Well
STRT.FT 1000.0 :
STOP.FT 1010.0 :
STEP.FT 1.0 :
NULL. -999.25 :
WELL. 33 : WELL
LEASE. Bloir 'A' : LEASE
ELEV  .  1379.0 : ELEVATION
EREF  .  KB : ELEVATION_REFERENCE
~Curve
DEPT.FT :
GR.GAPI :
~ASCII
""" + "".join(f"{1000 + i:.1f} {50 + i}\n" for i in range(11))


def _reg(tmp_path, texto=LAS_KGS):
    ruta = tmp_path / "x.las"
    ruta.write_text(texto, encoding="latin-1")
    r = RegistroLAS.abrir(str(ruta))
    r.fijar_indices(0, -1)
    return r


def test_kb_de_la_cabecera(tmp_path):
    """Los LAS del KGS traen la KB como ELEV con EREF KB: la TVDSS ya no pide cargarla a mano."""
    r = _reg(tmp_path)
    assert cabecera_pozo.elevacion_kb(r) == 1379.0
    assert cabecera_pozo.elevacion_kb(_reg(tmp_path, LAS_KGS.replace("KB : ELEV", "GL : ELEV"))) == NULO
    from kurvo.nucleo.proyecto import Pozo
    pozo = Pozo("Bloir 'A' 33")
    assert cabecera_pozo.fijar_kb(pozo, r) and pozo.trayectoria.tvd_a_ss == 1379.0
    pozo.trayectoria.tvd_a_ss = 1000.0                  # la que ya tiene el pozo no se cambia
    assert not cabecera_pozo.fijar_kb(pozo, r) and pozo.trayectoria.tvd_a_ss == 1000.0


def test_importar_trayectoria_conserva_la_kb_del_archivo(qapp, tmp_path, monkeypatch):
    """Nota 4: Importar ignoraba el #TVD_TO_SS del archivo y dejaba el valor de la casilla."""
    from kurvo.vista import editores
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    try:
        v.proyecto.nuevo_pozo("P1", 0, 0)
        v.refrescar_todo()
        archivo = tmp_path / "t.txt"
        archivo.write_text("#TVD_TO_SS 1379\n#MD INC AZIM\n0 0 0\n1000 1 0\n", encoding="utf-8")
        monkeypatch.setattr(editores.QFileDialog, "getOpenFileName", lambda *a, **k: (str(archivo), ""))
        v.editor_tray.importar()
        t = v.proyecto.pozos[0].trayectoria
        assert t.tvd_a_ss == 1379.0 and len(t.estaciones) == 2
        assert "1379" in v.editor_tray.lbl_resumen.text()            # el efecto se ve (nota 6)
    finally:
        v.proyecto.modificado = False
        v.close()


def test_siguiente_paso():
    p = [flujo.EstadoPaso(k, t, a, flujo.OPCIONAL) for k, t, a in flujo.PASOS]
    p[0].estado, p[1].estado, p[5].estado = flujo.HECHO, flujo.AVISO, flujo.PENDIENTE
    assert flujo.siguiente(p) == 1                 # recién importado: Revisar antes que Comprobar
    p[2].estado = flujo.HECHO
    assert flujo.siguiente(p) == 5                 # ya corrigió algo: Comprobar
    for x in p:
        x.estado = flujo.HECHO
    assert flujo.siguiente(p) == -1


def test_inicio_ejemplo_eje_y_buscador(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QStandardPaths
    from kurvo.vista.ventana import VentanaPrincipal
    QStandardPaths.setTestModeEnabled(True)
    v = VentanaPrincipal()
    try:
        assert v.centro.currentWidget() is v.inicio                 # sin pozos: ¿qué quieres hacer?
        destino = v.abrir_ejemplo("el_dorado")
        assert destino is not None and (destino / "topes.txt").exists()
        assert len(v.proyecto.pozos) == 12 and v.centro.currentWidget() is v.pestanas
        assert v.pestanas.currentWidget() is v.pagina_logplot
        assert all(p.trayectoria.tvd_a_ss > 1000 for p in v.proyecto.pozos)      # KB de la cabecera
        assert "next step" in v.franja.lbl_siguiente.text()
        # eje de profundidad: un pozo sin trayectoria se declara vertical y la TVD se calcula sola
        pl = v.pagina_logplot
        pozo, reg = pl._pozo_y_registro()
        assert not reg.existe_columna(reg.indice_tvd)
        assert not pl.preparar_tvd(1, preguntar=lambda: "")                     # cancelar
        assert pl.preparar_tvd(1, preguntar=lambda: "vertical")
        assert all(r.existe_columna(r.indice_tvd) for r in pozo.logs) and len(pozo.trayectoria.estaciones) == 2
        tvd = reg.columnas[reg.indice_tvd].datos
        md = reg.columnas[reg.indice_md].datos
        assert abs(float(tvd[md != NULO][-1]) - float(md[md != NULO][-1])) < 1e-6
        # el buscador encuentra una herramienta por parte de su nombre
        disparadas = []
        v.acciones["create_tvd"].triggered.connect(lambda *_: disparadas.append(1))
        v.franja._buscar("tvd from")
        assert disparadas
        # cada vista del centro se abre desde su acción
        for clave, w in v.vistas.items():
            if clave != "tpl":                       # la plantilla abre su ventana
                v.mostrar_vista(clave)
                assert v.pestanas.currentWidget() is w
        v.pagina_inicio()
        assert v.centro.currentWidget() is v.inicio
    finally:
        v.proyecto.modificado = False
        v.close()
        QStandardPaths.setTestModeEnabled(False)


def test_trayectoria_vacia_explica_que_falta(qapp, tmp_path):
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    try:
        v.proyecto.nuevo_pozo("P1", 0, 0)
        v.proyecto.pozos[0].trayectoria = Trayectoria()
        v.refrescar_todo()
        v.editor_tray.cargar()
        assert "vertical" in v.editor_tray.lbl_resumen.text()
    finally:
        v.proyecto.modificado = False
        v.close()


def test_ejemplos_en_el_ejecutable_van_junto_al_exe():
    bat = (Path(__file__).resolve().parents[1] / "empaquetado" / "construir.bat").read_text(encoding="utf-8")
    assert "_internal\\ejemplos" in bat and "move" in bat


def test_qc_a_pantalla_completa_y_salida_del_inicio(qapp, tmp_path):
    """Segunda prueba manual: con pozos y uno elegido seguía la pantalla de inicio; el QC se abría en un
    lateral."""
    from kurvo.vista.ventana import VentanaPrincipal
    from kurvo.demo import proyecto_demo
    v = VentanaPrincipal()
    try:
        v.show()
        v.proyecto = proyecto_demo()
        v.centro.setCurrentWidget(v.inicio)
        v.seleccion.fijar(pozo=0, log=0, curva="")
        assert v.centro.currentWidget() is v.pestanas
        v.docks["proyecto"].show()                  # la disposición guardada por otras pruebas puede ocultarlo
        v.acciones["qc_window"].trigger()
        qapp.processEvents()
        assert v.centro.isHidden() and v.docks["proyecto"].isHidden() and v.panel_qc.b_ampliar.isChecked()
        v.ribbon.setCurrentIndex(2)                   # otro paso: el QC vuelve al lateral
        qapp.processEvents()
        assert not v.centro.isHidden() and not v.docks["proyecto"].isHidden()
    finally:
        v.proyecto.modificado = False
        v.close()


def test_el_centro_muestra_solo_las_vistas_del_paso(qapp, tmp_path):
    """Tercera prueba manual: las diez pestañas del centro se veían en todos los pasos."""
    from kurvo.demo import proyecto_demo
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    v.proyecto = proyecto_demo()
    v.refrescar_todo()
    assert v.pestanas.tabBar().isHidden()            # una sola navegación: los pasos de arriba
    grupos_vistas = {}
    for paso in range(v.ribbon.count()):
        v.ribbon.setCurrentIndex(paso)
        assert v.pestanas.currentWidget() in [v.vistas[k] for k in v.VISTAS_POR_PASO[paso]] + [
            w for k, w in v.vistas.items() if k not in {x for vs in v.VISTAS_POR_PASO for x in vs}]
    for g, t in v.ribbon.grupos:
        grupos_vistas.setdefault(t, 0)
        grupos_vistas[t] += 1
    assert grupos_vistas["Views"] == 7                # cada paso termina con sus vistas
    v.ribbon.setCurrentIndex(3)
    v.acciones["view_trajectory"].trigger()
    assert v.pestanas.currentWidget() is v.editor_tray and v.acciones["view_trajectory"].isChecked()
    v.ribbon.setCurrentIndex(1)                      # Revisar no tiene la trayectoria: vuelve al gráfico
    assert v.pestanas.currentWidget() is v.pagina_logplot and v.acciones["view_logplot"].isChecked()
    v.acciones["mod:view/Pickett Plot"].trigger()
    assert v.pestanas.currentWidget() is v.vistas["Pickett Plot"]
    v.ribbon.setCurrentIndex(0)
    v.mostrar_vista("tray")                          # pedida desde Ver o el buscador: aparece igual
    assert v.pestanas.currentWidget() is v.editor_tray
    d = v.mostrar_vista("tpl")                       # la plantilla es una ventana, no una pestaña
    assert d.isVisible() and v.editor_tpl.isVisible() and v.pestanas.indexOf(v.editor_tpl) < 0
    d.close()
    v.proyecto.modificado = False
    v.close()


def test_formato_propio_kurvo(tmp_path):
    """D124: el proyecto se guarda en un formato propio (zip con proyecto.json, LAS 2.0 e historial)."""
    import json
    import zipfile

    import pytest
    from kurvo.demo import proyecto_demo
    from kurvo.nucleo import historial
    from kurvo.nucleo.proyecto import ErrorProyecto, Proyecto
    pr = proyecto_demo()
    reg = pr.pozos[0].logs[0]
    historial.aplicar(reg, "Smooth", "", lambda: reg.columna("GR").datos.__setitem__(5, 1.0))
    pr.pozos[0].trayectoria.tvd_a_ss = 1379.0
    ruta = tmp_path / "p.kurvo"
    pr.guardar(ruta)
    with zipfile.ZipFile(ruta) as z:
        datos = json.loads(z.read("proyecto.json"))
        assert datos["formato"] == "kurvo-proyecto" and datos["version"] == 1
        assert f"registros/{reg.uid}.las" in z.namelist() and f"historial/{reg.uid}.bitacora" in z.namelist()
    q = Proyecto.abrir(ruta)
    r2 = q.pozos[0].logs[0]
    assert [p.nombre for p in q.pozos] == [p.nombre for p in pr.pozos]
    assert r2.columna("GR").datos[5] == 1.0 and r2.historial.bitacora[-1].operacion == "Smooth"
    assert "GR" in r2.historial.originales and q.pozos[0].trayectoria.tvd_a_ss == 1379.0
    assert len(q.plantillas) == len(pr.plantillas) and len(q.zonas) == len(pr.zonas)
    # un archivo que no es un proyecto del programa se rechaza con un mensaje claro
    otro = tmp_path / "otro.kurvo"
    with zipfile.ZipFile(otro, "w") as z:
        z.writestr("version.ini", "MAJOR=2013")
    with pytest.raises(ErrorProyecto):
        Proyecto.abrir(otro)


def test_alias_del_usuario_se_recuerdan():
    from kurvo.nucleo.bases import BaseAlias, alias_por_defecto
    a = alias_por_defecto()
    a.grupos[0].alias.append("MI_ALIAS")
    b = BaseAlias.desde_texto(a.a_texto())
    assert b.grupo_de("MI_ALIAS") == 0 and BaseAlias.desde_texto("{roto") is None


EJEMPLOS = Path(__file__).resolve().parents[1] / "docs" / "ejemplos"


def test_ejemplo_el_dorado_se_arma_con_los_archivos_de_docs(qapp, tmp_path, monkeypatch):
    """docs/ejemplos/el_dorado: 12 pozos variados (productores, mojado, seco, inyector, pozos viejos) con
    topes, trayectoria, litología de 5 mud logs y la mecánica de 8 pozos, todo con las importaciones de la
    aplicación."""
    import zipfile
    from kurvo.vista import ventana as V
    docs = EJEMPLOS / "el_dorado"
    zipfile.ZipFile(docs / "las_el_dorado.zip").extractall(tmp_path / "las")
    actual = {}
    monkeypatch.setattr(V.QFileDialog, "getOpenFileName", lambda *a, **k: (str(docs / actual["f"]), ""))
    monkeypatch.setattr(V, "aviso", lambda *a, **k: None)
    v = V.VentanaPrincipal()
    try:
        assert len(v.importar_carpeta_las(str(tmp_path / "las"))) == 12
        pr = v.proyecto
        assert len(pr.pozos) == 12 and not pr.zonas                       # los topes vienen de topes.txt
        actual["f"] = "topes.txt"
        v.importar_zonas()
        assert len(pr.zonas) == 14
        i = pr.indice_pozo
        arb = next(z for z in pr.zonas if z.nombre == "Arbuckle")
        assert arb.prof(i("Barnhill 'A' 31")) == 2452 and arb.prof(i("COX 'A' 1")) == NULO
        assert all(p.trayectoria.tvd_a_ss > 1300 for p in pr.pozos)          # KB de la cabecera de cada LAS
        nombres = {it.nombre for it in v.base_herr.items}
        completaciones = {"Bloir 'A' 33": ["bloir_a_33_completacion_2011.txt", "bloir_a_33_taponamiento_2014.txt"],
                          "Bloir 'A' 32": ["bloir_a_32_completacion_2010.txt"],
                          "Barnhill 'A' 31": ["barnhill_a_31_completacion_2011.txt"],
                          "Koogler 'A' 301": ["koogler_a_301_completacion_2011.txt"],
                          "Hess 'A' 32": ["hess_a_32_completacion_2011.txt"],
                          "Enyart 'A' 115": ["enyart_a_115_completacion_2011.txt"],
                          "Hess 'A' 34": ["hess_a_34_completacion_2013.txt"],
                          "WHIPPLE #8": ["whipple_8_completacion_2022.txt"]}
        for pozo, archivos in completaciones.items():
            for f in archivos:
                actual["f"] = f
                v.importar_comp(i(pozo))
        assert all(h.nombre_herramienta in nombres for p in pr.pozos for c in p.completaciones for h in c.herramientas)
        for pozo, f in (("Bloir 'A' 33", "bloir_a_33_litologia.txt"), ("Barnhill 'A' 31", "barnhill_a_31_litologia.txt"),
                        ("Koogler 'A' 301", "koogler_a_301_litologia.txt"), ("Hess 'A' 32", "hess_a_32_litologia.txt"),
                        ("Hess 'A' 34", "hess_a_34_litologia.txt")):
            actual["f"] = f
            v.importar_lito(i(pozo))
            ints = pr.pozos[i(pozo)].litologias[0].intervalos
            assert all(a.base <= b.tope for a, b in zip(ints, ints[1:]))      # sin solapes
            assert all(x.tope < x.base for x in ints)
        assert pr.pozos[i("Hess 'A' 34")].litologias[0].intervalos[-1].tipo == 5   # Arbuckle: dolomita
        b33 = pr.pozos[i("Bloir 'A' 33")]
        b33.trayectoria = Trayectoria.abrir(docs / "bloir_a_33_trayectoria.txt")
        assert abs(b33.trayectoria.tvd_en(2481.0) - 2480.95) < 0.01
    finally:
        v.proyecto.modificado = False
        v.close()


def test_ejemplo_cutter_se_arma_con_los_archivos_de_docs(qapp, tmp_path, monkeypatch):
    """docs/ejemplos/cutter: 10 pozos de gas y petróleo en areniscas Morrow/Chester (corridas de papel
    digitalizadas, un pozo de 1962, tres modernos con fractura y cementación por etapas y un pozo profundo con
    mud log digital), con topes HUG, litología del mud log y la mecánica de 4 pozos."""
    import zipfile
    from kurvo.vista import ventana as V
    docs = EJEMPLOS / "cutter"
    zipfile.ZipFile(docs / "las_cutter.zip").extractall(tmp_path / "las")
    actual = {}
    monkeypatch.setattr(V.QFileDialog, "getOpenFileName", lambda *a, **k: (str(docs / actual["f"]), ""))
    monkeypatch.setattr(V, "aviso", lambda *a, **k: None)
    v = V.VentanaPrincipal()
    try:
        assert len(v.importar_carpeta_las(str(tmp_path / "las"))) == 36
        pr = v.proyecto
        assert len(pr.pozos) == 10 and not pr.zonas
        actual["f"] = "topes.txt"
        v.importar_zonas()
        assert len(pr.zonas) == 15
        i = pr.indice_pozo
        chester = next(z for z in pr.zonas if z.nombre == "Chester")
        assert chester.prof(i("Sara 1-28")) == 5458 and chester.prof(i("BROWN 3-1")) == NULO
        assert all(p.trayectoria.tvd_a_ss > 2700 for p in pr.pozos)          # KB de la cabecera
        nombres = {it.nombre for it in v.base_herr.items}
        for pozo, archivos in (("Sara 1-28", ["sara_1-28_completacion_1997.txt", "sara_1-28_taponamiento_2022.txt"]),
                               ("BROWN 3-1", ["brown_3-1_completacion_2019.txt"]),
                               ("Cutter #10", ["cutter_10_completacion_2024.txt"]),
                               ("CUTTER W I UNIT (CUTTER KGS 1) 9", ["cutter_wiu_9_completacion_2012.txt"])):
            for f in archivos:
                actual["f"] = f
                v.importar_comp(i(pozo))
        assert all(h.nombre_herramienta in nombres for p in pr.pozos for c in p.completaciones for h in c.herramientas)
        actual["f"] = "cutter_wiu_9_litologia.txt"
        v.importar_lito(i("CUTTER W I UNIT (CUTTER KGS 1) 9"))
        ints = pr.pozos[i("CUTTER W I UNIT (CUTTER KGS 1) 9")].litologias[0].intervalos
        assert len(ints) > 50 and ints[-1].tipo == 22                         # basamento ígneo al fondo
        assert all(a.base <= b.tope for a, b in zip(ints, ints[1:]))
    finally:
        v.proyecto.modificado = False
        v.close()


def test_manual_desde_ayuda(qapp, tmp_path):
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    try:
        d = v.abrir_manual()
        from PySide6.QtWidgets import QTextBrowser
        assert d is not None and "siete pasos" in d.findChild(QTextBrowser).toPlainText()
        d.close()
    finally:
        v.close()


def test_grafico_empieza_donde_hay_datos(qapp):
    """Sin completación ni litología, el gráfico en MD empieza en el primer dato y no en 0 ft
    (los pozos de Cutter, con datos desde 1600 ft, se veían vacíos al seleccionarlos)."""
    import numpy as np
    from kurvo.nucleo.intervalos import Completacion, Herramienta
    from kurvo.nucleo.las import Columna, RegistroLAS
    from kurvo.nucleo.plantilla import Plantilla
    from kurvo.vista.logplot import DatosLogPlot, LogPlot
    prof = np.arange(1600.0, 5780.5, 0.5)
    reg = RegistroLAS(nombre="r", columnas=[Columna("DEPT", prof, "ft"), Columna("ILD", np.ones_like(prof), "ohmm")])
    reg.indice_md = 0
    lp = LogPlot(DatosLogPlot(Plantilla(), reg))
    assert (lp.prof_min, lp.prof_max) == (1600.0, 5780.0)
    comp = Completacion(nombre="c", herramientas=[Herramienta("", "Casing 5-1/2\"", 0.0, 5700.0)])
    lp = LogPlot(DatosLogPlot(Plantilla(), reg, completacion=comp))
    assert (lp.prof_min, lp.prof_max) == (0.0, 5780.0)                 # el revestimiento desde superficie sí cuenta


def test_pistas_sin_datos_se_esconden(qapp):
    """Las pistas sin datos en el pozo no se dibujan y las demás se corren a la izquierda (D128);
    la plantilla del proyecto no cambia."""
    import numpy as np
    from kurvo.nucleo.intervalos import Litologia
    from kurvo.nucleo.las import Columna, RegistroLAS
    from kurvo.nucleo.plantilla import PISTA_LITOLOGIA, CurvaPlantilla, Pista, Plantilla
    from kurvo.vista.logplot import DatosLogPlot, LogPlot
    prof = np.arange(1000.0, 1100.5, 0.5)
    reg = RegistroLAS(nombre="r", columnas=[Columna("DEPT", prof), Columna("GR", np.full_like(prof, 50.0)),
                                            Columna("RHOB", np.full_like(prof, -999.25))])
    reg.indice_md = 0
    t = Plantilla()
    t.pistas = [Pista(x=100, ancho=150, curvas=[CurvaPlantilla(nombre_x="GR")]),
                Pista(x=260, ancho=100, tipo=PISTA_LITOLOGIA),
                Pista(x=370, ancho=150, curvas=[CurvaPlantilla(nombre_x="RHOB")]),
                Pista(x=530, ancho=150, curvas=[CurvaPlantilla(nombre_x="GR")])]
    lp = LogPlot(DatosLogPlot(t, reg, ocultar_vacias=True))
    assert lp.ocultas == 2 and [p.x for p in lp.d.plantilla.pistas] == [100, 260]   # se conserva el espacio de 10
    assert set(lp.curvas) == {(0, 0), (1, 0)} and lp.d.plantilla.pistas[1].curvas[0] is t.pistas[3].curvas[0]
    assert [p.x for p in t.pistas] == [100, 260, 370, 530]                      # la plantilla no cambia
    assert LogPlot(DatosLogPlot(t, reg)).ocultas == 0                          # apagado: se dibuja todo
    lito = Litologia(nombre="l")
    lito.intervalos.append(__import__("kurvo.nucleo.intervalos", fromlist=["IntervaloLito"]).IntervaloLito(1000, 1050, 2))
    lp = LogPlot(DatosLogPlot(t, reg, litologia=lito, ocultar_vacias=True))
    assert lp.ocultas == 1 and [p.x for p in lp.d.plantilla.pistas] == [100, 260, 370]
    lp.imagen()                                                                 # se dibuja sin errores
