"""Reporte de control de calidad por pozo en HTML o PDF (mantenimiento, prioridad 9).

Las figuras (curva contra profundidad con las muestras dudosas en rojo, e histograma) se
dibujan con QPainter. En HTML van incrustadas en base64 (un solo archivo); en PDF se registran
como recursos de un QTextDocument."""
from __future__ import annotations

import base64
import datetime as dt
import html

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import (QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPainterPath,
                           QPdfWriter, QPen, QTextDocument)

from ..i18n import tr
from ..nucleo import preferencias, qc
from ..nucleo.comun import NULO
from ..nucleo.validacion import resumen

NOTA_COLOR = {"A": "#2e7d32", "B": "#b26a00", "C": "#c62828"}
NIVEL_COLOR = {"ERROR": "#c62828", "WARNING": "#b26a00", "INFO": "#1565c0"}


def _validos(d):
    return (d != NULO) & np.isfinite(d)


def imagen_curva(datos, prof, bandera=None, ancho=120, alto=360, rango=None) -> QImage:
    img = QImage(ancho, alto, QImage.Format_RGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    d, z = np.asarray(datos, float), np.asarray(prof, float)
    ok = _validos(d) & _validos(z)
    p.setPen(QPen(QColor(200, 200, 200), 1))
    p.drawRect(0, 0, ancho - 1, alto - 1)
    if ok.sum() >= 2:
        z0, z1 = z[ok].min(), z[ok].max()
        lo, hi = rango or (np.percentile(d[ok], 0.5), np.percentile(d[ok], 99.5))
        if hi <= lo:
            lo, hi = lo - 1, hi + 1
        fx = lambda v: 4 + (ancho - 8) * (np.clip(v, lo, hi) - lo) / (hi - lo)  # noqa: E731
        fy = lambda v: 4 + (alto - 8) * (v - z0) / (z1 - z0 if z1 > z0 else 1)  # noqa: E731
        if bandera is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 210, 210))
            for i in np.where((bandera > 0) & _validos(z))[0]:
                y = fy(z[i])
                p.drawRect(QRectF(1, y - 0.5, ancho - 2, 1.5))
        camino = QPainterPath()
        nuevo = True
        for i in range(len(d)):
            if not ok[i]:
                nuevo = True
                continue
            pt = QPointF(fx(d[i]), fy(z[i]))
            if nuevo:
                camino.moveTo(pt)
                nuevo = False
            else:
                camino.lineTo(pt)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(25, 80, 170), 1))
        p.drawPath(camino)
        p.setPen(QColor(90, 90, 90))
        p.setFont(QFont("Arial", 7))
        p.drawText(QRectF(2, alto - 14, ancho - 4, 12), Qt.AlignLeft, f"{lo:.3g}")
        p.drawText(QRectF(2, alto - 14, ancho - 4, 12), Qt.AlignRight, f"{hi:.3g}")
    p.end()
    return img


def imagen_histograma(datos, ancho=220, alto=110, bins=30) -> QImage:
    img = QImage(ancho, alto, QImage.Format_RGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    d = np.asarray(datos, float)
    v = d[_validos(d)]
    p.setPen(QPen(QColor(200, 200, 200), 1))
    p.drawRect(0, 0, ancho - 1, alto - 1)
    if v.size >= 2 and v.max() > v.min():
        h, bordes = np.histogram(v, bins)
        w = (ancho - 8) / bins
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(90, 140, 210))
        for k, n in enumerate(h):
            hh = (alto - 22) * n / h.max()
            p.drawRect(QRectF(4 + k * w, alto - 16 - hh, max(w - 1, 1), hh))
        p.setPen(QColor(90, 90, 90))
        p.setFont(QFont("Arial", 7))
        p.drawText(QRectF(2, alto - 14, ancho - 4, 12), Qt.AlignLeft, f"{bordes[0]:.3g}")
        p.drawText(QRectF(2, alto - 14, ancho - 4, 12), Qt.AlignRight, f"{bordes[-1]:.3g}")
    p.end()
    return img


def _f(x) -> str:
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.4g}"


