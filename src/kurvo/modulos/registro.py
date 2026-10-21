"""Descubre automáticamente los módulos de esta carpeta."""
from __future__ import annotations

import importlib
import inspect
import pkgutil

from . import base


def descubrir_modulos() -> list[base.Modulo]:
    from .. import modulos as paquete

    encontrados = []
    for info in pkgutil.iter_modules(paquete.__path__):
        if info.name in ("base", "registro"):
            continue
        try:
            mod = importlib.import_module(f"{paquete.__name__}.{info.name}")
        except Exception as e:  # noqa: BLE001
            print(f"[módulos] No se pudo cargar {info.name}: {e}")
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, base.Modulo) and cls is not base.Modulo \
                    and not cls.__name__.startswith("_") \
                    and cls.__module__ == mod.__name__:
                encontrados.append(cls())
    return sorted(encontrados, key=lambda m: m.nombre)
