"""Proyecto de demostración con datos sintéticos propios (para pruebas y capturas)."""
from __future__ import annotations

import datetime as dt

import numpy as np

from .nucleo.comun import NULO
from .nucleo.intervalos import Completacion, Herramienta, IntervaloLito, Litologia
from .nucleo.las import Columna, Mnemonico, RegistroLAS
from .nucleo.plantilla import (BORDE_DER, BORDE_IZQ, PISTA_COMPLETACION, PISTA_LITOLOGIA,
                               AreaPlantilla, Plantilla)
from .nucleo.proyecto import LogPlot, Proyecto
from .nucleo.trayectoria import Estacion, Trayectoria


def _registro(rng, desplaz: float, nombre: str) -> RegistroLAS:
    md = np.arange(150.0, 650.0, 0.5)
    n = len(md)
    arena = (np.sin((md + desplaz) / 37.0) > 0.2) & (md > 220)
    gr = np.where(arena, 35, 95) + rng.normal(0, 6, n)
    sp = np.where(arena, -60, -10) + rng.normal(0, 3, n)
    phi = np.where(arena, 0.24, 0.08) + rng.normal(0, 0.015, n)
    rhob = 2.65 - phi * 1.65 + rng.normal(0, 0.01, n)
    nphi = np.where(arena, phi * 100 - 3, 30 + rng.normal(0, 2, n))
    ild = np.where(arena & (md < 420), 60, 4) * np.exp(rng.normal(0, 0.15, n))
    dt_ = 55.5 + phi * 133.5
    gr[(md > 500) & (md < 510)] = NULO
    tvd = md - 0.002 * np.maximum(md - 300, 0) ** 1.5
    reg = RegistroLAS(nombre=nombre, nombre_pozo="")
    for nom, uni, datos in (("DEPT", "M", md), ("TVD", "M", tvd), ("GR", "API", gr),
                            ("SP", "MV", sp), ("ILD", "OHMM", ild), ("RHOB", "G/C3", rhob),
                            ("NPHI", "PU", nphi), ("DT", "US/F", dt_)):
        reg.columnas.append(Columna(nom, np.round(datos, 4), uni))
    reg.mnemonicos.append(Mnemonico("NULL", "", "-999.25", "", 1))
    reg.fijar_indices(0, 1)
    return reg


def plantilla_demo() -> Plantilla:
    t = Plantilla(nombre="Demo", y=110, escala=300, formato_titulo="Well: [%WELLNAME%]    Log: [%LOGNAME%]")
    p = t.nueva_pista()
    p.x, p.ancho = 70, 130
    c = t.nueva_curva(p, "GR"); c.color, c.escala_min, c.escala_max = "rgb(0, 128, 0)", 0, 150
    c.rejilla_x.micro_paso, c.rejilla_x.macro_paso = 10, 50
    c = t.nueva_curva(p, "SP"); c.color, c.escala_min, c.escala_max = "rgb(255, 0, 0)", -100, 20
    c.rejilla_x.micro_visible = c.rejilla_x.macro_visible = False
    p.areas.append(AreaPlantilla("GR", BORDE_DER, "rgb(183, 255, 211)"))
    p = t.nueva_pista(); p.ancho = 130
    c = t.nueva_curva(p, "ILD"); c.color, c.logaritmica = "rgb(128, 64, 64)", True
    c.escala_min, c.escala_max = 0.2, 2000
    p.areas.append(AreaPlantilla(BORDE_IZQ, "ILD", "rgb(231, 150, 97)"))
    p = t.nueva_pista(); p.ancho = 130
    c = t.nueva_curva(p, "NPHI"); c.color, c.invertida = "rgb(0, 0, 255)", True
    c.escala_min, c.escala_max = 0, 60
    c.rejilla_x.micro_paso, c.rejilla_x.macro_paso = 6, 30
    c = t.nueva_curva(p, "RHOB"); c.color, c.escala_min, c.escala_max = "rgb(255, 0, 128)", 1.65, 2.65
    c.rejilla_x.micro_visible = c.rejilla_x.macro_visible = False
    p.areas.append(AreaPlantilla("RHOB", "NPHI", "rgb(250, 220, 30)"))
    p = t.nueva_pista(PISTA_LITOLOGIA); p.ancho, p.ancho_lito = 150, 50
    p = t.nueva_pista(PISTA_COMPLETACION); p.ancho, p.ancho_comp = 220, 90
    return t


