"""Registro LAS en memoria: cabecera, curvas, profundidades MD/TVD y lectura/escritura LAS 2.0."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .comun import NULO, UID, a_float, entre, escribir_lineas, leer_lineas
from .historial import Historial

MAX_COLUMNAS = 10000
SECCIONES = ("~v", "~w", "~c", "~p", "~o", "~a")


class ErrorLAS(Exception):
    pass


@dataclass
class Mnemonico:
    nombre: str
    unidad: str = ""
    valor: str = ""
    descripcion: str = ""
    seccion: int = 0          # 0=V 1=W 2=C 3=P 4=O


@dataclass
class Columna:
    nombre: str
    datos: np.ndarray
    unidad: str = ""
    descripcion: str = ""

    def minimo(self) -> float:
        v = self.datos[self.datos != NULO]
        return float(v.min()) if v.size else 0.0

    def maximo(self) -> float:
        v = self.datos[self.datos != NULO]
        return float(v.max()) if v.size else 0.0


def es_mnemonico(linea: str) -> bool:
    """Línea no comentada que contiene '.' y ':'."""
    t = linea.strip()
    return bool(t) and not t.startswith("#") and "." in t and ":" in t


def parse_mnemonico(linea: str, seccion: int = 0) -> Mnemonico:
    """MNEM.UNIDAD VALOR : DESCRIPCIÓN."""
    t = linea.strip()
    nombre, resto = t.split(".", 1)
    if ":" in resto:
        antes, desc = resto.rsplit(":", 1)
    else:
        antes, desc = resto, ""
    if antes[:1].isspace() or not antes:
        unidad, valor = "", antes.strip()
    else:
        partes = antes.split(None, 1)
        unidad = partes[0]
        valor = partes[1].strip() if len(partes) > 1 else ""
    return Mnemonico(nombre.strip(), unidad.strip(), valor, desc.strip(), seccion)


@dataclass
class RegistroLAS:
    nombre: str = ""
    columnas: list[Columna] = field(default_factory=list)
    mnemonicos: list[Mnemonico] = field(default_factory=list)
    nombre_pozo: str = ""
    nulo_archivo: float = NULO
    wrap: bool = False
    cabecera: str = ""
    indice_md: int = -1
    indice_tvd: int = -1
    uid: int = field(default_factory=UID.nuevo)
    ruta: str = ""
    historial: Historial = field(default_factory=Historial, repr=False, compare=False)

    # ------------------------------------------------------------------ columnas
    @property
    def n_columnas(self) -> int:
        return len(self.columnas)

    @property
    def n_filas(self) -> int:
        return max((len(c.datos) for c in self.columnas), default=0)

    def nombres(self) -> list[str]:
        return [c.nombre for c in self.columnas]

    def indice_columna(self, nombre: str) -> int:
        for i, c in enumerate(self.columnas):
            if c.nombre == nombre:
                return i
        u = nombre.upper()
        for i, c in enumerate(self.columnas):
            if c.nombre.upper() == u:
                return i
        return -1

    def existe_columna(self, i: int) -> bool:
        return 0 <= i < len(self.columnas)

    def columna(self, ref) -> Columna:
        return self.columnas[ref if isinstance(ref, int) else self.indice_columna(ref)]

    def agregar_columna(self, nombre: str, datos=None, unidad: str = "",
                        descripcion: str = "") -> Columna:
        n = self.n_filas
        if datos is None:
            datos = np.full(n, NULO)
        col = Columna(nombre, np.asarray(datos, dtype=float), unidad, descripcion)
        self.columnas.append(col)
        return col

    def agregar_lineal(self, nombre: str, inicio: float, paso: float, n: int) -> Columna:
        return self.agregar_columna(nombre, inicio + paso * np.arange(n))

    def borrar_columna(self, i: int) -> None:
        del self.columnas[i]
        for attr in ("indice_md", "indice_tvd"):
            v = getattr(self, attr)
            if v == i:
                setattr(self, attr, -1)
            elif v > i:
                setattr(self, attr, v - 1)

    def mover_columna(self, i: int, destino: int) -> None:
        col = self.columnas.pop(i)
        destino = max(0, min(destino, len(self.columnas)))
        self.columnas.insert(destino, col)

    def borrar_fila(self, fila: int) -> None:
        for c in self.columnas:
            c.datos = np.delete(c.datos, fila)

    def fijar_indices(self, md: int, tvd: int) -> None:
        """Columnas de profundidad MD y TVD (-1 si no hay)."""
        self.indice_md, self.indice_tvd = md, tvd

    def mnemonico(self, nombre: str) -> Mnemonico | None:
        """Mnemónico de la cabecera; busca en todas las secciones."""
        for m in self.mnemonicos:
            if m.nombre.upper() == nombre.upper():
                return m
        return None

    # ------------------------------------------------------------- consultas
    def valor_en(self, prof: float, col_prof: int, col_valor: int) -> float:
        """Interpolación lineal; 0.0 si la profundidad queda fuera."""
        if not (self.existe_columna(col_prof) and self.existe_columna(col_valor)):
            return 0.0
        p = self.columnas[col_prof].datos
        v = self.columnas[col_valor].datos
        resultado = 0.0
        for i in range(1, len(p)):
            d0, d1 = p[i - 1], p[i]
            v0, v1 = v[i - 1], v[i]
            if d1 < d0:
                d0, d1, v0, v1 = d1, d0, v1, v0
            if entre(prof, d0, d1):
                if d1 == d0:
                    return float(v0)
                return float((prof - d0) / (d1 - d0) * (v1 - v0) + v0)
        return resultado

    def datos_en_md(self, md: float) -> list[float]:
        """Valor de cada columna a la profundidad MD."""
        return [self.valor_en(md, self.indice_md, c) for c in range(self.n_columnas)]

    # ------------------------------------------------------------- archivo
    @classmethod
    def abrir(cls, ruta: str | Path, nombre: str | None = None) -> "RegistroLAS":
        lineas = leer_lineas(ruta)
        reg = cls.desde_lineas(lineas)
        reg.nombre = nombre or Path(ruta).stem
        reg.ruta = str(ruta)
        return reg

    @classmethod
    def desde_lineas(cls, lineas: list[str]) -> "RegistroLAS":
        pos = {s: -1 for s in SECCIONES}
        for i, linea in enumerate(lineas):
            t = linea.strip().lower()
            for s in SECCIONES:
                if t.startswith(s) and pos[s] == -1:
                    pos[s] = i
            if min(pos["~v"], pos["~w"], pos["~c"]) >= 0 and pos["~a"] >= 0:
                break
        if min(pos["~v"], pos["~w"], pos["~c"], pos["~a"]) < 0:
            raise ErrorLAS("Error! Missing log header section. Las File could not be opened.")

        reg = cls()
        for indice, s in enumerate(("~v", "~w", "~c", "~p", "~o")):
            if pos[s] < 0:
                continue
            j = pos[s] + 1
            while j < len(lineas) and not lineas[j].strip().startswith("~"):
                if es_mnemonico(lineas[j]):
                    m = parse_mnemonico(lineas[j], indice)
                    reg.mnemonicos.append(m)
                    if indice == 2 and len(reg.columnas) < MAX_COLUMNAS:
                        reg.columnas.append(Columna(m.nombre, np.zeros(0), m.unidad, m.descripcion))
                j += 1
        reg.cabecera = "\n".join(l.strip() for l in lineas[:pos["~a"]])

        m = reg.mnemonico("NULL")
        if m is not None:
            reg.nulo_archivo = a_float(m.valor, NULO)
        m = reg.mnemonico("WRAP")
        reg.wrap = m is not None and m.valor.strip().upper() == "YES"
        m = reg.mnemonico("WELL")
        if m is not None:
            reg.nombre_pozo = m.valor

        ncol = len(reg.columnas)
        if ncol and not reg.wrap:
            # camino rápido (D90): todas las filas con ncol números → un solo np.array
            filas_txt = [t for t in (l.strip() for l in lineas[pos["~a"] + 1:]) if t and not t.startswith("#")]
            partes = [t.split() for t in filas_txt]
            if all(len(p) == ncol for p in partes):
                try:
                    datos = np.array(partes, dtype=float).reshape(-1, ncol)
                except ValueError:
                    datos = None
                if datos is not None:
                    for k, c in enumerate(reg.columnas):
                        c.datos = datos[:, k].copy()
                    return reg
        if ncol:
            valores: list[float] = []
            filas: list[list[float]] = []
            for linea in lineas[pos["~a"] + 1:]:
                t = linea.strip()
                if not t or t.startswith("#"):
                    continue
                tokens = [a_float(x, NULO) for x in t.split()]
                if reg.wrap:
                    valores.extend(tokens)
                    while len(valores) >= ncol:
                        filas.append(valores[:ncol])
                        valores = valores[ncol:]
                else:
                    fila = tokens[:ncol] + [NULO] * (ncol - len(tokens))
                    filas.append(fila)
            datos = np.array(filas, dtype=float).reshape(-1, ncol)
            for k, c in enumerate(reg.columnas):
                c.datos = datos[:, k].copy()
        return reg

    def lineas_las(self, pozo: str = "") -> list[str]:
        """LAS 2.0 con datos %15.5lf. Escribe una
        cabecera LAS 2.0 completa: STRT/STOP/STEP/NULL calculados de los datos, WELL y el resto de
        mnemónicos de ~W y ~P que traía el archivo."""
        from .comun import formato_num
        from .validacion import SECCION_W, valores_cabecera
        out = ["~Version Information", "VERS. 2.0: ", "WRAP. NO: ", "~Well Information"]
        vals = valores_cabecera(self)
        unidad = self.columnas[self.indice_md].unidad if self.existe_columna(self.indice_md) else ""
        propios = {"STRT": "START DEPTH", "STOP": "STOP DEPTH", "STEP": "STEP", "NULL": "NULL VALUE"}
        for n, d in propios.items():
            if n in vals:
                out.append(f"{n}.{unidad if n != 'NULL' else ''} {formato_num(vals[n])} : {d}")
        w = [m for m in self.mnemonicos if m.seccion == SECCION_W and m.nombre.upper() not in propios]
        if not any(m.nombre.upper() == "WELL" for m in w):
            out.append(f"WELL. {self.nombre_pozo.strip() or pozo or self.nombre} : WELL")
        out += [f"{m.nombre}.{m.unidad} {m.valor} : {m.descripcion}" for m in w]
        out.append("~Curve Information")
        for c in self.columnas:
            out.append(f"{c.nombre}.{c.unidad} \t \t:\t {c.descripcion}")
        par = [m for m in self.mnemonicos if m.seccion == 3]
        if par:
            out.append("~Parameter Information")
            out += [f"{m.nombre}.{m.unidad} {m.valor} : {m.descripcion}" for m in par]
        out += ["~Other information", "~A"]
        n = self.n_filas
        if n and self.columnas:
            # una sola operación de formato por fila (mismo texto que columna a columna, D90)
            m = np.full((n, len(self.columnas)), NULO)
            for k, c in enumerate(self.columnas):
                m[:len(c.datos), k] = c.datos[:n]
            fmt = "%15.5f\t" * len(self.columnas)
            out += [fmt % fila for fila in map(tuple, m.tolist())]
        return out

    def guardar(self, ruta: str | Path, pozo: str = "") -> None:
        escribir_lineas(ruta, self.lineas_las(pozo))

    def copia(self) -> "RegistroLAS":
        nuevo = RegistroLAS(self.nombre, [Columna(c.nombre, c.datos.copy(), c.unidad, c.descripcion)
                                          for c in self.columnas],
                            [Mnemonico(**vars(m)) for m in self.mnemonicos], self.nombre_pozo,
                            self.nulo_archivo, self.wrap, self.cabecera,
                            self.indice_md, self.indice_tvd)
        return nuevo
