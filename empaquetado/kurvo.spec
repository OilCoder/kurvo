# PyInstaller: ejecutable de Windows en una carpeta (onedir), v0.4 (D102).
#   Variante sin deep learning (por defecto):  pyinstaller empaquetado/kurvo.spec
#   Variante completa con PyTorch:             set KURVO_CON_DL=1 && pyinstaller empaquetado/kurvo.spec
# No incluye los datos de prueba.
import os
from pathlib import Path

RAIZ = Path(SPECPATH).resolve().parent
CON_DL = os.environ.get("KURVO_CON_DL") == "1"
NOMBRE = "Kurvo" + ("" if CON_DL else "-sinDL")

excluir = ["tkinter", "matplotlib", "IPython", "pytest", "dliswriter", "h5py", "PyInstaller"]
if not CON_DL:
    excluir += ["torch", "torchvision", "torchaudio", "triton"]

ocultos = ["dlisio", "openpyxl", "scipy.interpolate"]
if CON_DL:
    ocultos += ["torch"]

a = Analysis(
    [str(RAIZ / "empaquetado" / "lanzador.py")],
    pathex=[str(RAIZ / "src")],
    datas=[(str(RAIZ / "README.md"), "."), (str(RAIZ / "datos" / "realistas"), "ejemplos"),
           # los dos ejemplos reales (D125): archivos para importar, sus guías, el manual y sus capturas
           (str(RAIZ / "docs" / "ejemplos" / "el_dorado"), "ejemplos/el_dorado"),
           (str(RAIZ / "docs" / "ejemplos" / "cutter"), "ejemplos/cutter"),
           (str(RAIZ / "docs" / "ejemplo_el_dorado.md"), "ejemplos"), (str(RAIZ / "docs" / "ejemplo_cutter.md"), "ejemplos"),
           (str(RAIZ / "docs" / "manual.md"), "ejemplos"), (str(RAIZ / "docs" / "alcance.md"), "ejemplos")]
          + [(str(p), "ejemplos/capturas") for p in sorted((RAIZ / "docs" / "capturas").glob("gui_v10_*.png"))],
    hiddenimports=ocultos,
    excludes=excluir,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=NOMBRE,
    icon=str(RAIZ / "empaquetado" / "kurvo.ico"),
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NOMBRE)
