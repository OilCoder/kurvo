"""Mide el rendimiento con un proyecto sintético grande (v0.4, D89).

Uso: .venv/Scripts/python tests/medir_rendimiento.py [pozos] [muestras] [curvas]
(por defecto 50 × 20 000 × 15). Imprime los tiempos en segundos de: generar, guardar y abrir el
.kurvo, abrir en la ventana, cambiar la selección, editar una celda, reconstruir el árbol (frío y
con la caché de QC) y calcular el tablero de QC."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
os.environ["KURVO_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="kurvo_rend_"), "a.ini")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class Cronometro:
    def __init__(self):
        self.tiempos: dict[str, float] = {}

    def __call__(self, nombre, funcion, *args):
        t0 = time.perf_counter()
        r = funcion(*args)
        self.tiempos[nombre] = time.perf_counter() - t0
        print(f"{nombre:<38} {self.tiempos[nombre]:8.3f} s", flush=True)
        return r


def medir(n_pozos=50, n_muestras=20000, n_curvas=15, ventana_qt=True) -> dict[str, float]:
    from kurvo.demo import proyecto_grande
    from kurvo.nucleo import qc
    from kurvo.nucleo.proyecto import Proyecto
    c = Cronometro()
    pr = c("generar proyecto", proyecto_grande, n_pozos, n_muestras, n_curvas)
    ruta = Path(tempfile.mkdtemp(prefix="kurvo_rend_")) / "grande.kurvo"
    c("guardar .kurvo", pr.guardar, ruta)
    c("abrir .kurvo (núcleo)", Proyecto.abrir, ruta)
    c("notas QC, un registro tras otro (frío)",
      lambda: [qc.notas(r) for p in pr.pozos for r in p.logs])
    qc.invalidar()
    c("notas QC en paralelo (frío)", qc.notas_varios, [r for p in pr.pozos for r in p.logs])
    if not ventana_qt:
        return c.tiempos
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    v.resize(1600, 960)
    v.show()
    app.processEvents()
    qc.invalidar()
    c("abrir en la ventana (incluye árbol)", v.abrir, str(ruta))
    app.processEvents()
    c("cambiar la selección (otro pozo)", lambda: (v.seleccion.fijar(pozo=n_pozos // 2, log=0, curva="GR"),
                                                    app.processEvents()))
    v.pestanas.setCurrentWidget(v.editor_logs)
    app.processEvents()
    m = v.editor_logs.modelo
    c("editar una celda", lambda: (m.setData(m.index(10, 2), "55.5"), app.processEvents()))
    c("reconstruir el árbol (con caché QC)", v.reconstruir_arbol)
    qc.invalidar()
    c("reconstruir el árbol (QC en frío)", v.reconstruir_arbol)
    v.mostrar_panel("qc")
    c("tablero de QC", lambda: (v.panel_qc.ir_a("dashboard"), v.panel_qc.datos_cambiados(),
                                app.processEvents()))
    v.proyecto.modificado = False
    v.close()
    return c.tiempos


if __name__ == "__main__":
    args = [int(x) for x in sys.argv[1:4]]
    medir(*args)
