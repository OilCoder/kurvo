"""Redes 1D, dispositivo (GPU/CPU), entrenamiento con validación por pozo e incertidumbre por
MC dropout calibrada con los pozos de validación (D121). Todo lo que importa torch está aquí; el resto
del paquete funciona sin él."""
from __future__ import annotations

import base64
import io
import json
import math
import time
from dataclasses import asdict, dataclass, field

import numpy as np

from . import datos as D

ARQUITECTURAS = {"unet": "1D U-Net (convolutional)", "bigru": "Bidirectional GRU (recurrent)"}
TAREAS = {"regresion": "Curve reconstruction", "clasificacion": "Lithofacies classification"}


def torch_disponible() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def elegir_dispositivo(forzar_cpu: bool = False):
    """(torch.device, descripción legible). CUDA si hay GPU NVIDIA, MPS en Mac, si no CPU."""
    import torch
    if not forzar_cpu and torch.cuda.is_available():
        i = torch.cuda.current_device()
        mem = torch.cuda.get_device_properties(i).total_memory / 2**30
        return torch.device("cuda", i), f"GPU: {torch.cuda.get_device_name(i)} ({mem:.0f} GB, CUDA {torch.version.cuda})"
    mps = getattr(torch.backends, "mps", None)
    if not forzar_cpu and mps is not None and mps.is_available():
        return torch.device("mps"), "GPU: Apple Metal (MPS)"
    hilos = torch.get_num_threads()
    return torch.device("cpu"), f"CPU ({hilos} threads)" + (" — forced" if forzar_cpu else "")


@dataclass
class Configuracion:
    tarea: str = "regresion"
    arquitectura: str = "unet"
    entradas: list[str] = field(default_factory=list)
    unidades: list[str] = field(default_factory=list)
    objetivo: str = ""
    clases: list[int] = field(default_factory=list)          # ids de litología (clasificación)
    largo: int = 128                                          # muestras por ventana
    canales: int = 32
    dropout: float = 0.2
    epocas: int = 60
    lote: int = 32
    lr: float = 2e-3
    paciencia: int = 10
    semilla: int = 0
    muestras_mc: int = 20
    por_pozo: bool = True
    enmascarar: float = 0.15       # fracción de entradas ocultadas al azar al entrenar (robustez a huecos)
    # factor que lleva la desviación del MC dropout al error real medido en los pozos de validación (D121);
    # 0 = sin calibrar (no hubo validación)
    calibracion: float = 0.0


# ------------------------------------------------------------------ modelos
def construir_modelo(cfg: Configuracion, n_entrada: int, n_salida: int):
    import torch
    from torch import nn

    class Bloque(nn.Module):
        def __init__(self, a, b, p):
            super().__init__()
            self.f = nn.Sequential(nn.Conv1d(a, b, 5, padding=2), nn.BatchNorm1d(b), nn.GELU(),
                                   nn.Dropout(p), nn.Conv1d(b, b, 5, padding=2), nn.BatchNorm1d(b), nn.GELU())

        def forward(self, x):
            return self.f(x)

    class UNet1D(nn.Module):
        """Codificador-decodificador con atajos: ve contexto de ~largo muestras y conserva el detalle."""

        def __init__(self, cin, cout, c, p, niveles=3):
            super().__init__()
            self.bajada = nn.ModuleList()
            self.subida = nn.ModuleList()
            self.ups = nn.ModuleList()
            a = cin
            anchos = [c * 2 ** i for i in range(niveles + 1)]
            for w in anchos[:-1]:
                self.bajada.append(Bloque(a, w, p))
                a = w
            self.fondo = Bloque(a, anchos[-1], p)
            for w in reversed(anchos[:-1]):
                self.ups.append(nn.ConvTranspose1d(w * 2, w, 2, stride=2))
                self.subida.append(Bloque(w * 2, w, p))
            self.salida = nn.Conv1d(anchos[0], cout, 1)
            self.pool = nn.MaxPool1d(2)

        def forward(self, x):
            atajos = []
            for b in self.bajada:
                x = b(x)
                atajos.append(x)
                x = self.pool(x)
            x = self.fondo(x)
            for up, b, s in zip(self.ups, self.subida, reversed(atajos)):
                x = up(x)
                if x.shape[-1] != s.shape[-1]:
                    x = nn.functional.pad(x, (0, s.shape[-1] - x.shape[-1]))
                x = b(torch.cat([x, s], 1))
            return self.salida(x)

    class BiGRU(nn.Module):
        def __init__(self, cin, cout, c, p):
            super().__init__()
            self.entrada = nn.Conv1d(cin, c, 3, padding=1)
            self.gru = nn.GRU(c, c, num_layers=2, batch_first=True, bidirectional=True, dropout=p)
            self.drop = nn.Dropout(p)
            self.salida = nn.Linear(2 * c, cout)

        def forward(self, x):
            h = torch.relu(self.entrada(x)).transpose(1, 2)
            h, _ = self.gru(h)
            return self.salida(self.drop(h)).transpose(1, 2)

    if cfg.arquitectura == "bigru":
        return BiGRU(n_entrada, n_salida, cfg.canales * 2, cfg.dropout)
    return UNet1D(n_entrada, n_salida, cfg.canales, cfg.dropout)


