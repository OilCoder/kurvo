"""Dibujo del gráfico de registros: pistas, curvas, rejillas, rellenos, litología, completación y zonas.

La geometría (rango, escala, transformación a píxeles, orden de dibujo, rellenos sólo donde
izquierda < derecha); el aspecto de cabeceras y de la completación es diseño propio y los patrones de litología
siguen la convención FGDC/USGS."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field, replace

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPolygonF)

from ..i18n import tr
from ..nucleo.bases import BaseAlias, BaseHerramientas, BaseLitologia, litologias_por_defecto
from ..nucleo.comun import NULO, parse_color, valor_a_px
from ..nucleo.intervalos import Completacion, Litologia, Zona
from ..nucleo.las import RegistroLAS
from ..nucleo.plantilla import (BORDE_DER, BORDE_IZQ, PISTA_COMPLETACION, PISTA_CURVAS,
                                PISTA_LITOLOGIA, CurvaPlantilla, Plantilla)
from ..nucleo.trayectoria import Trayectoria
from .patrones_lito import brocha_patron, color_patron

MODO_TVD, MODO_TVDSS, MODO_MD = 0, 1, 2
NOMBRES_MODO = {MODO_TVD: "TVD", MODO_TVDSS: "TVDSS", MODO_MD: "MD"}
ESTILOS_QT = {0: Qt.SolidLine, 1: Qt.DotLine, 2: Qt.DashLine, 3: Qt.DashDotDotLine,
              4: Qt.DashDotLine}
PX_POR_ESCALA = 500.0
UNIDADES_GAS = ("UNITS", "PPM", "%")   # C1/C2 de un registro de lodo: no son calibres (D112)


def qcolor(texto: str) -> QColor:
    return QColor(*parse_color(texto))


def pluma(color: str, ancho: int = 1, tipo: int = 0) -> QPen:
    p = QPen(qcolor(color), max(ancho, 0))
    p.setStyle(ESTILOS_QT.get(tipo, Qt.SolidLine))
    p.setCosmetic(False)
    return p


@dataclass
class CurvaResuelta:
    plantilla: CurvaPlantilla
    columnas: list[int] = field(default_factory=list)


@dataclass
class DatosLogPlot:
    plantilla: Plantilla
    registro: RegistroLAS | None = None
    trayectoria: Trayectoria | None = None
    litologia: Litologia | None = None
    completacion: Completacion | None = None
    zonas: list[tuple[Zona, float]] = field(default_factory=list)   # (zona, prof. MD en este pozo)
    modo: int = MODO_MD
    prof_propia: tuple[float, float] | None = None
    escala_propia: float | None = None
    nombre_pozo: str = ""
    base_lito: BaseLitologia | None = None
    base_herr: BaseHerramientas | None = None
    alias: BaseAlias | None = None
    capas: frozenset = frozenset()      # "qc", "dl", "original": capas opcionales (v0.3, D56)
    ocultar_vacias: bool = False        # esconder las pistas sin datos en este pozo (D128)


class LogPlot:
    """Equivalente de myLogPlot: prepara la vista y dibuja con QPainter."""

    def __init__(self, datos: DatosLogPlot):
        self.d = datos
        self.listo = False
        self.mensajes: list[str] = []
        self.col_prof = -1
        self.prof_min = 0.0
        self.prof_max = 0.0
        self.alto = 0.0
        self.ancho = 0.0
        self.curvas: dict[tuple[int, int], CurvaResuelta] = {}
        self.escalas: dict[int, tuple[float, float]] = {}    # id(curva) -> escala de este registro
        self.factores: dict[tuple[int, int], float] = {}     # (id(curva), columna) -> ×100 / ÷100 (D112)
        self.ocultas = 0                                    # pistas escondidas por no tener datos (D128)
        self.preparar()

    # ------------------------------------------------------------ profundidad
    def a_prof_vista(self, md: float) -> float:
        """Convierte una profundidad MD (litología, completación, zonas) al modo de vista."""
        if md == NULO:
            return NULO
        t = self.d.trayectoria
        if self.d.modo == MODO_TVD and t is not None:
            return t.tvd_en(md)
        if self.d.modo == MODO_TVDSS and t is not None:
            v = t.tvd_en(md)
            return NULO if v == NULO else v - t.tvd_a_ss
        return md

    def prof_registro(self) -> np.ndarray | None:
        r = self.d.registro
        if r is None or not r.existe_columna(self.col_prof):
            return None
        p = r.columnas[self.col_prof].datos.copy()
        if self.d.modo == MODO_TVDSS and self.d.trayectoria is not None:
            p = p - self.d.trayectoria.tvd_a_ss
        return p

    # ------------------------------------------------------------ preparar
    def preparar(self) -> None:
        """Resuelve las columnas de cada curva y el rango de profundidad antes de dibujar."""
        t, r = self.d.plantilla, self.d.registro
        self.listo = False
        if r is not None:
            idx = r.indice_md if self.d.modo == MODO_MD else r.indice_tvd
            if not r.existe_columna(idx):
                self.mensajes.append(tr("Error!, cannot find ") +
                                     ("DEPTH MD" if self.d.modo == MODO_MD else "DEPTH TVD"))
                return
            self.col_prof = idx
            faltan = []
            for i, pista in enumerate(t.pistas):
                if pista.tipo != PISTA_CURVAS:
                    continue
                for j, c in enumerate(pista.curvas):
                    res = CurvaResuelta(c)
                    if not c.usar_grupo:
                        k = r.indice_columna(c.nombre_x)
                        if k >= 0:
                            res.columnas = [k]
                        else:
                            faltan.append(c.nombre_x)
                    elif self.d.alias is not None:
                        g = self.d.alias.grupo_de(c.nombre_x)
                        res.columnas = [k for k, nom in enumerate(r.nombres())
                                        if g != -1 and self.d.alias.grupo_de(nom) == g]
                        if g != -1:
                            self._filtrar_grupo(c, res, self.d.alias.grupos[g].nombre.upper())
                    self.curvas[(i, j)] = res
            if faltan:
                self.mensajes.append(tr("Warning, data of: {0} not found").format(", ".join(faltan)))
        if self.d.ocultar_vacias:
            self._esconder_vacias()
            t = self.d.plantilla

        if self.d.prof_propia is None:
            pmin = pmax = 0.0
            p = self.prof_registro()
            if p is not None:
                v = p[p != NULO]
                if v.size:
                    pmin, pmax = abs(float(v.min())), abs(float(v.max()))
            cmin = cmax = lmin = lmax = 0.0
            if self.d.completacion is not None:
                cmin, cmax = self.d.completacion.prof_min(), self.d.completacion.prof_max()
            if self.d.litologia is not None:
                lmin, lmax = self.d.litologia.prof_min(), self.d.litologia.prof_max()
            if self.d.modo == MODO_TVDSS and p is not None and v.size:
                # TVDSS con signo (pendiente 24): en pozos de tierra lo que está sobre el nivel del mar
                # es negativo y un abs() lo doblaba (Sara 1-28: 1240–2910 en vez de
                # −2910 a 2896). Completación y litología solo cuentan si existen.
                extra = [self.a_prof_vista(x) for x, hay in ((cmin, self.d.completacion), (cmax, self.d.completacion),
                                                             (lmin, self.d.litologia), (lmax, self.d.litologia))
                         if hay is not None]
                extra = [x for x in extra if x != NULO]
                self.prof_min = min([float(v.min())] + extra)
                self.prof_max = max([float(v.max())] + extra)
            else:
                if self.d.modo != MODO_MD:
                    cmin, cmax, lmin, lmax = (self.a_prof_vista(x) for x in (cmin, cmax, lmin, lmax))
                # completación y litología solo amplían el rango si existen: si no, sus 0 hacían
                # empezar el gráfico en 0 ft y un pozo con datos desde 1600 ft se veía vacío
                extremos = [(pmin, pmax)] if p is not None and v.size else []
                extremos += [(abs(a), abs(b)) for a, b, hay in ((cmin, cmax, self.d.completacion),
                                                                (lmin, lmax, self.d.litologia)) if hay is not None]
                self.prof_min = min((a for a, _ in extremos), default=0.0)
                self.prof_max = max((b for _, b in extremos), default=0.0)
        else:
            self.prof_min, self.prof_max = self.d.prof_propia
        if self.prof_max == self.prof_min:
            self.mensajes.append(tr("Depth minimum and maximum is equal. Unable to plot."))
            return
        for res in self.curvas.values():
            if res.plantilla.escala_auto:
                self._escala_de_datos(res.plantilla, res.columnas)
        escala = self.d.escala_propia or t.escala or 200.0
        self.alto = (self.prof_max - self.prof_min) * PX_POR_ESCALA / escala
        self.ancho = t.mas_a_la_derecha() + t.mas_a_la_izquierda()
        hay_zonas = any(prof != NULO for _, prof in self.d.zonas)
        if t.zona_nombre_visible and t.zona_nombre_posicion == 1 and (hay_zonas or not self.d.ocultar_vacias):
            self.ancho += t.zona_nombre_ancho
        self.listo = True

    def _esconder_vacias(self) -> None:
        """Deja fuera del dibujo las pistas sin datos en este pozo (D128): las de curvas cuyas curvas no
        tienen ningún valor en el registro, y las de litología o completación si el pozo no las tiene.
        Las demás se corren a la izquierda para no dejar huecos. Se trabaja sobre una copia: la
        plantilla del proyecto no cambia, y al aparecer los datos (un Compuesto) la pista vuelve."""
        t, r = self.d.plantilla, self.d.registro

        def con_datos(k: int) -> bool:
            d = r.columnas[k].datos
            return bool(np.any((d != NULO) & np.isfinite(d)))

        visibles = []
        for i, pista in enumerate(t.pistas):
            if pista.tipo == PISTA_CURVAS:
                res = [self.curvas.get((i, j)) for j in range(len(pista.curvas))]
                vis = not pista.curvas or (r is not None and any(
                    x is not None and any(con_datos(k) for k in x.columnas) for x in res))
            elif pista.tipo == PISTA_LITOLOGIA:
                vis = self.d.litologia is not None and bool(self.d.litologia.intervalos)
            else:
                vis = self.d.completacion is not None and bool(self.d.completacion.herramientas)
            visibles.append(vis)
        if all(visibles) or not any(visibles):
            return
        orden = sorted(range(len(t.pistas)), key=lambda i: t.pistas[i].x)
        tramos = [(t.pistas[i].x, t.pistas[i].x + t.pistas[i].ancho) for i in orden if visibles[i]]
        corrimiento, nueva_x = 0.0, {}
        for n, i in enumerate(orden):
            p = t.pistas[i]
            if visibles[i]:
                nueva_x[i] = p.x - corrimiento
            elif not any(a < p.x + p.ancho and p.x < b for a, b in tramos):   # no tapada por una visible
                siguiente = next((t.pistas[k].x for k in orden[n + 1:]), p.x + p.ancho)
                corrimiento += max(siguiente - p.x, 0.0)                     # su ancho y el espacio que sigue
        mapa, pistas = {}, []
        for i, p in enumerate(t.pistas):
            if visibles[i]:
                mapa[i] = len(pistas)
                pistas.append(replace(p, x=nueva_x[i]))
        vista = copy.copy(t)
        vista.pistas = pistas
        self.curvas = {(mapa[i], j): v for (i, j), v in self.curvas.items() if i in mapa}
        self.d = replace(self.d, plantilla=vista)
        self.ocultas = len(t.pistas) - len(pistas)

    # ------------------------------------------------------------ coordenadas
    @property
    def y0(self) -> float:
        return self.d.plantilla.y

    def prof_a_y(self, prof: float) -> float:
        """Profundidad → y en píxeles."""
        return valor_a_px(prof, self.prof_min, self.prof_max, self.alto, self.y0)

    def y_a_prof(self, y: float) -> float:
        """y en píxeles → profundidad."""
        if y < self.y0:
            return 0.0
        return (self.prof_max - self.prof_min) * (y - self.y0) / self.alto + self.prof_min

    def _escala_de_datos(self, c: CurvaPlantilla, columnas: list[int]) -> None:
        """Escala automática (D111): P5–P95 de la primera columna con datos en el intervalo de
        profundidad que se ve, ensanchado un 25 % a cada lado y redondeado. El SP no tiene cero
        absoluto (la línea base va de −500 a +120 mV según el pozo y deriva cientos de mV a lo largo
        del pozo) y el neutrón en cuentas depende de la herramienta, así que una escala fija los deja
        fuera de la pista."""
        from ..nucleo.plantilla_auto import escala_de_datos
        p = self.prof_registro()
        if p is None:
            return
        q = p if self.d.modo == MODO_TVDSS else np.abs(p)
        en_vista = (p != NULO) & (q >= self.prof_min) & (q <= self.prof_max)
        for k in columnas:
            d = self.d.registro.columnas[k].datos[en_vista]
            if np.any((d != NULO) & np.isfinite(d)):
                self.escalas[id(c)] = escala_de_datos(d, c.logaritmica, (5, 95), 0.25)
                return

    def _filtrar_grupo(self, c: CurvaPlantilla, res: CurvaResuelta, grupo: str) -> None:
        """Ajustes al dibujar una curva por grupo de alias (D112), sin tocar los datos:
        - CAL: C1/C2 de un registro de gas de lodo (unidad "units", ppm o %) no son calibres;
        - porosidades: una curva en PU o % en una escala de V/V (o al revés) se dibuja ×100 (o ÷100),
          porque un mismo campo trae las dos (Cutter: NPHI en %, DPHI en DECP, SPOR en PU)."""
        from ..nucleo.unidades import canonica
        cols = self.d.registro.columnas
        if grupo == "CAL":
            res.columnas = [k for k in res.columnas if canonica(cols[k].unidad) not in UNIDADES_GAS]
        elif grupo in ("PHIN", "PHID", "PHIS", "POR"):
            escala_pu = max(abs(c.escala_min), abs(c.escala_max)) > 1.5
            for k in res.columnas:
                d = cols[k].datos
                v = d[(d != NULO) & np.isfinite(d)]
                if v.size:
                    datos_pu = float(np.median(v)) > 1.5        # el mismo criterio que la plantilla (D109)
                    if datos_pu != escala_pu:
                        self.factores[(id(c), k)] = 0.01 if datos_pu else 100.0

    def datos_dibujo(self, k: int, c: CurvaPlantilla) -> np.ndarray:
        """Valores de la columna k como se dibujan con la curva c (con el factor de unidad de D112)."""
        d = self.d.registro.columnas[k].datos
        f = self.factores.get((id(c), k))
        return d if f is None else np.where(d == NULO, NULO, d * f)

    def escala(self, c: CurvaPlantilla) -> tuple[float, float]:
        """(mín., máx.) con que se dibuja la curva en este log plot."""
        return self.escalas.get(id(c), (c.escala_min, c.escala_max))

    def x_curva(self, valores, c: CurvaPlantilla, x0: float, ancho: float) -> np.ndarray:
        """Valores → x en píxeles (escala lineal o log10, invertida o no)."""
        vmin, vmax = self.escala(c)
        if c.invertida:
            vmin, vmax = vmax, vmin
        v = np.asarray(valores, dtype=float)
        if c.logaritmica:
            if vmin < 0 or vmax < 0 or vmin == 0 or vmax == 0:
                return np.zeros_like(v)
            with np.errstate(all="ignore"):
                lv = np.log10(np.where(v > 0, v, np.nan))
            out = x0 + (lv - math.log10(vmin)) / (math.log10(vmax) - math.log10(vmin)) * ancho
            return np.nan_to_num(out, nan=x0)
        if vmax == vmin:
            return np.full_like(v, x0)
        return (v - vmin) / (vmax - vmin) * ancho + x0

    def tamano(self) -> tuple[int, int]:
        return (int(self.ancho + 20), int(self.y0 + self.alto + 30))

    # ------------------------------------------------------------ dibujo
    def dibujar(self, p: QPainter) -> None:
        """Fondo, rellenos, curvas con rejillas, litología, completación y zonas."""
        w, h = self.tamano()
        p.fillRect(QRectF(0, 0, w, h), Qt.white)
        if not self.listo:
            p.setPen(Qt.red)
            p.drawText(QRectF(10, 10, max(w, 400), 40), Qt.AlignLeft,
                       "\n".join(self.mensajes) or tr("No data"))
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        self._titulo(p)
        for i, pista in enumerate(self.d.plantilla.pistas):
            self._cabecera(p, i, pista)
        self._rellenos(p)
        for i, pista in enumerate(self.d.plantilla.pistas):
            if pista.tipo == PISTA_CURVAS:
                self._curvas(p, i, pista)
            elif pista.tipo == PISTA_LITOLOGIA:
                self._litologia(p, pista)
            elif pista.tipo == PISTA_COMPLETACION:
                self._completacion(p, pista)
            self._borde(p, pista)
        self._eje_prof(p)
        self._zonas(p)
        t = self.d.plantilla
        if t.borde_visible:
            p.setPen(pluma(t.borde_color, t.borde_ancho, t.borde_tipo))
            p.setBrush(Qt.NoBrush)
            x0 = t.mas_a_la_izquierda()
            p.drawRect(QRectF(x0, self.y0, t.mas_a_la_derecha() - x0, self.alto))

    def imagen(self, zoom: float = 1.0) -> QImage:
        w, h = self.tamano()
        img = QImage(max(1, int(w * zoom)), max(1, int(h * zoom)), QImage.Format_ARGB32)
        img.fill(Qt.white)
        p = QPainter(img)
        p.scale(zoom, zoom)
        self.dibujar(p)
        p.end()
        return img

    # ------------------------------------------------------------ partes
    def _titulo(self, p: QPainter) -> None:
        t = self.d.plantilla
        if not t.mostrar_titulo:
            return
        texto = (t.formato_titulo
                 .replace("%WELLNAME%", self.d.nombre_pozo)
                 .replace("%LOGNAME%", self.d.registro.nombre if self.d.registro else "")
                 .replace("%LITHONAME%", self.d.litologia.nombre if self.d.litologia else "")
                 .replace("%COMPNAME%", self.d.completacion.nombre if self.d.completacion else ""))
        p.setPen(Qt.black)
        p.setFont(QFont("Arial", 12, QFont.Bold))
        p.drawText(QRectF(0, 4, self.ancho, 22), Qt.AlignHCenter | Qt.AlignVCenter, texto)
        p.setPen(QPen(QColor(150, 150, 150), 1))
        p.drawLine(QPointF(0, 30), QPointF(self.ancho, 30))

    def _cabecera(self, p: QPainter, i: int, pista) -> None:
        """Una línea por curva sobre la pista: 'min NOMBRE max' en el color de la curva."""
        if pista.tipo != PISTA_CURVAS:
            return
        f = QFont("Arial", max(6, pista.tam_fuente_cabecera - 1))
        p.setFont(f)
        fila = pista.tam_fuente_cabecera + 8.0
        for j, c in enumerate(pista.curvas):
            y = self.y0 - 6 - (j + 1) * fila   # la curva 1 queda junto a la pista
            if y < 32:
                continue
            col = qcolor(c.color)
            p.setPen(col)
            lo, hi = self.escala(c)
            izq, der = (hi, lo) if c.invertida else (lo, hi)
            caja = QRectF(pista.x, y, pista.ancho, fila - 2)
            p.drawText(caja, Qt.AlignLeft | Qt.AlignBottom, "%g" % izq)
            p.drawText(caja, Qt.AlignHCenter | Qt.AlignBottom, c.nombre_x)
            p.drawText(caja, Qt.AlignRight | Qt.AlignBottom, "%g" % der)
            p.setPen(pluma(c.color, 1, c.tipo_linea))
            p.drawLine(QPointF(pista.x, y + fila - 1), QPointF(pista.x + pista.ancho, y + fila - 1))

    def _borde(self, p: QPainter, pista) -> None:
        if pista.borde_visible:
            p.setPen(pluma(pista.borde_color, pista.borde_ancho, pista.borde_tipo))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(pista.x, self.y0, pista.ancho, self.alto))

    def _rejilla(self, p: QPainter, pista, c: CurvaPlantilla) -> None:
        """Líneas menores y mayores en X (unidades de la curva) y en Y (profundidad)."""
        x0, x1, y0, y1 = pista.x, pista.x + pista.ancho, self.y0, self.y0 + self.alto
        rx, ry = c.rejilla_x, c.rejilla_y
        p.setFont(QFont(rx.macro_fuente, rx.macro_tam))
        # X
        vmin, vmax = sorted(self.escala(c))
        for micro in (True, False):
            visible = rx.micro_visible if micro else rx.macro_visible
            if not visible:
                continue
            color, ancho, tipo = ((rx.micro_color, rx.micro_ancho, rx.micro_tipo) if micro
                                  else (rx.macro_color, rx.macro_ancho, rx.macro_tipo))
            p.setPen(pluma(color, ancho, tipo))
            for v in self._ticks_x(c, vmin, vmax, micro):
                x = float(self.x_curva([v], c, pista.x, pista.ancho)[0])
                if x0 - 0.5 <= x <= x1 + 0.5:
                    p.drawLine(QPointF(x, y0), QPointF(x, y1))
        # Y
        for micro in (True, False):
            visible = ry.micro_visible if micro else ry.macro_visible
            paso = ry.micro_paso if micro else ry.macro_paso
            if not visible or paso <= 0:
                continue
            color, ancho, tipo = ((ry.micro_color, ry.micro_ancho, ry.micro_tipo) if micro
                                  else (ry.macro_color, ry.macro_ancho, ry.macro_tipo))
            p.setPen(pluma(color, ancho, tipo))
            d = math.ceil(self.prof_min / paso) * paso
            while d <= self.prof_max:
                y = self.prof_a_y(d)
                p.drawLine(QPointF(x0, y), QPointF(x1, y))
                d += paso

    def _ticks_x(self, c: CurvaPlantilla, vmin: float, vmax: float, micro: bool):
        """Desde el mínimo, avanzar hasta antes del máximo (los bordes no se repiten)."""
        out = []
        if c.logaritmica:
            if vmin <= 0 or vmax <= 0:
                return out
            v = vmin
            siguiente = siguiente_micro_log if micro else siguiente_macro_log
            for _ in range(1000):
                v = siguiente(v)
                if v <= 0 or v >= vmax:
                    break
                out.append(v)
            return out
        paso = c.rejilla_x.micro_paso if micro else c.rejilla_x.macro_paso
        if id(c) in self.escalas and paso > 0:      # escala automática: las mismas divisiones de la plantilla
            lo, hi = sorted((c.escala_min, c.escala_max))
            paso *= (vmax - vmin) / (hi - lo) if hi > lo else 1.0
        if paso <= 0:
            return out
        v = vmin
        while len(out) < 2000:
            v += paso
            if v >= vmax - 1e-9 * abs(paso):
                break
            out.append(v)
        return out

    def _clip(self, p: QPainter, pista) -> None:
        p.setClipRect(QRectF(pista.x, self.y0, pista.ancho, self.alto))

    def _curvas(self, p: QPainter, i: int, pista) -> None:
        prof = self.prof_registro()
        self._clip(p, pista)
        for j, c in enumerate(pista.curvas):
            self._rejilla(p, pista, c)
            res = self.curvas.get((i, j))
            if prof is None or res is None:
                continue
            ys = valor_a_px_vec(prof, self.prof_min, self.prof_max, self.alto, self.y0)
            for k in res.columnas:
                if "dl" in self.d.capas:
                    self._banda_dl(p, k, c, pista, ys)
                if "original" in self.d.capas:
                    self._original(p, k, c, pista, ys)
            p.setPen(pluma(c.color, c.ancho, c.tipo_linea))
            p.setBrush(Qt.NoBrush)
            for k in res.columnas:
                xs = self.x_curva(self.datos_dibujo(k, c), c, pista.x, pista.ancho)
                # se unen todas las muestras, también los nulos (quedan fuera del clip)
                camino = QPainterPath()
                if len(xs):
                    camino.moveTo(xs[0], ys[0])
                    for x, y in zip(xs[1:], ys[1:]):
                        camino.lineTo(x, y)
                p.drawPath(camino)
            if "qc" in self.d.capas:
                for k in res.columnas:
                    self._banderas(p, k, c, pista, ys)
        p.setClipping(False)

    # ------------------------------------------------------------ capas opcionales (v0.3)
    def _banderas(self, p: QPainter, k: int, c: CurvaPlantilla, pista, ys) -> None:
        """Muestras dudosas de QC: punto rojo sobre la curva y marca en el borde derecho de la pista."""
        from ..nucleo import qc
        reg = self.d.registro
        try:
            malas = qc.dudosas(reg, k, self.d.alias)
        except (IndexError, ValueError):
            return
        if not malas.any():
            return
        xs = self.x_curva(self.datos_dibujo(k, c), c, pista.x, pista.ancho)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(220, 30, 30, 200))
        x_borde = pista.x + pista.ancho - 5
        for i in np.where(malas)[0]:
            p.drawEllipse(QPointF(xs[i], ys[i]), 1.8, 1.8)
            p.drawRect(QRectF(x_borde, ys[i] - 0.8, 4, 1.6))

    def _banda_dl(self, p: QPainter, k: int, c: CurvaPlantilla, pista, ys) -> None:
        """Banda predicción ± desviación (MC dropout) si existen <curva>_DL y <curva>_DL_STD."""
        reg = self.d.registro
        nombre = reg.columnas[k].nombre
        base = nombre[:-5] if nombre.upper().endswith("_FILL") else nombre[:-3] if nombre.upper().endswith("_DL")             else nombre
        i_m, i_s = reg.indice_columna(base + "_DL"), reg.indice_columna(base + "_DL_STD")
        if i_m < 0 or i_s < 0:
            return
        m, s = reg.columnas[i_m].datos, reg.columnas[i_s].datos
        ok = (m != NULO) & (s != NULO) & np.isfinite(m) & np.isfinite(s)
        if ok.sum() < 2:
            return
        izq = self.x_curva(np.where(ok, m - s, np.nan), c, pista.x, pista.ancho)
        der = self.x_curva(np.where(ok, m + s, np.nan), c, pista.x, pista.ancho)
        color = qcolor(c.color)
        color.setAlpha(60)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        idx = np.where(ok)[0]
        cortes = np.where(np.diff(idx) > 1)[0] + 1
        for tramo in np.split(idx, cortes):
            if len(tramo) < 2:
                continue
            poli = QPolygonF([QPointF(izq[i], ys[i]) for i in tramo] + [QPointF(der[i], ys[i]) for i in tramo[::-1]])
            p.drawPolygon(poli)

    def _original(self, p: QPainter, k: int, c: CurvaPlantilla, pista, ys) -> None:
        """Curva original (antes de la primera edición), discontinua y gris, debajo de la actual."""
        from ..nucleo import historial
        reg = self.d.registro
        o = historial.original(reg, reg.columnas[k].nombre)
        if o is None:
            return
        if len(o.datos) == len(ys):
            ys_o = ys
        elif o.prof is not None and len(o.prof) == len(o.datos) and self.d.modo == MODO_MD:
            ys_o = valor_a_px_vec(o.prof, self.prof_min, self.prof_max, self.alto, self.y0)
        else:
            return
        xs = self.x_curva(o.datos, c, pista.x, pista.ancho)
        ok = (np.asarray(o.datos) != NULO) & np.isfinite(xs)
        pen = QPen(QColor(120, 120, 120), max(c.ancho, 1))
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        camino = QPainterPath()
        nuevo = True
        for i in range(len(xs)):
            if not ok[i]:
                nuevo = True
                continue
            if nuevo:
                camino.moveTo(xs[i], ys_o[i])
                nuevo = False
            else:
                camino.lineTo(xs[i], ys_o[i])
        p.drawPath(camino)

    def _borde_area(self, pista, nombre: str) -> np.ndarray | None:
        prof = self.prof_registro()
        n = len(prof) if prof is not None else 0
        if nombre == BORDE_IZQ:
            return np.full(n, pista.x)
        if nombre == BORDE_DER:
            return np.full(n, pista.x + pista.ancho)
        r = self.d.registro
        for c in pista.curvas:
            if c.nombre_x == nombre and r is not None:
                k = r.indice_columna(nombre)
                if k >= 0:
                    return self.x_curva(self.datos_dibujo(k, c), c, pista.x, pista.ancho)
        if r is not None and r.indice_columna(nombre) >= 0:
            c = pista.curvas[0] if pista.curvas else CurvaPlantilla()
            return self.x_curva(r.columna(nombre).datos, c, pista.x, pista.ancho)
        return None

    def _rellenos(self, p: QPainter) -> None:
        """Polígonos entre borde izquierdo y derecho donde izq < der."""
        prof = self.prof_registro()
        if prof is None:
            return
        ys = valor_a_px_vec(prof, self.prof_min, self.prof_max, self.alto, self.y0)
        for pista in self.d.plantilla.pistas:
            if pista.tipo != PISTA_CURVAS:
                continue
            self._clip(p, pista)
            for a in pista.areas:
                izq, der = self._borde_area(pista, a.curva_izq), self._borde_area(pista, a.curva_der)
                if izq is None or der is None:
                    continue
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(qcolor(a.color)))
                for poli in poligonos_relleno(ys, izq, der):
                    p.drawPolygon(poli)
            p.setClipping(False)

    def _litologia(self, p: QPainter, pista) -> None:
        lit = self.d.litologia
        if lit is None:
            return
        self._clip(p, pista)
        ancho = min(pista.ancho_lito, pista.ancho)
        for it in lit.intervalos:
            yt, yb = self.prof_a_y(self.a_prof_vista(it.tope)), self.prof_a_y(self.a_prof_vista(it.base))
            caja = QRectF(pista.x, yt, ancho, yb - yt)
            p.setPen(QPen(Qt.black, 1))
            p.setBrush(patron_litologia(it.tipo, self.d.base_lito))
            p.drawRect(caja)
            if pista.ancho > ancho + 10:
                p.setPen(Qt.black)
                p.setFont(QFont("Arial", 8, QFont.Bold))
                nombre = it.comentario
                if self.d.base_lito is not None and self.d.base_lito.tipo(it.tipo):
                    nombre = self.d.base_lito.tipo(it.tipo).nombre
                p.drawText(QRectF(pista.x + ancho + 3, yt + 1, pista.ancho - ancho - 4, max(12.0, yb - yt)),
                           Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, nombre)
        p.setClipping(False)

    def _completacion(self, p: QPainter, pista) -> None:
        comp = self.d.completacion
        if comp is None:
            return
        self._clip(p, pista)
        ancho = min(pista.ancho_comp, pista.ancho)
        cx = pista.x + ancho / 2
        base = self.d.base_herr
        od_max = 1.0
        if base is not None:
            ods = [base.item(h.nombre_herramienta).od for h in comp.herramientas
                   if base.item(h.nombre_herramienta)]
            od_max = max(ods, default=1.0) or 1.0
        ultimo_y = -1e9
        for h in sorted(comp.herramientas, key=lambda h: (h.tope, h.base)):
            yt = self.prof_a_y(self.a_prof_vista(h.tope))
            yb = self.prof_a_y(self.a_prof_vista(h.base))
            item = base.item(h.nombre_herramienta) if base is not None else None
            cat = base.categoria(item.categoria) if (base is not None and item) else None
            od = (item.od if item else od_max * 0.6) / od_max * (ancho / 2 - 4)
            dibujar_herramienta(p, cat.nombre if cat else h.nombre_herramienta, cx, yt, yb, od)
            if pista.ancho > ancho + 10 and h.comentario:
                ym = (yt + yb) / 2 if yb - yt < 40 else yt + 12
                ym = max(ym, ultimo_y + 14)          # evita encimar etiquetas
                ultimo_y = ym
                p.setPen(QPen(Qt.black, 1))
                p.drawLine(QPointF(cx + od + 2, ym), QPointF(pista.x + ancho + 8, ym))
                p.setFont(QFont("Arial", 8, QFont.Bold))
                p.drawText(QRectF(pista.x + ancho + 10, ym - 7, pista.ancho - ancho - 10, 40),
                           Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, h.comentario)
        p.setClipping(False)

    def _eje_prof(self, p: QPainter) -> None:
        """Etiquetas de profundidad en el margen izquierdo (rejilla Y mayor de la 1.ª curva)."""
        t = self.d.plantilla
        paso = 100.0
        for pista in t.pistas:
            if pista.curvas:
                paso = pista.curvas[0].rejilla_y.macro_paso or paso
                break
        x0 = t.mas_a_la_izquierda()
        p.setPen(Qt.black)
        p.setFont(QFont("Arial", 8))
        d = math.ceil(self.prof_min / paso) * paso
        while d <= self.prof_max:
            y = self.prof_a_y(d)
            p.drawText(QRectF(0, y - 7, x0 - 4, 14), Qt.AlignRight | Qt.AlignVCenter, "%g" % d)
            d += paso
        p.save()
        p.translate(10, self.y0 + min(self.alto, 300) / 2)
        p.rotate(-90)
        r = self.d.registro
        unidad = r.columnas[self.col_prof].unidad.strip() if r is not None and r.existe_columna(self.col_prof) else ""
        if not unidad:      # sin unidad en el archivo: la de User Settings (D98)
            from ..nucleo import preferencias
            unidad = preferencias.actual().unidad_prof
        p.drawText(QRectF(-60, -8, 120, 16), Qt.AlignCenter, f"{NOMBRES_MODO.get(self.d.modo, '')} ({unidad.lower()})")
        p.restore()

    def _zonas(self, p: QPainter) -> None:
        t = self.d.plantilla
        x0, x1 = t.mas_a_la_izquierda(), t.mas_a_la_derecha()
        for z, md in self.d.zonas:
            prof = self.a_prof_vista(md)
            if prof == NULO or not (self.prof_min <= prof <= self.prof_max):
                continue
            y = self.prof_a_y(prof)
            p.setPen(pluma(z.color, z.ancho, z.tipo_linea))
            p.drawLine(QPointF(x0, y), QPointF(x1, y))
            if t.zona_nombre_visible:
                p.setPen(pluma(z.color, z.ancho, z.tipo_linea))
                p.setFont(QFont("Arial", 8, QFont.Bold))
                p.setFont(QFont("Arial", 11, QFont.Bold))
                if t.zona_nombre_posicion == 1:
                    ancho_txt = p.fontMetrics().horizontalAdvance(z.nombre)
                    p.drawLine(QPointF(x1, y), QPointF(x1 + t.zona_nombre_ancho - ancho_txt - 6, y))
                    p.setPen(qcolor(z.color))
                    p.drawText(QRectF(x1, y - 9, t.zona_nombre_ancho - 2, 18),
                               Qt.AlignRight | Qt.AlignVCenter, z.nombre)
                else:
                    p.drawText(QRectF(x0 + 2, y - 16, t.zona_nombre_ancho, 14), Qt.AlignLeft, z.nombre)


# ------------------------------------------------------------------ auxiliares
def siguiente_macro_log(x: float) -> float:
    """Menor 10^k (k=-20..20) mayor que x."""
    for k in range(-20, 21):
        if x < 10.0 ** k:
            return 10.0 ** k
    return 0.0


def anterior_macro_log(x: float) -> float:
    for k in range(20, -21, -1):
        if 10.0 ** k <= x * 1.0000001:
            return 10.0 ** k
    return 0.0


def siguiente_micro_log(x: float) -> float:
    """Menor k·10^⌊log x⌋ (k = 2…10) mayor que 1.01·x."""
    base = anterior_macro_log(x)
    for k in range(2, 11):
        if x * 1.01 < k * base:
            return k * base
    return base + base


def valor_a_px_vec(v, vmin, vmax, longitud, origen) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    if vmax == vmin:
        return np.full_like(v, origen)
    return (v - vmin) / (vmax - vmin) * longitud + origen


def poligonos_relleno(ys, izq, der) -> list[QPolygonF]:
    """Tramos contiguos donde izq < der, cerrados por la derecha y la izquierda.

    En los cruces se interpola el punto de intersección para que el relleno no tenga escalones."""
    polis = []
    n = len(ys)
    i = 0
    while i < n:
        if not izq[i] < der[i]:
            i += 1
            continue
        ini = i
        while i < n and izq[i] < der[i]:
            i += 1
        fin = i  # exclusivo
        pts_d, pts_i = [], []
        if ini > 0:
            yc = _cruce(ys[ini - 1], ys[ini], izq[ini - 1] - der[ini - 1], izq[ini] - der[ini])
            xc = izq[ini - 1] + (izq[ini] - izq[ini - 1]) * _frac(ys[ini - 1], ys[ini], yc)
            pts_d.append(QPointF(xc, yc))
        for k in range(ini, fin):
            pts_d.append(QPointF(der[k], ys[k]))
        if fin < n:
            yc = _cruce(ys[fin - 1], ys[fin], izq[fin - 1] - der[fin - 1], izq[fin] - der[fin])
            xc = izq[fin - 1] + (izq[fin] - izq[fin - 1]) * _frac(ys[fin - 1], ys[fin], yc)
            pts_d.append(QPointF(xc, yc))
        for k in range(fin - 1, ini - 1, -1):
            pts_i.append(QPointF(izq[k], ys[k]))
        polis.append(QPolygonF(pts_d + pts_i))
    return polis


def _cruce(y0, y1, d0, d1):
    if d1 == d0:
        return y1
    return y0 + (y1 - y0) * (d0 / (d0 - d1))


def _frac(y0, y1, y):
    return 0.0 if y1 == y0 else (y - y0) / (y1 - y0)


def nombre_litologia(tipo: int, base: BaseLitologia | None = None) -> str:
    """Nombre del tipo en la base del usuario o, si no está, en la base propia por defecto."""
    t = base.tipo(tipo) if base is not None else None
    if t is None:
        t = litologias_por_defecto().tipo(tipo)
    return t.nombre if t is not None else ""


def color_litologia(tipo: int, base: BaseLitologia | None = None) -> QColor:
    return color_patron(nombre_litologia(tipo, base))


def patron_litologia(tipo: int, base: BaseLitologia | None = None) -> QBrush:
    """Patrón estándar (FGDC/USGS) elegido por el nombre del tipo; ver patrones_lito.py."""
    return brocha_patron(nombre_litologia(tipo, base))


def imagen_litologia(tipo: int, base: BaseLitologia | None = None) -> QImage:
    """Muestra del patrón (icono del editor de litología), con la misma regla que el Log Plot."""
    from .patrones_lito import imagen_patron
    return imagen_patron(nombre_litologia(tipo, base))


def dibujar_herramienta(p: QPainter, categoria: str, cx: float, yt: float, yb: float, r: float):
    """Esquema propio de cada categoría de herramienta de completación."""
    cat = categoria.lower()
    p.setBrush(Qt.NoBrush)
    if "cement" in cat:
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(170, 170, 170), Qt.Dense4Pattern))
        p.drawRect(QRectF(cx - r - 6, yt, 6, yb - yt))
        p.drawRect(QRectF(cx + r, yt, 6, yb - yt))
    elif "perfo" in cat:
        p.setPen(QPen(QColor(200, 0, 0), 2))
        y = yt
        while y <= yb:
            p.drawLine(QPointF(cx + r, y), QPointF(cx + r + 10, y))
            p.drawLine(QPointF(cx - r, y), QPointF(cx - r - 10, y))
            y += 4
    elif "packer" in cat or "plug" in cat:
        p.setPen(QPen(Qt.black, 1))
        p.setBrush(QBrush(QColor(60, 60, 60) if "packer" in cat else QColor(120, 70, 30)))
        p.drawRect(QRectF(cx - r, yt, 2 * r, max(2.0, yb - yt)))
    elif "shoe" in cat:
        p.setPen(QPen(Qt.black, 1))
        p.setBrush(QBrush(Qt.black))
        for s in (-1, 1):
            p.drawPolygon(QPolygonF([QPointF(cx + s * r, yb), QPointF(cx + s * (r + 6), yb),
                                     QPointF(cx + s * r, yb - 8)]))
    elif "head" in cat:
        p.setPen(QPen(Qt.black, 1))
        p.setBrush(QBrush(QColor(90, 90, 160)))
        p.drawRect(QRectF(cx - r - 4, yt, 2 * r + 8, max(4.0, yb - yt)))
    elif "open" in cat:
        p.setPen(QPen(QColor(120, 80, 40), 1, Qt.DashLine))
        p.drawLine(QPointF(cx - r, yt), QPointF(cx - r, yb))
        p.drawLine(QPointF(cx + r, yt), QPointF(cx + r, yb))
    elif "tubing" in cat:
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(cx - r, 0, cx + r, 0)
        g.setColorAt(0, QColor(90, 90, 90))
        g.setColorAt(0.5, QColor(235, 235, 235))
        g.setColorAt(1, QColor(90, 90, 90))
        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(cx - r, yt, 2 * r, yb - yt))
    else:   # casing y otros: dos paredes
        grosor = 3
        p.setPen(QPen(QColor(40, 40, 40), grosor))
        p.drawLine(QPointF(cx - r, yt), QPointF(cx - r, yb))
        p.drawLine(QPointF(cx + r, yt), QPointF(cx + r, yb))


def datos_desde_proyecto(pr, i_logplot: int, base_lito=None, base_herr=None, alias=None,
                         plantilla_por_defecto: Plantilla | None = None, capas=frozenset()) -> DatosLogPlot:
    """Arma los datos de un log plot guardado en setting.ini (LogPlot del proyecto)."""
    lp = pr.logplots[i_logplot]
    pozo = pr.pozos[lp.pozo] if 0 <= lp.pozo < len(pr.pozos) else None
    sel = lambda lista, i: lista[i] if pozo is not None and 0 <= i < len(lista) else None  # noqa: E731
    plantilla = (pr.plantillas[lp.plantilla] if 0 <= lp.plantilla < len(pr.plantillas)
                 else plantilla_por_defecto or Plantilla())
    zonas = []
    if pozo is not None:
        ip = pr.pozos.index(pozo)
        for k, z in enumerate(pr.zonas):
            visible = lp.zonas_visibles[k] if k < len(lp.zonas_visibles) else True
            if visible:
                zonas.append((z, z.prof(ip)))
    return DatosLogPlot(
        plantilla=plantilla, registro=sel(pozo.logs, lp.las) if pozo else None,
        trayectoria=pozo.trayectoria if pozo else None,
        litologia=sel(pozo.litologias, lp.lito) if pozo else None,
        completacion=sel(pozo.completaciones, lp.comp) if pozo else None,
        zonas=zonas, modo=lp.modo_prof,
        prof_propia=(lp.prof_tope, lp.prof_base) if lp.usar_prof_propia else None,
        escala_propia=lp.escala if lp.usar_escala_propia else None,
        nombre_pozo=pozo.nombre if pozo else "", base_lito=base_lito, base_herr=base_herr,
        alias=alias, capas=frozenset(capas), ocultar_vacias=lp.ocultar_vacias)
