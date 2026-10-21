"""Módulo "Advance Log Analysis": arcillosidad, porosidad y saturación (calculos/petrofisica.py)."""
from __future__ import annotations

from ..i18n import tr
from ..calculos import petrofisica as pf
from ..vista.dialogos import Campo, aviso, pedir
from .base import Modulo, agregar_resultado, contexto

LIMITAR = "Limit result to 0.0 - 1.0"


class AdvanceLogAnalysis(Modulo):
    nombre = "Advance Log Analysis"
    descripcion = "VShale, porosidad y saturación de agua sobre el LAS activo."

    def acciones_editor_logs(self, app):
        f = lambda m: (lambda: self._ejecutar(app, m))  # noqa: E731
        return [("VShale", [("From Gamma Ray Log", f("gr")), ("From Spontaneous Potential Log", f("sp")),
                            ("From Neutron Porosity", f("n")), ("From Neutron Density Porosity", f("nd"))]),
                ("Porosity", [("From Density Log", f("den")), ("From Sonic Log", f("son"))]),
                ("Sw", [("Archie Formula", f("archie")), ("Dispersed Clay", f("disp")),
                        ("Simandoux Formula", f("sim")), ("Simandoux Modified Formula", f("simm")),
                        ("Indonesian Formula", f("indo")), ("Indonesian Modified Formula", f("indom"))])]

    def _ejecutar(self, app, modo):
        pozo, reg, col = contexto(app)
        if reg is None:
            aviso(app, tr("Please select a log first."))
            return
        cols = reg.nombres()
        c0 = col if 0 <= col < len(cols) else 0
        C = lambda clave, etiqueta, defecto=None: Campo(clave, etiqueta, "columna",  # noqa: E731
                                                       cols[c0] if defecto is None else defecto, cols)
        F = lambda clave, etiqueta, d, dec=4: Campo(clave, etiqueta, "float", d, decimales=dec)  # noqa: E731
        T = lambda d: Campo("nombre", "Generated Column Name", "texto", d)  # noqa: E731
        L = Campo("limitar", LIMITAR, "bool", True)
        sw_comun = [F("a", "Constant, a", 1), F("m", "Cementation Factor, m", 2),
                    F("n", "Saturation Exponent, n", 2), F("rw", "Water Resistivity, Rw (ohm-m)", 0.1)]
        cfg = {
            "gr": ("VShale from GR", [C("x", "Gamma Ray"), F("lim", "GR clean formation", 0),
                                      F("sh", "GR shale", 100), T("VSH_GR"), L]),
            "sp": ("VShale from SP", [C("x", "Spontaneous Potential"), F("lim", "SP clean formation", 0),
                                      F("sh", "SP shale", 100), T("VSH_SP"), L]),
            "n": ("VShale from Neutron Porosity", [C("x", "Neutron Porosity"), F("sh", "Porosity of shale", 0.5),
                                                   T("VSH_N"), L]),
            "nd": ("VShale from Neutron & Density Porosity",
                   [C("x", "Neutron Porosity"), C("y", "Density Porosity"),
                    F("nsh", "Neutron Porosity of Shale", 0.5), F("dsh", "Density Porosity of Shale", 0.2),
                    T("VSH_ND"), L]),
            "den": ("Porosity from Density", [C("x", "Density Log"),
                                              Campo("mat", "Matrix", "opcion", "Quarts",
                                                    list(pf.MATRIZ_DENSIDAD) + ["Custom"]),
                                              F("ma", "Matrix Density (gr/cc)", 2.648),
                                              F("fl", "Fluid Density (gr/cc)", 1.0), T("PORE_D")]),
            "son": ("Porosity from Sonic", [C("x", "Sonic Log"),
                                            Campo("mat", "Matrix", "opcion", "Sandstones",
                                                  list(pf.MATRIZ_SONICO) + ["Custom"]),
                                            F("ma", "Matrix Transit Time (us/ft)", 55),
                                            F("fl", "Fluid Transit Time (us/ft)", 189), T("PORE_S")]),
            "archie": ("Sw Archie", [C("phi", "Porosity (fraction)"),
                                     C("rt", "True Formation Resistivity, Rt (ohm-m)"), *sw_comun,
                                     T("SW"), L]),
            "disp": ("Sw Dispersed Clay", [C("phid", "Porosity Density (fraction)"),
                                           C("phis", "Porosity Sonic (fraction)"),
                                           C("rt", "True Formation Resistivity, Rt (ohm-m)"),
                                           F("rw", "Water Resistivity, Rw (ohm-m)", 0.1),
                                           T("SW"), L]),
        }
        for k, titulo in (("sim", "Sw Simandoux"), ("simm", "Sw Simandoux Modified"),
                          ("indo", "Sw Indonesian"), ("indom", "Sw Indonesian Modified")):
            cfg[k] = (titulo, [C("phi", "Porosity Efective (fraction)"), C("vsh", "VShale (fraction)"),
                               C("rt", "True Formation Resistivity, Rt (ohm-m)"), *sw_comun,
                               F("rsh", "Shale Resistivity, Rsh (ohm-m)", 1), T("SW"), L])
        titulo, campos = cfg[modo]

        def preset(dlg, clave, texto):
            tabla = pf.MATRIZ_DENSIDAD if modo == "den" else pf.MATRIZ_SONICO
            if texto in tabla:
                dlg.fijar("ma", tabla[texto])

        v = pedir(titulo, campos, app, al_cambiar_opcion=preset)
        if v is None:
            return
        if not v.get("nombre"):
            aviso(app, tr("Empty name is not allowed!"))
            return
        d = lambda clave: reg.columnas[v[clave]].datos  # noqa: E731
        try:
            if modo in ("gr", "sp"):
                r = pf.vsh_indice(d("x"), v["lim"], v["sh"], v["limitar"])
            elif modo == "n":
                r = pf.vsh_neutron(d("x"), v["sh"], v["limitar"])
            elif modo == "nd":
                r = pf.vsh_neutron_densidad(d("x"), d("y"), v["nsh"], v["dsh"], v["limitar"])
            elif modo == "den":
                r = pf.porosidad_densidad(d("x"), v["ma"], v["fl"])
            elif modo == "son":
                r = pf.porosidad_sonico(d("x"), v["ma"], v["fl"])
            elif modo == "archie":
                if v["rw"] <= 0:
                    raise ValueError(tr("Water resistivity should be more than 0!"))
                r = pf.sw_archie(d("phi"), d("rt"), v["a"], v["m"], v["n"], v["rw"], v["limitar"])
            elif modo == "disp":
                r = pf.sw_arcilla_dispersa(d("phid"), d("phis"), d("rt"), v["rw"], v["limitar"])
            elif modo.startswith("sim"):
                r = pf.sw_simandoux(d("phi"), d("rt"), d("vsh"), v["a"], v["m"], v["n"], v["rw"], v["rsh"],
                                    v["limitar"], modo == "simm")
            else:
                r = pf.sw_indonesia(d("phi"), d("rt"), d("vsh"), v["a"], v["m"], v["n"], v["rw"], v["rsh"],
                                    v["limitar"], modo == "indom")
        except (ValueError, IndexError) as e:
            aviso(app, str(e))
            return
        agregar_resultado(app, v["nombre"], r, "", titulo)