def _tabla_curvas(curvas: list[qc.EstadoCurva]) -> str:
    filas = []
    for e in curvas:
        rango = f"{e.rango[0]:g}–{e.rango[1]:g}" if e.rango else "—"
        filas.append(
            f"<tr><td><b>{html.escape(e.nombre)}</b></td><td>{html.escape(e.unidad)}</td>"
            f"<td style='color:{NOTA_COLOR[e.nota]};font-weight:bold;text-align:center'>{e.nota}</td>"
            f"<td>{e.pct_nulos:g}</td><td>{e.n_huecos}</td><td>{_f(e.minimo)}</td><td>{_f(e.maximo)}</td>"
            f"<td>{_f(e.media)}</td><td>{_f(e.desv)}</td><td>{_f(e.p10)}</td><td>{_f(e.p50)}</td>"
            f"<td>{_f(e.p90)}</td><td>{rango}</td><td>{e.fuera_rango}</td><td>{e.picos}</td>"
            f"<td>{e.muestras_planas}</td><td>{html.escape('; '.join(e.avisos)) or 'OK'}</td></tr>")
    cab = ("Curve", "Unit", "Grade", "Null %", "Gaps", "Min", "Max", "Mean", "Std", "P10", "P50", "P90",
           "Physical range", "Out", "Spikes", "Flat", "Notes")
    return ("<table class='t'><tr>" + "".join(f"<th>{html.escape(tr(c))}</th>" for c in cab) + "</tr>"
            + "".join(filas) + "</table>")


ESTILO = """<style>
body { font-family: Arial, Helvetica, sans-serif; font-size: 10pt; color: #222; }
h1 { font-size: 18pt; margin-bottom: 2px; } h2 { font-size: 14pt; border-bottom: 2px solid #345;
padding-bottom: 2px; margin-top: 18px; } h3 { font-size: 11pt; margin: 10px 0 4px 0; }
table.t { border-collapse: collapse; margin: 4px 0 8px 0; }
table.t th { background: #e8edf3; border: 1px solid #b8c4d2; padding: 2px 4px; font-size: 8pt; }
table.t td { border: 1px solid #d0d7e0; padding: 2px 4px; font-size: 8pt; }
.meta { color: #555; } .leyenda { color: #666; font-size: 8pt; }
</style>"""


