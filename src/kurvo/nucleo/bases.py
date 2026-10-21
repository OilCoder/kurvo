"""Bases propias del programa: tipos de litología, herramientas de completación y grupos de alias de
curvas (qué mnemónicos son GR, RHOB...). Los alias que edita el usuario se guardan como JSON (D124)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


# ------------------------------------------------------------------ litologías
@dataclass
class TipoLito:
    id: int
    nombre: str
    bitmap: int


@dataclass
class BaseLitologia:
    tipos: list[TipoLito] = field(default_factory=list)

    def tipo(self, id_: int) -> TipoLito | None:
        return next((t for t in self.tipos if t.id == id_), None)


# ------------------------------------------------------------------ herramientas
@dataclass
class CategoriaHerramienta:
    id: int
    nombre: str
    bitmap: int
    centrada: bool
    zorden: int
    estirar: bool


@dataclass
class ItemHerramienta:
    categoria: int
    nombre: str
    od: float
    id_: float


@dataclass
class BaseHerramientas:
    categorias: list[CategoriaHerramienta] = field(default_factory=list)
    items: list[ItemHerramienta] = field(default_factory=list)

    def item(self, nombre: str) -> ItemHerramienta | None:
        return next((i for i in self.items if i.nombre == nombre), None)

    def categoria(self, id_: int) -> CategoriaHerramienta | None:
        return next((c for c in self.categorias if c.id == id_), None)


# ------------------------------------------------------------------ alias
@dataclass
class GrupoAlias:
    nombre: str
    descripcion: str = ""
    origen: str = "RES"
    icono: str = ""
    alias: list[str] = field(default_factory=list)


@dataclass
class BaseAlias:
    grupos: list[GrupoAlias] = field(default_factory=list)

    def grupo(self, nombre: str) -> GrupoAlias | None:
        return next((g for g in self.grupos if g.nombre.upper() == nombre.upper()), None)

    def indice_grupo(self, nombre: str) -> int:
        """Grupo cuyo nombre o alias coincide con el mnemónico."""
        return self.grupo_de(nombre)

    def grupo_de(self, mnemonico: str) -> int:
        u = mnemonico.strip().upper()
        for i, g in enumerate(self.grupos):
            if g.nombre.upper() == u or any(a.upper() == u for a in g.alias):
                return i
        # otra versión de la misma curva (DT_2 del registro compuesto, D110): el grupo de DT
        m = re.fullmatch(r"(.+)_\d+", u)
        return self.grupo_de(m.group(1)) if m else -1

    def a_texto(self) -> str:
        """JSON de los grupos y sus alias (lo que el usuario edita en Grupos de curvas)."""
        return json.dumps([{"nombre": g.nombre, "descripcion": g.descripcion, "origen": g.origen, "icono": g.icono,
                            "alias": g.alias} for g in self.grupos], ensure_ascii=False)

    @classmethod
    def desde_texto(cls, texto: str) -> "BaseAlias | None":
        try:
            return cls([GrupoAlias(d["nombre"], d.get("descripcion", ""), d.get("origen", "RES"),
                                   d.get("icono", ""), list(d.get("alias", []))) for d in json.loads(texto)])
        except (ValueError, KeyError, TypeError):
            return None


def herramientas_por_defecto() -> BaseHerramientas:
    """Herramientas de completación de tamaños API estándar."""
    b = BaseHerramientas()
    cats = [(1, "Casing", False, 1, True), (2, "Tubing", True, 1, True), (3, "Packer", True, 2, True),
            (4, "Casing Shoe", False, 1, True), (5, "Perforation", False, 1, False),
            (6, "Bridge Plug", True, 0, True), (7, "Cement Plug", True, 0, True),
            (8, "Cement", False, 0, True), (9, "Well Head", True, 2, True), (10, "OpenHole", False, 0, False)]
    b.categorias = [CategoriaHerramienta(i, n, i, c, z, e) for i, n, c, z, e in cats]
    # 8-5/8" (24 lb/ft) es el revestimiento superficial habitual en pozos de tierra de EE. UU. (Kansas, D115)
    for od, id_ in ((20, 19), (16, 15.124), (13.375, 12.347), (9.625, 8.535), (8.625, 8.097), (7, 6.276), (5.5, 4.892)):
        nom = f'{od:g}"' if od != 9.625 else '9-5/8"'
        nom = {13.375: '13-3/8"', 8.625: '8-5/8"', 5.5: '5-1/2"'}.get(od, nom)
        b.items += [ItemHerramienta(1, f"Casing {nom}", od, id_),
                    ItemHerramienta(4, f"Casing Shoe {nom}", od + 0.5, id_),
                    ItemHerramienta(5, f"Perforation {nom}", od + 1.5, id_),
                    ItemHerramienta(8, f"Cement {nom}", od + 2, od),
                    ItemHerramienta(6, f"Bridge Plug {nom}", id_, 0),
                    ItemHerramienta(7, f"Cement Plug {nom}", id_, 0)]
    for od, id_ in ((2.375, 1.995), (2.875, 2.441), (3.5, 2.992), (4.5, 3.958)):
        b.items.append(ItemHerramienta(2, f'Tubing {od:g}"', od, id_))
    for od in (7, 9.625):
        b.items.append(ItemHerramienta(3, f'Packer {od:g}"' if od == 7 else 'Packer 9-5/8"', od - 0.8, 2.5))
    b.items.append(ItemHerramienta(9, 'Well Head 13"', 13.0, 0))
    # pozo abierto (completación a hueco abierto, p. ej. el Arbuckle de Kansas; D120)
    for diam, nom in ((6.125, '6-1/8"'), (7.875, '7-7/8"'), (8.75, '8-3/4"'), (12.25, '12-1/4"'), (17.5, '17-1/2"')):
        b.items.append(ItemHerramienta(10, f"Open Hole {nom}", diam, 0))
    return b


def litologias_por_defecto() -> BaseLitologia:
    nombres = ["Default", "Sandstone", "Limestone", "Claystone", "Shale", "Dolomite", "Siltstone",
               "Conglomerate", "Coal", "Anhydrite", "Shaly sandstone", "Silty sandstone",
               "Sandy shale", "Silty shale", "Calcareous shale", "Sandy limestone", "Chalk", "Marl",
               "Breccia", "Chert", "Gypsum", "Salt", "Igneous", "Metamorphic"]
    return BaseLitologia([TipoLito(i, n, i) for i, n in enumerate(nombres)])


def alias_por_defecto() -> BaseAlias:
    """Grupos de mnemónicos habituales (lista propia, nomenclatura estándar de la industria)."""
    datos = {
        "DEPT": ("Depth", ["DEPT", "DEPTH", "DEP", "MD", "TVD", "TVDE", "DEPTH MD", "DEPTH TVD"]),
        # v0.5 (D106): mnemónicos de los LAS reales del KGS (RILD, LL, RLL3, CNLS, DPHI, RHOC, CILD...)
        "GR": ("Gamma Ray", ["GR", "GRC", "SGR", "CGR", "GAM", "GRD", "GRS", "GAMM", "ECGR", "HGR", "GRGC",
                             "GRSG", "GCGR", "GRDI",
                             # 1.0 (D122): nombres de las cargas de la KCC (GAMMA, DEN(CDL), RES(DI)...)
                             "GAMMA"]),
        "SP": ("Spontaneous Potential", ["SP", "SPC", "SSP"]),
        "CAL": ("Caliper", ["CAL", "CALI", "CALS", "HCAL", "C1", "C2", "DCAL", "MCAL", "MELCAL", "LCAL",
                            "CALX", "CALY", "HDIA", "MSFCAL", "CALIPER", "CALIPERL", "CALN", "CALD"]),
        "RESD": ("Deep Resistivity", ["ILD", "LLD", "RD", "RT", "AT90", "RLA5", "HDRS", "RILD", "LL", "RT90",
                                      "AO90", "IDPH",
                                      # registros eléctricos e inducción de los años 60 (D111)
                                      "RES", "RLL", "IND", "RES(DI)", "RES(DG)"]),
        "RESM": ("Medium Resistivity", ["ILM", "RM", "AT30", "RLA3", "RILM", "RT30", "RT60", "AT60", "IMPH",
                                        "LAT16", "RES(MI)"]),
        "RESS": ("Shallow Resistivity", ["SFLU", "SFL", "MSFL", "LLS", "RS", "RXO", "AT10", "RLL3", "MLL",
                                         "RT10", "RT20", "AT20", "SFLA",
                                         "LL8", "GUARD", "RSFE", "RN16"]),
        "RMIC": ("Microresistivity", ["MI", "MN", "MINV", "MNOR", "MEL15", "MEL20", "MLI", "MLN"]),
        "COND": ("Conductivity", ["CILD", "CILM", "CIL", "CT90", "COND", "COND(DI)", "COND(MI)"]),
        "RHOB": ("Bulk Density", ["RHOB", "RHOZ", "DEN", "ZDEN", "DEN(CDL)"]),
        "PHIN": ("Neutron Porosity", ["NPHI", "TNPH", "NPOR", "CNC", "PHIN", "CNLS", "CNSS", "CNDL", "CNPOR",
                                      "NPHS", "NPHL", "NPHD", "NPLS", "NPRL", "NPRS", "NPRD", "POR(NEU)"]),
        # neutrón antiguo en cuentas (API, cps): no es porosidad
        "NEUT": ("Neutron (counts)", ["NEUT", "NEU", "GNT", "NCNT"]),
        "PHID": ("Density Porosity", ["PHID", "DPHI", "DPOR", "DPHS", "DPHD", "DLIM", "DPHZ", "POR(DEN)", "DPRL",
                                      "DPRS", "DPRD", "DPLS"]),
        "PHIS": ("Sonic Porosity", ["PHIS", "SPOR", "SPHI", "SPRL", "SPHL", "SPHS", "SPHD"]),
        "DTC": ("Sonic Travel Time", ["DT", "DTC", "DTCO", "AC", "SONI", "SON", "DTC1", "DELTAT", "DT35"]),
        "PE": ("Photoelectric Effect", ["PE", "PEF", "PEFZ", "PEFL", "PDPE"]),
        "TENS": ("Cable Tension", ["TENS", "LTEN", "TEN", "HTEN", "TSS1"]),
        "VSH": ("Volume Shale", ["VSH", "VSHALE", "VCL", "VSH_GR", "VSH_SP", "VSH_N", "VSH_ND"]),
        # PHID y PHIS tienen grupo propio (D106)
        "POR": ("Porosity", ["PHIE", "PHIT", "POR", "PORE_D", "PORE_S"]),
        "SW": ("Water Saturation", ["SW", "SWE", "SWT"]),
        # v0.4 (D93): condición de pozo con los mnemónicos de compañía (HDRA, BIT...)
        "DRHO": ("Density Correction", ["DRHO", "HDRA", "DCOR", "ZCOR", "CORR", "RHOC", "DRH", "COMP"]),
        "BS": ("Bit Size", ["BS", "BIT", "BITSIZE", "BIT_SIZE", "HOLE_SIZE"]),
    }
    return BaseAlias([GrupoAlias(k, d, "RES", "", a) for k, (d, a) in datos.items()])
