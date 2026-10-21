# Cambios

## 1.0 (octubre de 2026)

Primera versión publicada.

### Para el usuario

- **Siete pasos del trabajo** en la barra superior: Preparar, Revisar, Corregir, Alinear y comparar, Reconstruir,
  Comprobar y Entregar. Cada paso muestra solo sus herramientas y sus vistas.
- **Franja general** con el proyecto, deshacer, vistas, preferencias, ayuda, el **siguiente paso** del pozo elegido y
  un **buscador** de herramientas por nombre.
- **Pantalla de inicio** y **dos ejemplos reales** (El Dorado, 12 pozos de petróleo en carbonatos; Cutter, 10 pozos de
  gas y petróleo en areniscas) con topes, litología, mecánica de pozo y una guía paso a paso.
- **Manual** completo dentro del programa (Ayuda › Manual).
- **Gráfico limpio:** esconde las pistas sin datos en el pozo elegido y empieza en el primer dato.
- **Profundidad en el eje del gráfico:** MD, TVD o TVDSS. El programa calcula la TVD, pregunta si un pozo sin
  trayectoria es vertical y toma la elevación KB de la cabecera del LAS.
- **Control de calidad** con notas A/B/C por curva, a pantalla completa, con vista en profundidad, cobertura,
  histogramas, comparación entre pozos, gráfico cruzado, correlación, antes/después y tablero del proyecto.
- **Reparación** con vista previa, bitácora y deshacer: quitar picos, rellenar huecos, edición gráfica, suavizar,
  nulos, límites, calculadora, empalme, compuesto de corridas y operaciones por lote.
- **Normalización entre pozos**, desfase automático, corte transversal con topes y aplanamiento, trayectoria.
- **Reconstrucción de curvas con deep learning** (desde el código, con PyTorch), validada a ciegas, con incertidumbre
  calibrada.
- **Petrofísica básica:** arcillosidad, porosidad, saturación (Archie, arcilla dispersa, Simandoux, Indonesia),
  Pickett y Hingle.
- **Entregas:** LAS 2.0, CSV, Excel, reporte de QC en HTML o PDF e impresión.
- **Formato de proyecto propio** (`.kurvo`: un zip con un `proyecto.json` legible, los registros en LAS 2.0 y la
  bitácora) y plantillas en `.kvplantilla`.
- Interfaz en **español e inglés**, tema claro u oscuro.
- Reconoce los mnemónicos de compañía más comunes, incluidos los de las cargas de la KCC de Kansas.

### Limitaciones conocidas

Ver el [manual](docs/manual.md#10-limitaciones-conocidas).
