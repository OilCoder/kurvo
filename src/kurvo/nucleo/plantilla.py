"""Plantilla del gráfico de registros: pistas, curvas con su escala y rejilla, áreas rellenas y
nombres de zona. Se guarda dentro del proyecto o sola, en un archivo .kvplantilla (D124)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .comun import UID, color_aleatorio

BORDE_IZQ = "$LEFT_BORDER"
BORDE_DER = "$RIGHT_BORDER"

PISTA_CURVAS, PISTA_COMPLETACION, PISTA_LITOLOGIA = 0, 1, 2


@dataclass
class Rejilla:
    micro_visible: bool = True
    micro_paso: float = 20.0
    micro_tipo: int = 0
    micro_color: str = "rgb(225,225,225)"
    micro_ancho: int = 1
    micro_etiqueta: bool = False
    micro_fuente: str = "Arial"
    micro_tam: int = 8
    micro_color_fuente: str = "rgb(0,0,0)"
    macro_visible: bool = True
    macro_paso: float = 100.0
    macro_tipo: int = 0
    macro_color: str = "rgb(135,135,135)"
    macro_ancho: int = 1
    macro_etiqueta: bool = True
    macro_fuente: str = "Arial"
    macro_tam: int = 8
    macro_color_fuente: str = "rgb(0,0,0)"


@dataclass
class CurvaPlantilla:
    nombre_x: str = ""
    nombre_y: str = "DEPT"
    color: str = field(default_factory=color_aleatorio)
    ancho: int = 1
    tipo_linea: int = 0
    logaritmica: bool = False
    invertida: bool = False
    escala_min: float = 0.0
    escala_max: float = 100.0
    escala_y_min: float = 0.0
    escala_y_max: float = 100.0
    usar_grupo: bool = False
    # escala de cada registro a partir de sus datos (SP, neutrón en cuentas: D111); mín./máx. quedan
    # para cuando la curva no tiene datos
    escala_auto: bool = False
    rejilla_x: Rejilla = field(default_factory=Rejilla)
    rejilla_y: Rejilla = field(default_factory=Rejilla)


@dataclass
class AreaPlantilla:
    curva_izq: str = BORDE_IZQ
    curva_der: str = BORDE_DER
    color: str = field(default_factory=color_aleatorio)


@dataclass
class Pista:
    x: float = 0.0
    ancho: float = 100.0
    alto: float = 1000.0
    borde_visible: bool = True
    borde_ancho: int = 1
    borde_tipo: int = 0
    borde_color: str = "rgb(0,0,0)"
    tam_fuente_cabecera: int = 9
    tipo: int = PISTA_CURVAS
    ancho_comp: float = 100.0
    ancho_lito: float = 100.0
    curvas: list[CurvaPlantilla] = field(default_factory=list)
    areas: list[AreaPlantilla] = field(default_factory=list)


@dataclass
class Plantilla:
    nombre: str = ""
    x: float = 0.0
    y: float = 100.0
    ancho: float = 840.0
    alto: float = 250.0
    escala: float = 200.0
    eje_y: str = "DEPT"
    mostrar_titulo: bool = True
    formato_titulo: str = "%LOGNAME%"
    borde_color: str = "rgb(10,10,10)"
    borde_tipo: int = 0
    borde_ancho: int = 2
    borde_visible: bool = True
    zona_nombre_visible: bool = True
    zona_nombre_posicion: int = 1
    zona_nombre_ancho: float = 100.0
    pistas: list[Pista] = field(default_factory=list)
    uid: int = field(default_factory=UID.nuevo)

    # ----------------------------------------------------------- creación
    def mas_a_la_derecha(self) -> float:
        return max((p.x + p.ancho for p in self.pistas), default=0.0)

    def mas_a_la_izquierda(self) -> float:
        return min((p.x for p in self.pistas), default=0.0)

    def nueva_pista(self, tipo: int = PISTA_CURVAS) -> Pista:
        """Pista nueva a la derecha de las demás: de curvas, de completación o de litología."""
        ancho = {PISTA_CURVAS: 100.0, PISTA_COMPLETACION: 200.0, PISTA_LITOLOGIA: 300.0}[tipo]
        p = Pista(x=self.mas_a_la_derecha() + 30.0, ancho=ancho, tipo=tipo)
        self.pistas.append(p)
        return p

    def nueva_curva(self, pista: Pista, nombre: str = "") -> CurvaPlantilla:
        c = CurvaPlantilla(nombre_x=nombre, nombre_y=self.eje_y)
        pista.curvas.append(c)
        return c

    # ----------------------------------------------------------- archivo (D124)
    @classmethod
    def abrir(cls, ruta: str | Path, nombre: str | None = None) -> "Plantilla":
        """Plantilla de un archivo .kvplantilla (JSON con los mismos campos que en memoria)."""
        from .archivo_proyecto import desde_json
        t = desde_json(cls, json.loads(Path(ruta).read_text(encoding="utf-8")))
        if nombre:
            t.nombre = nombre
        return t

    def guardar(self, ruta: str | Path) -> None:
        from .archivo_proyecto import a_json
        Path(ruta).write_text(json.dumps(a_json(self), ensure_ascii=False, indent=1), encoding="utf-8")
