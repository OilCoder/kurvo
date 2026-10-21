"""Identidad del pozo a partir de la cabecera LAS (v0.5, D104).

Con los LAS reales del Kansas Geological Survey (data/) se vio que:
- WELL suele traer solo el número del pozo ("1", "2", "1-28") y el nombre está en LEAS o LEASE
  ("Katie 1-28", o "REIN 'A'" sin el número en los archivos antiguos). Usar WELL a secas juntaba
  105 archivos de pozos distintos en un pozo "1".
- Un mismo pozo llega en varios archivos (`_part1`, `_part2`...) con el mismo UWI/API: el UWI
  identifica el pozo aunque el nombre cambie de mayúsculas entre archivos.
- LAT/LONG (o X/Y) dan las coordenadas del pozo.
- La sección ~Other trae los topes de formación como tabla CSV "BASE,TOP,FORMATION"."""
from __future__ import annotations

import math
import re

from .comun import NULO, a_float

SECCION_W = 1
LEASE = ("LEAS", "LEASE")
IDENTIFICADORES = ("UWI", "API")
NULOS_TEXTO = ("", "NAN", "NONE", "NULL", "N/A", "-999.25")
# colores de las zonas creadas desde los topes del LAS (se distinguen en el log plot)
COLORES_TOPES = ("rgb(200,30,30)", "rgb(30,90,200)", "rgb(20,140,60)", "rgb(170,60,170)", "rgb(220,120,0)",
                 "rgb(0,140,150)", "rgb(120,80,30)", "rgb(90,90,90)")


def _num(texto) -> float:
    v = a_float(texto, NULO)
    return v if math.isfinite(v) else NULO


def _valor(reg, nombres, seccion: int | None = SECCION_W) -> str:
    for n in nombres:
        for m in reg.mnemonicos:
            if m.nombre.strip().upper() == n and (seccion is None or m.seccion == seccion):
                v = m.valor.strip()
                if v.upper() not in NULOS_TEXTO:
                    return v
    return ""


def nombre_pozo(reg, respaldo: str = "") -> str:
    """Nombre del pozo: LEASE + WELL cuando WELL es solo el número ("REIN 'A'" + "2" → "REIN 'A' 2");
    LEASE si ya termina con el número ("Katie 1-28"); WELL si no hay LEASE; si no, `respaldo`."""
    pozo = (reg.nombre_pozo or "").strip()
    if pozo.upper() in NULOS_TEXTO:
        pozo = ""
    lease = _valor(reg, LEASE)
    if not lease:
        return pozo or respaldo
    if not pozo:
        return lease
    l, w = " ".join(lease.upper().split()), " ".join(pozo.upper().split())
    if l == w or l.endswith(" " + w) or l.endswith("#" + w):
        return " ".join(lease.split())
    if w.startswith(l):              # WELL ya trae el nombre completo
        return " ".join(pozo.split())
    return f"{' '.join(lease.split())} {' '.join(pozo.split())}"


def identificador(reg) -> str:
    """UWI o API normalizado (solo dígitos): mismo pozo aunque el texto tenga guiones o no."""
    v = _valor(reg, IDENTIFICADORES, None)
    d = re.sub(r"\D", "", v)
    return d if len(d) >= 8 and set(d) != {"0"} else ""


def coordenadas(reg) -> tuple[float, float] | None:
    """(X, Y) del pozo: X/Y si existen, si no LONG/LAT. None si faltan o no son números."""
    for nx, ny in ((("X", "XCOORD", "X_COORD"), ("Y", "YCOORD", "Y_COORD")),
                   (("LONG", "LON", "LONGITUDE"), ("LAT", "LATI", "LATITUDE"))):
        x, y = _num(_valor(reg, nx)), _num(_valor(reg, ny))
        if x != NULO and y != NULO and (x, y) != (0.0, 0.0):
            return x, y
    return None


REFERENCIAS_KB = ("", "KB", "KELLY BUSHING", "DF", "DERRICK FLOOR", "RT", "ROTARY TABLE", "DRILL FLOOR")


def elevacion_kb(reg) -> float:
    """Elevación de la referencia de profundidad (KB, mesa rotaria o piso de perforación) sobre el
    nivel del mar: EKB; si no, ELEV cuando EREF dice KB/DF/RT o no dice nada (así vienen los LAS del
    KGS: ELEV 1379, EREF KB); si no, EDF. La elevación del terreno (EGL) no sirve. NULO si no hay."""
    v = _num(_valor(reg, ("EKB", "KB", "ELEV_KB"), None))
    if v != NULO and v != 0.0:
        return v
    ref = _valor(reg, ("EREF", "PDAT", "DMF", "LMF"), None).upper().strip()
    v = _num(_valor(reg, ("ELEV", "EPD"), None))
    if v != NULO and v != 0.0 and ref in REFERENCIAS_KB:
        return v
    v = _num(_valor(reg, ("EDF",), None))
    return v if v != 0.0 else NULO


