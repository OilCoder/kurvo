"""Deep learning: preparación de datos (sin torch) y entrenamiento/predicción (si hay torch)."""
import numpy as np
import pytest

from kurvo.aprendizaje import datos as D
from kurvo.demo import proyecto_demo
from kurvo.nucleo.bases import alias_por_defecto
from kurvo.nucleo.comun import NULO



def test_extraer_y_normalizar():
    pr = proyecto_demo()
    alias = alias_por_defecto()
    reg = pr.pozos[0].logs[0]
    p = D.extraer(reg, "DEMO-1", ["GR", "LLD", "NOEXISTE"], "DT", alias)
    assert p.X.shape == (3, reg.n_filas)
    assert p.curvas == ["GR", "ILD", ""]                   # LLD encontrado por alias (ILD)
    assert np.isnan(p.X[2]).all() and np.isnan(p.X[0]).sum() == (reg.columna("GR").datos == NULO).sum()
    n = D.ajustar_normalizador([p], ["GR", "LLD", "NOEXISTE"], ["API", "OHMM", ""], False, True, alias)
    assert n.log_entrada == [False, True, False]
    Z = D.entrada_red(p, n)
    assert Z.shape == (6, reg.n_filas) and Z.dtype == np.float32
    assert (Z[5] == 0).all() and (Z[2] == 0).all()        # curva ausente: valor 0 y máscara 0
    assert abs(float(np.median(Z[0][Z[3] > 0]))) < 0.05   # GR centrado por pozo
    y = D.objetivo_red(p, n)
    assert abs(np.nanmean(y)) < 1e-5 and abs(np.nanstd(y) - 1) < 1e-4
    np.testing.assert_allclose(D.desnormalizar(y, n)[np.isfinite(y)], p.y[np.isfinite(p.y)], rtol=1e-5)
    d = n.a_dict()
    assert D.Normalizador.desde_dict(d).a_dict() == d


def test_etiquetas_de_litologia_y_ventanas():
    pr = proyecto_demo()
    reg, lit = pr.pozos[0].logs[0], pr.pozos[0].litologias[0]
    p = D.extraer(reg, "DEMO-1", ["GR"], litologia=lit)
    assert set(np.unique(p.y)) == {D.IGNORAR} | {it.tipo for it in lit.intervalos}
    assert D.ventanas(10, 4, 3) == [0, 3, 6] and D.ventanas(3, 8, 2) == [0]
    assert D.cortar(np.ones((2, 3)), 5).shape == (2, 5)


def test_facies_a_intervalos():
    from kurvo.modulos.deep_learning import facies_a_intervalos
    lit = facies_a_intervalos(np.arange(10.0), np.array([1, 1, 1, 2, 2, np.nan, 3, 3, 3, 3], float), "X")
    assert [(i.tope, i.base, i.tipo) for i in lit.intervalos] == [(0, 2, 1), (3, 4, 2), (6, 9, 3)]


# ------------------------------------------------------------------ con PyTorch
@pytest.fixture()
def redes():
    pytest.importorskip("torch")
    from kurvo.aprendizaje import redes
    return redes


def _pozos(entradas, objetivo):
    pr = proyecto_demo()
    alias = alias_por_defecto()
    return [D.extraer(p.logs[0], p.nombre, entradas, objetivo, alias) for p in pr.pozos], alias


@pytest.mark.parametrize("arq", ["unet", "bigru"])
def test_regresion_entrena_y_predice(redes, arq):
    entradas = ["GR", "RHOB", "NPHI", "ILD"]
    pozos, alias = _pozos(entradas, "DT")
    cfg = redes.Configuracion("regresion", arq, entradas, ["API", "G/C3", "PU", "OHMM"], "DT",
                              largo=64, canales=8, epocas=25, lote=16, lr=5e-3, muestras_mc=5, paciencia=25)
    norm = D.ajustar_normalizador(pozos[:2], entradas, cfg.unidades, False, True, alias)
    m = redes.ModeloCurvas(cfg, norm)
    res = m.entrenar(pozos[:2], pozos[2:], forzar_cpu=True)
    assert res.epocas >= 1 and res.historia_ent[-1] < res.historia_ent[0]
    met = res.metricas[0]
    assert met.r2 > 0.5, met                              # DT del demo depende de la porosidad
    media, desv = m.predecir(pozos[2])
    assert media.shape == pozos[2].prof.shape and np.nanmin(desv) >= 0
    copia = redes.ModeloCurvas.desde_texto(m.a_texto())
    m2, d2 = copia.predecir(pozos[2], muestras_mc=0)       # determinista (la copia puede ir en GPU)
    m1, _ = m.predecir(pozos[2], muestras_mc=0)
    assert np.nanmax(np.abs(m2 - m1)) < 0.05 and np.nanmax(d2) == 0


