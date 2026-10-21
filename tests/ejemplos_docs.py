"""Arma los proyectos de los ejemplos de docs/ejemplos con las importaciones de la aplicación, como lo haría
un usuario siguiendo las guías (capturas y pruebas)."""
import zipfile
from pathlib import Path

EJEMPLOS = Path(__file__).resolve().parents[1] / "docs" / "ejemplos"

# archivo de completación o litología -> pozo (nombre como lo arma la importación)
ARCHIVOS = {
    "el_dorado": {
        "comp": {"Bloir 'A' 33": ["bloir_a_33_completacion_2011.txt", "bloir_a_33_taponamiento_2014.txt"],
                 "Bloir 'A' 32": ["bloir_a_32_completacion_2010.txt"],
                 "Barnhill 'A' 31": ["barnhill_a_31_completacion_2011.txt"],
                 "Koogler 'A' 301": ["koogler_a_301_completacion_2011.txt"],
                 "Hess 'A' 32": ["hess_a_32_completacion_2011.txt"],
                 "Enyart 'A' 115": ["enyart_a_115_completacion_2011.txt"],
                 "Hess 'A' 34": ["hess_a_34_completacion_2013.txt"],
                 "WHIPPLE #8": ["whipple_8_completacion_2022.txt"]},
        "lito": {"Bloir 'A' 33": "bloir_a_33_litologia.txt", "Barnhill 'A' 31": "barnhill_a_31_litologia.txt",
                 "Koogler 'A' 301": "koogler_a_301_litologia.txt", "Hess 'A' 32": "hess_a_32_litologia.txt",
                 "Hess 'A' 34": "hess_a_34_litologia.txt"},
        "tray": {"Bloir 'A' 33": "bloir_a_33_trayectoria.txt"},
        "zip": "las_el_dorado.zip"},
    "cutter": {
        "comp": {"Sara 1-28": ["sara_1-28_completacion_1997.txt", "sara_1-28_taponamiento_2022.txt"],
                 "BROWN 3-1": ["brown_3-1_completacion_2019.txt"],
                 "Cutter #10": ["cutter_10_completacion_2024.txt"],
                 "CUTTER W I UNIT (CUTTER KGS 1) 9": ["cutter_wiu_9_completacion_2012.txt"]},
        "lito": {"CUTTER W I UNIT (CUTTER KGS 1) 9": "cutter_wiu_9_litologia.txt"},
        "tray": {},
        "zip": "las_cutter.zip"},
}


def armar(v, nombre, carpeta, monkeypatch):
    """Importa los LAS, los topes, la mecánica, la litología y la trayectoria del ejemplo en la ventana `v`."""
    from kurvo.nucleo.trayectoria import Trayectoria
    from kurvo.vista import ventana as V
    docs = EJEMPLOS / nombre
    datos = ARCHIVOS[nombre]
    zipfile.ZipFile(docs / datos["zip"]).extractall(carpeta)
    actual = {}
    monkeypatch.setattr(V.QFileDialog, "getOpenFileName", lambda *a, **k: (str(docs / actual["f"]), ""))
    v.importar_carpeta_las(str(carpeta))
    pr = v.proyecto
    actual["f"] = "topes.txt"
    v.importar_zonas()
    for pozo, archivos in datos["comp"].items():
        for f in archivos:
            actual["f"] = f
            v.importar_comp(pr.indice_pozo(pozo))
    for pozo, f in datos["lito"].items():
        actual["f"] = f
        v.importar_lito(pr.indice_pozo(pozo))
    for pozo, f in datos["tray"].items():
        p = pr.pozos[pr.indice_pozo(pozo)]
        kb = p.trayectoria.tvd_a_ss
        p.trayectoria = Trayectoria.abrir(docs / f)
        p.trayectoria.tvd_a_ss = p.trayectoria.tvd_a_ss or kb
        p.trayectoria.calcular()
    v.refrescar_todo()
    return pr
