"""Historial del proyecto: operaciones compuestas (v0.4, D84–D85).

Una herramienta que toca varios registros (normalización, lote, desfase automático, predicción DL)
o que crea curvas que se agregan a las plantillas abre una operación:

    op = proyecto.historial_ops.iniciar("Normalize wells")
    ... historial.aplicar(reg1, ...); historial.aplicar(reg2, ...)
    proyecto.historial_ops.terminar(op, proyecto, plantillas=True, alias=alias)

Cada foto de deshacer que se toma mientras está abierta lleva el número de la operación
(`Foto.grupo`), así que la operación no copia datos: apunta a los historiales de cada registro.
Deshacerla deshace en cada registro las fotos de ese grupo (cada bitácora anota su parte) y quita
de las plantillas las curvas que se agregaron; rehacerla hace lo contrario."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from . import historial, plantilla_auto

LIMITE = 50
_numeros = count(1)


class ErrorOperacion(Exception):
    pass


@dataclass
class OperacionCompuesta:
    grupo: int
    descripcion: str
    registros: list = field(default_factory=list)
    plantillas: list = field(default_factory=list)       # CambioPlantilla
    curvas_nuevas: list = field(default_factory=list)    # (registro, nombre)
    deshecha: bool = False

    @property
    def n_registros(self) -> int:
        return len(self.registros)


class HistorialProyecto:
    def __init__(self):
        self.operaciones: list[OperacionCompuesta] = []
        self._abierta: OperacionCompuesta | None = None
        self._nivel = 0

    # ---------------------------------------------------------------- registro
    def iniciar(self, descripcion: str) -> OperacionCompuesta | None:
        """Abre una operación; si ya hay una abierta (herramienta dentro de otra), devuelve None
        y los cambios quedan en la exterior."""
        self._nivel += 1
        if self._abierta is not None:
            return None
        op = OperacionCompuesta(next(_numeros), descripcion)
        self._abierta = op
        historial._compuesta = {"grupo": op.grupo, "tocados": {}}
        return op

    def terminar(self, op: OperacionCompuesta | None, proyecto=None, plantillas: bool = True,
                 alias=None) -> OperacionCompuesta | None:
        self._nivel = max(0, self._nivel - 1)
        if op is None or op is not self._abierta:
            return None
        tocados = historial._compuesta["tocados"] if historial._compuesta else {}
        historial._compuesta = None
        self._abierta = None
        self._nivel = 0
        for reg, previas in tocados.values():
            if any(f.grupo == op.grupo for f in reg.historial.deshacer):
                op.registros.append(reg)
                antes = {n.upper() for n in previas}
                op.curvas_nuevas += [(reg, n) for n in reg.nombres() if n.upper() not in antes]
        if plantillas and proyecto is not None:
            for reg in op.registros:
                nuevas = [n for r, n in op.curvas_nuevas if r is reg]
                op.plantillas += plantilla_auto.agregar_nuevas(proyecto, reg, nuevas, alias)
        if not op.registros and not op.plantillas:
            return None
        # como en un registro, un cambio nuevo descarta lo que había por rehacer en esos registros
        ids = {id(r) for r in op.registros}
        self.operaciones = [o for o in self.operaciones
                            if not (o.deshecha and (ids & {id(r) for r in o.registros} or o.plantillas))]
        self.operaciones.append(op)
        del self.operaciones[:-LIMITE]
        return op

    # ---------------------------------------------------------------- consultas
    def buscar(self, grupo: int) -> OperacionCompuesta | None:
        return next((o for o in self.operaciones if o.grupo == grupo), None)

    def ultima(self, deshecha: bool = False, varios: bool = True) -> OperacionCompuesta | None:
        """Última operación hecha (o la primera por rehacer); con `varios`, solo las que tocaron
        más de un registro (las de uno se deshacen desde ese registro)."""
        ops = [o for o in self.operaciones if o.deshecha == deshecha and (not varios or o.n_registros > 1)]
        if not ops:
            return None
        return ops[0] if deshecha else ops[-1]

    # ---------------------------------------------------------------- deshacer / rehacer
    def deshacer(self, op: OperacionCompuesta) -> int:
        """Deshace la operación en todos sus registros. Exige que sea lo último de cada uno."""
        tarde = [r.nombre for r in op.registros
                 if not r.historial.deshacer or r.historial.deshacer[-1].grupo != op.grupo]
        if tarde:
            raise ErrorOperacion(", ".join(tarde))
        for reg in op.registros:
            while reg.historial.deshacer and reg.historial.deshacer[-1].grupo == op.grupo:
                historial.deshacer(reg)
        for c in reversed(op.plantillas):
            c.deshacer()
        op.deshecha = True
        return len(op.registros)

    def rehacer(self, op: OperacionCompuesta) -> int:
        tarde = [r.nombre for r in op.registros
                 if not r.historial.rehacer or r.historial.rehacer[-1].grupo != op.grupo]
        if tarde:
            raise ErrorOperacion(", ".join(tarde))
        for reg in op.registros:
            while reg.historial.rehacer and reg.historial.rehacer[-1].grupo == op.grupo:
                historial.rehacer(reg)
        for c in op.plantillas:
            c.rehacer()
        op.deshecha = False
        return len(op.registros)

    def deshacer_en(self, reg) -> tuple[str, OperacionCompuesta | None] | None:
        """Ctrl+Z sobre un registro: si su último cambio es parte de una operación compuesta, la
        deshace entera; si no, deshace solo ese cambio. Devuelve (descripción, operación)."""
        h = reg.historial
        if not h.deshacer:
            return None
        op = self.buscar(h.deshacer[-1].grupo) if h.deshacer[-1].grupo else None
        if op is not None and not op.deshecha:
            self.deshacer(op)
            return op.descripcion, op
        return historial.deshacer(reg), None

    def rehacer_en(self, reg) -> tuple[str, OperacionCompuesta | None] | None:
        h = reg.historial
        if not h.rehacer:
            return None
        op = self.buscar(h.rehacer[-1].grupo) if h.rehacer[-1].grupo else None
        if op is not None and op.deshecha:
            self.rehacer(op)
            return op.descripcion, op
        return historial.rehacer(reg), None
