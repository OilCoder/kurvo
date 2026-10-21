"""Operaciones sobre registros LAS: registro parcial, filtro, combinación, compuesto y TVD/MD."""
from __future__ import annotations

import numpy as np

from .comun import NULO, formato_num
from .historial import remuestrear_a
from .las import Mnemonico, RegistroLAS
from .trayectoria import Trayectoria


def log_parcial(reg: RegistroLAS, fila_ini: int, fila_fin: int, nombre: str) -> RegistroLAS:
    """Filas inicio–fin (base 1, inclusivas) en un registro nuevo."""
    if not nombre.strip():
        raise ValueError("Empty name is not allowed! Please set new name.")
    a, b = sorted((fila_ini, fila_fin))
    nuevo = reg.copia()
    nuevo.nombre = nombre.strip()
    for c in nuevo.columnas:
        c.datos = c.datos[a - 1:b]
    return nuevo


def filtrar(reg: RegistroLAS, col: int, operador: str, v1: float, v2: float = 0.0,
            accion: str = "Delete rows") -> int:
    """Borra filas o anula valores que cumplen la condición. Devuelve el nº afectado."""
    d = reg.columnas[col].datos
    cond = {">=": d >= v1, "<=": d <= v1, "between": (d >= v1) & (d <= v2),
            "is null": d == NULO, "not null": d != NULO}[operador]
    if accion == "Delete rows":
        for c in reg.columnas:
            c.datos = c.datos[~cond]
    else:
        d[cond] = NULO
    return int(cond.sum())


def combinar(a: RegistroLAS, b: RegistroLAS, nombre: str = "Merged") -> RegistroLAS:
    """Combine Las Files: columnas de b remuestreadas a la profundidad MD de a (nulo fuera de rango)."""
    if not (a.existe_columna(a.indice_md) and b.existe_columna(b.indice_md)):
        raise ValueError('Please select log column for "Depth MD" and "Depth TVD".')
    nuevo = a.copia()
    nuevo.nombre = nombre or "Merged"
    md = a.columnas[a.indice_md].datos
    pb = b.columnas[b.indice_md]
    lo, hi = pb.minimo(), pb.maximo()
    for k, c in enumerate(b.columnas):
        if k == b.indice_md or nuevo.indice_columna(c.nombre) >= 0:
            continue
        datos = np.array([b.valor_en(x, b.indice_md, k) if (x != NULO and lo <= x <= hi) else NULO
                          for x in md])
        nuevo.agregar_columna(c.nombre, datos, c.unidad, c.descripcion)
    return nuevo


def _iguales(a, b, ok) -> bool:
    """Mismos valores donde las dos curvas tienen dato (redondeo de 1e-3 o 1e-4 relativo)."""
    return bool(np.all(np.abs(a[ok] - b[ok]) <= np.maximum(1e-3, 1e-4 * np.abs(a[ok]))))


def _nombre_libre(reg: RegistroLAS, nombre: str) -> str:
    k = 2
    while reg.indice_columna(f"{nombre}_{k}") >= 0:
        k += 1
    return f"{nombre}_{k}"


