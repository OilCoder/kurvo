"""Calculadora de curvas: fórmulas guardadas en archivos `.formula`.

Sintaxis observada en Sample/Formulas y Doc/advance_formula.zzo:
    Var := expresión;     (asignaciones, separadas por ';')
    expresión_final       (resultado)
X1..Xn son las curvas de entrada. Funciones: sin cos tan asin acos atan sinh cosh tanh asinh
acosh atanh log10 log exp sqrt int abs if(c,a,b) y potencia con '^'.
Una muestra con alguna entrada nula da nulo."""
from __future__ import annotations

import ast
import re

import numpy as np

from ..nucleo.comun import NULO


class ErrorFormula(Exception):
    pass


FUNCIONES = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan, "asin": np.arcsin, "acos": np.arccos,
    "atan": np.arctan, "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh, "asinh": np.arcsinh,
    "acosh": np.arccosh, "atanh": np.arctanh, "log10": np.log10, "log": np.log, "exp": np.exp,
    "sqrt": np.sqrt, "int": np.rint, "abs": np.abs,
}

_OPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide,
        ast.Pow: np.power, ast.Mod: np.mod}
_CMP = {ast.Eq: np.equal, ast.NotEq: np.not_equal, ast.Lt: np.less, ast.LtE: np.less_equal,
        ast.Gt: np.greater, ast.GtE: np.greater_equal}


def _traducir(expr: str) -> str:
    e = expr.replace("<>", "!=").replace("^", "**")
    e = re.sub(r"(?<![<>!=:])=(?!=)", "==", e)
    e = re.sub(r"\bif\s*\(", "_si_(", e, flags=re.I)   # 'if' es palabra reservada de Python
    return e


def dividir(texto: str) -> tuple[list[tuple[str, str]], str]:
    """Separa asignaciones y expresión final."""
    partes = [p.strip() for p in texto.replace("\r", "").split(";")]
    partes = [p for p in partes if p]
    if not partes:
        raise ErrorFormula("(No function has been parsed yet)")
    asign, final = [], partes[-1]
    for p in partes[:-1]:
        if ":=" not in p:
            raise ErrorFormula("Syntax error: Operator expected")
        k, v = p.split(":=", 1)
        asign.append((k.strip(), v.strip()))
    if ":=" in final:
        k, v = final.split(":=", 1)
        asign.append((k.strip(), v.strip()))
        final = k.strip()
    return asign, final


def variables_entrada(texto: str) -> list[str]:
    asign, final = dividir(texto)
    usados = set(re.findall(r"\bX(\d+)\b", " ".join(v for _, v in asign) + " " + final))
    return [f"X{i}" for i in sorted(int(u) for u in usados)]


def _evaluar(nodo, env):
    if isinstance(nodo, ast.Expression):
        return _evaluar(nodo.body, env)
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
        return float(nodo.value)
    if isinstance(nodo, ast.Name):
        if nodo.id not in env:
            raise ErrorFormula(f"Syntax error: Unknown identifier ({nodo.id})")
        return env[nodo.id]
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPS:
        return _OPS[type(nodo.op)](_evaluar(nodo.left, env), _evaluar(nodo.right, env))
    if isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, (ast.USub, ast.UAdd)):
        v = _evaluar(nodo.operand, env)
        return -v if isinstance(nodo.op, ast.USub) else v
    if isinstance(nodo, ast.Compare) and len(nodo.ops) == 1 and type(nodo.ops[0]) in _CMP:
        return _CMP[type(nodo.ops[0])](_evaluar(nodo.left, env),
                                       _evaluar(nodo.comparators[0], env)).astype(float)
    if isinstance(nodo, ast.BoolOp):
        vals = [_evaluar(v, env) != 0 for v in nodo.values]
        f = np.logical_and if isinstance(nodo.op, ast.And) else np.logical_or
        r = vals[0]
        for v in vals[1:]:
            r = f(r, v)
        return r.astype(float)
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
        nombre = nodo.func.id.lower()
        args = [_evaluar(a, env) for a in nodo.args]
        if nombre == "_si_":
            if len(args) != 3:
                raise ErrorFormula("Illegal number of parameters to function")
            return np.where(args[0] != 0, args[1], args[2])
        if nombre in FUNCIONES:
            if len(args) != 1:
                raise ErrorFormula("Illegal number of parameters to function")
            return FUNCIONES[nombre](args[0])
        raise ErrorFormula(f"Syntax error: Unknown identifier ({nodo.func.id})")
    raise ErrorFormula("Syntax error")


def evaluar(texto: str, entradas: dict[str, np.ndarray]) -> np.ndarray:
    asign, final = dividir(texto)
    n = len(next(iter(entradas.values()))) if entradas else 1
    env = {k: np.asarray(v, dtype=float) for k, v in entradas.items()}
    nulos = np.zeros(n, dtype=bool)
    for v in env.values():
        nulos |= v == NULO
    with np.errstate(all="ignore"):
        for k, expr in asign:
            env[k] = _compilar_y_evaluar(expr, env, n)
        r = _compilar_y_evaluar(final, env, n)
    r = np.broadcast_to(r, (n,)).astype(float).copy()
    r[nulos | ~np.isfinite(r)] = NULO
    return r


def _compilar_y_evaluar(expr: str, env, n):
    if expr.count("(") != expr.count(")"):
        raise ErrorFormula("Mismatched parenthesis")
    try:
        arbol = ast.parse(_traducir(expr), mode="eval")
    except SyntaxError as e:
        raise ErrorFormula("Syntax error") from e
    return np.broadcast_to(_evaluar(arbol, env), (n,)).astype(float)
