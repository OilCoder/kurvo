"""Registro único de acciones (QAction con nombre, icono, ayuda emergente y atajo).

El ribbon, el menú contextual del editor de logs y el del árbol usan la *misma* QAction, de modo
que una herramienta tiene un solo nombre, un solo icono y un solo atajo, y nada queda escondido
solo en un menú (ver D52). Los textos son claves en inglés que pasan por `tr()`; al cambiar de
idioma basta con `retraducir()`.

Cada definición indica qué ejecuta:
- "metodo": método de la ventana principal;
- "curva:funcion": función de vista/edicion_curvas.py sobre la curva seleccionada;
- "editor:metodo": método del editor de logs sobre el registro seleccionado;
- "panel:clave": muestra u oculta un panel acoplable (acción con casilla);
- "vista:clave": trae al centro una vista (gráfico, tabla, trayectoria...; D123)."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QAction, QActionGroup, QKeySequence

from ..i18n import tr
from . import iconos


@dataclass(frozen=True)
class DefAccion:
    clave: str
    texto: str
    icono: str
    ayuda: str
    destino: str
    atajo: str = ""


DEFINICIONES = [
    # ---------------------------------------------------------------- General
    DefAccion("open", "Open Project", "open", "Open a project file (.kurvo)", "abrir_dialogo", "Ctrl+O"),
    DefAccion("save", "Save Project", "save", "Save the project", "guardar", "Ctrl+S"),
    DefAccion("save_as", "Save Project As", "save_as", "Save the project with a new name", "guardar_como",
              "Ctrl+Shift+S"),
    DefAccion("close_project", "Close Project", "close_project", "Close the current project", "cerrar_proyecto"),
    DefAccion("print", "Print", "print", "Print the current log plot", "imprimir", "Ctrl+P"),
    DefAccion("print_setup", "Print Setup", "print_setup", "Paper size, orientation and margins",
              "configurar_impresion"),
    DefAccion("settings", "User Settings", "settings",
              "Language, null values, QC thresholds, physical ranges and deep learning defaults",
              "preferencias_usuario"),
    DefAccion("help", "How To", "help", "Step-by-step guide to the maintenance workflow", "ayuda", "F1"),
    DefAccion("about", "About", "about", "About this application", "acerca"),
    DefAccion("diagnostic", "Diagnostic Log", "diagnostic", "Messages and warnings of this session",
              "ver_diagnostico"),
    DefAccion("exit", "Exit", "exit", "Close the application", "close"),
    DefAccion("panel_project", "Project Tree", "panel_project", "Show or hide the project tree", "panel:proyecto"),
    DefAccion("panel_workflow", "Workflow", "workflow",
              "Show or hide the workflow panel: status of every maintenance step for each well",
              "panel:flujo"),
    DefAccion("panel_qc", "QC Panel", "qc_window", "Show or hide the quality control panel", "panel:qc"),
    DefAccion("panel_history", "Change Log Panel", "history", "Show or hide the change log of the selected log",
              "panel:historial"),
    DefAccion("panel_properties", "Curve Properties", "properties",
              "Show or hide the properties of the selected curve: name, unit, alias group, QC grade, origin, "
              "statistics and physical range", "panel:propiedades"),
    # ---------------------------------------------------------------- Maintenance (orden del flujo)
    DefAccion("import_las", "Import LAS", "import_las",
              "Import one or more LAS files; each goes to the well with the same UWI or name (LEASE + WELL) "
              "or to a new well, and its formation tops become zones", "importar_las_dialogo"),
    DefAccion("import_las_folder", "Import LAS Folder", "import_las_folder",
              "Import every LAS file of a folder and its subfolders (a whole field) without questions",
              "importar_carpeta_las"),
    DefAccion("import_dlis", "Import DLIS", "import_dlis", "Import the frames of a DLIS file as logs",
              "importar_dlis_dialogo"),
    DefAccion("validate", "Validate LAS", "validate",
              "Check depth, header, nulls and curve names of the selected log and fix them", "editor:validar"),
    DefAccion("mnemonics", "Standardize Mnemonics", "mnemonics",
              "Rename curves to the standard names of the alias database", "mant:estandarizar"),
    DefAccion("convert_units", "Convert Units", "units", "Convert the units of the selected curve",
              "mant:convertir_unidades"),
    DefAccion("resample", "Resample", "resample", "Resample all curves of the selected log to a constant step",
              "mant:remuestrear"),
    DefAccion("qc_window", "Quality Control", "qc_window",
              "Interactive QC panel: grades, depth view, coverage, histograms, wells comparison, "
              "crossplot and correlation", "ventana_qc", "F7"),
    DefAccion("dashboard", "QC Dashboard", "dashboard",
              "Wells × curves matrix with the QC grade of every curve; click a cell to open it", "dashboard_qc"),
    DefAccion("qc_flags", "Add QC Flags", "qc_flag",
              "Add a <curve>_QC column (1 = doubtful sample) for the selected curve", "banderas_qc"),
    DefAccion("undo", "Undo", "undo", "Undo the last change to the selected log", "deshacer", "Ctrl+Z"),
    DefAccion("redo", "Redo", "redo", "Redo the last undone change", "rehacer", "Ctrl+Y"),
    DefAccion("history", "Change Log", "history", "Every change made to the selected log, with date and detail",
              "editor:ver_historial"),
    DefAccion("graphic_edit", "Graphic Edit", "graphic_edit",
              "Edit the selected curve on a depth plot: null, interpolate, despike or redraw by hand",
              "curva:edicion_grafica"),
    DefAccion("curve_null", "Set Interval to Null", "curve_null", "Set an interval of the selected curve to null",
              "curva:a_nulo"),
    DefAccion("curve_value", "Set Interval to Value", "curve_value",
              "Set an interval of the selected curve to a constant value", "curva:constante"),
    DefAccion("interpolate", "Interpolate Gaps", "interpolate", "Fill the null gaps of the selected curve",
              "curva:interpolar"),
    DefAccion("despike", "Despike", "despike", "Remove spikes from the selected curve", "curva:despike"),
    DefAccion("smooth", "Smooth", "smooth", "Smooth the selected curve with a moving window", "curva:suavizar"),
    DefAccion("clip", "Clip to Range", "clip", "Clip or null the values of the selected curve outside a range",
              "curva:recortar"),
    DefAccion("splice", "Splice Runs", "splice", "Join two runs of a curve at a splice depth", "curva:empalmar"),
    DefAccion("compare_original", "Compare with Original", "compare_original",
              "Original (before the first edit) against the current curve", "curva:comparar_original"),
    DefAccion("restore_original", "Restore Original Curve", "restore_original",
              "Return the selected curve to its original version", "curva:restaurar"),
    DefAccion("normalize", "Normalize Wells", "normalize",
              "Match a curve of every well to a reference well (percentiles)", "normalizar_pozos"),
    DefAccion("depth_shift", "Auto Depth Shift", "depth_shift",
              "Find the depth shift between two logs by cross-correlation and apply it", "desfase_automatico"),
    DefAccion("batch", "Batch Operations", "batch", "Apply an operation to many logs and wells at once", "lote"),
    DefAccion("deep_learning", "Deep Learning", "deep_learning",
              "Reconstruct missing curves or classify lithofacies with neural networks", "deep_learning"),
    DefAccion("qc_report", "QC Report", "qc_report", "Quality control report per well (HTML or PDF)",
              "reporte_qc"),
    DefAccion("export_las", "Export LAS", "export_las", "Export the selected log to a LAS 2.0 file",
              "exportar_las_activo"),
    DefAccion("export_csv", "Export CSV", "export_csv", "Export the selected log to CSV", "exportar_csv"),
    DefAccion("export_excel", "Export Excel", "export_excel", "Export all logs to an Excel workbook",
              "exportar_excel"),
    # ---------------------------------------------------------------- editor de logs
    DefAccion("create_tvd", "Create TVD from MD", "create_tvd", "Compute a TVD column from MD and the trajectory",
              "editor:crear_tvd"),
    DefAccion("create_md", "Create MD from TVD", "create_md", "Compute an MD column from TVD and the trajectory",
              "editor:crear_md"),
    DefAccion("filter", "Filter Rows", "filter", "Delete rows or set them to null by a condition",
              "editor:filtrar"),
    # ---------------------------------------------------------------- Advance
    DefAccion("partial_log", "Create Partial Log", "partial_log", "Copy a range of rows to a new log",
              "log_parcial"),
    DefAccion("calculator", "Advance Calculator", "calculator", "Create a curve from a formula", "calculadora"),
    DefAccion("combine", "Combine Las Files", "combine", "Merge two logs of the well by depth", "combinar_las"),
    DefAccion("composite", "Composite Well Log", "composite",
              "Join all the logs of the well (tool runs, _part files) into one log; the originals are kept",
              "componer_pozo"),
    DefAccion("grouping", "Log Grouping", "grouping", "Edit the curve alias groups", "agrupacion_logs"),
    DefAccion("plugins", "Plugin Manager", "plugins", "Installed modules", "gestor_modulos"),
    # ---------------------------------------------------------------- vistas del centro (D123)
    DefAccion("view_logplot", "Log Plot", "logplot", "The curves of the well in tracks", "vista:logplot"),
    DefAccion("view_cross_section", "Cross Section", "cross_section",
              "Several wells side by side, with their tops joined", "vista:corte"),
    DefAccion("view_table", "Data Table", "log",
              "The values of the selected log as a table: columns, units and single cells", "vista:logs"),
    DefAccion("view_trajectory", "Trajectory", "trajectory",
              "Survey stations, KB elevation and the TVD/TVDSS of the well", "vista:tray"),
    DefAccion("view_zones", "Formation Tops", "zones", "Tops of every zone in every well", "vista:zonas"),
    DefAccion("view_lithology", "Lithology", "lithology", "Lithology intervals of the well", "vista:lito"),
    DefAccion("view_completion", "Completion", "completion", "Casing, perforations and plugs of the well",
              "vista:comp"),
    DefAccion("view_templates", "Templates", "templates", "Which curves go in each track, and their scales",
              "vista:tpl"),
    DefAccion("manual", "User Manual", "help", "The complete manual: the screen, the seven steps and every tool",
              "abrir_manual"),
    DefAccion("start_page", "Start Page", "app", "What do you want to do? Open, import or try an example",
              "pagina_inicio"),
    DefAccion("examples", "Try an Example", "open",
              "Load a real example well (Kansas Geological Survey data) and open its step-by-step guide",
              "abrir_ejemplo"),
]


# etiquetas cortas solo para los botones del ribbon (D96): la acción conserva su nombre completo en
# los menús, la ayuda emergente y la barra de estado
CORTOS = {"mnemonics": "Mnemonics", "convert_units": "Units", "qc_window": "Quality Control",
          "dashboard": "Dashboard", "qc_flags": "QC Flags", "history": "Changes", "normalize": "Normalize",
          "batch": "Batch", "graphic_edit": "Graphic Edit",
          "panel_project": "Tree", "panel_properties": "Properties", "panel_history": "Changes",
          "save_as": "Save As", "close_project": "Close",
          # pasos del trabajo (D123): nombres de la tarea, no de la herramienta
          "import_las_folder": "Import Folder", "composite": "Composite", "combine": "Combine",
          "partial_log": "Partial Log", "validate": "Validate", "despike": "Remove Spikes",
          "interpolate": "Fill Gaps", "curve_null": "Set Null", "curve_value": "Set Value", "clip": "Limits",
          "calculator": "Calculator", "compare_original": "Before / After", "restore_original": "Restore",
          "deep_learning": "Reconstruct Curve", "qc_report": "QC Report", "export_las": "LAS",
          "export_csv": "CSV", "export_excel": "Excel", "create_tvd": "TVD from MD", "create_md": "MD from TVD",
          "grouping": "Curve Groups", "depth_shift": "Auto Depth Shift",
          "mod:Depth Shifting/Depth Shifting": "Manual Depth Shift", "settings": "Settings"}


class RegistroAcciones:
    """QActions de la ventana principal, una por herramienta."""

    def __init__(self, app):
        self.app = app
        self.defs = {d.clave: d for d in DEFINICIONES}
        self.acciones: dict[str, QAction] = {}
        self.grupo_vistas = QActionGroup(app)          # la vista del centro que se ve queda marcada
        self.grupo_vistas.setExclusive(True)
        self.por_vista: dict[str, QAction] = {}
        for d in DEFINICIONES:
            a = QAction(iconos.icono(d.icono), "", app)
            a.setObjectName(f"accion_{d.clave}")
            if d.atajo:
                a.setShortcut(QKeySequence(d.atajo))
            if d.destino.startswith("panel:"):
                a.setCheckable(True)
                a.toggled.connect(lambda v, k=d.destino[6:]: app.mostrar_panel(k, v))
            else:
                if d.destino.startswith("vista:") and d.destino != "vista:tpl":
                    self.agrupar_vista(a, d.destino[6:])
                a.triggered.connect(lambda *_, dd=d: self.ejecutar(dd.clave))
            app.addAction(a)
            self.acciones[d.clave] = a
        self.modulos: dict[str, list[tuple[str, object]]] = {}
        self.retraducir()

    def agrupar_vista(self, accion: QAction, vista: str) -> None:
        accion.setCheckable(True)
        self.grupo_vistas.addAction(accion)
        self.por_vista[vista] = accion

    def marcar_vista(self, vista: str) -> None:
        a = self.por_vista.get(vista)
        if a is not None:
            a.setChecked(True)

    def __getitem__(self, clave: str) -> QAction:
        return self.acciones[clave]

    def __contains__(self, clave: str) -> bool:
        return clave in self.acciones

    def ejecutar(self, clave: str):
        d = self.defs[clave]
        destino = d.destino
        app = self.app
        if ":" in destino:
            tipo, nombre = destino.split(":", 1)
            if tipo == "curva":
                if not app.preparar_curva():
                    return None
                from . import edicion_curvas
                return getattr(edicion_curvas, nombre)(app.editor_logs)
            if tipo == "editor":
                if app.registro_seleccionado() is None:
                    return None
                return getattr(app.editor_logs, nombre)()
            if tipo == "mant":
                if app.registro_seleccionado() is None:
                    return None
                if nombre == "convertir_unidades" and not app.preparar_curva():
                    return None
                from . import mantenimiento_ui
                return getattr(mantenimiento_ui, nombre)(app.editor_logs)
            if tipo == "vista":
                return app.mostrar_vista(nombre)
        return getattr(app, destino)()

    def retraducir(self) -> None:
        for clave, a in self.acciones.items():
            d = self.defs[clave]
            a.setText(tr(d.texto))
            atajo = f" — {QKeySequence(d.atajo).toString(QKeySequence.NativeText)}" if d.atajo else ""
            a.setToolTip(f"<b>{tr(d.texto)}</b>{atajo}<br>{tr(d.ayuda)}")
            a.setStatusTip(tr(d.ayuda))

    def accion(self, clave: str, texto: str, icono: str, ayuda: str, funcion) -> QAction:
        """Acción extra (p. ej. de un módulo de interpretación), registrada con la misma forma."""
        if clave in self.acciones:
            return self.acciones[clave]
        d = DefAccion(clave, texto, icono, ayuda, "")
        self.defs[clave] = d
        a = QAction(iconos.icono(icono), tr(texto), self.app)
        a.setObjectName(f"accion_{clave}")
        a.setToolTip(f"<b>{tr(texto)}</b><br>{tr(ayuda)}" if ayuda else tr(texto))
        a.setStatusTip(tr(ayuda) if ayuda else "")
        a.triggered.connect(lambda *_: funcion())
        self.acciones[clave] = a
        return a