def componer(registros: list[RegistroLAS], nombre: str = "Composite", paso: float | None = None) -> RegistroLAS:
    """Registro compuesto de un pozo (D110): todas las curvas de sus registros en una sola tabla de
    profundidad, del tope más somero a la base más profunda, con el paso más fino (o `paso`).

    Los LAS del KGS traen cada corrida de herramienta en un archivo (`_part1`, `_part2`...): misma
    profundidad, curvas distintas. Si una curva se repite con los mismos valores (copias exactas,
    p. ej. Deighton_1 part1 y part2) se queda una y la copia solo rellena sus nulos; si los valores
    difieren (otra pasada u otra digitalización: el DT de Katie_1-28 part3 y part4 difiere hasta
    68 µs/ft) se guardan las dos, la segunda como NOMBRE_2. La descripción dice de qué registro sale
    cada curva. Los registros originales no se tocan."""
    from .unidades import canonica, convertir, magnitud
    from .validacion import paso_regular
    fuentes = [r for r in registros if r.existe_columna(r.indice_md) and r.n_filas]
    if len(fuentes) < 2:
        raise ValueError("The well needs at least two logs with a depth column.")
    unidad = fuentes[0].columnas[fuentes[0].indice_md].unidad
    profs = []
    for r in fuentes:
        c = r.columnas[r.indice_md]
        p = np.asarray(c.datos, float)
        if canonica(c.unidad) != canonica(unidad) and magnitud(c.unidad) == magnitud(unidad) == "length":
            p = convertir(p, c.unidad, unidad)
        profs.append(p)
    validas = [p[(p != NULO) & np.isfinite(p)] for p in profs]
    if paso is None:
        pasos = [paso_regular(p) or (float(np.median(np.diff(np.sort(v)))) if v.size > 1 else 0.0)
                 for p, v in zip(profs, validas)]
        pasos = [abs(x) for x in pasos if x and np.isfinite(x)]
        paso = min(pasos) if pasos else 0.5
    if paso <= 0:
        raise ValueError("The depth step must be greater than zero.")
    lo = min(float(v.min()) for v in validas if v.size)
    hi = max(float(v.max()) for v in validas if v.size)
    md = lo + paso * np.arange(int(round((hi - lo) / paso)) + 1)
    base = fuentes[0]
    nuevo = RegistroLAS(nombre or "Composite", mnemonicos=[Mnemonico(**vars(m)) for m in base.mnemonicos
                                                           if m.seccion != 2],
                        nombre_pozo=base.nombre_pozo, nulo_archivo=base.nulo_archivo, cabecera=base.cabecera)
    nuevo.agregar_columna(base.columnas[base.indice_md].nombre or "DEPT", md, unidad,
                          base.columnas[base.indice_md].descripcion)
    nuevo.indice_md = 0
    for m in nuevo.mnemonicos:              # la cabecera del primero, con el intervalo del compuesto
        if m.seccion == 1 and m.nombre.upper() in ("STRT", "STOP", "STEP"):
            m.valor, m.unidad = formato_num({"STRT": lo, "STOP": float(md[-1]), "STEP": paso}[m.nombre.upper()]), unidad
    for r, p in zip(fuentes, profs):
        for k, c in enumerate(r.columnas):
            if k == r.indice_md:
                continue
            datos = remuestrear_a(p, c.datos, md)
            nuevos = (datos != NULO) & np.isfinite(datos)
            if not nuevos.any():
                continue
            j = nuevo.indice_columna(c.nombre)
            if j >= 0 and canonica(nuevo.columnas[j].unidad) == canonica(c.unidad):
                previo = nuevo.columnas[j].datos
                ok = nuevos & (previo != NULO)
                if _iguales(previo, datos, ok):
                    previo[nuevos & (previo == NULO)] = datos[nuevos & (previo == NULO)]
                    continue
            desc = f"{c.descripcion} [{r.nombre}]".strip()
            nuevo.agregar_columna(c.nombre if j < 0 else _nombre_libre(nuevo, c.nombre), datos, c.unidad, desc)
            if k == r.indice_tvd and nuevo.indice_tvd < 0:
                nuevo.indice_tvd = nuevo.n_columnas - 1
    return nuevo


def crear_tvd(reg: RegistroLAS, tray: Trayectoria, nombre: str = "TVD") -> int:
    if not reg.existe_columna(reg.indice_md):
        raise ValueError('Please select log column for "Depth MD" and "Depth TVD".')
    md = reg.columnas[reg.indice_md].datos
    reg.agregar_columna(nombre, np.array([NULO if v == NULO else tray.tvd_en(v) for v in md]),
                        reg.columnas[reg.indice_md].unidad)
    reg.indice_tvd = reg.n_columnas - 1
    return reg.indice_tvd


def crear_md(reg: RegistroLAS, tray: Trayectoria, nombre: str = "MD") -> int:
    if not reg.existe_columna(reg.indice_tvd):
        raise ValueError('Please select log column for "Depth MD" and "Depth TVD".')
    tvd = reg.columnas[reg.indice_tvd].datos
    reg.agregar_columna(nombre, np.array([NULO if v == NULO else tray.md_en(v) for v in tvd]),
                        reg.columnas[reg.indice_tvd].unidad)
    reg.indice_md = reg.n_columnas - 1
    return reg.indice_md
