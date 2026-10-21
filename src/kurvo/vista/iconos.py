"""Iconos propios dibujados por código (sin recursos de terceros).

Sistema visual:
- Rejilla de 24 × 24 unidades, trazo de 1,6 con extremos y uniones redondeadas; se dibujan a
  16, 24, 32 y 48 px para que se vean nítidos en cualquier tamaño.
- Tinta pizarra para la forma base y un color de acento por familia, para reconocer de un vistazo
  el tipo de herramienta: azul = archivo/proyecto, naranja = edición, verde = calidad y validación,
  violeta = análisis y modelos, verde azulado = pozos y datos, rojo = cerrar/salir/avisos.
- Metáforas: se usan las convenciones conocidas (disquete para guardar, flecha curva para
  deshacer, impresora, interrogación) y, en las herramientas propias del dominio, la curva de
  registro (una línea vertical ondulada) como elemento común, de modo que "curva + lápiz" es
  editar la curva, "curva + flechas verticales" es desplazarla en profundidad, etc.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

TINTA = QColor("#2b3a4a")
AZUL = QColor("#1e6fd9")
NARANJA = QColor("#e07b00")
VERDE = QColor("#2e9e5b")
VIOLETA = QColor("#7b4fd1")
TEAL = QColor("#0f9a9a")
ROJO = QColor("#d23f3f")
PAPEL = QColor("#ffffff")
SOMBRA = QColor("#e9eef4")
TAMANOS = (16, 24, 32, 48)


class Lienzo:
    """Ayudante de dibujo en coordenadas de rejilla 24 × 24."""

    def __init__(self, p: QPainter, lado: int):
        self.p = p
        self.k = lado / 24.0
        p.setRenderHint(QPainter.Antialiasing, True)
        p.scale(self.k, self.k)

    def pluma(self, color=TINTA, ancho=1.6, estilo=Qt.SolidLine):
        pen = QPen(color, ancho, estilo, Qt.RoundCap, Qt.RoundJoin)
        self.p.setPen(pen)
        return pen

    def relleno(self, color=None):
        self.p.setBrush(QBrush(color) if color is not None else Qt.NoBrush)

    def linea(self, *pts, color=TINTA, ancho=1.6):
        self.pluma(color, ancho)
        self.p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))

    def poligono(self, pts, color=TINTA, fondo=None, ancho=1.6):
        self.pluma(color, ancho)
        self.relleno(fondo)
        self.p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))

    def rect(self, x, y, w, h, color=TINTA, fondo=None, r=1.5, ancho=1.6):
        self.pluma(color, ancho)
        self.relleno(fondo)
        self.p.drawRoundedRect(QRectF(x, y, w, h), r, r)

    def circulo(self, cx, cy, r, color=TINTA, fondo=None, ancho=1.6):
        self.pluma(color, ancho)
        self.relleno(fondo)
        self.p.drawEllipse(QPointF(cx, cy), r, r)

    def punto(self, cx, cy, r=1.1, color=TINTA):
        self.p.setPen(Qt.NoPen)
        self.relleno(color)
        self.p.drawEllipse(QPointF(cx, cy), r, r)

    def arco(self, cx, cy, r, inicio, barrido, color=TINTA, ancho=1.6):
        self.pluma(color, ancho)
        self.relleno(None)
        self.p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(inicio * 16), int(barrido * 16))

    def texto(self, x, y, w, h, t, color=TINTA, tam=5.5, negrita=True):
        self.p.setPen(color)
        f = QFont("Arial")
        f.setPointSizeF(tam)
        f.setBold(negrita)
        self.p.setFont(f)
        self.p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, t)

    def flecha(self, x0, y0, x1, y1, color=TINTA, ancho=1.6, punta=3.0):
        self.linea((x0, y0), (x1, y1), color=color, ancho=ancho)
        a = math.atan2(y1 - y0, x1 - x0)
        for s in (1, -1):
            self.linea((x1, y1), (x1 - punta * math.cos(a + s * 0.6), y1 - punta * math.sin(a + s * 0.6)),
                       color=color, ancho=ancho)

    # ------------------------------------------------------------ elementos de dominio
    def curva(self, x, y0, y1, amp=2.2, color=AZUL, ancho=1.6, fase=0.0):
        """Curva de registro vertical (el elemento común de las herramientas de curvas)."""
        path = QPainterPath()
        n = 24
        for i in range(n + 1):
            t = i / n
            y = y0 + (y1 - y0) * t
            xx = x + amp * (math.sin(t * 9.5 + fase) * 0.7 + math.sin(t * 23 + fase) * 0.3)
            path.moveTo(xx, y) if i == 0 else path.lineTo(xx, y)
        self.pluma(color, ancho)
        self.relleno(None)
        self.p.drawPath(path)

    def documento(self, x=5, y=2.5, w=13, h=19, fondo=PAPEL, color=TINTA, doblez=4):
        self.poligono([(x, y), (x + w - doblez, y), (x + w, y + doblez), (x + w, y + h), (x, y + h)], color, fondo)
        self.linea((x + w - doblez, y), (x + w - doblez, y + doblez), (x + w, y + doblez), color=color, ancho=1.2)

    def carpeta(self, abierta=False, color=AZUL):
        if abierta:
            self.poligono([(2.5, 6), (9, 6), (11, 8), (19, 8), (19, 10), (6, 10), (3.5, 19.5), (2.5, 19.5)],
                          TINTA, SOMBRA)
            self.poligono([(6, 10), (21.5, 10), (18.5, 19.5), (3.5, 19.5)], TINTA, color.lighter(165))
        else:
            self.poligono([(2.5, 5.5), (9, 5.5), (11, 7.5), (21.5, 7.5), (21.5, 19.5), (2.5, 19.5)],
                          TINTA, color.lighter(165))

    def disquete(self, color=AZUL):
        self.poligono([(3.5, 3.5), (17, 3.5), (20.5, 7), (20.5, 20.5), (3.5, 20.5)], TINTA, color.lighter(170))
        self.rect(7, 3.5, 9, 5.5, TINTA, PAPEL, r=0.5, ancho=1.3)
        self.rect(13, 4.6, 1.8, 3.2, TINTA, TINTA, r=0.2, ancho=0.6)
        self.rect(6.5, 12.5, 11, 8, TINTA, PAPEL, r=0.5, ancho=1.3)

    def lapiz(self, x, y, largo=9, color=NARANJA):
        """Lápiz a 45° con la punta en (x, y)."""
        d = largo / math.sqrt(2)
        a = 1.6
        self.poligono([(x, y), (x + 1.2, y - 3.2 + 0.5), (x + d + a, y - d + a - 3.2 + 0.5 + 1.2 - 1.2),
                       (x + d + a - 2.0, y - d - a), (x + 3.2 - 0.5, y - 1.2)], TINTA, color, ancho=1.2)
        self.linea((x + 1.6, y - 3.6), (x + 3.6, y - 1.6), ancho=1.0)

    def base_datos(self, color=TEAL):
        self.pluma(TINTA, 1.5)
        self.relleno(color.lighter(170))
        self.p.drawRect(QRectF(4, 5.5, 16, 13))
        self.p.drawEllipse(QRectF(4, 15.5, 16, 5.5))
        self.pluma(color.lighter(170), 2.0)
        self.p.drawLine(QPointF(4.9, 18), QPointF(19.1, 18))
        self.pluma(TINTA, 1.5)
        self.relleno(None)
        self.p.drawArc(QRectF(4, 15.5, 16, 5.5), 180 * 16, 180 * 16)
        self.relleno(color.lighter(120))
        self.p.drawEllipse(QRectF(4, 3, 16, 5.5))

    def insignia(self, cx, cy, color, simbolo: str):
        """Círculo de color con un símbolo blanco (✓, ×, !, +, engranaje...)."""
        self.circulo(cx, cy, 4.6, PAPEL, color, ancho=1.2)
        b = PAPEL
        if simbolo == "check":
            self.linea((cx - 2.3, cy + 0.1), (cx - 0.6, cy + 1.9), (cx + 2.4, cy - 1.8), color=b, ancho=1.6)
        elif simbolo == "x":
            self.linea((cx - 1.8, cy - 1.8), (cx + 1.8, cy + 1.8), color=b, ancho=1.6)
            self.linea((cx - 1.8, cy + 1.8), (cx + 1.8, cy - 1.8), color=b, ancho=1.6)
        elif simbolo == "!":
            self.linea((cx, cy - 2.4), (cx, cy + 0.6), color=b, ancho=1.7)
            self.punto(cx, cy + 2.4, 0.9, b)
        elif simbolo == "+":
            self.linea((cx - 2.2, cy), (cx + 2.2, cy), color=b, ancho=1.6)
            self.linea((cx, cy - 2.2), (cx, cy + 2.2), color=b, ancho=1.6)
        elif simbolo == "gear":
            for i in range(8):
                a = i * math.pi / 4
                self.linea((cx + 1.6 * math.cos(a), cy + 1.6 * math.sin(a)),
                           (cx + 3.0 * math.cos(a), cy + 3.0 * math.sin(a)), color=b, ancho=1.2)
            self.circulo(cx, cy, 1.7, b, color, ancho=1.2)
        elif simbolo == "down":
            self.flecha(cx, cy - 2.6, cx, cy + 2.4, b, 1.5, 2.0)
        elif simbolo == "up":
            self.flecha(cx, cy + 2.6, cx, cy - 2.4, b, 1.5, 2.0)
        elif simbolo == "play":
            self.poligono([(cx - 1.4, cy - 2.4), (cx + 2.4, cy), (cx - 1.4, cy + 2.4)], b, b, ancho=0.8)


# ====================================================================== iconos
def _abrir(c):
    c.carpeta(abierta=True)
    c.flecha(15, 15.5, 15, 3.5, AZUL, 1.8, 3.0)


def _guardar(c):
    c.disquete()


def _guardar_como(c):
    c.disquete()
    c.p.save()
    c.p.translate(0.5, 0.5)
    c.lapiz(12.5, 21.5, 10)
    c.p.restore()


def _cerrar_proyecto(c):
    c.carpeta()
    c.insignia(17.5, 16.5, ROJO, "x")


def _imprimir(c):
    c.rect(6.5, 3, 11, 6, TINTA, PAPEL, r=0.6)
    c.rect(2.5, 8.5, 19, 9, TINTA, SOMBRA, r=2)
    c.rect(6.5, 14, 11, 7.5, TINTA, PAPEL, r=0.6)
    c.linea((8.5, 17), (15.5, 17), ancho=1.1)
    c.linea((8.5, 19.2), (13.5, 19.2), ancho=1.1)
    c.punto(18.5, 11.5, 1.0, VERDE)


def _config_impresion(c):
    _imprimir(c)
    c.insignia(18, 18, AZUL, "gear")


def _ayuda(c):
    c.circulo(12, 12, 9.2, AZUL, AZUL.lighter(175))
    c.pluma(AZUL, 2.2)
    c.relleno(None)
    path = QPainterPath()
    path.moveTo(8.8, 9.6)
    path.cubicTo(8.8, 5.6, 15.4, 5.6, 15.3, 9.6)
    path.cubicTo(15.2, 12.2, 12, 11.8, 12, 14.4)
    c.p.drawPath(path)
    c.punto(12, 17.6, 1.4, AZUL)


def _acerca(c):
    c.circulo(12, 12, 9.2, AZUL, AZUL.lighter(175))
    c.punto(12, 7.6, 1.5, AZUL)
    c.linea((12, 11), (12, 17.2), color=AZUL, ancho=2.4)


def _diagnostico(c):
    c.documento(4, 2.5, 14, 19)
    for y in (8, 11, 14):
        c.linea((7, y), (14, y), ancho=1.1)
    c.insignia(17.5, 17.5, NARANJA, "!")


def _salir(c):
    c.rect(3.5, 3, 10, 18, TINTA, SOMBRA, r=0.8)
    c.punto(11, 12.5, 0.9)
    c.flecha(10, 12, 21, 12, ROJO, 1.9, 3.2)


def _deshacer(c):
    """Flecha que vuelve hacia atrás (convención de casi todas las aplicaciones)."""
    c.pluma(NARANJA, 2.2)
    c.relleno(None)
    path = QPainterPath()
    path.moveTo(19.5, 19)
    path.cubicTo(19.5, 11.5, 15.5, 8.5, 10, 8.5)
    path.lineTo(7.5, 8.5)
    c.p.drawPath(path)
    c.poligono([(3, 8.5), (8.6, 4.3), (8.6, 12.7)], NARANJA, NARANJA, ancho=1.0)


def _rehacer(c):
    c.p.translate(24, 0)
    c.p.scale(-1, 1)
    _deshacer(c)


def _historial(c):
    c.circulo(12.5, 12.5, 8, TINTA, PAPEL)
    c.linea((12.5, 8), (12.5, 12.5), (15.8, 14.6), color=NARANJA, ancho=1.8)
    c.arco(12.5, 12.5, 8, 160, 70, PAPEL, 3.2)
    c.poligono([(2.2, 9.6), (6.6, 9.4), (4.0, 13.0)], TINTA, TINTA, ancho=0.8)


def _edicion_grafica(c):
    c.rect(3, 2.5, 13, 19, TINTA, PAPEL, r=1)
    c.linea((9.5, 3.5), (9.5, 20.5), color=SOMBRA.darker(115), ancho=0.9)
    c.curva(9.5, 4, 20, 3.0)
    c.lapiz(14, 18.5, 10)


def _validar(c):
    c.documento(4, 2.5, 14, 19)
    for y in (8, 11, 14):
        c.linea((7, y), (14, y), ancho=1.1)
    c.insignia(17.5, 17.5, VERDE, "check")


def _remuestrear(c):
    # muestras irregulares a la izquierda → regulares a la derecha
    c.linea((4.5, 3), (4.5, 21), color=TINTA, ancho=1.3)
    for y in (4.5, 6, 10.5, 12, 13, 18.5):
        c.punto(4.5, y, 1.25, NARANJA)
    c.flecha(7.5, 12, 14, 12, TINTA, 1.6, 2.6)
    c.linea((18.5, 3), (18.5, 21), color=TINTA, ancho=1.3)
    for i in range(6):
        c.punto(18.5, 4.5 + i * 3, 1.25, VERDE)
        c.linea((16.5, 4.5 + i * 3), (17.4, 4.5 + i * 3), ancho=1.0)


def _mnemonicos(c):
    """Etiqueta con un nombre cualquiera → etiqueta con el nombre estándar."""
    c.poligono([(2.5, 3.5), (12, 3.5), (15, 7), (12, 10.5), (2.5, 10.5)], TINTA, SOMBRA, ancho=1.3)
    c.texto(2.5, 3.5, 10, 7, "ild", TINTA.lighter(160), 4.6, False)
    c.flecha(8, 11.5, 8, 14.5, TEAL, 1.4, 1.8)
    c.poligono([(4.5, 14.5), (16.5, 14.5), (20.5, 18), (16.5, 21.5), (4.5, 21.5)], TINTA, VERDE.lighter(165),
               ancho=1.3)
    c.texto(4.5, 14.5, 12, 7, "RD", TINTA, 5.0)


def _lote(c):
    for i, f in enumerate((SOMBRA, SOMBRA, PAPEL)):
        c.documento(3 + i * 2.5, 2 + i * 2, 11, 14, f)
    c.curva(13.5, 8.5, 18, 1.6, AZUL, 1.3)
    c.insignia(18, 18, VIOLETA, "play")


def _normalizar(c):
    def campana(cx, s, alto, color):
        path = QPainterPath()
        for i in range(41):
            x = 2 + i * 0.5
            y = 20 - alto * math.exp(-0.5 * ((x - cx) / s) ** 2)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        c.pluma(color, 1.7)
        c.relleno(None)
        c.p.drawPath(path)
    c.linea((2, 20.5), (22, 20.5), ancho=1.3)
    campana(8, 2.6, 13, TINTA.lighter(200))
    campana(15, 2.6, 13, VERDE)
    c.flecha(8.5, 5, 13.5, 5, VERDE, 1.4, 2.2)


def _desfase(c):
    c.curva(6.5, 3, 21, 2.2, TINTA)
    c.curva(15.5, 7, 21, 2.2, AZUL, fase=0)
    c.flecha(21, 12, 21, 5.5, NARANJA, 1.7, 2.4)
    c.flecha(21, 12, 21, 18.5, NARANJA, 1.7, 2.4)


def _reporte_qc(c):
    c.documento(4, 2.5, 14, 19)
    for i, h in enumerate((5, 8, 4)):
        c.rect(7 + i * 3, 16 - h, 2, h, TINTA, AZUL.lighter(150), r=0.3, ancho=0.9)
    c.linea((6.5, 16.6), (15.5, 16.6), ancho=1.0)
    c.insignia(17.5, 17.5, VERDE, "check")


def _deep_learning(c):
    """Red neuronal: tres capas de nodos conectadas."""
    capas = [(4.5, (6.5, 12, 17.5)), (12, (6.5, 12, 17.5)), (19.5, (9, 15))]
    for (x0, ys0), (x1, ys1) in zip(capas[:-1], capas[1:]):
        for y0 in ys0:
            for y1 in ys1:
                c.linea((x0, y0), (x1, y1), color=VIOLETA.lighter(140), ancho=0.9)
    for k, (x, ys) in enumerate(capas):
        for y in ys:
            c.circulo(x, y, 2.2, VIOLETA, PAPEL if k == 1 else VIOLETA.lighter(160), ancho=1.4)


def _archivo_con(etiqueta, color, entrada: bool):
    def f(c):
        c.documento(3.5, 2.5, 14, 19)
        c.rect(2, 12.5, 13, 6.5, color, color, r=1.2, ancho=0.8)
        c.texto(2, 12.5, 13, 6.5, etiqueta, PAPEL, 4.6)
        c.insignia(18, 7, TEAL if entrada else AZUL, "down" if entrada else "up")
    return f


def _carpeta_las(c):
    """Import LAS Folder: carpeta con la etiqueta LAS y la insignia de entrada."""
    c.carpeta()
    c.rect(4.5, 11, 13, 6.5, TEAL, TEAL, r=1.2, ancho=0.8)
    c.texto(4.5, 11, 13, 6.5, "LAS", PAPEL, 4.6)
    c.insignia(18, 7, TEAL, "down")


def _excel(c):
    c.documento(3.5, 2.5, 14, 19)
    c.rect(5.5, 8, 10, 10, TINTA, VERDE.lighter(175), r=0.3, ancho=1.0)
    for x in (8.8, 12.1):
        c.linea((x, 8), (x, 18), ancho=0.8)
    for y in (11.3, 14.6):
        c.linea((5.5, y), (15.5, y), ancho=0.8)
    c.insignia(18, 7, AZUL, "up")


def _log_parcial(c):
    c.rect(3, 2.5, 12, 19, TINTA, PAPEL, r=1)
    c.curva(9, 3.5, 20.5, 3.0, TINTA.lighter(220))
    c.p.save()
    c.p.setClipRect(QRectF(3, 8, 12, 8))
    c.curva(9, 3.5, 20.5, 3.0, AZUL, 1.8)
    c.p.restore()
    c.rect(2, 8, 14, 8, NARANJA, None, r=0.5, ancho=1.3)
    c.flecha(16.5, 12, 22, 12, NARANJA, 1.6, 2.4)


def _calculadora(c):
    c.rect(5, 2.5, 14, 19, TINTA, SOMBRA, r=2)
    c.rect(7.5, 5, 9, 4, TINTA, PAPEL, r=0.5, ancho=1.1)
    c.texto(7.5, 5, 9, 4, "f(x)", VIOLETA, 3.6)
    for i in range(3):
        for j in range(3):
            c.rect(7.5 + j * 3.2, 11 + i * 3.2, 2.4, 2.2, TINTA, PAPEL if (i, j) != (2, 2) else VIOLETA.lighter(150),
                   r=0.4, ancho=0.9)


def _combinar(c):
    c.documento(2.5, 2, 9, 11, PAPEL, doblez=3)
    c.documento(12.5, 2, 9, 11, PAPEL, doblez=3)
    c.linea((7, 13.5), (7, 15.5), (12, 18), color=TEAL, ancho=1.7)
    c.linea((17, 13.5), (17, 15.5), (12, 18), color=TEAL, ancho=1.7)
    c.flecha(12, 17.5, 12, 22, TEAL, 1.7, 2.4)


def _compuesto(c):
    """Composite Well Log: tres corridas (tramos de curva) que caen en un solo registro."""
    for i, col in enumerate((AZUL, VERDE, NARANJA)):
        c.rect(2.5 + i * 4, 2.5, 3, 7, col, col.lighter(170), r=0.6, ancho=0.9)
    c.flecha(8, 10.5, 8, 13.5, TEAL, 1.5, 2.0)
    c.rect(3, 14, 10, 8, TINTA, PAPEL, r=0.8, ancho=1.0)
    for i, col in enumerate((AZUL, VERDE, NARANJA)):
        c.linea((4.5 + i * 3.2, 15), (5.3 + i * 3.2, 17), (4.3 + i * 3.2, 19), (5.1 + i * 3.2, 21), color=col, ancho=1.2)
    c.insignia(18, 7, TEAL, "down")


def _agrupar(c):
    """Varios alias (etiquetas) unidos en un mismo grupo."""
    for i, (y, t) in enumerate(((3.5, "GR"), (9.8, "SGR"), (16.1, "CGR"))):
        c.poligono([(8.5, y), (18, y), (21.5, y + 2.2), (18, y + 4.4), (8.5, y + 4.4)], TINTA,
                   TEAL.lighter(170) if i == 0 else SOMBRA, ancho=1.2)
        c.texto(8.5, y, 10.5, 4.4, t, TINTA, 3.3)
    c.linea((6.5, 5.7), (3.5, 5.7), (3.5, 18.3), (6.5, 18.3), color=TEAL, ancho=1.6)
    c.linea((3.5, 12), (6.5, 12), color=TEAL, ancho=1.6)


def _base_litologia(c):
    c.base_datos(NARANJA)
    c.pluma(TINTA, 0.9)
    for y in (11, 14):
        c.p.drawLine(QPointF(4.8, y), QPointF(19.2, y))
    for x, y0 in ((8, 8.5), (14, 8.5), (11, 11), (17, 11), (8, 14), (14, 14)):
        c.p.drawLine(QPointF(x, y0 + (0 if y0 != 8.5 else 0.5)), QPointF(x, y0 + 2.5))


def _base_herramientas(c):
    """Base de datos + llave fija (catálogo de herramientas de completación)."""
    c.base_datos(TEAL)
    c.p.save()
    c.p.translate(12, 13)
    c.p.rotate(-45)
    c.rect(-1.1, -1, 2.2, 8, TINTA, PAPEL, r=1.0, ancho=1.2)
    path = QPainterPath()
    path.moveTo(-1.4, -0.6)
    path.lineTo(-3.4, -2.6)
    path.lineTo(-3.4, -5.2)
    path.lineTo(-1.6, -7)
    path.lineTo(-1.6, -4.2)
    path.lineTo(1.6, -4.2)
    path.lineTo(1.6, -7)
    path.lineTo(3.4, -5.2)
    path.lineTo(3.4, -2.6)
    path.lineTo(1.4, -0.6)
    path.closeSubpath()
    c.pluma(TINTA, 1.2)
    c.relleno(PAPEL)
    c.p.drawPath(path)
    c.p.restore()


def _complemento(c):
    path = QPainterPath()
    path.moveTo(4, 8)
    path.lineTo(9, 8)
    path.arcTo(QRectF(9, 4.5, 4.5, 4.5), 200, -220)
    path.lineTo(18, 8)
    path.lineTo(18, 12.5)
    path.arcTo(QRectF(17.5, 12.5, 4.5, 4.5), 110, -220)
    path.lineTo(18, 20)
    path.lineTo(4, 20)
    path.closeSubpath()
    c.pluma(TINTA, 1.5)
    c.relleno(VIOLETA.lighter(165))
    c.p.drawPath(path)


# ------------------------------------------------------------------ árbol y pestañas
def _pozos(c):
    c.poligono([(12, 2.5), (6.5, 20.5), (17.5, 20.5)], TINTA, None, 1.5)
    c.linea((8.6, 13.5), (15.4, 13.5), ancho=1.2)
    c.linea((10.2, 8.2), (13.8, 8.2), ancho=1.2)
    c.linea((8.6, 13.5), (13.8, 8.2), ancho=1.0)
    c.linea((4, 20.5), (20, 20.5), color=TEAL, ancho=2.0)


def _pozo(c):
    c.linea((3, 7), (21, 7), color=TEAL, ancho=1.8)
    c.rect(10, 3, 4, 4, TINTA, SOMBRA, r=0.4, ancho=1.2)
    c.linea((12, 7), (12, 21), color=TINTA, ancho=2.4)
    c.linea((9.5, 7), (9.5, 17), ancho=1.0)
    c.linea((14.5, 7), (14.5, 17), ancho=1.0)


def _registro(c):
    c.rect(4, 2.5, 16, 19, TINTA, PAPEL, r=1)
    c.linea((12, 2.5), (12, 21.5), color=SOMBRA.darker(115), ancho=0.9)
    c.curva(8, 4, 20, 2.2, VERDE, 1.4)
    c.curva(16, 4, 20, 2.2, AZUL, 1.4, fase=1.5)


def _completacion(c):
    c.linea((7, 3), (7, 21), ancho=1.8)
    c.linea((17, 3), (17, 21), ancho=1.8)
    c.linea((10, 3), (10, 17), color=TEAL, ancho=1.5)
    c.linea((14, 3), (14, 17), color=TEAL, ancho=1.5)
    c.rect(9, 13, 6, 2.5, TINTA, TINTA, r=0.4, ancho=0.8)
    for y in (18, 20):
        c.linea((4, y), (6.3, y), color=ROJO, ancho=1.2)
        c.linea((17.7, y), (20, y), color=ROJO, ancho=1.2)


def _litologia(c):
    from .patrones_lito import brocha_patron
    for i, (n, y) in enumerate((("Sandstone", 3), ("Shale", 9.5), ("Limestone", 16))):
        c.pluma(TINTA, 1.1)
        b = brocha_patron(n)
        tr = b.transform()
        tr.scale(0.25, 0.25)
        b.setTransform(tr)
        c.p.setBrush(b)
        c.p.drawRect(QRectF(5, y, 14, 6.5 if i < 2 else 5))


def _zonas(c):
    c.linea((5, 3), (5, 21), ancho=1.6)
    c.poligono([(5, 3.5), (16, 3.5), (13.5, 6.5), (16, 9.5), (5, 9.5)], TINTA, ROJO.lighter(150), 1.2)
    c.linea((5, 14.5), (20, 14.5), color=AZUL, ancho=1.8)
    c.linea((5, 19), (20, 19), color=VERDE, ancho=1.8)


def _plantillas(c):
    c.rect(2.5, 3, 19, 18, TINTA, PAPEL, r=1)
    for x in (8.8, 15.2):
        c.linea((x, 3), (x, 21), ancho=1.0)
    c.rect(2.5, 3, 19, 4, TINTA, SOMBRA, r=1, ancho=1.2)


def _logplot(c):
    c.rect(2.5, 2.5, 19, 19, TINTA, PAPEL, r=1)
    for x in (8.8, 15.2):
        c.linea((x, 2.5), (x, 21.5), ancho=1.0)
    c.curva(5.6, 4, 20, 1.6, VERDE, 1.3)
    c.curva(12, 4, 20, 1.6, ROJO, 1.3, fase=2)
    c.curva(18.3, 4, 20, 1.6, AZUL, 1.3, fase=4)


def _corte(c):
    for x in (3, 10, 17):
        c.rect(x, 4, 4, 16, TINTA, PAPEL, r=0.6, ancho=1.1)
    c.linea((3, 9), (7, 9), (10, 11), (14, 11), (17, 8), (21, 8), color=ROJO, ancho=1.4)
    c.linea((3, 15), (7, 15), (10, 17), (14, 17), (17, 14.5), (21, 14.5), color=AZUL, ancho=1.4)


def _trayectoria(c):
    c.linea((3, 3), (21, 3), color=TEAL, ancho=1.6)
    c.pluma(TINTA, 2.0)
    c.relleno(None)
    path = QPainterPath()
    path.moveTo(6, 3)
    path.lineTo(6, 9)
    path.cubicTo(6, 15, 11, 19, 20, 20)
    c.p.drawPath(path)
    for x, y in ((6, 9), (8.2, 15.5), (13.5, 19.2)):
        c.punto(x, y, 1.3, NARANJA)


def _crossplot(c):
    """Gráfico cruzado (Pickett, Hingle): ejes, puntos y recta de ajuste."""
    c.linea((4, 3), (4, 20), (21, 20), ancho=1.5)
    for x, y in ((7, 16), (9, 14.5), (10.5, 15), (12, 12), (13.5, 11.5), (15, 9), (16.5, 9.5), (18, 6.5)):
        c.punto(x, y, 1.15, AZUL)
    c.linea((6, 17.5), (19.5, 5), color=ROJO, ancho=1.4)


def _aplicacion(c):
    """Icono de Kurvo: una K cuyo trazo vertical es una curva de registro, con el tramo reparado en
    naranja, sobre un cuadrado redondeado en degradado verde azulado → azul profundo."""
    from PySide6.QtGui import QLinearGradient
    g = QLinearGradient(2, 2, 22, 22)
    g.setColorAt(0, QColor("#12a8a0"))
    g.setColorAt(1, QColor("#16306e"))
    c.p.setPen(Qt.NoPen)
    c.p.setBrush(QBrush(g))
    c.p.drawRoundedRect(QRectF(1, 1, 22, 22), 5, 5)
    blanco, naranja = QColor("#ffffff"), QColor("#ffae2b")

    def tramo(y0, y1, color):
        path = QPainterPath()
        n = 30
        for i in range(n + 1):
            y = y0 + (y1 - y0) * i / n
            t = (y - 4.5) / 15
            x = 8 + 1.25 * (math.sin(t * 9.5) * 0.7 + math.sin(t * 23) * 0.3)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        c.pluma(color, 2.1)
        c.relleno(None)
        c.p.drawPath(path)
    tramo(4.5, 9.6, blanco)
    tramo(9.6, 14.2, naranja)
    tramo(14.2, 19.5, blanco)
    c.linea((9.6, 12), (17.6, 4.6), color=blanco, ancho=2.3)
    c.linea((11.6, 10.4), (17.8, 19.4), color=blanco, ancho=2.3)


# ====================================================================== v0.3: herramientas nuevas
def _lupa(c, cx=10, cy=10, r=6.5, color=VERDE, fondo=PAPEL):
    c.circulo(cx, cy, r, TINTA, fondo, 1.6)
    c.linea((cx + r * 0.72, cy + r * 0.72), (cx + r * 0.72 + 5.5, cy + r * 0.72 + 5.5), color=TINTA, ancho=2.6)


def _ventana_qc(c):
    """Lupa con visto sobre una curva (familia calidad)."""
    c.curva(10, 2.5, 21.5, 2.4, AZUL.lighter(150), 1.3)
    _lupa(c, 10, 10, 6.5)
    c.linea((6.8, 10.2), (9.1, 12.6), (13.4, 7.6), color=VERDE, ancho=2.0)


def _tablero(c):
    """Matriz pozos × curvas con la nota coloreada."""
    colores = [[VERDE, VERDE, NARANJA], [VERDE, ROJO, VERDE], [SOMBRA.darker(115), VERDE, NARANJA]]
    for i in range(3):
        for j in range(3):
            c.rect(3 + j * 6.2, 3 + i * 6.2, 5.4, 5.4, TINTA, colores[i][j].lighter(130), r=0.8, ancho=1.0)


def _bandera_qc(c):
    c.curva(7, 3, 21, 2.2, AZUL, 1.5)
    c.linea((13.5, 21), (13.5, 3.5), color=TINTA, ancho=1.5)
    c.poligono([(13.5, 3.5), (21, 6), (13.5, 9)], ROJO, ROJO, ancho=1.0)


def _unidades(c):
    c.rect(2, 2.5, 11, 8, TINTA, SOMBRA, r=1.2, ancho=1.2)
    c.texto(2, 2.5, 11, 8, "ft", TINTA, 5.2)
    c.flecha(8, 12, 13, 16.5, TEAL, 1.5, 2.2)
    c.rect(11, 13.5, 11, 8, TINTA, VERDE.lighter(165), r=1.2, ancho=1.2)
    c.texto(11, 13.5, 11, 8, "m", TINTA, 5.2)


def _pista(c, x0=4.5, ancho=10):
    c.rect(x0, 2.5, ancho, 19, TINTA, PAPEL, r=1, ancho=1.3)


def _curva_nula(c):
    _pista(c)
    c.p.save()
    c.p.setClipRect(QRectF(0, 0, 24, 9))
    c.curva(9.5, 3.5, 20.5, 2.2, AZUL, 1.5)
    c.p.restore()
    c.p.save()
    c.p.setClipRect(QRectF(0, 15, 24, 9))
    c.curva(9.5, 3.5, 20.5, 2.2, AZUL, 1.5)
    c.p.restore()
    c.linea((5.5, 10), (13.5, 10), color=NARANJA, ancho=1.0)
    c.linea((5.5, 14), (13.5, 14), color=NARANJA, ancho=1.0)
    c.insignia(18, 12, ROJO, "x")


def _curva_valor(c):
    _pista(c)
    c.p.save()
    c.p.setClipRect(QRectF(0, 0, 24, 9))
    c.curva(9.5, 3.5, 20.5, 2.2, AZUL, 1.5)
    c.p.restore()
    c.p.save()
    c.p.setClipRect(QRectF(0, 15, 24, 9))
    c.curva(9.5, 3.5, 20.5, 2.2, AZUL, 1.5)
    c.p.restore()
    c.linea((10.5, 9), (12, 9.5), (12, 14.5), (10, 15), color=NARANJA, ancho=1.8)
    c.texto(15, 9, 8, 6, "=", NARANJA, 8)


def _interpolar(c):
    _pista(c)
    for y0, y1 in ((0, 9), (15, 24)):
        c.p.save()
        c.p.setClipRect(QRectF(0, y0, 24, y1 - y0))
        c.curva(9.5, 3.5, 20.5, 2.2, AZUL, 1.5)
        c.p.restore()
    c.pluma(NARANJA, 1.8, Qt.DotLine)
    c.relleno(None)
    path = QPainterPath()
    path.moveTo(8.7, 9)
    path.cubicTo(7.0, 11, 12.5, 13, 10.4, 15)
    c.p.drawPath(path)
    c.flecha(19, 7, 19, 17, NARANJA, 1.4, 2.2)


def _despike(c):
    _pista(c, 3, 11)
    c.linea((8, 3.5), (9.5, 7), (7.5, 10), (8.5, 11.2), (8.4, 13.4), (9.5, 16), (7.8, 20.5), color=AZUL, ancho=1.5)
    c.linea((8.5, 11.2), (19.5, 12.2), (8.4, 13.4), color=ROJO.lighter(130), ancho=1.2)
    c.linea((15.5, 9), (21, 15.5), color=ROJO, ancho=1.8)
    c.linea((15.5, 15.5), (21, 9), color=ROJO, ancho=1.8)


def _suavizar(c):
    c.linea((4, 3), (6.5, 5), (3, 7.5), (6.5, 10), (3.5, 12.5), (7, 15), (3, 17.5), (6, 21), color=TINTA.lighter(200),
            ancho=1.3)
    c.flecha(9, 12, 13.5, 12, TINTA, 1.4, 2.2)
    c.curva(18, 3, 21, 1.8, NARANJA, 1.9)


def _recortar(c):
    c.linea((7, 2.5), (7, 21.5), color=NARANJA, ancho=1.4)
    c.linea((17, 2.5), (17, 21.5), color=NARANJA, ancho=1.4)
    c.linea((10, 3), (17, 5.5), (17, 9), (12, 11), (7, 13), (7, 16), (13, 18), (11, 21), color=AZUL, ancho=1.6)
    c.linea((17, 5.5), (20.5, 7), (17, 9), color=ROJO.lighter(140), ancho=1.0)
    c.linea((7, 13), (3.5, 14.5), (7, 16), color=ROJO.lighter(140), ancho=1.0)


def _empalmar(c):
    c.p.save()
    c.p.setClipRect(QRectF(0, 0, 24, 12))
    c.curva(9, 2.5, 21.5, 2.2, AZUL, 1.7)
    c.p.restore()
    c.p.save()
    c.p.setClipRect(QRectF(0, 12, 24, 12))
    c.curva(15, 2.5, 21.5, 2.2, VERDE, 1.7, fase=0.4)
    c.p.restore()
    c.pluma(NARANJA, 1.2, Qt.DashLine)
    c.p.drawLine(QPointF(3, 12), QPointF(21, 12))
    c.punto(12, 12, 1.8, NARANJA)


def _comparar_original(c):
    _pista(c, 3, 18)
    c.curva(10, 3.5, 20.5, 3.0, TINTA.lighter(230), 2.0)
    c.curva(13, 3.5, 20.5, 3.0, AZUL, 1.4, fase=0.5)


def _restaurar_original(c):
    c.curva(7, 3, 21, 2.2, TINTA.lighter(220), 1.6)
    c.circulo(15.5, 14.5, 5.5, TINTA, PAPEL, 1.0)
    c.arco(15.5, 14.5, 3.6, 60, 270, NARANJA, 1.7)
    c.poligono([(15.4, 9.5), (18.8, 10.2), (16.6, 12.6)], NARANJA, NARANJA, ancho=0.8)


def _crear_prof(etiqueta):
    def f(c):
        _trayectoria(c)
        c.rect(10, 13, 13, 8.5, TINTA, PAPEL, r=1.2, ancho=1.1)
        c.texto(10, 13, 13, 8.5, etiqueta, TEAL, 4.6)
    return f


def _filtro(c):
    c.poligono([(3, 4), (21, 4), (14, 12.5), (14, 20), (10, 18), (10, 12.5)], TINTA, TEAL.lighter(165), 1.4)


def _engranaje(c, cx=12, cy=12, r=6.0, color=AZUL):
    path = QPainterPath()
    dientes = 8
    for i in range(dientes * 2):
        a0 = i * math.pi / dientes
        a1 = (i + 1) * math.pi / dientes
        rr = r + 2.4 if i % 2 == 0 else r
        for a in (a0, a1):
            x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
            if i == 0 and a == a0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
    path.closeSubpath()
    c.pluma(TINTA, 1.3)
    c.relleno(color.lighter(165))
    c.p.drawPath(path)
    c.circulo(cx, cy, 2.6, TINTA, PAPEL, 1.3)


def _preferencias(c):
    _engranaje(c)


def _panel_proyecto(c):
    c.rect(2.5, 3, 7, 4.5, TINTA, AZUL.lighter(165), r=0.8, ancho=1.2)
    c.linea((6, 7.5), (6, 18.5), color=TINTA, ancho=1.2)
    for y in (12, 18.5):
        c.linea((6, y), (11, y), color=TINTA, ancho=1.2)
        c.rect(11, y - 2.3, 10.5, 4.6, TINTA, SOMBRA if y == 18.5 else TEAL.lighter(170), r=0.8, ancho=1.2)


def _flujo(c):
    """Pasos encadenados: hechos (✓ verde), en curso y pendiente."""
    for i, (x, color) in enumerate(((4.5, VERDE), (12, VERDE), (19.5, SOMBRA.darker(120)))):
        c.circulo(x, 12, 3.4, TINTA if i < 2 else TINTA.lighter(180), color.lighter(120) if i < 2 else PAPEL, 1.2)
        if i < 2:
            c.linea((x - 1.6, 12), (x - 0.4, 13.3), (x + 1.7, 10.8), color=PAPEL, ancho=1.3)
    c.linea((8, 12), (8.6, 12), color=TINTA, ancho=1.2)
    c.linea((15.5, 12), (16.1, 12), color=TINTA, ancho=1.2)
    c.linea((3, 19.5), (21, 19.5), color=VERDE, ancho=1.6)
    c.linea((14, 19.5), (21, 19.5), color=SOMBRA.darker(120), ancho=1.6)


def _ojo(c):
    path = QPainterPath()
    path.moveTo(2, 12)
    path.cubicTo(7, 4.5, 17, 4.5, 22, 12)
    path.cubicTo(17, 19.5, 7, 19.5, 2, 12)
    c.pluma(TINTA, 1.5)
    c.relleno(PAPEL)
    c.p.drawPath(path)
    c.circulo(12, 12, 3.8, AZUL, AZUL.lighter(150), 1.4)
    c.punto(12, 12, 1.5, TINTA)


def _aplicar(c):
    c.circulo(12, 12, 9, VERDE, VERDE.lighter(170), 1.5)
    c.linea((7.5, 12.2), (10.6, 15.3), (16.8, 8.6), color=VERDE.darker(110), ancho=2.4)


def _cerrar(c):
    c.circulo(12, 12, 9, TINTA.lighter(160), SOMBRA, 1.3)
    c.linea((8.5, 8.5), (15.5, 15.5), color=TINTA, ancho=1.9)
    c.linea((8.5, 15.5), (15.5, 8.5), color=TINTA, ancho=1.9)


def _calcular(c):
    c.linea((4, 3), (4, 20), (21, 20), ancho=1.4)
    for i, h in enumerate((6, 11, 8, 14)):
        c.rect(6 + i * 3.4, 19 - h, 2.4, h, TINTA, AZUL.lighter(150), r=0.3, ancho=0.9)
    c.insignia(18, 7, VERDE, "play")


def _ejecutar(c):
    c.poligono([(6.5, 4), (19.5, 12), (6.5, 20)], VERDE.darker(110), VERDE.lighter(140), 1.5)


def _detener(c):
    c.rect(5, 5, 14, 14, ROJO.darker(110), ROJO.lighter(140), r=2, ancho=1.5)


def _entrenar(c):
    _deep_learning(c)
    c.insignia(18.5, 18.5, VERDE, "play")


def _predecir(c):
    capas = [(4, (6, 12, 18)), (10.5, (9, 15))]
    for y0 in capas[0][1]:
        for y1 in capas[1][1]:
            c.linea((4, y0), (10.5, y1), color=VIOLETA.lighter(140), ancho=0.9)
    for x, ys in capas:
        for y in ys:
            c.circulo(x, y, 1.9, VIOLETA, VIOLETA.lighter(160), 1.2)
    c.flecha(12.5, 12, 16, 12, TINTA, 1.4, 2)
    c.curva(19.5, 3, 21, 1.8, VIOLETA, 1.8)


def _guardar_modelo(c):
    c.disquete(VIOLETA)
    c.insignia(18, 18, VIOLETA, "+")


def _cargar_modelo(c):
    c.carpeta(abierta=True, color=VIOLETA)
    c.flecha(15, 3.5, 15, 14, VIOLETA, 1.8, 3.0)


def _llave(c, color=VERDE):
    c.p.save()
    c.p.translate(12, 12)
    c.p.rotate(45)
    c.rect(-1.4, -2, 2.8, 12, TINTA, color.lighter(160), r=1.2, ancho=1.2)
    path = QPainterPath()
    path.addEllipse(QPointF(0, -5.5), 4.6, 4.6)
    sub = QPainterPath()
    sub.addRect(QRectF(-1.6, -11, 3.2, 6.5))
    c.pluma(TINTA, 1.2)
    c.relleno(color.lighter(160))
    c.p.drawPath(path.subtracted(sub))
    c.p.restore()


def _corregir(c):
    _llave(c)


def _corregir_todo(c):
    c.documento(3, 2.5, 13, 18)
    for y in (8, 11, 14):
        c.linea((6, y), (12.5, y), ancho=1.0)
    c.p.save()
    c.p.translate(6, 6)
    c.p.scale(0.75, 0.75)
    _llave(c)
    c.p.restore()


def _agregar(c):
    c.circulo(12, 12, 9, VERDE, VERDE.lighter(165), 1.4)
    c.linea((12, 7), (12, 17), color=VERDE.darker(120), ancho=2.4)
    c.linea((7, 12), (17, 12), color=VERDE.darker(120), ancho=2.4)


def _borrar(c):
    c.rect(6, 7, 12, 14, TINTA, ROJO.lighter(175), r=1.2, ancho=1.4)
    c.linea((4, 6.5), (20, 6.5), color=TINTA, ancho=1.6)
    c.linea((9.5, 6.5), (10, 3.5), (14, 3.5), (14.5, 6.5), color=TINTA, ancho=1.4)
    for x in (9.5, 12, 14.5):
        c.linea((x, 10), (x, 18), color=ROJO, ancho=1.2)


def _arriba(c):
    c.flecha(12, 20, 12, 4, AZUL, 2.2, 5)


def _abajo(c):
    c.flecha(12, 4, 12, 20, AZUL, 2.2, 5)


def _color(c):
    c.circulo(12, 12, 9, TINTA, SOMBRA, 1.3)
    for (x, y), col in zip(((8, 9), (12.5, 6.5), (16.5, 9.5), (8.5, 14)), (ROJO, NARANJA, VERDE, AZUL)):
        c.punto(x, y, 1.9, col)
    c.circulo(15, 15.5, 2.4, TINTA, PAPEL, 1.0)


def _importar(c):
    c.linea((4, 14), (4, 20.5), (20, 20.5), (20, 14), color=TINTA, ancho=1.6)
    c.flecha(12, 3, 12, 16, TEAL, 2.0, 4)


def _exportar(c):
    c.linea((4, 14), (4, 20.5), (20, 20.5), (20, 14), color=TINTA, ancho=1.6)
    c.flecha(12, 16, 12, 3, AZUL, 2.0, 4)


def _zoom(signo):
    def f(c):
        _lupa(c, 10, 10, 6.5, AZUL, PAPEL)
        if signo in "+-":
            c.linea((7, 10), (13, 10), color=AZUL, ancho=2.0)
        if signo == "+":
            c.linea((10, 7), (10, 13), color=AZUL, ancho=2.0)
        if signo == "1":
            c.texto(5, 6, 10, 8, "1:1", AZUL, 4.2)
    return f


def _refrescar(c):
    c.arco(12, 12, 7.5, 30, 150, AZUL, 2.0)
    c.arco(12, 12, 7.5, 210, 150, AZUL, 2.0)
    c.poligono([(18.6, 4.5), (19.4, 9.6), (14.6, 8.4)], AZUL, AZUL, 0.8)
    c.poligono([(5.4, 19.5), (4.6, 14.4), (9.4, 15.6)], AZUL, AZUL, 0.8)


def _nuevo(c):
    c.documento(4, 2.5, 14, 19)
    c.insignia(17.5, 17.5, VERDE, "+")


def _dibujar(c):
    c.curva(7, 3, 21, 2.2, AZUL, 1.4)
    c.lapiz(9, 20, 13)


def _resumen(c):
    c.rect(2.5, 3.5, 19, 17, TINTA, PAPEL, r=1, ancho=1.3)
    c.rect(2.5, 3.5, 19, 4, TINTA, SOMBRA, r=1, ancho=1.2)
    for i, col in enumerate((VERDE, NARANJA, VERDE)):
        y = 9.5 + i * 3.7
        c.rect(4.5, y, 3, 2.4, col, col, r=0.4, ancho=0.6)
        c.linea((9.5, y + 1.2), (19, y + 1.2), ancho=1.0)


def _vista_prof(c):
    c.rect(2.5, 2.5, 19, 19, TINTA, PAPEL, r=1)
    c.linea((12, 2.5), (12, 21.5), ancho=1.0)
    c.curva(7.2, 4, 20, 1.8, VERDE, 1.3)
    c.curva(16.8, 4, 20, 1.8, AZUL, 1.3, fase=1.5)
    for y in (9, 15):
        c.rect(3.2, y, 17.6, 1.6, ROJO.lighter(150), ROJO.lighter(170), r=0.2, ancho=0.5)


def _cobertura(c):
    for i, partes in enumerate(((VERDE, 1.0),
                                (VERDE, 0.55, PAPEL, 0.2, VERDE, 0.25),
                                (VERDE, 0.3, NARANJA, 0.15, VERDE, 0.55),
                                (PAPEL, 0.25, VERDE, 0.75))):
        x = 3.5 + i * 4.6
        y = 3
        for col, frac in zip(partes[::2], partes[1::2]):
            h = 18 * frac
            c.rect(x, y, 3.4, h, TINTA if col is PAPEL else col, col.lighter(115) if col is not PAPEL else PAPEL,
                   r=0.2, ancho=0.6)
            y += h


def _histograma(c):
    c.linea((3, 20.5), (21, 20.5), ancho=1.3)
    for i, h in enumerate((3, 7, 12, 15, 10, 6, 2.5)):
        c.rect(3.5 + i * 2.5, 20 - h, 2.1, h, TINTA, AZUL.lighter(150), r=0.2, ancho=0.8)


def _comparar_pozos(c):
    def campana(cx, color):
        path = QPainterPath()
        for i in range(41):
            x = 2 + i * 0.5
            y = 20 - 13 * math.exp(-0.5 * ((x - cx) / 2.6) ** 2)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        c.pluma(color, 1.8)
        c.relleno(None)
        c.p.drawPath(path)
    c.linea((2, 20.5), (22, 20.5), ancho=1.3)
    campana(9, AZUL)
    campana(14, NARANJA)


def _cajas(c):
    for x, (a, b, m, lo, hi) in ((6, (8, 15, 11, 4, 19)), (16, (6, 12, 9, 3, 16))):
        c.linea((x, lo), (x, a), ancho=1.1)
        c.linea((x, b), (x, hi), ancho=1.1)
        c.rect(x - 3, a, 6, b - a, TINTA, AZUL.lighter(160) if x == 6 else NARANJA.lighter(160), r=0.4, ancho=1.2)
        c.linea((x - 3, m), (x + 3, m), color=ROJO, ancho=1.4)


def _correlacion(c):
    valores = [[1, .6, -.4], [.6, 1, .1], [-.4, .1, 1]]
    for i in range(3):
        for j in range(3):
            v = valores[i][j]
            col = QColor(ROJO) if v > 0 else QColor(AZUL)
            col = col.lighter(int(100 + 90 * (1 - abs(v))))
            c.rect(3 + j * 6.2, 3 + i * 6.2, 5.6, 5.6, TINTA, col, r=0.4, ancho=0.8)


def _antes_despues(c):
    c.rect(2.5, 2.5, 19, 19, TINTA, PAPEL, r=1, ancho=1.2)
    c.linea((12, 2.5), (12, 21.5), ancho=1.0)
    c.curva(7.2, 4, 20, 2.0, TINTA.lighter(220), 1.6)
    c.curva(7.2, 4, 20, 2.0, AZUL, 1.0, fase=0.3)
    c.linea((16.8, 4), (16.8, 9), (18.5, 11), (16.8, 13), (16.8, 20), color=NARANJA, ancho=1.4)


def _paso_prof(c):
    c.linea((5, 3), (5, 21), ancho=1.3)
    for i, y in enumerate((4, 7, 10, 11.2, 14, 17, 20)):
        c.linea((5, y), (9 if i != 3 else 12, y), color=ROJO if i == 3 else TINTA, ancho=1.2)
    c.linea((13, 6), (13, 9), (17, 9), (17, 13.5), (21, 13.5), color=AZUL, ancho=1.5)


def _condicion_pozo(c):
    c.linea((7, 2.5), (7, 8), (4.5, 11), (5, 14), (7, 16), (7, 21.5), color=TINTA, ancho=1.6)
    c.linea((17, 2.5), (17, 8), (19.5, 11), (19, 14), (17, 16), (17, 21.5), color=TINTA, ancho=1.6)
    c.poligono([(7, 8), (4.5, 11), (5, 14), (7, 16)], ROJO.lighter(130), ROJO.lighter(170), 0.8)
    c.poligono([(17, 8), (19.5, 11), (19, 14), (17, 16)], ROJO.lighter(130), ROJO.lighter(170), 0.8)
    c.linea((9.5, 2.5), (9.5, 21.5), color=TEAL, ancho=1.0)
    c.linea((14.5, 2.5), (14.5, 21.5), color=TEAL, ancho=1.0)


def _curva_nodo(c, color=AZUL):
    c.rect(6, 2.5, 12, 19, TINTA.lighter(200), PAPEL, r=1, ancho=1.1)
    c.curva(12, 4, 20, 3.0, color, 1.8)


def _curva_editada(c):
    _curva_nodo(c)
    c.lapiz(13, 21, 9)


def _curva_generada(c):
    _curva_nodo(c, VIOLETA)
    c.insignia(17.5, 17.5, VIOLETA, "+")


def _todo_registro(c):
    c.rect(4, 2.5, 16, 19, TINTA, PAPEL, r=1)
    c.rect(4, 2.5, 16, 19, TEAL, SOMBRA, r=1, ancho=1.2)
    c.curva(12, 4, 20, 3.0, AZUL, 1.4)


def _reporte(c):
    _reporte_qc(c)


def _mahalanobis(c):
    c.linea((4, 3), (4, 20), (21, 20), ancho=1.4)
    c.p.save()
    c.p.translate(12.5, 12)
    c.p.rotate(-35)
    c.pluma(VERDE, 1.3, Qt.DashLine)
    c.relleno(None)
    c.p.drawEllipse(QPointF(0, 0), 7, 3.6)
    c.p.restore()
    for x, y in ((9, 15), (11, 13.5), (13, 12), (14.5, 10.5), (16, 9.5), (11.5, 11.8)):
        c.punto(x, y, 1.0, AZUL)
    c.punto(18, 16, 1.6, ROJO)


def _propiedades(c):
    """Ficha de la curva: curva a la izquierda, filas de propiedades y la "i" de información."""
    c.rect(3, 3, 18, 18, TINTA, PAPEL, r=1.5, ancho=1.4)
    c.curva(7, 5, 19, 2.0, AZUL, 1.4)
    for y in (7.5, 11.5, 15.5):
        c.linea((11, y), (18, y), color=TINTA.lighter(160), ancho=1.4)
    c.circulo(17.5, 17.5, 4.6, PAPEL, AZUL, 1.2)
    c.texto(12.9, 12.9, 9.2, 9.2, "i", PAPEL, 6.5)


ICONOS = {
    # General
    "open": _abrir, "save": _guardar, "save_as": _guardar_como, "close_project": _cerrar_proyecto,
    "print": _imprimir, "print_setup": _config_impresion, "help": _ayuda, "about": _acerca,
    "diagnostic": _diagnostico, "exit": _salir,
    # Maintenance
    "undo": _deshacer, "redo": _rehacer, "history": _historial, "graphic_edit": _edicion_grafica,
    "validate": _validar, "resample": _remuestrear, "mnemonics": _mnemonicos, "batch": _lote,
    "normalize": _normalizar, "depth_shift": _desfase, "qc_report": _reporte_qc, "deep_learning": _deep_learning,
    "import_dlis": _archivo_con("DLIS", TEAL, True), "export_csv": _archivo_con("CSV", AZUL, False),
    "export_excel": _excel,
    # Advance
    "partial_log": _log_parcial, "calculator": _calculadora, "combine": _combinar, "composite": _compuesto, "grouping": _agrupar,
    "litho_db": _base_litologia, "tool_db": _base_herramientas, "plugins": _complemento,
    # árbol y pestañas
    "wells": _pozos, "well": _pozo, "log": _registro, "completion": _completacion, "lithology": _litologia,
    "zones": _zonas, "templates": _plantillas, "logplot": _logplot, "cross_section": _corte,
    "trajectory": _trayectoria, "crossplot": _crossplot, "app": _aplicacion,
    # v0.3: flujo, QC y herramientas de curva
    "import_las": _archivo_con("LAS", TEAL, True), "export_las": _archivo_con("LAS", AZUL, False),
    "import_las_folder": _carpeta_las,
    "units": _unidades, "qc_window": _ventana_qc, "dashboard": _tablero, "qc_flag": _bandera_qc,
    "curve_null": _curva_nula, "curve_value": _curva_valor, "interpolate": _interpolar, "despike": _despike,
    "smooth": _suavizar, "clip": _recortar, "splice": _empalmar, "compare_original": _comparar_original,
    "restore_original": _restaurar_original, "create_tvd": _crear_prof("TVD"), "create_md": _crear_prof("MD"),
    "filter": _filtro, "settings": _preferencias, "panel_project": _panel_proyecto, "workflow": _flujo,
    # botones de diálogos
    "preview": _ojo, "apply": _aplicar, "close": _cerrar, "compute": _calcular, "run": _ejecutar,
    "stop": _detener, "train": _entrenar, "predict": _predecir, "save_model": _guardar_modelo,
    "load_model": _cargar_modelo, "fix": _corregir, "fix_all": _corregir_todo, "add": _agregar,
    "delete": _borrar, "up": _arriba, "down": _abajo, "color": _color, "import": _importar,
    "export": _exportar, "zoom_in": _zoom("+"), "zoom_out": _zoom("-"), "zoom_reset": _zoom("1"),
    "refresh": _refrescar, "new": _nuevo, "draw": _dibujar, "report": _reporte,
    # pestañas del panel de QC y árbol
    "summary": _resumen, "depth_view": _vista_prof, "coverage": _cobertura, "histogram": _histograma,
    "compare_wells": _comparar_pozos, "boxplot": _cajas, "correlation": _correlacion,
    "before_after": _antes_despues, "depth_step": _paso_prof, "borehole": _condicion_pozo,
    "curve": _curva_nodo, "curve_edited": _curva_editada, "curve_generated": _curva_generada,
    "whole_log": _todo_registro, "mahalanobis": _mahalanobis,
    # v0.4
    "properties": _propiedades,
}

NOTA_COLORES = {"A": VERDE, "B": NARANJA, "C": ROJO}


def pixmap(nombre: str, lado: int = 32) -> QPixmap:
    pm = QPixmap(lado, lado)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    ICONOS[nombre](Lienzo(p, lado))
    p.end()
    return pm


@lru_cache(maxsize=None)
def icono(nombre: str) -> QIcon:
    ic = QIcon()
    for t in TAMANOS:
        ic.addPixmap(pixmap(nombre, t))
    return ic


def _pixmap_insignia(base: str, nota: str, lado: int) -> QPixmap:
    """Icono base con la nota de QC (A/B/C) en una insignia de color abajo a la derecha."""
    pm = pixmap(base, lado)
    if nota not in NOTA_COLORES:
        return pm
    p = QPainter(pm)
    c = Lienzo(p, lado)
    c.circulo(17.5, 17.5, 6.2, PAPEL, NOTA_COLORES[nota], 1.2)
    c.texto(11.3, 11.3, 12.4, 12.4, nota, PAPEL, 7.2)
    p.end()
    return pm


@lru_cache(maxsize=None)
def icono_nota(base: str, nota: str) -> QIcon:
    """Insignia de estado del árbol: icono de log o curva con la nota de QC."""
    ic = QIcon()
    for t in TAMANOS:
        ic.addPixmap(_pixmap_insignia(base, nota, t))
    return ic


@lru_cache(maxsize=None)
def icono_estado(estado: str) -> QIcon:
    """Estado de un paso del flujo: hecho (✓ verde), aviso (! naranja), pendiente (círculo) u opcional."""
    def dibujo(c):
        if estado == "done":
            c.insignia(12, 12, VERDE, "check")
        elif estado == "warning":
            c.insignia(12, 12, NARANJA, "!")
        elif estado == "pending":
            c.circulo(12, 12, 4.6, ROJO, PAPEL, 1.6)
        else:
            c.circulo(12, 12, 4.6, SOMBRA.darker(130), PAPEL, 1.2)
    ic = QIcon()
    for t in TAMANOS:
        pm = QPixmap(t, t)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        lz = Lienzo(p, t)
        p.translate(-12, -12)
        p.scale(2, 2)
        dibujo(lz)
        p.end()
        ic.addPixmap(pm)
    return ic
