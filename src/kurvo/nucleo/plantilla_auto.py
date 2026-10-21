"""Curvas nuevas en las plantillas (v0.4, D82–D83).

Cuando una herramienta crea una curva (`_FILL`, `_NORM`, `_DL`, `_DS`, `_SPL`, `_QC`, la calculadora
o un módulo), se agrega sola a las plantillas que la mostrarían:
- si su curva de origen está en una pista, va en esa pista con la misma escala y el mismo color, en
  línea discontinua;
- las banderas `_QC` van a una pista de banderas (0–1) a la derecha;
- si no tiene origen en la plantilla (calculadora, módulos), va en una pista nueva con una escala
  redondeada a partir de sus datos (logarítmica para la resistividad);
- `_DL_STD` y `_DL_P` no se agregan: se ven como banda de incertidumbre (D56).

Cada agregado devuelve un `CambioPlantilla` para poder deshacerlo (historial_proyecto.py)."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass

import numpy as np

from .comun import NULO
from .plantilla import PISTA_CURVAS, PISTA_LITOLOGIA, CurvaPlantilla, Pista, Plantilla

SUFIJOS_OMITIR = ("_DL_STD", "_DL_P", "_STD")
SUFIJO_BANDERA = "_QC"
LINEA_DISCONTINUA = 2            # Qt.DashLine en logplot.ESTILOS_QT
GRUPOS_LOG = ("RESD", "RESM", "RESS", "RES", "RT", "ILD", "LLD")


@dataclass
class CambioPlantilla:
    plantilla: Plantilla
    pista: Pista
    curva: CurvaPlantilla
    pista_nueva: bool = False
    indice_pista: int = -1          # posición de la pista nueva en la plantilla

    def deshacer(self) -> None:
        if self.curva in self.pista.curvas:
            self.pista.curvas.remove(self.curva)
        if self.pista_nueva and not self.pista.curvas and self.pista in self.plantilla.pistas:
            self.plantilla.pistas.remove(self.pista)

    def rehacer(self) -> None:
        if self.pista_nueva and self.pista not in self.plantilla.pistas:
            self.plantilla.pistas.insert(min(self.indice_pista, len(self.plantilla.pistas)), self.pista)
        if self.curva not in self.pista.curvas:
            self.pista.curvas.append(self.curva)


def _mayus(s: str) -> str:
    return s.strip().upper()


def origen(nombre: str, columnas: list[str]) -> str:
    """Curva de la que deriva `nombre`: la columna más larga que es su prefijo seguido de "_"
    (GR_NORM → GR, RHOB_DL_STD → RHOB). Vacío si no deriva de otra."""
    n = _mayus(nombre)
    candidatas = [c for c in columnas if _mayus(c) != n and n.startswith(_mayus(c) + "_")]
    return max(candidatas, key=len) if candidatas else ""


def _curva_en(plantilla: Plantilla, nombre: str, alias=None):
    """(pista, curva) de la plantilla que muestra `nombre` (por nombre o grupo de alias)."""
    n = _mayus(nombre)
    for pista in plantilla.pistas:
        if pista.tipo != PISTA_CURVAS:
            continue
        for c in pista.curvas:
            if _mayus(c.nombre_x) == n:
                return pista, c
    if alias is not None:
        g = alias.grupo_de(nombre)
        if g >= 0:
            for pista in plantilla.pistas:
                if pista.tipo != PISTA_CURVAS:
                    continue
                for c in pista.curvas:
                    if c.usar_grupo and alias.grupo_de(c.nombre_x) == g:
                        return pista, c
    return None


def contiene(plantilla: Plantilla, nombre: str) -> bool:
    n = _mayus(nombre)
    return any(_mayus(c.nombre_x) == n for p in plantilla.pistas for c in p.curvas)


def escala_de_datos(datos, logaritmica: bool = False, percentiles=(1, 99), margen: float = 0.0) -> tuple[float, float]:
    """Escala redondeada que abarca del P1 al P99 de los datos válidos (o los percentiles dados,
    ensanchados en `margen` veces su diferencia a cada lado)."""
    v = np.asarray(datos, float)
    v = v[(v != NULO) & np.isfinite(v)]
    if logaritmica:
        v = v[v > 0]
        if not v.size:
            return 0.2, 2000.0
        lo, hi = np.percentile(v, percentiles)
        return 10 ** math.floor(math.log10(lo)), 10 ** math.ceil(math.log10(hi) + 1e-9)
    if not v.size:
        return 0.0, 1.0
    lo, hi = (float(x) for x in np.percentile(v, percentiles))
    lo, hi = lo - margen * (hi - lo), hi + margen * (hi - lo)
    if hi <= lo:
        lo, hi = lo - 1.0, hi + 1.0
    paso = 10 ** math.floor(math.log10(hi - lo))
    return math.floor(lo / paso) * paso, math.ceil(hi / paso) * paso


def _es_log(nombre: str, alias=None) -> bool:
    if alias is not None:
        g = alias.grupo_de(nombre)
        if g >= 0 and _mayus(alias.grupos[g].nombre) in GRUPOS_LOG:
            return True
    return _mayus(nombre) in GRUPOS_LOG


def _pista_nueva(plantilla: Plantilla, ancho: float = 100.0) -> tuple[Pista, int]:
    p = Pista(x=plantilla.mas_a_la_derecha() + 30.0 if plantilla.pistas else 30.0, ancho=ancho,
              alto=plantilla.alto)
    plantilla.pistas.append(p)
    return p, len(plantilla.pistas) - 1


def _sin_rejilla_x(c: CurvaPlantilla) -> None:
    """La pista ya dibuja la rejilla de su primera curva; la curva agregada no repite la suya."""
    c.rejilla_x.micro_visible = c.rejilla_x.macro_visible = False
    c.rejilla_y.micro_visible = c.rejilla_y.macro_visible = False


def agregar(plantilla: Plantilla, nombre: str, reg, alias=None) -> CambioPlantilla | None:
    """Agrega la curva `nombre` del registro a la plantilla según las reglas del módulo."""
    u = _mayus(nombre)
    if u.endswith(SUFIJOS_OMITIR) or contiene(plantilla, nombre):
        return None
    k = reg.indice_columna(nombre)
    if k < 0 or k in (reg.indice_md, reg.indice_tvd):
        return None
    if u.endswith(SUFIJO_BANDERA):
        pista = next((p for p in plantilla.pistas if p.tipo == PISTA_CURVAS and p.curvas
                      and all(_mayus(c.nombre_x).endswith(SUFIJO_BANDERA) for c in p.curvas)), None)
        nueva, i = pista is None, -1
        if nueva:
            pista, i = _pista_nueva(plantilla, 80.0)
        c = CurvaPlantilla(nombre_x=reg.columnas[k].nombre, nombre_y=plantilla.eje_y, color="rgb(220,30,30)",
                           escala_min=0.0, escala_max=1.0)
        c.rejilla_x.micro_visible = False
        c.rejilla_x.macro_paso = 1.0
        if not nueva:
            _sin_rejilla_x(c)
        pista.curvas.append(c)
        return CambioPlantilla(plantilla, pista, c, nueva, i)
    base = origen(reg.columnas[k].nombre, reg.nombres())
    encontrada = _curva_en(plantilla, base, alias) if base else None
    if encontrada is not None:
        pista, ref = encontrada
        c = copy.deepcopy(ref)
        c.nombre_x = reg.columnas[k].nombre
        c.usar_grupo = False
        c.tipo_linea = LINEA_DISCONTINUA
        _sin_rejilla_x(c)
        pista.curvas.append(c)
        return CambioPlantilla(plantilla, pista, c)
    log = _es_log(base or nombre, alias)
    lo, hi = escala_de_datos(reg.columnas[k].datos, log)
    pista, i = _pista_nueva(plantilla)
    c = CurvaPlantilla(nombre_x=reg.columnas[k].nombre, nombre_y=plantilla.eje_y, logaritmica=log,
                       escala_min=lo, escala_max=hi)
    c.rejilla_x.macro_paso = c.rejilla_x.micro_paso = 0.0 if log else (hi - lo) / 4
    c.rejilla_x.micro_visible = False
    pista.curvas.append(c)
    return CambioPlantilla(plantilla, pista, c, True, i)


def plantillas_destino(proyecto, reg, nombre: str, alias=None) -> list[Plantilla]:
    """Plantillas de los log plots que muestran el registro y plantillas que ya muestran la curva
    de origen; si no hay ninguna, la del log plot actual (que sigue a la selección)."""
    destino: list[Plantilla] = []

    def poner(i):
        if 0 <= i < len(proyecto.plantillas) and proyecto.plantillas[i] not in destino:
            destino.append(proyecto.plantillas[i])
    for lp in proyecto.logplots:
        if 0 <= lp.pozo < len(proyecto.pozos):
            logs = proyecto.pozos[lp.pozo].logs
            if 0 <= lp.las < len(logs) and logs[lp.las] is reg:
                poner(lp.plantilla)
    base = origen(nombre, reg.nombres())
    if _mayus(nombre).endswith(SUFIJO_BANDERA) and not base:
        base = nombre[:-len(SUFIJO_BANDERA)]
    if base:
        for i, t in enumerate(proyecto.plantillas):
            if _curva_en(t, base, alias) is not None:
                poner(i)
    if not destino and 0 <= proyecto.logplot_actual < len(proyecto.logplots):
        poner(proyecto.logplots[proyecto.logplot_actual].plantilla)
    return destino


def agregar_nuevas(proyecto, reg, nombres: list[str], alias=None) -> list[CambioPlantilla]:
    cambios = []
    for n in nombres:
        for t in plantillas_destino(proyecto, reg, n, alias):
            c = agregar(t, n, reg, alias)
            if c is not None:
                cambios.append(c)
    return cambios


# ------------------------------------------------------------------ plantilla estándar (v0.5, D109, D111)
# (grupo de alias, color, mín., máx., logarítmica, invertida, tipo de línea, escala automática) por pista
PISTAS_ESTANDAR = (
    (("GR", "rgb(0,128,0)", 0, 150, False, False, 0, False), ("CAL", "rgb(0,0,0)", 6, 16, False, False, 2, False),
     ("SP", "rgb(200,0,0)", -100, 0, False, False, 1, True)),
    (("RESD", "rgb(200,0,0)", 0.2, 2000, True, False, 0, False),
     ("RESM", "rgb(0,0,200)", 0.2, 2000, True, False, 0, False),
     ("RESS", "rgb(0,140,0)", 0.2, 2000, True, False, 2, False)),
    (("RHOB", "rgb(200,0,120)", 1.95, 2.95, False, False, 0, False),
     ("PHIN", "rgb(0,0,220)", -0.15, 0.45, False, True, 0, False),
     ("PHID", "rgb(220,120,0)", -0.15, 0.45, False, True, 2, False),
     ("PHIS", "rgb(120,60,0)", -0.15, 0.45, False, True, 1, False)),
    (("DTC", "rgb(120,60,0)", 40, 140, False, True, 0, False),
     ("PE", "rgb(130,0,170)", 0, 10, False, False, 2, False)),
)
# pistas que solo se agregan si alguna curva del proyecto es de su grupo (registros antiguos y control)
PISTAS_OPCIONALES = (
    (("NEUT", "rgb(0,0,220)", 0, 1000, False, False, 0, True),),
    (("RMIC", "rgb(0,0,0)", 0, 50, False, False, 0, False),     # carbonatos de Kansas: P95 de 26 a 110 ohm-m
     ("DRHO", "rgb(200,0,120)", -0.25, 0.25, False, False, 2, False)),
)
GRUPOS_POROSIDAD = ("PHIN", "PHID", "PHIS")
ESCALA_PU = 100.0           # porosidad en PU o %: la escala de V/V por 100


def _porosidad_en_pu(proyecto, grupos, alias) -> bool:
    """Si la porosidad del proyecto está en PU (o %): la mediana de las medianas de las curvas de esos
    grupos pasa de 1.5. Se mira el valor y no la unidad, porque en los LAS reales hay curvas en V/V
    rotuladas PU y curvas sin unidad (D107)."""
    if alias is None:
        return False
    indices = {alias.grupos.index(g) for g in (alias.grupo(n) for n in grupos) if g is not None}
    medianas = []
    for p in proyecto.pozos:
        for r in p.logs:
            for c in r.columnas:
                if alias.grupo_de(c.nombre) in indices:
                    v = c.datos[(c.datos != NULO) & np.isfinite(c.datos)]
                    if v.size:
                        medianas.append(float(np.median(v)))
    return bool(medianas) and float(np.median(medianas)) > 1.5


def _grupos_del_proyecto(proyecto, alias) -> set[str]:
    if alias is None:
        return set()
    indices = {alias.grupo_de(c.nombre) for p in proyecto.pozos for r in p.logs for c in r.columnas}
    return {alias.grupos[i].nombre.upper() for i in indices if i >= 0}


def plantilla_estandar(proyecto, alias, nombre: str = "Standard") -> Plantilla:
    """Plantilla por grupos de alias (GR/CAL/SP | litología | resistividades | densidad-neutrón-porosidades |
    sónico-PE, y NEUT y micro/DRHO si el proyecto los tiene) que sirve para cualquier LAS: cada curva
    toma las columnas de su grupo (usar_grupo). La escala de la porosidad (V/V o PU) sale de los
    valores del proyecto; la del SP y la del neutrón en cuentas, de los datos de cada registro."""
    t = Plantilla(nombre=nombre, y=110, escala=500, formato_titulo="Well: [%WELLNAME%]    Log: [%LOGNAME%]")
    t.zona_nombre_ancho = 190.0          # nombres de formación largos ("Cherokee Shale", "Kansas City")
    pu = _porosidad_en_pu(proyecto, GRUPOS_POROSIDAD, alias)
    hay = _grupos_del_proyecto(proyecto, alias)
    pistas = list(PISTAS_ESTANDAR) + [p for p in PISTAS_OPCIONALES if any(g in hay for g, *_ in p)]
    for k, curvas in enumerate(pistas):
        if k == 1:                          # litología del pozo junto al GR/SP (D111, pedido del usuario)
            lito = t.nueva_pista(PISTA_LITOLOGIA)
            lito.ancho, lito.ancho_lito = 130.0, 60.0
        pista = t.nueva_pista()
        pista.ancho = 130
        if k == 0:
            pista.x = 70
        if k >= len(PISTAS_ESTANDAR):
            curvas = [c for c in curvas if c[0] in hay]
        for n, (grupo, color, lo, hi, log, inv, linea, auto) in enumerate(curvas):
            if grupo in GRUPOS_POROSIDAD and pu:
                lo, hi = lo * ESCALA_PU, hi * ESCALA_PU
            c = t.nueva_curva(pista, grupo)
            c.usar_grupo, c.color, c.logaritmica, c.tipo_linea, c.invertida = True, color, log, linea, inv
            c.escala_min, c.escala_max, c.escala_auto = lo, hi, auto
            c.rejilla_x.micro_visible = False
            c.rejilla_x.macro_paso = 0.0 if log else (hi - lo) / 4
            if n:
                _sin_rejilla_x(c)
    return t
