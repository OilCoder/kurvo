"""Textos largos de ayuda (How To) en inglés y en español."""

_ESTILO = ("<style>body{font-family:Segoe UI,Arial;font-size:10pt} h2{color:#1e4f8a} h3{color:#2b3a4a;"
           "margin-bottom:2px} li{margin-bottom:3px} .k{background:#eef2f7;padding:0 3px}</style>")

EN = {"howto": _ESTILO + """
<h2>How to maintain well log curves</h2>
<p>The bar at the top has the <b>seven steps of the work</b>, from left to right; each step shows only its tools.
Above it, a thin strip has what is not a step: Project, Save, Undo, View, Settings, Help, and a search box
that finds any tool by its name (type “tvd” or “spikes”). On the right of that strip, the <b>next step</b> of
the selected well, with a button to go there. The Workflow panel (View menu) shows the state of every
step: done (✓), with warnings (!) or pending. The center has no tabs: each step ends with a <b>Views</b> group
(Log Plot always; Trajectory, Cross Section and Formation Tops in Align and Compare; Pickett in Check...). The
template of the Log Plot opens with <b>Edit...</b> next to its name or with a right click on the plot.</p>
<p><b>Selection.</b> Click a well, log or curve in the project tree (or a column of the Data Table): every tool
uses that well/log/curve/zone by default. The status bar shows the current selection.</p>
<p><b>First time?</b> Help › <span class="k">Try an Example</span> loads a real well and opens its guide.</p>
<h3>1 · Prepare</h3>
<ul><li><span class="k">Import LAS</span>, <span class="k">Import Folder</span> or <span class="k">Import DLIS</span>. Nulls of the
file become −999.25; the KB elevation is taken from the LAS header when it has it.</li>
<li><span class="k">Composite</span> joins the runs of a well into one log (the originals are kept).</li>
<li><span class="k">Validate LAS</span>: depth order, duplicates, header, nulls and curve names, with automatic fixes;
<span class="k">Standardize Mnemonics</span>, <span class="k">Convert Units</span> and <span class="k">Resample</span>.</li></ul>
<h3>2 · Review</h3>
<ul><li><span class="k">Quality Control</span> (F7) opens the QC panel: grades A/B/C per curve and zone, curves vs depth
with doubtful samples in red and the borehole condition track (CALI − BS, DRHO), coverage, histograms,
wells comparison, crossplot, correlation, before/after and depth step. It opens over the whole window;
<b>Back to the plot</b> returns it to the side.</li>
<li><span class="k">QC Dashboard</span>: wells × curves matrix; click a cell to open it.</li></ul>
<h3>3 · Correct</h3>
<ul><li>Remove spikes, fill gaps, manual edit, smooth, nulls and limits, calculator: each with a <b>Preview</b>
before <b>Apply</b>.</li>
<li>Every change goes to the <span class="k">Change Log</span> and can be undone (Ctrl+Z / Ctrl+Y). The original of each
curve is kept: <span class="k">Before / After</span> and <span class="k">Restore</span>.
<span class="k">Batch Operations</span> applies a tool to many logs at once.</li></ul>
<h3>4 · Align and Compare</h3>
<ul><li><span class="k">Trajectory</span>: survey stations and KB. To see the well in TVD or TVDSS, choose it in the
<b>Depth axis</b> above the Log Plot: the program computes the TVD, and if the well has no trajectory it asks
whether it is vertical.</li>
<li><span class="k">Auto Depth Shift</span>, <span class="k">Normalize Wells</span>, <span class="k">Cross Section</span> and
<span class="k">Formation Tops</span>.</li></ul>
<h3>5 · Reconstruct</h3>
<ul><li><span class="k">Reconstruct Curve</span> (deep learning) rebuilds missing curves from several wells. Samples
flagged by QC are excluded from training; the Log Plot layer “DL uncertainty” shows the prediction ± its
standard deviation, calibrated on the validation wells.</li></ul>
<h3>6 · Check</h3>
<ul><li>Check the grades again in the QC panel, the petrophysics (Vshale, porosity, Sw, Pickett, Hingle) and the
context of the well (lithology, completion).</li></ul>
<h3>7 · Deliver</h3>
<ul><li><span class="k">Export LAS</span>, CSV or Excel, the <span class="k">QC Report</span> (HTML or PDF) and printing.</li></ul>
<p><b>Panels.</b> The project tree, QC, Change Log and properties are dockable: drag them, tab them together or
float them. Show or hide them from View.</p>
<p><b>Language and settings.</b> Settings › <span class="k">User Settings</span>: English/Español, null values, QC
thresholds, physical ranges and deep learning defaults.</p>
"""}

