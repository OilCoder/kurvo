"""El proyecto: pozos con sus registros, zonas, plantillas, gráficos de registros y corte. Se guarda en
un archivo .kurvo (archivo_proyecto.py, D124)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .comun import UID
from .intervalos import Completacion, Litologia, Zona
from .historial_proyecto import HistorialProyecto
from .las import RegistroLAS
from .plantilla import Plantilla
from .trayectoria import Trayectoria


class ErrorProyecto(Exception):
    pass


@dataclass
class Pozo:
    nombre: str
    x: float = 0.0
    y: float = 0.0
    trayectoria: Trayectoria = field(default_factory=Trayectoria)
    logs: list[RegistroLAS] = field(default_factory=list)
    completaciones: list[Completacion] = field(default_factory=list)
    litologias: list[Litologia] = field(default_factory=list)
    uid: int = field(default_factory=UID.nuevo)


@dataclass
class LogPlot:
    """Estado de un gráfico de registros: pozo, registro, plantilla, profundidades y zonas visibles."""
    nombre: str = "default"
    pozo: int = -1
    las: int = -1
    lito: int = -1
    comp: int = -1
    plantilla: int = -1
    usar_prof_propia: bool = False
    prof_tope: float = 0.0
    prof_base: float = 100.0
    usar_escala_propia: bool = False
    escala: float = 200.0
    modo_prof: int = 2            # 0 TVD, 1 TVDSS, 2 MD
    zonas_visibles: list[bool] = field(default_factory=list)
    ocultar_vacias: bool = True   # esconder al dibujar las pistas sin datos en este pozo (D128)


@dataclass
class PozoCorte:
    nombre: str
    pozo: int = 0
    las: int = 0
    lito: int = 0
    plantilla: int = 0
    comp: int = 0
    usar_prof_propia: bool = False
    tope: float = 0.0
    base: float = 1000.0


@dataclass
class CorteTransversal:
    pozos: list[PozoCorte] = field(default_factory=list)
    zonas_visibles: list[bool] = field(default_factory=list)
    plantilla_global_usar: bool = False
    plantilla_global: int = 0
    prof_global_usar: bool = False
    prof_global_tope: float = 0.0
    prof_global_base: float = 1000.0
    escala_global_usar: bool = False
    escala_global: float = 500.0
    modo_prof_global: int = 2
    modo_prof_global_usar: bool = True
    aplanamiento: float = 1000.0
    prof_aplanar: float = 0.0
    zona_aplanar: int = -1


@dataclass
class Analisis:
    """Análisis de un módulo (Pickett, Hingle...): su contenido se guarda como texto."""
    tipo: str
    uid: int
    nombre: str
    extra: str
    contenido: str


@dataclass
class Proyecto:
    ruta: str = ""
    pozos: list[Pozo] = field(default_factory=list)
    zonas: list[Zona] = field(default_factory=list)
    plantillas: list[Plantilla] = field(default_factory=list)
    logplots: list[LogPlot] = field(default_factory=list)
    logplot_actual: int = -1
    corte: CorteTransversal = field(default_factory=CorteTransversal)
    editores: dict[str, int] = field(default_factory=dict)
    analisis: list[Analisis] = field(default_factory=list)
    modificado: bool = False
    # umbrales de QC y rangos físicos propios del proyecto (JSON de preferencias.PreferenciasQC);
    # vacío = se usan los del usuario (D87)
    qc_ajustes: str = ""
    # operaciones compuestas para deshacer de una vez (no se guarda, como las fotos de deshacer)
    historial_ops: HistorialProyecto = field(default_factory=HistorialProyecto, repr=False, compare=False)

    # ----------------------------------------------------------- consultas
    def indice_pozo(self, nombre: str) -> int:
        return next((i for i, p in enumerate(self.pozos) if p.nombre == nombre), -1)

    def existe_pozo(self, nombre: str) -> bool:
        return self.indice_pozo(nombre) >= 0

    def nombre_libre(self, base: str, existentes) -> str:
        """Primer nombre libre de la forma base1, base2…"""
        existentes = set(existentes)
        i = 1
        while f"{base}{i}" in existentes:
            i += 1
        return f"{base}{i}"

    # ----------------------------------------------------------- edición
    def nuevo_pozo(self, nombre: str | None = None, x: float = 0.0, y: float = 0.0) -> Pozo:
        nombre = nombre or self.nombre_libre("WellName", (p.nombre for p in self.pozos))
        if self.existe_pozo(nombre):
            raise ErrorProyecto("Well name is already exists.")
        if not nombre.strip():
            raise ErrorProyecto("Empty well name is not allowed")
        p = Pozo(nombre, x, y)
        self.pozos.append(p)
        for z in self.zonas:
            z.profundidades.append(0.0)
        self.modificado = True
        return p

    def borrar_pozo(self, i: int) -> None:
        del self.pozos[i]
        for z in self.zonas:
            if i < len(z.profundidades):
                del z.profundidades[i]
        self.modificado = True

    def nueva_zona(self, nombre: str | None = None) -> Zona:
        nombre = nombre or self.nombre_libre("NewZone", (z.nombre for z in self.zonas))
        if any(z.nombre == nombre for z in self.zonas):
            raise ErrorProyecto("Zone is already exists.")
        z = Zona(nombre, [0.0] * len(self.pozos))
        self.zonas.append(z)
        for lp in self.logplots:
            lp.zonas_visibles.append(True)
        self.modificado = True
        return z

    @staticmethod
    def mover(lista: list, i: int, destino: int) -> None:
        x = lista.pop(i)
        lista.insert(max(0, min(destino, len(lista))), x)

    # ----------------------------------------------------------- archivo
    @classmethod
    def vacio(cls) -> "Proyecto":
        return cls()

    @classmethod
    def abrir(cls, ruta: str | Path) -> "Proyecto":
        from . import archivo_proyecto
        try:
            return archivo_proyecto.abrir(cls, ruta)
        except archivo_proyecto.ErrorArchivo as e:
            raise ErrorProyecto(str(e)) from e

    def guardar(self, ruta: str | Path | None = None) -> None:
        from . import archivo_proyecto
        ruta = Path(ruta or self.ruta)
        archivo_proyecto.guardar(self, ruta)
        self.ruta = str(ruta)
        self.modificado = False
