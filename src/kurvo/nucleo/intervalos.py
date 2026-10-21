"""Litología (myLithoTable), completación (myDataWellToolPack) y zonas (myDataWellTop).

Cada uno se importa y exporta como texto."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from .comun import NULO, UID, a_float, a_int, escribir_lineas, formato_num, leer_lineas


# ------------------------------------------------------------------ litología
@dataclass
class IntervaloLito:
    tope: float
    base: float
    tipo: int = 0
    comentario: str = ""


@dataclass
class Litologia:
    nombre: str = ""
    intervalos: list[IntervaloLito] = field(default_factory=list)
    uid: int = field(default_factory=UID.nuevo)

    CABECERA = "#Depth Start\tDepth End\tLithology Type\tRemarks"

    def prof_min(self) -> float:
        return min((i.tope for i in self.intervalos), default=0.0)

    def prof_max(self) -> float:
        return max((i.base for i in self.intervalos), default=0.0)

    @classmethod
    def desde_lineas(cls, lineas: list[str], nombre: str = "") -> "Litologia":
        lit = cls(nombre=nombre)
        for linea in lineas:
            s = linea.strip()
            if not s or s.startswith("#"):
                continue
            c = linea.split("\t")
            if len(c) < 3:
                c = s.split(None, 3)
            if len(c) < 3:
                continue
            lit.intervalos.append(IntervaloLito(a_float(c[0]), a_float(c[1]), a_int(c[2]),
                                                c[3].strip() if len(c) > 3 else ""))
        return lit

    @classmethod
    def abrir(cls, ruta, nombre=None) -> "Litologia":
        return cls.desde_lineas(leer_lineas(ruta), nombre or Path(ruta).stem)

    def lineas(self) -> list[str]:
        return [self.CABECERA] + ["\t".join((formato_num(i.tope), formato_num(i.base), str(i.tipo),
                                             i.comentario)) for i in self.intervalos]

    def guardar(self, ruta) -> None:
        escribir_lineas(ruta, self.lineas())


# ---------------------------------------------------------------- completación
@dataclass
class Herramienta:
    comentario: str
    nombre_herramienta: str
    tope: float
    base: float


@dataclass
class Completacion:
    nombre: str = ""
    fecha: dt.date = field(default_factory=dt.date.today)
    herramientas: list[Herramienta] = field(default_factory=list)
    uid: int = field(default_factory=UID.nuevo)

    def prof_min(self) -> float:
        return min((h.tope for h in self.herramientas), default=0.0)

    def prof_max(self) -> float:
        return max((h.base for h in self.herramientas), default=0.0)

    @classmethod
    def desde_lineas(cls, lineas: list[str], nombre: str = "", separador: str = "|") -> "Completacion":
        """Salta 4 líneas de cabecera; campos comentario|herramienta|tope|base."""
        comp = cls(nombre=nombre)
        for linea in lineas[4:]:
            if not linea.strip():
                continue
            c = [x.strip() for x in linea.split(separador)]
            while len(c) < 4:
                c.append("")
            comp.herramientas.append(Herramienta(c[0], c[1], a_float(c[2]), a_float(c[3])))
        return comp

    @classmethod
    def abrir(cls, ruta, nombre=None, separador="|") -> "Completacion":
        lineas = leer_lineas(ruta)
        nom = nombre or (lineas[2].lstrip("#").strip() if len(lineas) > 2 else Path(ruta).stem)
        return cls.desde_lineas(lineas, nom, separador)

    def lineas(self, pozo: str = "") -> list[str]:
        out = ["#COMPLETION", "#" + pozo, "#" + self.nombre,
               "#" + self.fecha.strftime("%m/%d/%y 00:00:00")]
        out += ["|".join((h.comentario, h.nombre_herramienta, formato_num(h.tope),
                          formato_num(h.base))) for h in self.herramientas]
        return out

    def guardar(self, ruta, pozo: str = "") -> None:
        escribir_lineas(ruta, self.lineas(pozo))


# ---------------------------------------------------------------------- zonas
@dataclass
class Zona:
    nombre: str
    profundidades: list[float] = field(default_factory=list)   # una por pozo (MD)
    color: str = "rgb(255,0,0)"
    tipo_linea: int = 0
    ancho: int = 2
    uid: int = field(default_factory=UID.nuevo)

    def prof(self, i_pozo: int) -> float:
        return self.profundidades[i_pozo] if i_pozo < len(self.profundidades) else NULO


def leer_zonas(lineas: list[str]) -> tuple[list[str], list[Zona]]:
    """Lista de topes: '#WELLTOPS, pozo1, pozo2' y 'Zona, p1, p2'."""
    pozos: list[str] = []
    zonas: list[Zona] = []
    for linea in lineas:
        s = linea.strip()
        if not s:
            continue
        partes = [x.strip() for x in s.split(",")]
        if partes[0].upper().startswith("#WELLTOPS"):
            pozos = partes[1:]
            continue
        if s.startswith("#"):
            continue
        valores = [a_float(x if x else "0", 0.0) for x in partes[1:]]
        valores += [0.0] * (len(pozos) - len(valores))
        zonas.append(Zona(partes[0], valores))
    return pozos, zonas


def lineas_zonas(pozos: list[str], zonas: list[Zona]) -> list[str]:
    out = ["#WELLTOPS" + "".join(", " + p for p in pozos)]
    for z in zonas:
        out.append(z.nombre + "".join(", " + formato_num(z.prof(i)) for i in range(len(pozos))))
    return out