ES = {"howto": _ESTILO + """
<h2>Cómo hacer el mantenimiento de las curvas</h2>
<p>La barra de arriba tiene los <b>siete pasos del trabajo</b>, de izquierda a derecha; cada paso muestra solo sus
herramientas. Encima, una franja delgada tiene lo que no es un paso: Proyecto, Guardar, Deshacer, Ver,
Configuración, Ayuda y un buscador que encuentra cualquier herramienta por su nombre (escriba «tvd» o
«picos»). A la derecha de esa franja, el <b>siguiente paso</b> del pozo seleccionado, con un botón para ir. El
panel Flujo de trabajo (menú Ver) muestra el estado de cada paso: hecho (✓), con avisos (!) o pendiente. El
centro no tiene pestañas: cada paso termina con un grupo <b>Vistas</b> (el gráfico de registros siempre;
Trayectoria, Corte transversal y Topes de formación en Alinear y comparar; Pickett en Comprobar...). La plantilla
del gráfico se abre con <b>Editar...</b> junto a su nombre o con clic derecho sobre el gráfico.</p>
<p><b>Selección.</b> Haga clic en un pozo, registro o curva del árbol del proyecto (o en una columna de la Tabla de
datos): todas las herramientas usan ese pozo/registro/curva/zona por defecto. La barra de estado muestra la
selección actual.</p>
<p><b>¿Primera vez?</b> Ayuda › <span class="k">Probar un ejemplo</span> carga un pozo real y abre su guía.</p>
<h3>1 · Preparar</h3>
<ul><li><span class="k">Importar LAS</span>, <span class="k">Importar carpeta</span> o <span class="k">Importar DLIS</span>. Los
nulos del archivo pasan a −999,25; la elevación KB se toma de la cabecera del LAS cuando la trae.</li>
<li><span class="k">Compuesto</span> une las corridas de un pozo en un registro (se conservan los originales).</li>
<li><span class="k">Validar LAS</span>: orden de profundidad, duplicados, cabecera, nulos y nombres de curvas, con
correcciones automáticas; <span class="k">Estandarizar mnemónicos</span>, <span class="k">Convertir unidades</span> y
<span class="k">Remuestrear</span>.</li></ul>
<h3>2 · Revisar</h3>
<ul><li><span class="k">Control de calidad</span> (F7) abre el panel de QC: notas A/B/C por curva y zona, curvas contra
profundidad con las muestras dudosas en rojo y la pista de condición de pozo (CALI − BS, DRHO), cobertura,
histogramas, comparación entre pozos, crossplot, correlación, antes/después y paso de profundidad.
Se abre ocupando toda la ventana; <b>Volver al gráfico</b> lo devuelve al lateral.</li>
<li><span class="k">Tablero de QC</span>: matriz pozos × curvas; un clic en una celda la abre.</li></ul>
<h3>3 · Corregir</h3>
<ul><li>Quitar picos, rellenar huecos, edición gráfica, suavizar, nulos y límites, calculadora: cada una con
<b>Vista previa</b> antes de <b>Aplicar</b>.</li>
<li>Cada cambio queda en la <span class="k">Bitácora de cambios</span> y se puede deshacer (Ctrl+Z / Ctrl+Y). Se conserva el
original de cada curva: <span class="k">Antes / después</span> y <span class="k">Restaurar</span>.
<span class="k">Operaciones por lote</span> aplica una herramienta a muchos registros a la vez.</li></ul>
<h3>4 · Alinear y comparar</h3>
<ul><li><span class="k">Trayectoria</span>: estaciones de desviación y KB. Para ver el pozo en TVD o TVDSS, elíjalo en el
<b>Eje de profundidad</b> sobre el gráfico de registros: el programa calcula la TVD y, si el pozo no tiene
trayectoria, pregunta si es vertical.</li>
<li><span class="k">Desfase automático</span>, <span class="k">Normalizar pozos</span>, <span class="k">Corte transversal</span> y
<span class="k">Topes de formación</span>.</li></ul>
<h3>5 · Reconstruir</h3>
<ul><li><span class="k">Reconstruir curva</span> (deep learning) reconstruye curvas faltantes a partir de varios pozos.
Las muestras con bandera de QC no se usan para entrenar; la capa «Incertidumbre DL» del gráfico muestra la
predicción ± su desviación estándar, calibrada con los pozos de validación.</li></ul>
<h3>6 · Comprobar</h3>
<ul><li>Revise de nuevo las notas en el panel de QC, la petrofísica (Vsh, porosidad, Sw, Pickett, Hingle) y el
contexto del pozo (litología, completación).</li></ul>
<h3>7 · Entregar</h3>
<ul><li><span class="k">Exportar LAS</span>, CSV o Excel, el <span class="k">Reporte de QC</span> (HTML o PDF) y la impresión.</li></ul>
<p><b>Paneles.</b> El árbol del proyecto, el QC, la bitácora y las propiedades son acoplables: se pueden arrastrar,
agrupar en pestañas o dejar flotando. Se muestran u ocultan desde Ver.</p>
<p><b>Idioma y preferencias.</b> Configuración › <span class="k">Preferencias</span>: English/Español, valores nulos,
umbrales de QC, rangos físicos y opciones por defecto de deep learning.</p>
"""}
