"""Genera los archivos LAS y DLIS "realistas" de datos/realistas/ (v0.4, D92).

No hay LAS ni DLIS reales en el repositorio, así que estos archivos imitan lo que trae un pozo
real: profundidad en pies, nulos -9999, mnemónicos de compañía (GRC, HCAL, AT90, RHOZ, HDRA,
TNPH, PEFZ, DTCO), una pasada repetida, CALI/BS/DRHO con un derrumbe, picos, un tramo plano de
herramienta trabada, huecos al comienzo del registro, unidades distintas entre pozos (G/C3 y
K/M3, V/V y PU, US/F y US/M), un desfase de profundidad entre pozos, filas duplicadas y un STEP
de cabecera incoherente. El DLIS (escrito con `dliswriter`, licencia MIT, solo hace falta para
regenerar) tiene un frame con TDEP en 0.1 in y un canal de forma de onda (2D) que no cabe en un LAS.

Uso: .venv/Scripts/python tests/generar_datos_realistas.py   (los archivos generados se versionan)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

DESTINO = Path(__file__).resolve().parents[1] / "datos" / "realistas"
NULO_ARCHIVO = -9999.0


def geologia(md, desplaz=0.0):
    """Capas de arena/lutita/caliza en función de la profundidad (pies)."""
    z = md + desplaz
    arena = (np.sin(z / 47.0) + 0.4 * np.sin(z / 13.0) > 0.35)
    caliza = (~arena) & (np.sin(z / 91.0) > 0.75)
    return arena, caliza


def curvas_pozo(md, rng, desplaz=0.0, gas_hasta=None):
    arena, caliza = geologia(md, desplaz)
    n = len(md)
    phi = np.where(arena, 0.22, np.where(caliza, 0.08, 0.12)) + rng.normal(0, 0.012, n)
    vsh = np.where(arena, 0.12, np.where(caliza, 0.05, 0.75)) + rng.normal(0, 0.03, n)
    gr = 18 + 120 * np.clip(vsh, 0, 1) + rng.normal(0, 4, n)
    rhob = np.where(caliza, 2.71, 2.65) * (1 - phi) + 1.0 * phi + rng.normal(0, 0.012, n)
    nphi = phi + 0.25 * np.clip(vsh, 0, 1) - np.where(caliza, 0.0, 0.03) + rng.normal(0, 0.01, n)
    rt = np.where(arena, 25.0, np.where(caliza, 60.0, 2.5)) * np.exp(rng.normal(0, 0.12, n))
    if gas_hasta is not None:
        rt = np.where(arena & (md < gas_hasta), rt * 8, rt)
    dt = 47.5 + 140 * phi + 25 * np.clip(vsh, 0, 1) + rng.normal(0, 1.0, n)
    pe = np.where(caliza, 5.1, np.where(arena, 1.9, 3.2)) + rng.normal(0, 0.08, n)
    sp = np.where(arena, -55, -8) + rng.normal(0, 2, n)
    return dict(gr=gr, rhob=rhob, nphi=nphi, rt=rt, dt=dt, pe=pe, sp=sp, arena=arena)


def escribir_las(ruta: Path, pozo: str, md, columnas, step_cabecera=None, nulo=NULO_ARCHIVO, extra_w=()):
    """columnas: lista de (mnemónico, unidad, descripción, datos). `md` en pies."""
    step = step_cabecera if step_cabecera is not None else float(md[1] - md[0])
    lineas = ["~VERSION INFORMATION",
              " VERS.                 2.0 : CWLS LOG ASCII STANDARD - VERSION 2.0",
              " WRAP.                  NO : ONE LINE PER DEPTH STEP",
              "~WELL INFORMATION",
              "#MNEM.UNIT       DATA                        DESCRIPTION",
              "#----- -----    ------------------          ------------",
              f" STRT.F       {md[0]:12.4f}                : START DEPTH",
              f" STOP.F       {md[-1]:12.4f}                : STOP DEPTH",
              f" STEP.F       {step:12.4f}                : STEP",
              f" NULL.        {nulo:12.4f}                : NULL VALUE",
              " COMP.        OPERADORA SINTETICA S.A.    : COMPANY",
              f" WELL.        {pozo:<27} : WELL",
              " FLD .        CAMPO LLANURA               : FIELD",
              " LOC .        LOTE 7                      : LOCATION",
              " CTRY.        COLOMBIA                    : COUNTRY",
              " SRVC.        SERVICIOS DE PERFILAJE      : SERVICE COMPANY",
              " DATE.        2026-03-14                  : LOG DATE",
              " UWI .        CO-0007-" + pozo[-3:] + "                : UNIQUE WELL ID"]
    lineas += [f" {m}  : {d}" for m, d in extra_w]
    lineas += ["~CURVE INFORMATION", "#MNEM.UNIT      API CODE      CURVE DESCRIPTION",
               " DEPT.F                       : MEASURED DEPTH"]
    lineas += [f" {m:<5}.{u:<10}             : {d}" for m, u, d, _ in columnas]
    lineas += ["~PARAMETER INFORMATION",
               " BHT .DEGF          185.0000 : BOTTOM HOLE TEMPERATURE",
               " RMF .OHMM            0.0850 : MUD FILTRATE RESISTIVITY",
               " MDWT.LB/G           10.2000 : MUD WEIGHT",
               "~OTHER INFORMATION",
               " Synthetic data generated for Kurvo tests (not a real well).",
               "~A  DEPTH     " + "  ".join(m for m, *_ in columnas)]
    datos = np.column_stack([md] + [np.where(np.isfinite(c[3]), c[3], nulo) for c in columnas])
    for fila in datos:
        lineas.append(" ".join(f"{v:11.4f}" for v in fila))
    ruta.write_text("\n".join(lineas) + "\n", encoding="ascii")


def principal(rng):
    """PZ-101: pasada principal con todo lo típico de un registro de campo."""
    md = np.round(np.arange(4800.0, 6200.0001, 0.5), 4)
    c = curvas_pozo(md, rng, 0.0, gas_hasta=5300)
    n = len(md)
    bs = np.full(n, 8.5)
    hcal = 8.5 + 0.15 * rng.normal(0, 1, n) + np.where(~c["arena"], 0.4, 0.05)
    derrumbe = (md > 5480) & (md < 5530)
    hcal[derrumbe] += 2.5 + rng.normal(0, 0.3, derrumbe.sum())
    hdra = rng.normal(0.01, 0.015, n)
    hdra[derrumbe] = 0.22 + rng.normal(0, 0.03, derrumbe.sum())
    rhob = c["rhob"].copy()
    rhob[derrumbe] -= 0.25                         # densidad mala en el derrumbe
    gr = c["gr"].copy()
    picos = rng.choice(np.arange(200, n - 200), 12, replace=False)
    gr[picos] += rng.choice([-1, 1], 12) * rng.uniform(80, 150, 12)
    rhob[(md >= 5800) & (md < 5812)] = 2.4512      # herramienta trabada: tramo plano
    dtco = c["dt"].copy()
    dtco[md < 5050] = np.nan                       # el sónico empezó más abajo
    dtco[(md > 5650) & (md < 5700)] = np.nan       # y falló en un tramo (para reconstruir con DL)
    for arr, hasta in ((gr, 4812.0), (hcal, 4806.0)):
        arr[md < hasta] = np.nan
    columnas = [("GRC", "GAPI", "GAMMA RAY CORRECTED", gr), ("SP", "MV", "SPONTANEOUS POTENTIAL", c["sp"]),
                ("HCAL", "IN", "HOLE CALIPER", hcal), ("BS", "IN", "BIT SIZE", bs),
                ("AT90", "OHMM", "ARRAY INDUCTION 90 IN", c["rt"]),
                ("AT30", "OHMM", "ARRAY INDUCTION 30 IN", c["rt"] * 0.8),
                ("AT10", "OHMM", "ARRAY INDUCTION 10 IN", c["rt"] * 0.55 + 0.4),
                ("RHOZ", "G/C3", "BULK DENSITY", rhob), ("HDRA", "G/C3", "DENSITY CORRECTION", hdra),
                ("TNPH", "V/V", "THERMAL NEUTRON POROSITY", c["nphi"]),
                ("PEFZ", "B/E", "PHOTOELECTRIC FACTOR", c["pe"]), ("DTCO", "US/F", "COMPRESSIONAL SLOWNESS", dtco)]
    return md, columnas


def repetida(rng, md_p, col_p):
    """PZ-101 pasada repetida: 5400–5700 ft, 0.5 ft más profunda y con su propio ruido."""
    sel = (md_p >= 5400) & (md_p <= 5700)
    md = md_p[sel]
    columnas = []
    for m, u, d, datos in col_p:
        if m not in ("GRC", "RHOZ", "TNPH", "AT90", "HCAL"):
            continue
        x = np.interp(md - 0.5, md_p, np.where(np.isfinite(datos), datos, np.nan))
        ruido = {"GRC": 3.0, "RHOZ": 0.01, "TNPH": 0.008, "AT90": 0.0, "HCAL": 0.05}[m]
        x = x + rng.normal(0, ruido, len(x)) if ruido else x * np.exp(rng.normal(0, 0.05, len(x)))
        columnas.append((m, u, d + " (REPEAT)", x))
    return md, columnas


def vecino(rng):
    """PZ-102: mismas capas 3 ft más arriba, otras unidades (K/M3, PU, US/M) y nulos -9999."""
    md = np.round(np.arange(4850.0, 6100.0001, 0.5), 4)
    c = curvas_pozo(md, rng, 3.0)
    gr = c["gr"] * 1.12 + 6                         # otra herramienta: necesita normalización
    columnas = [("GR", "GAPI", "GAMMA RAY", gr), ("CALI", "IN", "CALIPER", 8.6 + rng.normal(0, 0.1, len(md))),
                ("ILD", "OHMM", "DEEP INDUCTION", c["rt"]), ("RHOB", "K/M3", "BULK DENSITY", c["rhob"] * 1000),
                ("NPHI", "PU", "NEUTRON POROSITY", c["nphi"] * 100), ("DT", "US/M", "SONIC", c["dt"] * 3.28084)]
    return md, columnas


def problemas(rng):
    """PZ-103: nulos -999.25 y -999, filas duplicadas y STEP de cabecera incoherente."""
    md = np.round(np.arange(5000.0, 5600.0001, 0.5), 4)
    c = curvas_pozo(md, rng, -2.0)
    gr = c["gr"].copy()
    gr[rng.choice(len(md), 25, replace=False)] = -999.0     # nulo "extra" de otro sistema
    md = np.insert(md, [300, 301], [md[299], md[300]])       # dos profundidades repetidas
    ins = lambda a: np.insert(a, [300, 301], [a[299], a[300]])  # noqa: E731
    columnas = [("GR", "API", "GAMMA RAY", ins(gr)), ("RHOB", "G/CC", "DENSITY", ins(c["rhob"])),
                ("NPHI", "V/V", "NEUTRON", ins(c["nphi"])), ("DT", "US/F", "SONIC", ins(c["dt"]))]
    return md, columnas


def escribir_dlis(ruta: Path, rng):
    from dliswriter import DLISFile
    md_ft = np.round(np.arange(5000.0, 5500.0001, 0.5), 4)
    c = curvas_pozo(md_ft, rng, 1.5)
    n = len(md_ft)
    df = DLISFile()
    lf = df.add_logical_file()
    lf.add_origin("ORIGEN", well_name="PZ-104", field_name="CAMPO LLANURA", company="OPERADORA SINTETICA S.A.")
    tdep = lf.add_channel("TDEP", data=np.round(md_ft * 120).astype(np.float64), units="0.1 in",
                          long_name="Depth")
    canales = [tdep]
    for nombre, unidad, datos, desc in (("GR", "gAPI", c["gr"], "Gamma ray"), ("RHOB", "g/cm3", c["rhob"], "Density"),
                                        ("NPHI", "m3/m3", c["nphi"], "Neutron porosity"),
                                        ("DT", "us/ft", c["dt"], "Sonic"),
                                        ("CALI", "in", 8.5 + rng.normal(0, 0.1, n), "Caliper")):
        d = np.asarray(datos, np.float64).copy()
        if nombre == "GR":
            d[:20] = -999.25
        canales.append(lf.add_channel(nombre, data=d, units=unidad, long_name=desc))
    onda = rng.normal(0, 1, (n, 16)).astype(np.float32)
    canales.append(lf.add_channel("WF1", data=onda, units="mV", long_name="Waveform", dimension=[16]))
    lf.add_frame("MAIN", channels=canales, index_type="BOREHOLE-DEPTH")
    df.write(str(ruta))


def generar(destino: Path = DESTINO) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    md, cols = principal(rng)
    escribir_las(destino / "PZ-101_main.las", "PZ-101", md, cols)
    md_r, cols_r = repetida(rng, md, cols)
    escribir_las(destino / "PZ-101_repeat.las", "PZ-101", md_r, cols_r,
                 extra_w=[("RUN .        2", "RUN NUMBER (REPEAT PASS)")])
    md2, cols2 = vecino(rng)
    escribir_las(destino / "PZ-102.las", "PZ-102", md2, cols2)
    md3, cols3 = problemas(rng)
    escribir_las(destino / "PZ-103.las", "PZ-103", md3, cols3, step_cabecera=0.25, nulo=-999.25)
    salida = [destino / n for n in ("PZ-101_main.las", "PZ-101_repeat.las", "PZ-102.las", "PZ-103.las")]
    try:
        escribir_dlis(destino / "PZ-104.dlis", rng)
        salida.append(destino / "PZ-104.dlis")
    except ImportError:
        print("dliswriter no está instalado: no se regenera PZ-104.dlis")
    return salida


if __name__ == "__main__":
    for r in generar():
        print(r, r.stat().st_size)
