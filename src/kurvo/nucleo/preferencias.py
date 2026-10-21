"""Preferencias del usuario (sin Qt): idioma, nulos, umbrales de QC, rangos físicos y opciones
por defecto de deep learning. La vista las guarda en QSettings como JSON; el núcleo las lee con
`actual()`. Antes de v0.3 estos valores estaban fijos en el código (D64)."""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field

# rango físico por grupo de alias (o por mnemónico), en las unidades habituales; la unidad se
# comprueba con unidades.canonica para no aplicar el rango a otra escala
RANGOS_DEFECTO: dict[str, list[tuple[str, float, float]]] = {
    "GR": [("GAPI", 0, 350), ("API", 0, 350)],
    # la línea base del SP es arbitraria: en los LAS reales del KGS anda por −500 mV (D108)
    "SP": [("MV", -1000, 1000)],
    "CAL": [("IN", 2, 40), ("MM", 50, 1000), ("CM", 5, 100)],
    "RHOB": [("G/CC", 1.0, 3.3), ("KG/M3", 1000, 3300)],
    "DRHO": [("G/CC", -1.0, 1.0), ("KG/M3", -1000, 1000)],
    "PHIN": [("V/V", -0.15, 1.0), ("PU", -15, 100), ("%", -15, 100)],
    "DTC": [("US/FT", 35, 250), ("US/M", 115, 820)],
    "PE": [("B/E", 0, 20), ("", 0, 20)],
    "RESD": [("OHMM", 0.01, 1e5)], "RESM": [("OHMM", 0.01, 1e5)], "RESS": [("OHMM", 0.01, 1e5)],
    "VSH": [("V/V", 0, 1)], "POR": [("V/V", 0, 0.6)], "SW": [("V/V", 0, 1)],
    # v0.5 (D106): grupos nuevos de los LAS reales
    "PHID": [("V/V", -0.15, 1.0), ("PU", -15, 100), ("%", -15, 100)],
    "PHIS": [("V/V", -0.15, 1.0), ("PU", -15, 100), ("%", -15, 100)],
    "RMIC": [("OHMM", 0.01, 1e5)], "COND": [("MMHO/M", 0, 1e5)],
}
# grupos de rangos agregados después de v0.4: se suman a los rangos guardados antes (VERSION_RANGOS)
RANGOS_NUEVOS = {2: ("PHID", "PHIS", "RMIC", "COND")}
VERSION_RANGOS = 2


def completar_rangos(rangos: dict, version: int) -> dict:
    """Agrega a unos rangos guardados con una versión anterior los grupos que se crearon después
    (si el usuario ya los tiene, no se tocan)."""
    for v, grupos in RANGOS_NUEVOS.items():
        if version < v:
            for g in grupos:
                rangos.setdefault(g, copy.deepcopy(RANGOS_DEFECTO[g]))
    return rangos


UNIDADES_PROF = ("M", "FT")
TEMAS = ("light", "dark")


@dataclass
class UmbralesQC:
    nulos_aviso: float = 10.0        # % de nulos a partir del cual la curva tiene aviso (B)
    nulos_malo: float = 50.0         # % de nulos a partir del cual la nota es C
    fuera_malo: float = 5.0          # % de muestras fuera del rango físico para nota C
    saturacion: float = 1.0          # % de muestras pegadas al mín./máx. para aviso
    minimo_plano: int = 10           # muestras iguales seguidas que forman un tramo plano
    ventana_picos: int = 11          # muestras de la mediana móvil de picos
    sigma_picos: float = 4.0         # umbral de picos (sigmas robustas)
    derrumbe: float = 1.0            # CALI − BS (in) que se considera derrumbe
    drho: float = 0.15               # |DRHO| (g/cc) que indica mala corrección de densidad
    picos_por_mil: float = 5.0       # picos por cada 1000 muestras válidas que no bajan la nota a B (D110)
    calibre_cerrado: float = 4.0     # calibre (in) por debajo del cual el brazo está cerrado o en casing (D110)


@dataclass
class OpcionesDL:
    arquitectura: str = "unet"
    largo: int = 128
    epocas: int = 60
    lote: int = 32
    lr: float = 2e-3
    muestras_mc: int = 20
    forzar_cpu: bool = False
    excluir_qc: bool = True          # no entrenar con muestras que tienen bandera QC


