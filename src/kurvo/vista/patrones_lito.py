"""Patrones de litología estándar, dibujados por código.

Siguen la convención de símbolos de litología FGDC/USGS: arenisca con puntos, lutita con
guiones, caliza en ladrillo, dolomía en ladrillo inclinado, carbón negro, evaporitas
rayadas, etc. El tipo se reconoce por su nombre (inglés o español): el sustantivo principal da
el patrón base y los adjetivos ("sandy", "silty", "clayey", "calcareous") o los fósiles de los
ooze (nannofossil, foraminifer, diatom, radiolarian) añaden símbolos dispersos encima."""
from __future__ import annotations

import re
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF

LADO = 32          # lado del mosaico en píxeles

# clave: (color de fondo, patrón base)
PRIMARIOS = {
    "sand": ("#ffe680", "puntos"),
    "silt": ("#e6d9a6", "limo"),
    "clay": ("#bdbdb0", "guion_corto"),
    "shale": ("#9aa89a", "guion_largo"),
    "limestone": ("#9cc8ea", "ladrillo"),
    "dolomite": ("#cfaee0", "ladrillo_inclinado"),
    "chalk": ("#e8f2fa", "ladrillo_ralo"),
    "marl": ("#b3d1bd", "marga"),
    "ooze": ("#eef3f7", "vacio"),
    "conglomerate": ("#f2c27a", "circulos"),
    "breccia": ("#e6a87a", "triangulos"),
    "diamicton": ("#c9bc96", "diamicton"),
    "chert": ("#d9b38c", "triangulos_chicos"),
    "coal": ("#1a1a1a", "vacio"),
    "anhydrite": ("#e3b8e3", "rayado_cruzado"),
    "gypsum": ("#f2d6f2", "rayado_vertical"),
    "salt": ("#f4f4ff", "cubos"),
    "igneous": ("#e8a3a3", "uves"),
    "metamorphic": ("#c7b3d9", "ondas"),
    "default": ("#ffffff", "vacio"),
}

# patrón: expresión regular (sustantivo)
_NOMBRES = [
    ("sand", r"sand(stone)?s?|arenisca|arenas?"),
    ("silt", r"silt(stone)?s?|limolita|limos?"),
    ("shale", r"shales?|lutitas?"),
    ("clay", r"clay(stone)?s?|mud(stone)?s?|arcill(a|olita)s?|fango"),
    ("limestone", r"limestones?|calizas?|grainstone|packstone|wackestone"),
    ("dolomite", r"dolomit(e|a)s?|dolom[ií]as?|dolostone"),
    ("chalk", r"chalks?|cretas?"),
    ("marl", r"marls?|margas?"),
    ("ooze", r"oozes?"),
    ("conglomerate", r"conglomerat(e|es)|conglomerados?"),
    ("breccia", r"breccias?|brechas?"),
    ("diamicton", r"diamict(on|ite)s?|diamictitas?"),
    ("chert", r"cherts?|pedernal|s[ií]lex|flint"),
    ("coal", r"coals?|lignit(e|o)|carb[oó]n"),
    ("anhydrite", r"anhydrites?|anhidritas?"),
    ("gypsum", r"gypsum|yeso"),
    ("salt", r"salt|halit(e|a)|sal"),
    ("igneous", r"igneous|[ií]gnea|granit(e|o)|basalt(o)?|volcanic|volc[aá]nica|tuff?|toba"),
    ("metamorphic", r"metamorphic|metam[oó]rfica|schist|esquisto|gneiss|slate|pizarra"),
]

# adjetivo: (expresión regular, símbolo disperso, sustantivo que lo sustituye si va solo)
_MODIFICADORES = [
    ("sandy", r"sandy|arenos[oa]", "sand"),
    ("silty", r"silty|limos[oa]", "silt"),
    ("clayey", r"clayey|arcillos[oa]", "clay"),
    ("shaly", r"shaly|shaley|lut[ií]tic[oa]", "shale"),
    ("calcareous", r"calcareous|calc[aá]re[oa]", "limestone"),
    ("nannofossil", r"nann?o(fossil)?", "ooze"),
    ("foraminifer", r"foram(inifer(a|al)?)?|foramin[ií]feros?", "ooze"),
    ("diatom", r"diatom(ite|ea)?s?|diatomeas?", "ooze"),
    ("radiolarian", r"radiolari(an|o)s?", "ooze"),
]


_A_ADJETIVO = {"sand": "sandy", "silt": "silty", "clay": "clayey", "shale": "shaly",
               "limestone": "calcareous"}


def _buscar(texto: str, tabla) -> list[str]:
    hallados = [(m.start(), fila[0]) for fila in tabla
                for m in re.finditer(rf"\b({fila[1]})\b", texto)]
    return [c for _, c in sorted(hallados)]


