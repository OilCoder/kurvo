"""Traducción de la interfaz (inglés → español) con un diccionario propio.

Todo texto visible pasa por `tr("texto en inglés")`. El inglés es la clave y el idioma por
defecto; si falta la traducción se muestra el inglés. Los textos con datos usan marcadores de
`str.format`: `tr("Delete {0}?").format(nombre)`. Los mnemónicos de curvas, las unidades y los
nombres de archivo no se traducen (no se pasan por `tr`). (D60–D63)."""
from __future__ import annotations

IDIOMAS = {"en": "English", "es": "Español"}
_idioma = "en"


def idioma() -> str:
    return _idioma


def fijar_idioma(codigo: str) -> str:
    """Cambia el idioma de los textos que se creen a partir de ahora; devuelve el aplicado."""
    global _idioma
    _idioma = codigo if codigo in IDIOMAS else "en"
    return _idioma


def tr(texto: str) -> str:
    if _idioma == "es" and texto:
        from .es import ES
        return ES.get(texto, texto)
    return texto


def tr_ayuda(clave: str) -> str:
    """Textos largos (ayuda, explicaciones) que no conviene usar como clave de diccionario."""
    from . import ayuda
    textos = ayuda.ES if _idioma == "es" else ayuda.EN
    return textos.get(clave, ayuda.EN.get(clave, ""))
