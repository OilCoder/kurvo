"""Selección global: pozo, log, curva y zona actuales, compartidos por el árbol, el editor de logs,
el Log Plot, el panel de QC y las herramientas (cada una los toma por defecto). La barra de
estado la muestra (ver D53)."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..i18n import tr


class Seleccion(QObject):
    cambiada = Signal()

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.pozo = -1
        self.log = -1
        self.curva = ""
        self.zona = -1          # -1 = todo el registro
        self._bloqueo = 0

    @property
    def pr(self):
        return self.app.proyecto

    def fijar(self, pozo: int | None = None, log: int | None = None, curva: str | None = None,
              zona: int | None = None) -> None:
        antes = (self.pozo, self.log, self.curva, self.zona)
        if pozo is not None and pozo != self.pozo:
            self.pozo = pozo
            if log is None:
                log = 0
        if log is not None:
            self.log = log
        if curva is not None:
            self.curva = curva
        if zona is not None:
            self.zona = zona
        self.validar()
        if (self.pozo, self.log, self.curva, self.zona) != antes and not self._bloqueo:
            self.cambiada.emit()

    def validar(self) -> None:
        """Ajusta los índices al proyecto actual (tras borrar o abrir otro proyecto)."""
        pr = self.pr
        if not pr.pozos:
            self.pozo, self.log, self.curva = -1, -1, ""
        else:
            if not 0 <= self.pozo < len(pr.pozos):
                self.pozo = 0
            logs = pr.pozos[self.pozo].logs
            if not 0 <= self.log < len(logs):
                self.log = 0 if logs else -1
            reg = self.registro()
            if reg is not None and self.curva and reg.indice_columna(self.curva) < 0:
                self.curva = ""
        if not -1 <= self.zona < len(pr.zonas):
            self.zona = -1

    # ---------------------------------------------------------------- consultas
    def objeto_pozo(self):
        return self.pr.pozos[self.pozo] if 0 <= self.pozo < len(self.pr.pozos) else None

    def registro(self):
        p = self.objeto_pozo()
        return p.logs[self.log] if p is not None and 0 <= self.log < len(p.logs) else None

    def indice_curva(self) -> int:
        r = self.registro()
        return r.indice_columna(self.curva) if r is not None and self.curva else -1

    def intervalo_zona(self) -> tuple[float | None, float | None]:
        if self.zona < 0 or self.pozo < 0:
            return None, None
        from .multipozo_ui import intervalo_zona
        return intervalo_zona(self.pr, self.zona, self.pozo)

    def nombre_zona(self) -> str:
        return self.pr.zonas[self.zona].nombre if 0 <= self.zona < len(self.pr.zonas) else tr("Whole log")

    def texto(self) -> str:
        p, r = self.objeto_pozo(), self.registro()
        partes = [f"{tr('Well')}: {p.nombre if p else '—'}", f"{tr('Log')}: {r.nombre if r else '—'}",
                  f"{tr('Curve')}: {self.curva or '—'}", f"{tr('Zone')}: {self.nombre_zona()}"]
        return "   ·   ".join(partes)

    def __enter__(self):
        self._bloqueo += 1
        return self

    def __exit__(self, *exc):
        self._bloqueo -= 1