def clasificar(nombre: str) -> tuple[str, tuple[str, ...]]:
    """Devuelve (patrón primario, modificadores) a partir del nombre de la litología.

    "Silty clay" -> ("clay", ("silty",)); "Diamicton with sandy" -> ("diamicton", ("sandy",));
    "Calcareous" -> ("limestone", ()); "Nannofossil chalk" -> ("chalk", ("nannofossil",))."""
    texto = (nombre or "").lower()
    m = re.search(r"\b(with|con)\b", texto)
    principal, extra = (texto[:m.start()], texto[m.end():]) if m else (texto, "")
    nombres, mods = _buscar(principal, _NOMBRES), _buscar(principal, _MODIFICADORES)
    if nombres:
        primario = nombres[-1]
        mods += [_A_ADJETIVO[n] for n in nombres[:-1] if n in _A_ADJETIVO]
    elif mods:
        primario = next(s for c, _, s in _MODIFICADORES if c == mods[-1])
        if primario != "ooze":
            mods = mods[:-1]
    else:
        primario = "default"
    mods += [_A_ADJETIVO.get(n, "") for n in _buscar(extra, _NOMBRES)] + _buscar(extra, _MODIFICADORES)
    return primario, tuple(dict.fromkeys(x for x in mods if x))


# ------------------------------------------------------------------ dibujo
def _tinta(fondo: QColor) -> QColor:
    return QColor(235, 235, 235) if fondo.lightness() < 80 else QColor(20, 20, 20)