@dataclass
class Preferencias:
    idioma: str = "en"
    nulos_extra: list[float] = field(default_factory=list)   # además del NULL del archivo, al importar
    qc: UmbralesQC = field(default_factory=UmbralesQC)
    rangos: dict[str, list[tuple[str, float, float]]] = field(
        default_factory=lambda: copy.deepcopy(RANGOS_DEFECTO))
    dl: OpcionesDL = field(default_factory=OpcionesDL)
    plantilla_auto: bool = True      # las curvas nuevas se agregan solas a las plantillas (D82)
    unidad_prof: str = "M"           # unidad de profundidad si el archivo no la trae (D98): "M" o "FT"
    tema: str = "light"              # "light" o "dark" (D99)

    def a_json(self) -> str:
        return json.dumps({**asdict(self), "version_rangos": VERSION_RANGOS})

    @classmethod
    def desde_json(cls, texto: str | None) -> "Preferencias":
        p = cls()
        if not texto:
            return p
        try:
            d = json.loads(texto)
        except (TypeError, ValueError):
            return p
        p.idioma = str(d.get("idioma", p.idioma))
        p.nulos_extra = [float(x) for x in d.get("nulos_extra", []) if _es_num(x)]
        p.plantilla_auto = bool(d.get("plantilla_auto", p.plantilla_auto))
        if str(d.get("unidad_prof", "")).upper() in UNIDADES_PROF:
            p.unidad_prof = str(d["unidad_prof"]).upper()
        if d.get("tema") in TEMAS:
            p.tema = d["tema"]
        for destino, clave in ((p.qc, "qc"), (p.dl, "dl")):
            for k, v in (d.get(clave) or {}).items():
                if not hasattr(destino, k):
                    continue
                previo = getattr(destino, k)
                try:
                    setattr(destino, k, bool(v) if isinstance(previo, bool) else type(previo)(v))
                except (TypeError, ValueError):
                    pass
        if isinstance(d.get("rangos"), dict):
            p.rangos = {str(g).upper(): [(str(u), float(lo), float(hi)) for u, lo, hi in filas]
                        for g, filas in d["rangos"].items()}
            p.rangos = completar_rangos(p.rangos, int(d.get("version_rangos", 1)))
        return p


def _es_num(x) -> bool:
    try:
        float(x)
        return not isinstance(x, bool)
    except (TypeError, ValueError):
        return False


@dataclass
class PreferenciasQC:
    """Umbrales de QC y rangos físicos guardados en un proyecto (v0.4, D87): si existen, mandan
    sobre los del usuario para ese proyecto, así un proyecto compartido da las mismas notas en
    cualquier equipo."""
    qc: UmbralesQC = field(default_factory=UmbralesQC)
    rangos: dict[str, list[tuple[str, float, float]]] = field(
        default_factory=lambda: copy.deepcopy(RANGOS_DEFECTO))

    @classmethod
    def de(cls, p: Preferencias) -> "PreferenciasQC":
        return cls(copy.deepcopy(p.qc), copy.deepcopy(p.rangos))

    def a_json(self) -> str:
        return json.dumps({"version": 1, "version_rangos": VERSION_RANGOS, "qc": asdict(self.qc),
                           "rangos": self.rangos}, indent=1)

    @classmethod
    def desde_json(cls, texto: str | None) -> "PreferenciasQC | None":
        """None si el texto no es un JSON válido (el proyecto usará las preferencias del usuario)."""
        if not texto:
            return None
        try:
            d = json.loads(texto)
        except (TypeError, ValueError):
            return None
        if not isinstance(d, dict):
            return None
        p = Preferencias.desde_json(json.dumps({"qc": d.get("qc") or {}, "rangos": d.get("rangos"),
                                                "version_rangos": d.get("version_rangos", 1)}))
        return cls(p.qc, p.rangos)


_usuario = Preferencias()
_proyecto: PreferenciasQC | None = None
_actual = _usuario


def _combinar() -> None:
    """Las preferencias vigentes: las del usuario con el QC del proyecto si lo tiene. Es un objeto
    nuevo en cada cambio (la caché de notas de QC usa su identidad)."""
    global _actual
    if _proyecto is None:
        _actual = _usuario
    else:
        _actual = copy.copy(_usuario)
        _actual.qc, _actual.rangos = _proyecto.qc, _proyecto.rangos


def actual() -> Preferencias:
    return _actual


def usuario() -> Preferencias:
    return _usuario


def proyecto() -> PreferenciasQC | None:
    return _proyecto


def origen_qc() -> str:
    """"project" si los umbrales y rangos vigentes son los del proyecto; si no, "user"."""
    return "project" if _proyecto is not None else "user"


def fijar(p: Preferencias) -> None:
    global _usuario
    _usuario = p
    _combinar()


def fijar_proyecto(q: PreferenciasQC | None) -> None:
    global _proyecto
    _proyecto = q
    _combinar()