def proyecto_demo(semilla: int = 7) -> Proyecto:
    rng = np.random.default_rng(semilla)
    pr = Proyecto()
    for k, nombre in enumerate(("DEMO-1", "DEMO-2", "DEMO-3")):
        pozo = pr.nuevo_pozo(nombre, 1000.0 * k, 500.0 * k)
        tr = Trayectoria(tvd_a_ss=12.0 + k)
        for md, inc, az in ((0, 0, 0), (250, 1 + k, 90), (450, 6 + 2 * k, 95), (700, 12 + 3 * k, 100)):
            tr.estaciones.append(Estacion(md=md, inc=inc, azim=az))
        tr.calcular()
        pozo.trayectoria = tr
        pozo.logs.append(_registro(rng, 30.0 * k, f"Registro {nombre}"))
        lit = Litologia("Interpretación")
        for tope, base, tipo, com in ((150, 230, 3, "Arcilla"), (230, 330, 1, "Arenisca"),
                                      (330, 360, 4, "Lutita"), (360, 470, 2, "Caliza"),
                                      (470, 640, 1, "Arenisca")):
            lit.intervalos.append(IntervaloLito(tope + 5 * k, base + 5 * k, tipo, com))
        pozo.litologias.append(lit)
        comp = Completacion("Completación", dt.date(2024, 5, 1))
        comp.herramientas += [Herramienta('Casing 9-5/8"', 'Casing 9-5/8"', 0, 250),
                              Herramienta('Zapata 9-5/8"', 'Casing Shoe 9-5/8"', 240, 250),
                              Herramienta('Zapata 7"', 'Casing Shoe 7"', 630, 640),
                              Herramienta('Casing 7"', 'Casing 7"', 0, 640),
                              Herramienta("Tubería 3-1/2\"", 'Tubing 3.5"', 0, 400),
                              Herramienta('Packer 7"', 'Packer 7"', 390, 400),
                              Herramienta("Disparos", 'Perforation 7"', 420, 450)]
        pozo.completaciones.append(comp)
    for nombre, prof, color in (("Tope A", 228, "rgb(255, 0, 128)"), ("Tope B", 330, "rgb(31, 38, 226)"),
                                ("Tope C", 468, "rgb(255, 0, 0)")):
        z = pr.nueva_zona(nombre)
        z.profundidades = [prof + 5 * i for i in range(3)]
        z.color, z.tipo_linea, z.ancho = color, 2, 2
    pr.plantillas.append(plantilla_demo())
    for i in range(3):
        pr.logplots.append(LogPlot(nombre=f"logplot-{i + 1}", pozo=i, las=0, lito=0, comp=0,
                                   plantilla=0, modo_prof=2, zonas_visibles=[True] * 3))
    pr.logplot_actual = 0
    # análisis Pickett y Hingle de ejemplo sobre la arena de DEMO-1
    from .calculos.graficos import AnalisisSw, ConjuntoDatos
    from .nucleo.comun import UID
    from .nucleo.proyecto import Analisis
    reg = pr.pozos[0].logs[0]
    md = reg.columna("DEPT").datos
    sel = (md >= 240) & (md <= 340)
    phi = (2.65 - reg.columna("RHOB").datos[sel]) / 1.65
    an = AnalisisSw(a=1.0, m=2.0, n=2.0, rw=0.05)
    an.conjuntos.append(ConjuntoDatos("Arena (240-340)", pr.pozos[0].uid, reg.uid, "DEMO-1", reg.nombre,
                                      "PHI", "ILD", 240, 340, True, md[sel].tolist(), phi.tolist(),
                                      reg.columna("ILD").datos[sel].tolist()))
    for tipo in ("Pickett", "Hingle"):
        pr.analisis.append(Analisis(tipo, UID.nuevo(), f"{tipo}-1", "0", an.a_texto()))
    pr.modificado = False
    return pr


CURVAS_GRANDE = (("GR", "GAPI"), ("SP", "MV"), ("ILD", "OHMM"), ("ILM", "OHMM"), ("LLS", "OHMM"),
                 ("RHOB", "G/C3"), ("DRHO", "G/C3"), ("NPHI", "V/V"), ("PEF", "B/E"), ("DT", "US/F"),
                 ("DTS", "US/F"), ("CALI", "IN"), ("BS", "IN"))


def proyecto_grande(n_pozos: int = 50, n_muestras: int = 20000, n_curvas: int = 15,
                    semilla: int = 1) -> Proyecto:
    """Proyecto sintético para medir el rendimiento (v0.4, D89): `n_pozos` pozos con un registro de
    `n_muestras` muestras y `n_curvas` columnas (DEPT, TVD y hasta 13 curvas), la plantilla del demo
    y un log plot."""
    rng = np.random.default_rng(semilla)
    pr = Proyecto()
    md = 500.0 + 0.1524 * np.arange(n_muestras)
    curvas = CURVAS_GRANDE[:max(0, n_curvas - 2)]
    for k in range(n_pozos):
        pozo = pr.nuevo_pozo(f"W-{k + 1:03d}", 100.0 * k, 50.0 * k)
        reg = RegistroLAS(nombre=f"Main W-{k + 1:03d}", nombre_pozo=pozo.nombre)
        reg.columnas.append(Columna("DEPT", md.copy(), "M"))
        reg.columnas.append(Columna("TVD", md - 0.001 * (md - 500.0), "M"))
        capa = np.sin((md + 13.0 * k) / 41.0) > 0.1
        for nombre, unidad in curvas:
            base = {"GR": np.where(capa, 40, 100), "SP": np.where(capa, -50, -10),
                    "RHOB": np.where(capa, 2.3, 2.55), "DRHO": np.zeros(n_muestras),
                    "NPHI": np.where(capa, 0.22, 0.32), "PEF": np.where(capa, 2.0, 3.2),
                    "DT": np.where(capa, 85, 105), "DTS": np.where(capa, 150, 190),
                    "CALI": np.full(n_muestras, 8.6), "BS": np.full(n_muestras, 8.5)}.get(nombre)
            if base is None:                         # resistividades
                datos = np.where(capa, 30.0, 3.0) * np.exp(rng.normal(0, 0.2, n_muestras))
            elif nombre == "BS":
                datos = base.astype(float)
            else:
                datos = base + rng.normal(0, 0.02 * (abs(float(np.mean(base))) + 1), n_muestras)
            datos[rng.integers(0, n_muestras - 200):][:150] = NULO
            reg.columnas.append(Columna(nombre, np.round(datos, 4), unidad))
        reg.mnemonicos.append(Mnemonico("NULL", "", "-999.25", "", 1))
        reg.fijar_indices(0, 1)
        pozo.logs.append(reg)
    pr.plantillas.append(plantilla_demo())
    pr.logplots.append(LogPlot(nombre="logplot-1", pozo=0, las=0, plantilla=0, modo_prof=2))
    pr.logplot_actual = 0
    pr.modificado = False
    return pr
