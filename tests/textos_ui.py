"""Extrae del código los textos de la interfaz que pasan por tr() (directa o indirectamente), para
comprobar que todos tienen traducción al español."""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "kurvo"

# llamadas cuyo argumento (posición o nombre) se traduce después con tr()
INDIRECTOS = {
    "Campo": [1], "pedir": [0], "boton": [0, 2], "DefAccion": [1, 3], "accion": [1, 3],
    "editar": [0], "aplicar": [1], "operacion": [0], "anotar": [0], "_intervalo": [0], "Operacion": [1],
    "DialogoParametros": [0], "_pedir_con_vista": [3], "_grafico": [0],
}
NOMBRADOS = {"BarraAplicar": ["texto_aplicar", "texto_vista"]}
# asignaciones (o funciones) cuyos textos se muestran traducidos
CONSTANTES = {"PESTANAS", "PASOS", "ROLES", "TAREAS", "ARQUITECTURAS", "NOMBRES_CORRECCION", "LITOLOGIAS_ND",
              "columnas", "etiqueta_item", "nombre", "descripcion", "_nombres_pestanas", "_titulos_docks",
              "etiquetas", "cab", "ICONOS_ESTANDAR", "tipo"}
FUNCIONES = {"_construir_ribbon", "acciones_editor_logs"}


def _cadenas(nodo):
    for n in ast.walk(nodo):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value


def _util(s: str) -> bool:
    return any(c.isalpha() for c in s) and not s.startswith(("mod:", "panel:", "curva:", "editor:", "mant:"))


def textos() -> dict[str, str]:
    """{texto: archivo donde aparece}."""
    out: dict[str, str] = {}
    for ruta in RAIZ.rglob("*.py"):
        if "i18n" in ruta.parts:
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        rel = str(ruta.relative_to(RAIZ))

        def poner(s):
            if isinstance(s, str) and _util(s):
                out.setdefault(s, rel)
        for n in ast.walk(arbol):
            if isinstance(n, ast.Call):
                nombre = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ""
                if nombre == "tr" and n.args and isinstance(n.args[0], ast.Constant):
                    poner(n.args[0].value)
                for i in INDIRECTOS.get(nombre, []):
                    if len(n.args) > i and isinstance(n.args[i], ast.Constant):
                        poner(n.args[i].value)
                for kw in n.keywords:
                    if kw.arg in NOMBRADOS.get(nombre, []) and isinstance(kw.value, ast.Constant):
                        poner(kw.value.value)
                if nombre == "Campo" and any(k.arg == "traducir_opciones" for k in n.keywords) and len(n.args) > 4:
                    for s in _cadenas(n.args[4]):
                        poner(s)
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                objetivos = n.targets if isinstance(n, ast.Assign) else [n.target]
                for o in objetivos:
                    nom = o.id if isinstance(o, ast.Name) else o.attr if isinstance(o, ast.Attribute) else ""
                    if nom in CONSTANTES and n.value is not None:
                        for s in _cadenas(n.value):
                            poner(s)
            elif isinstance(n, ast.FunctionDef) and n.name in FUNCIONES:
                for s in _cadenas(n):
                    poner(s)
    return out