def fijar_kb(pozo, reg) -> bool:
    """Si el pozo no tiene todavía la elevación de referencia (TVD → SS), la toma de la cabecera del
    LAS (D123): así la TVDSS no necesita cargar la KB a mano pozo por pozo."""
    t = pozo.trayectoria
    if t.tvd_a_ss != 0.0:
        return False
    kb = elevacion_kb(reg)
    if kb == NULO:
        return False
    t.tvd_a_ss = kb
    if t.estaciones:
        t.calcular()
    return True


def topes(reg) -> list[tuple[str, float]]:
    """Topes de formación de la sección ~Other: tabla CSV con columnas TOP y FORMATION (o NAME)
    y opcionalmente BASE. Devuelve (formación, profundidad del tope) en el orden del archivo."""
    lineas = (reg.cabecera or "").splitlines()
    dentro, cols, out = False, None, []
    for linea in lineas:
        s = linea.strip()
        if s.startswith("~"):
            dentro, cols = s[:2].upper() == "~O", None
            continue
        if not dentro or not s or s.startswith("#"):
            continue
        partes = [p.strip() for p in s.split(",")]
        if cols is None:
            arriba = [p.upper() for p in partes]
            if "TOP" in arriba and ("FORMATION" in arriba or "NAME" in arriba):
                cols = (arriba.index("TOP"), arriba.index("FORMATION") if "FORMATION" in arriba else arriba.index("NAME"))
            continue
        if len(partes) <= max(cols):
            continue
        prof = _num(partes[cols[0]])
        nombre = ",".join(partes[cols[1]:]) if cols[1] == len(arriba) - 1 else partes[cols[1]]
        if prof != NULO and nombre.strip():
            out.append((nombre.strip(), prof))
    return out


# ------------------------------------------------------------------ en el proyecto
def ubicar_pozo(pr, reg, respaldo: str = "") -> tuple[int, bool]:
    """Pozo del proyecto al que va el registro: el del mismo UWI/API, si no el del mismo nombre
    (sin distinguir mayúsculas) si no tiene otro UWI; si no, uno nuevo con las coordenadas de la
    cabecera (con el UWI en el nombre cuando otro pozo ya se llama igual).
    Devuelve (índice, nuevo)."""
    uwi = identificador(reg)
    if uwi:
        for i, p in enumerate(pr.pozos):
            if any(identificador(r) == uwi for r in p.logs):
                return i, False
    nombre = nombre_pozo(reg, respaldo) or "WellName"
    i = next((k for k, p in enumerate(pr.pozos) if p.nombre.strip().upper() == nombre.upper()), -1)
    if i >= 0:
        otros = {identificador(r) for r in pr.pozos[i].logs} - {""}
        if not uwi or not otros:
            return i, False
        # mismo nombre y otro UWI: es otro pozo (D110). En Schaben "Borger 1" son tres pozos de tres
        # operadores, a 400 m y 1 km, que la descarga guardó como Borger_1_part1…4
        nombre = f"{nombre} ({_valor(reg, IDENTIFICADORES, None)})"
    xy = coordenadas(reg) or (0.0, 0.0)
    pozo = pr.nuevo_pozo(nombre, *xy)
    for z in pr.zonas:              # un pozo nuevo no tiene los topes de las zonas que ya existen
        z.profundidades[-1] = NULO
    return pr.pozos.index(pozo), True


def asignar_topes(pr, i_pozo: int, lista: list[tuple[str, float]]) -> int:
    """Pone los topes en las zonas del proyecto (crea la zona si no existe; en los demás pozos queda
    sin profundidad). No cambia un tope que el pozo ya tiene. Devuelve cuántos se asignaron."""
    n = 0
    for nombre, prof in lista:
        z = next((z for z in pr.zonas if z.nombre.strip().upper() == nombre.upper()), None)
        if z is None:
            z = pr.nueva_zona(nombre)
            z.profundidades[:] = [NULO] * len(pr.pozos)
            z.color = COLORES_TOPES[(len(pr.zonas) - 1) % len(COLORES_TOPES)]
        while len(z.profundidades) < len(pr.pozos):
            z.profundidades.append(NULO)
        if z.profundidades[i_pozo] in (NULO, 0.0):
            z.profundidades[i_pozo] = prof
            n += 1
    return n