def construir(informes, alias=None, figuras: bool = True) -> tuple[str, dict[str, QImage]]:
    """`informes`: lista de (InformeRegistro, registro). Devuelve (html, imágenes por nombre)."""
    imagenes: dict[str, QImage] = {}
    u = preferencias.actual().qc
    partes = [f"<html><head><meta charset='utf-8'><title>{tr('QC Report')}</title>{ESTILO}</head><body>",
              f"<h1>{tr('Log Quality Control Report')}</h1>",
              "<p class='meta'>" + tr("Generated {0} · {1} log(s).").format(f"{dt.datetime.now():%Y-%m-%d %H:%M}",
                                                                          len(informes)) + " "
              + tr("Grades: {0} no issues · {1} minor issues · {2} review before use (no data, &gt;{3}% nulls "
                   "or &gt;{4}% out of physical range).").format(
                  "<b style='color:#2e7d32'>A</b>", "<b style='color:#b26a00'>B</b>", "<b style='color:#c62828'>C</b>",
                  f"{u.nulos_malo:g}", f"{u.fuera_malo:g}") + " "
              + (tr("Thresholds and physical ranges stored in the project.") if preferencias.origen_qc() == "project"
                 else tr("Thresholds and physical ranges from the user settings.")) + "</p>"]
    resumen_filas = []
    for inf, _ in informes:
        notas = [e.nota for e in inf.curvas]
        resumen_filas.append(f"<tr><td>{html.escape(inf.pozo)}</td><td>{html.escape(inf.registro)}</td>"
                             f"<td>{inf.filas}</td><td>{len(inf.curvas)}</td><td>{notas.count('A')}</td>"
                             f"<td>{notas.count('B')}</td><td>{notas.count('C')}</td>"
                             f"<td>{html.escape(resumen(inf.validacion))}</td></tr>")
    partes.append(f"<h2>{tr('Summary')}</h2><table class='t'><tr>"
                  + "".join(f"<th>{tr(c)}</th>" for c in ("Well", "Log", "Rows", "Curves", "A", "B", "C",
                                                          "LAS validation"))
                  + "</tr>" + "".join(resumen_filas) + "</table>")
    for n_inf, (inf, reg) in enumerate(informes):
        partes.append(f"<h2>{html.escape(inf.pozo)} — {html.escape(inf.registro)}</h2>")
        partes.append("<p class='meta'>" + tr("{0} rows · depth {1} to {2} {3} · step {4}").format(
            inf.filas, _f(inf.prof_min), _f(inf.prof_max), html.escape(inf.unidad_prof),
            _f(inf.paso) if inf.paso else tr("irregular")) + "</p>")
        if inf.validacion:
            partes.append(f"<h3>{tr('LAS validation')}</h3><ul>" + "".join(
                f"<li><b style='color:{NIVEL_COLOR[p.nivel]}'>{tr(p.nivel)}</b> {html.escape(p.mensaje)}</li>"
                for p in inf.validacion) + "</ul>")
        else:
            partes.append(f"<h3>{tr('LAS validation')}</h3><p>{tr('No problems found.')}</p>")
        if inf.pozo_malo:
            partes.append(f"<h3>{tr('Borehole condition')}</h3><ul>" + "".join(f"<li>{html.escape(x)}</li>"
                                                                                for x in inf.pozo_malo) + "</ul>")
        partes.append(f"<h3>{tr('Curves')}</h3>" + _tabla_curvas(inf.curvas))
        for nombre, tope, base, curvas in inf.zonas:
            fin = _f(base) if base is not None else tr("bottom")
            partes.append(f"<h3>{tr('Zone')} {html.escape(nombre)} ({_f(tope)} – {fin})</h3>" + _tabla_curvas(curvas))
        if figuras and reg.existe_columna(reg.indice_md):
            prof = reg.columnas[reg.indice_md].datos
            celdas = []
            for k, c in enumerate(reg.columnas):
                if k in (reg.indice_md, reg.indice_tvd):
                    continue
                clave_c, clave_h = f"qc_{n_inf}_{k}_c.png", f"qc_{n_inf}_{k}_h.png"
                imagenes[clave_c] = imagen_curva(c.datos, prof, qc.bandera(reg, k, alias))
                imagenes[clave_h] = imagen_histograma(c.datos, 120, 80)
                celdas.append(f"<td style='text-align:center'><b>{html.escape(c.nombre)}</b><br>"
                              f"<img src='{clave_c}' width='120' height='360'><br>"
                              f"<img src='{clave_h}' width='120' height='80'></td>")
            filas = ["<tr>" + "".join(celdas[i:i + 6]) + "</tr>" for i in range(0, len(celdas), 6)]
            partes.append(f"<h3>{tr('Curves vs depth')}</h3><p class='leyenda'>"
                          + tr("Pink bands mark samples flagged as doubtful (null, out of physical range, spike "
                               "or flat run).") + "</p><table>" + "".join(filas) + "</table>")
    partes.append("</body></html>")
    return "\n".join(partes), imagenes


def _png_b64(img: QImage) -> str:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(ba)).decode("ascii")


def guardar_html(ruta, informes, alias=None) -> None:
    texto, imagenes = construir(informes, alias)
    for nombre, img in imagenes.items():
        texto = texto.replace(f"src='{nombre}'", f"src='data:image/png;base64,{_png_b64(img)}'")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)


def guardar_pdf(ruta, informes, alias=None) -> None:
    texto, imagenes = construir(informes, alias)
    doc = QTextDocument()
    for nombre, img in imagenes.items():
        doc.addResource(QTextDocument.ImageResource, QUrl(nombre), img)
    doc.setHtml(texto)
    pdf = QPdfWriter(str(ruta))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(12, 12, 12, 12)))
    pdf.setResolution(110)
    pdf.setTitle(tr("Log Quality Control Report"))
    doc.setPageSize(QRectF(0, 0, pdf.width(), pdf.height()).size())
    doc.print_(pdf)
