"""Conversión de unidades de curvas (mantenimiento, prioridad 3).

Cada magnitud tiene una unidad base; cada unidad es (factor, desplazamiento) con
valor_base = valor · factor + desplazamiento. Los alias cubren cómo suelen escribirse las unidades
en los LAS (mayúsculas, con o sin barra, abreviaturas)."""
from __future__ import annotations

import numpy as np

from .comun import NULO

# magnitud -> {unidad canónica: (factor a la base, desplazamiento)}
MAGNITUDES: dict[str, dict[str, tuple[float, float]]] = {
    "length": {"M": (1.0, 0.0), "FT": (0.3048, 0.0), "IN": (0.0254, 0.0), "CM": (0.01, 0.0),
               "MM": (0.001, 0.0)},
    "slowness": {"US/M": (1.0, 0.0), "US/FT": (1 / 0.3048, 0.0)},
    "density": {"KG/M3": (1.0, 0.0), "G/CC": (1000.0, 0.0)},
    "temperature": {"DEGC": (1.0, 0.0), "DEGF": (5 / 9, -32 * 5 / 9), "K": (1.0, -273.15)},
    "fraction": {"V/V": (1.0, 0.0), "PU": (0.01, 0.0), "%": (0.01, 0.0)},
    "pressure": {"KPA": (1.0, 0.0), "PSI": (6.894757293168, 0.0), "BAR": (100.0, 0.0),
                 "MPA": (1000.0, 0.0)},
    "conductivity": {"MMHO/M": (1.0, 0.0), "S/M": (1000.0, 0.0)},
    "velocity": {"M/S": (1.0, 0.0), "FT/S": (0.3048, 0.0)},
}

ALIAS = {
    "M": "M", "METER": "M", "METERS": "M", "METRE": "M", "METRES": "M", "MTS": "M",
    "FT": "FT", "F": "FT", "FEET": "FT", "FOOT": "FT",
    "IN": "IN", "INCH": "IN", "INCHES": "IN", '"': "IN", "CM": "CM", "MM": "MM",
    "US/M": "US/M", "USEC/M": "US/M", "US/MT": "US/M", "MUS/M": "US/M",
    "US/FT": "US/FT", "US/F": "US/FT", "USEC/FT": "US/FT", "US/FEET": "US/FT", "MUS/FT": "US/FT",
    "KG/M3": "KG/M3", "KG/M^3": "KG/M3", "K/M3": "KG/M3", "KGM3": "KG/M3", "KG/M**3": "KG/M3", "G/CC": "G/CC", "G/C3": "G/CC", "G/CM3": "G/CC",
    "GM/CC": "G/CC", "GR/CC": "G/CC", "G/CM^3": "G/CC", "GRAM/CC": "G/CC",
    "DEGC": "DEGC", "°C": "DEGC", "C": "DEGC", "DEG C": "DEGC", "CELSIUS": "DEGC",
    "DEGF": "DEGF", "°F": "DEGF", "DEG F": "DEGF", "FAHRENHEIT": "DEGF", "K": "K", "KELVIN": "K",
    "V/V": "V/V", "FRAC": "V/V", "FRACTION": "V/V", "DEC": "V/V", "M3/M3": "V/V", "CFCF": "V/V",
    "DECP": "V/V", "DECIMAL": "V/V",
    "PU": "PU", "P.U.": "PU", "%": "%", "PERCENT": "%", "PCT": "%",
    "KPA": "KPA", "PSI": "PSI", "PSIA": "PSI", "PSIG": "PSI", "BAR": "BAR", "MPA": "MPA",
    "MMHO/M": "MMHO/M", "MS/M": "MMHO/M", "S/M": "S/M", "MMO/M": "MMHO/M", "MMHOS/M": "MMHO/M",
    "MMHO": "MMHO/M",
    "M/S": "M/S", "FT/S": "FT/S", "F/S": "FT/S",
    # sin conversión, solo para reconocerlas (rangos físicos del control de calidad)
    "OHMM": "OHMM", "OHM.M": "OHMM", "OHM-M": "OHMM", "OHM M": "OHMM", "OHMS": "OHMM",
    "GAPI": "GAPI", "API": "GAPI", "API UNITS": "GAPI", "MV": "MV", "B/E": "B/E", "BARN/E": "B/E",
    # v0.5 (D106): las de los LAS reales del KGS
    "BARNE": "B/E", "BARNS/E": "B/E", "BARNS/ELECTRON": "B/E", "B/ELEC": "B/E", "OHM-METER": "OHMM",
    "OHMM.": "OHMM", "NONE": "", "UNITLESS": "",
}


def canonica(unidad: str) -> str:
    u = (unidad or "").strip().upper()
    return ALIAS.get(u, u)


def magnitud(unidad: str) -> str | None:
    c = canonica(unidad)
    return next((m for m, us in MAGNITUDES.items() if c in us), None)


def destinos(unidad: str) -> list[str]:
    """Unidades a las que se puede convertir (sin la propia)."""
    m = magnitud(unidad)
    return [u for u in MAGNITUDES[m] if u != canonica(unidad)] if m else []


def convertir(datos, de: str, a: str) -> np.ndarray:
    """Convierte respetando nulos. Error si las unidades no son de la misma magnitud."""
    m1, m2 = magnitud(de), magnitud(a)
    if m1 is None or m1 != m2:
        raise ValueError(f"Cannot convert '{de}' to '{a}'.")
    f1, o1 = MAGNITUDES[m1][canonica(de)]
    f2, o2 = MAGNITUDES[m2][canonica(a)]
    d = np.asarray(datos, float)
    ok = (d != NULO) & np.isfinite(d)
    out = np.full(d.shape, NULO)
    out[ok] = ((d[ok] * f1 + o1) - o2) / f2
    return out


def convertir_columna(reg, indice: int, a: str, unidad_texto: str | None = None) -> int:
    """Convierte la columna en el registro y cambia su unidad. Devuelve las muestras convertidas."""
    c = reg.columnas[indice]
    nuevos = convertir(c.datos, c.unidad, a)
    n = int(np.count_nonzero(nuevos != NULO))
    c.datos = nuevos
    c.unidad = unidad_texto or a
    return n


def convertir_profundidad(reg, a: str) -> list[str]:
    """Convierte las columnas MD y TVD (si tienen la misma unidad de longitud)."""
    hechas = []
    for k in {reg.indice_md, reg.indice_tvd}:
        if reg.existe_columna(k) and magnitud(reg.columnas[k].unidad) == "length" \
                and canonica(reg.columnas[k].unidad) != canonica(a):
            convertir_columna(reg, k, a)
            hechas.append(reg.columnas[k].nombre)
    return hechas