def _base(p: QPainter, patron: str, n: int) -> None:
    """Patrón primario sobre un mosaico n×n (n = LADO)."""
    h = n / 4
    if patron == "puntos":
        for fila in range(4):
            for col in range(4):
                x = col * h + (h / 2 if fila % 2 else 0) + h / 4
                p.drawEllipse(QPointF(x % n, fila * h + h / 2), 1.1, 1.1)
    elif patron == "limo":
        for fila in range(4):
            y = fila * h + h / 2
            x0 = (h if fila % 2 else 0)
            p.drawLine(QPointF(x0 + 1, y), QPointF(x0 + h * 0.9, y))
            p.drawEllipse(QPointF((x0 + h * 2.2) % n, y), 0.9, 0.9)
            p.drawEllipse(QPointF((x0 + h * 3.2) % n, y), 0.9, 0.9)
    elif patron in ("guion_corto", "guion_largo"):
        largo = h * (0.8 if patron == "guion_corto" else 1.6)
        paso = h if patron == "guion_corto" else 2 * h
        for fila in range(4):
            y = fila * h + h / 2
            x = (paso / 2 if fila % 2 else 0)
            while x < n:
                p.drawLine(QPointF(x + 1, y), QPointF(min(x + largo, n), y))
                x += paso
    elif patron in ("ladrillo", "ladrillo_inclinado", "ladrillo_ralo", "marga"):
        filas = 2 if patron == "ladrillo_ralo" else 4
        alto = n / filas
        for fila in range(filas):
            y = fila * alto
            p.drawLine(QPointF(0, y), QPointF(n, y))
            if patron == "marga" and fila % 2:
                p.drawLine(QPointF(n * 0.15, y + alto / 2), QPointF(n * 0.4, y + alto / 2))
                p.drawLine(QPointF(n * 0.65, y + alto / 2), QPointF(n * 0.9, y + alto / 2))
                continue
            for x in ((n / 4, 3 * n / 4) if fila % 2 else (0, n / 2)):
                if patron == "ladrillo_inclinado":
                    p.drawLine(QPointF(x, y), QPointF(x + alto * 0.6, y + alto))
                else:
                    p.drawLine(QPointF(x, y), QPointF(x, y + alto))
    elif patron == "circulos":
        for (cx, cy, r) in ((n * .25, n * .3, n * .14), (n * .72, n * .2, n * .1),
                            (n * .6, n * .7, n * .16), (n * .15, n * .8, n * .08)):
            p.drawEllipse(QPointF(cx, cy), r, r * 0.8)
    elif patron in ("triangulos", "triangulos_chicos"):
        k = 0.12 if patron == "triangulos" else 0.07
        for (cx, cy) in ((n * .25, n * .3), (n * .75, n * .25), (n * .5, n * .75), (n * .05, n * .8)):
            r = n * k
            p.drawPolygon(QPolygonF([QPointF(cx, cy - r), QPointF(cx + r, cy + r * .8),
                                     QPointF(cx - r, cy + r * .8)]))
    elif patron == "diamicton":
        for fila in range(4):
            y = fila * h + h / 2
            p.drawLine(QPointF((h if fila % 2 else 0) + 1, y), QPointF((h if fila % 2 else 0) + h * .8, y))
        for (cx, cy, r) in ((n * .7, n * .3, n * .09), (n * .3, n * .72, n * .12)):
            p.drawEllipse(QPointF(cx, cy), r, r * .8)
    elif patron == "rayado_cruzado":
        for k in range(-1, 3):
            p.drawLine(QPointF(k * n / 2, n), QPointF(k * n / 2 + n, 0))
            p.drawLine(QPointF(k * n / 2, 0), QPointF(k * n / 2 + n, n))
    elif patron == "rayado_vertical":
        for k in range(4):
            p.drawLine(QPointF(k * h + h / 2, 0), QPointF(k * h + h / 2, n))
    elif patron == "cubos":
        for fila in range(2):
            for col in range(2):
                x, y = (col * n / 2 + (n / 4 if fila else 0) + 3) % n, fila * n / 2 + 3
                for dx in (0, -n):          # copia desplazada para que el cubo cruce el borde
                    p.drawRect(QRectF(x + dx, y, n / 2 - 7, n / 2 - 7))
    elif patron == "uves":
        for fila in range(3):
            for col in range(3):
                x = col * n / 3 + (n / 6 if fila % 2 else 0) + 2
                y = fila * n / 3 + 3
                w = n / 6
                p.drawPolyline(QPolygonF([QPointF(x, y), QPointF(x + w / 2, y + w), QPointF(x + w, y)]))
    elif patron == "ondas":
        for fila in range(3):
            y = fila * n / 3 + n / 6
            pts = [QPointF(x, y + (2 if (x // 4) % 2 else -2)) for x in range(0, n + 1, 4)]
            p.drawPolyline(QPolygonF(pts))


# posiciones dispersas de los símbolos de los modificadores (no chocan con el patrón base)
_DISPERSOS = ((0.38, 0.12), (0.88, 0.62), (0.12, 0.58), (0.62, 0.92))


def _modificador(p: QPainter, mod: str, n: int, indice: int) -> None:
    pos = _DISPERSOS[indice % 2::2] if indice < 2 else _DISPERSOS
    for fx, fy in pos:
        x, y = fx * n, fy * n
        if mod == "sandy":
            p.drawEllipse(QPointF(x, y), 1.1, 1.1)
        elif mod == "silty":
            p.drawLine(QPointF(x - 2.5, y), QPointF(x + .5, y))
            p.drawEllipse(QPointF(x + 2.5, y), .8, .8)
        elif mod in ("clayey", "shaly"):
            p.drawLine(QPointF(x - 3, y), QPointF(x + 3, y))
        elif mod == "calcareous":
            p.drawLine(QPointF(x - 3, y + 2), QPointF(x + 3, y + 2))
            p.drawLine(QPointF(x, y - 2), QPointF(x, y + 2))
        elif mod == "nannofossil":
            p.drawLine(QPointF(x - 2, y), QPointF(x + 2, y))
            p.drawLine(QPointF(x, y - 2), QPointF(x, y + 2))
        elif mod == "foraminifer":
            p.drawEllipse(QPointF(x, y), 2, 2)
        elif mod == "diatom":
            p.drawPolyline(QPolygonF([QPointF(x - 2, y - 2), QPointF(x, y + 2), QPointF(x + 2, y - 2)]))
        elif mod == "radiolarian":
            for dx, dy in ((2, 0), (1, 1.7), (-1, 1.7)):
                p.drawLine(QPointF(x - dx, y - dy), QPointF(x + dx, y + dy))


@lru_cache(maxsize=256)
def imagen_patron(nombre: str) -> QImage:
    """Mosaico LADO×LADO (fondo + patrón) para usar como textura repetida."""
    primario, mods = clasificar(nombre)
    color, patron = PRIMARIOS[primario]
    fondo = QColor(color)
    img = QImage(LADO, LADO, QImage.Format_ARGB32_Premultiplied)
    img.fill(fondo)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    tinta = _tinta(fondo)
    p.setPen(QPen(tinta, 1))
    p.setBrush(Qt.NoBrush)
    if patron in ("puntos",):
        p.setBrush(tinta)
    _base(p, patron, LADO)
    for i, m in enumerate(mods):
        p.setBrush(tinta if m == "sandy" or m == "silty" else Qt.NoBrush)
        _modificador(p, m, LADO, i if len(mods) > 1 else 2)
    p.end()
    return img


def color_patron(nombre: str) -> QColor:
    return QColor(PRIMARIOS[clasificar(nombre)[0]][0])


def brocha_patron(nombre: str) -> QBrush:
    b = QBrush()
    b.setTextureImage(imagen_patron(nombre))
    return b
