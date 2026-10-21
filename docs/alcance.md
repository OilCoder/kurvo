# Alcance de Kurvo

Acordado con el usuario el 2026-10-19 (D114). Sirve para decidir qué pendiente entra y cuál no.

## Objetivo

Kurvo deja **listos y confiables los registros de un pozo** para que otro los interprete o
los lleve a su modelo: los lee, detecta y repara sus problemas, los compara con los pozos vecinos
cuando eso ayuda a corregirlos, hace una interpretación petrofísica básica del pozo y exporta un LAS
limpio con la historia de cada cambio.

**El centro es el pozo y sus curvas, no el yacimiento.** Los otros pozos del proyecto están para
corregir y confirmar el pozo que se trabaja, no para analizar el campo.

## Qué entra, qué es zona gris y qué queda fuera

| Entra (el pozo es el centro) | Zona gris (otros pozos, al servicio del pozo) | Fuera (suite de yacimiento) |
|---|---|---|
| Importar y validar LAS y DLIS | Normalizar curvas contra un pozo de referencia | Mapas de topes, espesores o propiedades |
| QC de curvas: picos, huecos, tramos planos, unidades, condición de pozo | Corregir el desfase en profundidad comparando con un vecino | Producción, declinación, balance de materia |
| Editar y reparar, con deshacer y bitácora | Reconstruir curvas con deep learning entrenando con los vecinos | Modelos estáticos, mallas, volumetría |
| Compuesto de corridas, TVD/TVDSS, trayectoria | Corte de correlación para revisar los topes del pozo | Gestión del campo: estados de todos los pozos, arrendamientos |
| Petrofísica básica del pozo: arcillosidad, porosidad, Sw, Pickett y Hingle | Topes compartidos entre pozos (zonas) | Análisis de presiones de DST (ingeniería de yacimientos) |
| Completación, litología y DST del pozo como contexto en el log plot | | |
| Exportar LAS limpio, CSV y reportes | | |

## Criterios

1. **Petrofísica:** forma parte del objetivo, pero básica. Sirve para comprobar que las curvas
   reparadas dan un resultado razonable (por ejemplo, la Sw frente a lo que recuperó un DST). No
   crece hacia modelos multimineral, incertidumbre ni cortes de espesor neto de todo un campo.
2. **Corte de correlación:** se queda como herramienta para revisar los topes y el desfase del pozo
   frente a sus vecinos. Se corrige lo que lo hace engañoso (TVDSS en pozos de tierra, zonas que no
   se pidieron); no se le agregan mapas ni interpolación entre pozos.
3. **Datos del pozo de contexto** (completación, litología, DST): se muestran en el log plot del
   pozo. El DST es una marca de referencia (intervalo y lo recuperado), no un análisis de presiones.
4. **Varios pozos:** el proyecto puede tener muchos pozos (las herramientas de lote, el tablero de QC
   y el rendimiento lo permiten), pero cada herramienta multi-pozo tiene que responder a la pregunta
   "¿esto corrige o confirma un pozo?".

## Ejemplos

- **Ejemplos:** dos áreas de Kansas con 10–12 pozos variados cada una (`docs/ejemplo_el_dorado.md` y
  `docs/ejemplo_cutter.md`), recorridas con los siete pasos del trabajo.
- Los ejemplos sirven para aprender a usar el programa con datos reales; no son estudios de campo.