def test_incertidumbre_calibrada_con_validacion(redes):
    """D121: la banda del MC dropout se escala para que en la validación el 95 % del error quede en ±2σ;
    el factor se guarda con el modelo. Sin pozo de validación queda sin calibrar."""
    entradas = ["GR", "RHOB", "NPHI", "ILD"]
    pozos, alias = _pozos(entradas, "DT")
    cfg = redes.Configuracion("regresion", "unet", entradas, ["API", "G/C3", "PU", "OHMM"], "DT",
                              largo=64, canales=8, epocas=15, lote=16, lr=5e-3, muestras_mc=8, paciencia=15)
    norm = D.ajustar_normalizador(pozos[:2], entradas, cfg.unidades, False, True, alias)
    m = redes.ModeloCurvas(cfg, norm)
    res = m.entrenar(pozos[:2], pozos[2:], forzar_cpu=True)
    assert res.calibracion >= 1.0 and m.cfg.calibracion == res.calibracion
    media, desv = m.predecir(pozos[2])
    y = pozos[2].y
    ok = np.isfinite(y) & np.isfinite(media)
    assert np.mean(np.abs(y[ok] - media[ok]) <= 2 * desv[ok]) > 0.85      # 95 % salvo el azar del MC
    assert redes.ModeloCurvas.desde_texto(m.a_texto()).cfg.calibracion == res.calibracion
    sin_val = redes.ModeloCurvas(redes.Configuracion(**{**cfg.__dict__, "calibracion": 0.0}), norm)
    assert sin_val.entrenar(pozos[:2], [], forzar_cpu=True).calibracion == 0.0


def _litologia_coherente(reg):
    """Etiquetas que sí se pueden aprender de las curvas: arena (GR bajo) / lutita (GR alto),
    con la frontera tomada de la NPHI del demo (sin ruido en las arenas)."""
    from kurvo.modulos.deep_learning import facies_a_intervalos
    gr = reg.columna("GR").datos
    clase = np.where(reg.columna("NPHI").datos < 27, 1.0, 4.0)
    clase[gr == NULO] = np.nan
    return facies_a_intervalos(reg.columnas[reg.indice_md].datos, clase, "truth")


def test_clasificacion_litofacies(redes):
    pr = proyecto_demo()
    alias = alias_por_defecto()
    entradas = ["GR", "RHOB", "SP"]
    pozos = [D.extraer(p.logs[0], p.nombre, entradas, alias=alias, litologia=_litologia_coherente(p.logs[0]))
             for p in pr.pozos]
    clases = sorted({int(v) for p in pozos for v in p.y if v >= 0})
    cfg = redes.Configuracion("clasificacion", "unet", entradas, ["API", "G/C3", "PU"], "LITHO", clases,
                              largo=64, canales=8, epocas=25, lote=16, lr=5e-3, muestras_mc=3, paciencia=25)
    norm = D.ajustar_normalizador(pozos[:2], entradas, cfg.unidades, False, True, alias, regresion=False)
    m = redes.ModeloCurvas(cfg, norm)
    res = m.entrenar(pozos[:2], pozos[2:], forzar_cpu=True)
    assert res.metricas[0].exactitud > 0.9, res.metricas
    clase, prob = m.predecir(pozos[2])
    ok = np.isfinite(clase)
    assert set(np.unique(clase[ok])) <= set(clases) and np.nanmax(prob) <= 1.0 + 1e-6


def test_dispositivo(redes):
    import torch
    dev, texto = redes.elegir_dispositivo(forzar_cpu=True)
    assert dev.type == "cpu" and "forced" in texto
    dev, texto = redes.elegir_dispositivo()
    assert (dev.type == "cuda") == torch.cuda.is_available()


def test_dialogo_deep_learning(redes, qapp, tmp_path):
    from kurvo.vista.ventana import VentanaPrincipal
    v = VentanaPrincipal()
    v.proyecto = proyecto_demo()
    v.refrescar_todo()
    d = v.deep_learning()
    assert [c.currentText() for c in d.combos_rol] == ["Train", "Train", "Validate"]
    d.sp_epocas.setValue(3)
    d.sp_largo.setValue(64)
    d.sp_mc.setValue(2)
    d.chk_cpu.setChecked(True)
    assert d.entrenar(sincrono=True) is not None and d.b_predecir.isEnabled()
    assert d.predecir() == 3
    reg = v.proyecto.pozos[0].logs[0]
    assert {"DT_DL", "DT_DL_STD", "DT_FILL"} <= set(reg.nombres())
    a = d.guardar_modelo()
    v.proyecto.guardar(tmp_path / "p.kurvo")
    from kurvo.nucleo.proyecto import Proyecto
    pr2 = Proyecto.abrir(tmp_path / "p.kurvo")
    guardado = next(x for x in pr2.analisis if x.tipo == "dlmodel")
    assert guardado.nombre == a.nombre and redes.ModeloCurvas.desde_texto(guardado.contenido).cfg.objetivo == "DT"
    d.ch_tarea.setCurrentIndex(d.ch_tarea.findData("clasificacion"))
    assert d.entrenar(sincrono=True) is not None
    d.predecir()
    assert any(l.nombre == "DL facies" for l in v.proyecto.pozos[2].litologias)
    v.proyecto.modificado = False
    d.close()
    v.close()
