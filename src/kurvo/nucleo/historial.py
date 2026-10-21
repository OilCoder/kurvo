"""Deshacer/rehacer, bitácora de cambios y curvas originales de un registro LAS.

Toda edición de un registro pasa por `aplicar(reg, operación, detalle, función)`: se toma una
foto del registro, se ejecuta la función y, si algo cambió, se apila la foto para deshacer, se
anota el cambio en la bitácora y se guarda la versión original de cada curva modificada (la que
tenía antes de su primera edición), para poder compararla o restaurarla."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

LIMITE = 50              # pasos de deshacer por registro


@dataclass
class Cambio:
    fecha: str
    operacion: str
    columnas: str
    detalle: str = ""
    muestras: int = 0

    def linea(self) -> str:
        return "|".join((self.fecha, self.operacion, self.columnas, self.detalle.replace("|", "/"),
                         str(self.muestras)))

    @classmethod
    def desde_linea(cls, linea: str) -> "Cambio | None":
        c = linea.split("|")
        if len(c) < 3:
            return None
        muestras = int(c[4]) if len(c) > 4 and c[4].strip().lstrip("-").isdigit() else 0
        return cls(c[0], c[1], c[2], c[3] if len(c) > 3 else "", muestras)


@dataclass
class Foto:
    """Estado completo de las columnas de un registro."""
    columnas: list[tuple[str, np.ndarray, str, str]]
    indice_md: int
    indice_tvd: int
    descripcion: str = ""
    cabecera: list = field(default_factory=list)      # mnemónicos (copias)
    nulo_archivo: float = -999.25
    nombre_pozo: str = ""
    grupo: int = 0              # operación compuesta del proyecto a la que pertenece (0 = ninguna)


@dataclass
class CurvaOriginal:
    nombre: str
    datos: np.ndarray
    unidad: str = ""
    prof: np.ndarray | None = None       # profundidad MD de la versión original (si había)


@dataclass
class Historial:
    deshacer: list[Foto] = field(default_factory=list)
    rehacer: list[Foto] = field(default_factory=list)
    bitacora: list[Cambio] = field(default_factory=list)
    originales: dict[str, CurvaOriginal] = field(default_factory=dict)

    @property
    def puede_deshacer(self) -> bool:
        return bool(self.deshacer)

    @property
    def puede_rehacer(self) -> bool:
        return bool(self.rehacer)

    def anotar(self, operacion: str, columnas: str, detalle: str = "", muestras: int = 0) -> Cambio:
        c = Cambio(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), operacion, columnas, detalle, muestras)
        self.bitacora.append(c)
        return c


def foto(reg, descripcion: str = "") -> Foto:
    import copy
    return Foto([(c.nombre, c.datos.copy(), c.unidad, c.descripcion) for c in reg.columnas],
                reg.indice_md, reg.indice_tvd, descripcion, copy.deepcopy(reg.mnemonicos),
                reg.nulo_archivo, reg.nombre_pozo)


def restaurar(reg, f: Foto) -> None:
    from .las import Columna
    reg.columnas = [Columna(n, d.copy(), u, s) for n, d, u, s in f.columnas]
    reg.indice_md, reg.indice_tvd = f.indice_md, f.indice_tvd
    import copy
    reg.mnemonicos = copy.deepcopy(f.cabecera)
    reg.nulo_archivo, reg.nombre_pozo = f.nulo_archivo, f.nombre_pozo


def _diferencias(antes: Foto, reg) -> tuple[list[str], int]:
    """Columnas cambiadas (nombres actuales) y nº de muestras distintas."""
    previas = {n: (d, u, s) for n, d, u, s in antes.columnas}
    cambiadas, muestras = [], 0
    for c in reg.columnas:
        p = previas.get(c.nombre)
        if p is None:
            cambiadas.append(c.nombre)
            muestras += len(c.datos)
            continue
        d = p[0]
        if len(d) != len(c.datos):
            cambiadas.append(c.nombre)
            muestras += abs(len(d) - len(c.datos)) or len(c.datos)
        else:
            n = int(np.count_nonzero(~((d == c.datos) | (np.isnan(d) & np.isnan(c.datos)))))
            if n or p[1] != c.unidad or p[2] != c.descripcion:
                cambiadas.append(c.nombre)
                muestras += n
    actuales = set(reg.nombres())
    borradas = [n for n, *_ in antes.columnas if n not in actuales]
    estructura = [n for n, *_ in antes.columnas] != reg.nombres() or \
        (antes.indice_md, antes.indice_tvd) != (reg.indice_md, reg.indice_tvd)
    if borradas or (estructura and not cambiadas):
        cambiadas += borradas or ["(structure)"]
    if not cambiadas and ([vars(m) for m in antes.cabecera] != [vars(m) for m in reg.mnemonicos]
                          or antes.nulo_archivo != reg.nulo_archivo or antes.nombre_pozo != reg.nombre_pozo):
        cambiadas.append("(header)")
    return cambiadas, muestras


# operación compuesta en curso (ver nucleo/historial_proyecto.py): grupo y registros tocados
_compuesta: dict | None = None


def aplicar(reg, operacion: str, detalle: str, funcion, *args, **kwargs):
    """Ejecuta `funcion(*args, **kwargs)` registrando el cambio; devuelve su resultado."""
    h: Historial = reg.historial
    antes = foto(reg, operacion)
    if _compuesta is not None:
        antes.grupo = _compuesta["grupo"]
        _compuesta["tocados"].setdefault(id(reg), (reg, reg.nombres()))
    resultado = funcion(*args, **kwargs)
    cambiadas, muestras = _diferencias(antes, reg)
    if not cambiadas:
        return resultado
    h.deshacer.append(antes)
    del h.deshacer[:-LIMITE]
    h.rehacer.clear()
    _guardar_originales(h, antes, cambiadas)
    h.anotar(operacion, ", ".join(cambiadas), detalle, muestras)
    return resultado


def _guardar_originales(h: Historial, antes: Foto, cambiadas=None) -> None:
    """Primera versión conocida de cada curva modificada (se guarda antes de su primera edición).
    Hasta v0.2 se guardaban todas las curvas del registro en la primera edición (D68)."""
    prof = antes.columnas[antes.indice_md][1] if 0 <= antes.indice_md < len(antes.columnas) else None
    for n, d, u, _ in antes.columnas:
        if cambiadas is not None and n not in cambiadas:
            continue
        if n not in h.originales:
            h.originales[n] = CurvaOriginal(n, d.copy(), u, None if prof is None else prof.copy())


def deshacer(reg) -> str | None:
    h: Historial = reg.historial
    if not h.deshacer:
        return None
    f = h.deshacer.pop()
    h.rehacer.append(foto(reg, f.descripcion))
    h.rehacer[-1].grupo = f.grupo
    restaurar(reg, f)
    h.anotar("Undo", "", f.descripcion)
    return f.descripcion


def rehacer(reg) -> str | None:
    h: Historial = reg.historial
    if not h.rehacer:
        return None
    f = h.rehacer.pop()
    h.deshacer.append(foto(reg, f.descripcion))
    h.deshacer[-1].grupo = f.grupo
    restaurar(reg, f)
    h.anotar("Redo", "", f.descripcion)
    return f.descripcion


def renombrar_original(reg, viejo: str, nuevo: str) -> None:
    o = reg.historial.originales.pop(viejo, None)
    if o is not None:
        o.nombre = nuevo
        reg.historial.originales[nuevo] = o


def original(reg, nombre: str) -> CurvaOriginal | None:
    return reg.historial.originales.get(nombre)


def restaurar_original(reg, nombre: str) -> bool:
    """Devuelve la curva a su versión original (remuestreada a la profundidad actual si cambió)."""
    o = original(reg, nombre)
    i = reg.indice_columna(nombre)
    if o is None or i < 0:
        return False

    def _poner():
        col = reg.columnas[i]
        if len(o.datos) == len(col.datos):
            col.datos = o.datos.copy()
        elif o.prof is not None and reg.existe_columna(reg.indice_md):
            col.datos = remuestrear_a(o.prof, o.datos, reg.columnas[reg.indice_md].datos)
        else:
            raise ValueError("The original curve has a different number of samples and no depth.")
        col.unidad = o.unidad
    aplicar(reg, "Restore original", nombre, _poner)
    return True


def remuestrear_a(prof_origen, valores, prof_destino):
    """Interpolación lineal que respeta nulos (no interpola a través de un nulo)."""
    from .comun import NULO
    p = np.asarray(prof_origen, float)
    v = np.asarray(valores, float)
    q = np.asarray(prof_destino, float)
    ok = (p != NULO) & np.isfinite(p)
    p, v = p[ok], v[ok]
    orden = np.argsort(p, kind="stable")
    p, v = p[orden], v[orden]
    out = np.full(q.shape, NULO)
    if len(p) == 0:
        return out
    j = np.searchsorted(p, q, side="right")
    qv = (q != NULO) & np.isfinite(q)
    a = np.clip(j - 1, 0, len(p) - 1)
    exacta = qv & (j > 0) & (p[a] == q)
    out[exacta] = v[a[exacta]]
    b = np.clip(j, 0, len(p) - 1)
    interior = qv & ~exacta & (j > 0) & (j < len(p))
    interior &= (v[a] != NULO) & (v[b] != NULO)
    dp = p[b] - p[a]
    with np.errstate(invalid="ignore", divide="ignore"):
        t = np.where(dp != 0, (q - p[a]) / dp, 0.0)
    out[interior] = (v[a] + (v[b] - v[a]) * t)[interior]
    return out


# ------------------------------------------------------------------ persistencia en el proyecto
def lineas_bitacora(h: Historial) -> list[str]:
    return ["#DATE|OPERATION|COLUMNS|DETAIL|SAMPLES"] + [c.linea() for c in h.bitacora]


def leer_bitacora(h: Historial, lineas: list[str]) -> None:
    h.bitacora = [c for c in (Cambio.desde_linea(l) for l in lineas if l.strip() and not l.startswith("#"))
                  if c is not None]


def lineas_originales(h: Historial) -> list[str]:
    """Curvas originales en texto: '#CURVE|UNIT|N' seguido de N líneas 'prof valor'."""
    from .comun import NULO
    out = []
    for o in h.originales.values():
        out.append(f"#CURVE|{o.nombre}|{o.unidad}|{len(o.datos)}")
        prof = o.prof if o.prof is not None and len(o.prof) == len(o.datos) else np.full(len(o.datos), NULO)
        out += [f"{a:.6f} {b:.6f}" for a, b in zip(prof, o.datos)]
    return out


def leer_originales(h: Historial, lineas: list[str]) -> None:
    from .comun import NULO
    i = 0
    while i < len(lineas):
        l = lineas[i]
        if l.startswith("#CURVE|"):
            c = l.split("|")
            n = int(c[3]) if len(c) > 3 and c[3].isdigit() else 0
            filas = [x.split() for x in lineas[i + 1:i + 1 + n]]
            arr = np.array([[float(a), float(b)] for a, b in filas], float).reshape(-1, 2)
            prof = arr[:, 0] if arr.size and not np.all(arr[:, 0] == NULO) else None
            h.originales[c[1]] = CurvaOriginal(c[1], arr[:, 1].copy(), c[2], prof)
            i += n + 1
        else:
            i += 1