# ------------------------------------------------------------------ resultado
@dataclass
class Metricas:
    pozo: str
    muestras: int
    r2: float = math.nan
    rmse: float = math.nan
    exactitud: float = math.nan


@dataclass
class Resultado:
    historia_ent: list[float]
    historia_val: list[float]
    metricas: list[Metricas]
    dispositivo: str
    segundos: float
    epocas: int
    lote_final: int
    calibracion: float = 0.0        # ver Configuracion.calibracion


class ModeloCurvas:
    """Red entrenada + configuración + normalización: entrena, predice y se guarda como texto."""

    def __init__(self, cfg: Configuracion, normalizador: D.Normalizador | None = None):
        self.cfg = cfg
        self.norm = normalizador
        self.red = None
        self.dispositivo = None
        self.descripcion_dispositivo = ""

    # -------------------------------------------------------------- dimensiones
    @property
    def regresion(self) -> bool:
        return self.cfg.tarea == "regresion"

    @property
    def n_salida(self) -> int:
        return 1 if self.regresion else len(self.cfg.clases)

    def _entrada(self, p: D.Pozo) -> np.ndarray:
        return D.entrada_red(p, self.norm)

    def _objetivo(self, p: D.Pozo) -> np.ndarray:
        if self.regresion:
            return D.objetivo_red(p, self.norm)
        idx = {c: i for i, c in enumerate(self.cfg.clases)}
        return np.array([idx.get(int(v), D.IGNORAR) for v in p.y], dtype=np.int64)

    def _ventanas(self, pozos, paso):
        Xs, Ys = [], []
        L = self.cfg.largo
        for p in pozos:
            X, y = self._entrada(p), self._objetivo(p)
            for i in D.ventanas(X.shape[1], L, paso):
                yv = y[i:i + L]
                if (np.isfinite(yv).sum() if self.regresion else (yv >= 0).sum()) < max(4, L // 16):
                    continue
                Xs.append(D.cortar(X[:, i:i + L], L))
                relleno = np.nan if self.regresion else D.IGNORAR
                Ys.append(np.pad(yv, (0, L - len(yv)), constant_values=relleno))
        if not Xs:
            return None, None
        return np.stack(Xs), np.stack(Ys)

    # -------------------------------------------------------------- entrenamiento
    def entrenar(self, entrenamiento: list[D.Pozo], validacion: list[D.Pozo], forzar_cpu: bool = False,
                 progreso=None, cancelado=None) -> Resultado:
        """`progreso(época, total, pérdida_ent, pérdida_val)`; `cancelado()` -> True para parar."""
        import torch
        from torch import nn
        cfg = self.cfg
        torch.manual_seed(cfg.semilla)
        rng = np.random.default_rng(cfg.semilla)
        self.dispositivo, self.descripcion_dispositivo = elegir_dispositivo(forzar_cpu)
        Xe, Ye = self._ventanas(entrenamiento, max(cfg.largo // 4, 1))
        if Xe is None:
            raise ValueError("No training windows: the training wells have no target data.")
        Xv, Yv = self._ventanas(validacion, cfg.largo) if validacion else (None, None)
        n_in = Xe.shape[1]
        lote = cfg.lote
        t0 = time.time()
        while True:
            try:
                self.red = construir_modelo(cfg, n_in, self.n_salida).to(self.dispositivo)
                hist = self._bucle(Xe, Ye, Xv, Yv, lote, rng, progreso, cancelado, torch, nn)
                break
            except RuntimeError as e:          # memoria de GPU agotada: lote más chico o CPU
                if "out of memory" not in str(e).lower():
                    raise
                if self.dispositivo.type == "cuda":
                    torch.cuda.empty_cache()
                if lote > 4:
                    lote //= 2
                elif self.dispositivo.type != "cpu":
                    self.dispositivo, self.descripcion_dispositivo = elegir_dispositivo(True)
                    self.descripcion_dispositivo += " (GPU out of memory)"
                else:
                    raise
        metricas = [self.evaluar(p) for p in validacion]
        if self.regresion:
            cfg.calibracion = self.calibrar(validacion)
        return Resultado(hist[0], hist[1], metricas, self.descripcion_dispositivo, time.time() - t0,
                         len(hist[0]), lote, cfg.calibracion)

    def calibrar(self, validacion: list[D.Pozo]) -> float:
        """Factor de la incertidumbre (D121). La dispersión del MC dropout mide la duda del modelo, no
        lo que no puede saber (hueco derrumbado, un pozo distinto de los vecinos): en las pruebas a ciegas
        del banco de investigación resultó 4-10 veces menor que el error real. El factor hace que, en los
        pozos de validación, el 95 % del error quede dentro de ±2 desviaciones."""
        if self.cfg.muestras_mc <= 0:
            return 0.0
        self.cfg.calibracion = 0.0                   # medir con la dispersión sin corregir
        cocientes = []
        for p in validacion:
            if p.y is None:
                continue
            media, desv = self.predecir(p)
            y = np.asarray(p.y, float)
            ok = np.isfinite(y) & np.isfinite(media) & np.isfinite(desv) & (desv > 0)
            cocientes.append(np.abs(y[ok] - media[ok]) / desv[ok])
        z = np.concatenate(cocientes) if cocientes else np.array([])
        if z.size < 50:
            return 0.0
        return float(max(np.quantile(z, 0.95) / 2.0, 1.0))

    def _perdida(self, salida, y, nn, torch):
        if self.regresion:
            m = torch.isfinite(y)
            if not m.any():
                return salida.sum() * 0
            return nn.functional.smooth_l1_loss(salida[:, 0][m], y[m], beta=0.5)
        return nn.functional.cross_entropy(salida, y, ignore_index=D.IGNORAR)

    def _bucle(self, Xe, Ye, Xv, Yv, lote, rng, progreso, cancelado, torch, nn):
        cfg, dev = self.cfg, self.dispositivo
        opt = torch.optim.AdamW(self.red.parameters(), lr=cfg.lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=cfg.epocas *
                                                    max(1, math.ceil(len(Xe) / lote)))
        Xe_t, Ye_t = torch.from_numpy(Xe), torch.from_numpy(Ye)
        c = Xe.shape[1] // 2
        mejor, mejor_estado, sin_mejora = math.inf, None, 0
        h_ent, h_val = [], []
        for ep in range(cfg.epocas):
            self.red.train()
            orden = rng.permutation(len(Xe))
            total = 0.0
            for i in range(0, len(orden), lote):
                idx = torch.from_numpy(orden[i:i + lote])
                xb, yb = Xe_t[idx].to(dev), Ye_t[idx].to(dev)
                if cfg.enmascarar > 0:          # oculta curvas enteras de algunas ventanas
                    oc = (torch.rand(xb.shape[0], c, 1, device=dev) < cfg.enmascarar).float()
                    xb = torch.cat([xb[:, :c] * (1 - oc), xb[:, c:] * (1 - oc)], 1)
                opt.zero_grad()
                loss = self._perdida(self.red(xb), yb, nn, torch)
                loss.backward()
                nn.utils.clip_grad_norm_(self.red.parameters(), 1.0)
                opt.step()
                sched.step()
                total += loss.item() * len(idx)
            h_ent.append(total / len(Xe))
            val = self._perdida_val(Xv, Yv, lote, torch, nn) if Xv is not None else h_ent[-1]
            h_val.append(val)
            if progreso:
                progreso(ep + 1, cfg.epocas, h_ent[-1], val)
            if val < mejor - 1e-5:
                mejor, sin_mejora = val, 0
                mejor_estado = {k: v.detach().cpu().clone() for k, v in self.red.state_dict().items()}
            else:
                sin_mejora += 1
            if sin_mejora >= cfg.paciencia or (cancelado and cancelado()):
                break
        if mejor_estado is not None:
            self.red.load_state_dict(mejor_estado)
        return h_ent, h_val

    def _perdida_val(self, Xv, Yv, lote, torch, nn):
        self.red.eval()
        total = 0.0
        with torch.no_grad():
            for i in range(0, len(Xv), lote):
                xb = torch.from_numpy(Xv[i:i + lote]).to(self.dispositivo)
                yb = torch.from_numpy(Yv[i:i + lote]).to(self.dispositivo)
                total += float(self._perdida(self.red(xb), yb, nn, torch)) * len(xb)
        return total / len(Xv)

    # -------------------------------------------------------------- predicción
    def predecir(self, p: D.Pozo, muestras_mc: int | None = None):
        """Regresión: (media, desviación) en unidades de la curva. Clasificación: (clase, probabilidad).

        La incertidumbre es la dispersión de `muestras_mc` pasadas con dropout activo (MC dropout),
        multiplicada por el factor de calibración si lo hay (D121). Con `muestras_mc=0` la predicción es
        determinista (dropout apagado) y la desviación es 0."""
        import torch
        if self.dispositivo is None:
            self.dispositivo, self.descripcion_dispositivo = elegir_dispositivo()
            self.red.to(self.dispositivo)
        X = self._entrada(p)
        N, L = X.shape[1], self.cfg.largo
        inicios = D.ventanas(N, L, max(L // 4, 1))
        lotes = np.stack([D.cortar(X[:, i:i + L], L) for i in inicios])
        w = D.peso_ventana(L)
        pedido = muestras_mc if muestras_mc is not None else self.cfg.muestras_mc
        n_mc = max(1, pedido)
        self.red.eval()
        if pedido > 0:
            for m in self.red.modules():                     # MC dropout: solo dropout en modo train
                if m.__class__.__name__.startswith("Dropout"):
                    m.train()
        salidas = []
        with torch.no_grad():
            xt = torch.from_numpy(lotes).to(self.dispositivo)
            for _ in range(n_mc):
                o = []
                for i in range(0, len(xt), 64):
                    s = self.red(xt[i:i + 64])
                    o.append((s if self.regresion else torch.softmax(s, 1)).cpu().numpy())
                salidas.append(np.concatenate(o))
        salidas = np.stack(salidas)                          # (mc, ventanas, salida, L)
        acum = np.zeros((n_mc, salidas.shape[2], N), np.float64)
        peso = np.zeros(N)
        for k, i in enumerate(inicios):
            n = min(L, N - i)
            acum[:, :, i:i + n] += salidas[:, k, :, :n] * w[:n]
            peso[i:i + n] += w[:n]
        acum /= np.maximum(peso, 1e-9)
        sin_entrada = ~np.isfinite(D.transformar_entrada(p.X, self.norm.log_entrada)).any(axis=0)
        if self.regresion:
            vals = D.desnormalizar(acum[:, 0], self.norm)
            media, desv = vals.mean(0), vals.std(0)
            if self.cfg.calibracion > 0:
                desv = desv * self.cfg.calibracion
            media[sin_entrada], desv[sin_entrada] = np.nan, np.nan
            return media, desv
        prob = acum.mean(0)
        clase = np.array(self.cfg.clases)[prob.argmax(0)].astype(float)
        pmax = prob.max(0)
        clase[sin_entrada], pmax[sin_entrada] = np.nan, np.nan
        return clase, pmax

    def evaluar(self, p: D.Pozo) -> Metricas:
        pred, _ = self.predecir(p, muestras_mc=0)
        if self.regresion:
            y = np.asarray(p.y, float)
            ok = np.isfinite(y) & np.isfinite(pred)
            if ok.sum() < 2:
                return Metricas(p.nombre, int(ok.sum()))
            res = y[ok] - pred[ok]
            ss = ((y[ok] - y[ok].mean()) ** 2).sum()
            return Metricas(p.nombre, int(ok.sum()), float(1 - (res ** 2).sum() / ss) if ss > 0 else math.nan,
                            float(np.sqrt((res ** 2).mean())))
        ok = (p.y >= 0) & np.isfinite(pred)
        return Metricas(p.nombre, int(ok.sum()),
                        exactitud=float((pred[ok] == p.y[ok]).mean()) if ok.any() else math.nan)

    # -------------------------------------------------------------- persistencia (texto)
    def a_texto(self) -> str:
        import torch
        buf = io.BytesIO()
        torch.save({k: v.cpu() for k, v in self.red.state_dict().items()}, buf)
        return json.dumps({"formato": "kurvo.dl/1", "config": asdict(self.cfg),
                           "normalizador": self.norm.a_dict(), "n_entrada": 2 * len(self.cfg.entradas),
                           "pesos": base64.b64encode(buf.getvalue()).decode("ascii")})

    @classmethod
    def desde_texto(cls, texto: str) -> "ModeloCurvas":
        import torch
        d = json.loads(texto)
        m = cls(Configuracion(**d["config"]), D.Normalizador.desde_dict(d["normalizador"]))
        m.red = construir_modelo(m.cfg, d["n_entrada"], m.n_salida)
        estado = torch.load(io.BytesIO(base64.b64decode(d["pesos"])), map_location="cpu", weights_only=True)
        m.red.load_state_dict(estado)
        return m
