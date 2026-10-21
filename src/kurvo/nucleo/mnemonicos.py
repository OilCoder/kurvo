"""Estandarización de mnemónicos con la base de alias (mantenimiento, prioridad 4).

Cada curva cuyo nombre aparece como alias de un grupo se propone renombrar al nombre del grupo
(p. ej. ILD, LLD, AT90 → RESD; NPHI, TNPH → PHIN). Las columnas de profundidad no se tocan, y si
dos curvas llevarían al mismo nombre solo se renombra la primera; las demás se informan."""
from __future__ import annotations

from dataclasses import dataclass

from ..i18n import tr


@dataclass
class Propuesta:
    indice: int
    actual: str
    nuevo: str
    grupo: str = ""
    motivo: str = ""          # vacío si se puede aplicar; si no, por qué se omite

    @property
    def aplicable(self) -> bool:
        return not self.motivo and self.nuevo != self.actual


def proponer(reg, alias) -> list[Propuesta]:
    out: list[Propuesta] = []
    ocupados = {c.nombre.upper() for c in reg.columnas}
    tomados: set[str] = set()
    for k, c in enumerate(reg.columnas):
        if k in (reg.indice_md, reg.indice_tvd):
            continue
        g = alias.grupo_de(c.nombre)
        if g < 0:
            continue
        grupo = alias.grupos[g]
        destino = grupo.nombre
        if destino.upper() == c.nombre.upper():
            continue
        p = Propuesta(k, c.nombre, destino, grupo.descripcion)
        if grupo.nombre.upper() in ("DEPT", "NA"):
            continue
        if destino.upper() in ocupados or destino.upper() in tomados:
            p.motivo = tr("{0} already exists in the log").format(destino)
        else:
            tomados.add(destino.upper())
        out.append(p)
    return out


def aplicar(reg, propuestas: list[Propuesta]) -> int:
    from .historial import renombrar_original
    n = 0
    for p in propuestas:
        if p.aplicable and reg.columnas[p.indice].nombre == p.actual:
            reg.columnas[p.indice].nombre = p.nuevo
            if not reg.columnas[p.indice].descripcion and p.grupo:
                reg.columnas[p.indice].descripcion = p.grupo
            renombrar_original(reg, p.actual, p.nuevo)
            n += 1
    return n
