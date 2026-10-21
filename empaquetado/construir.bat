@echo off
REM Construye el ejecutable de Windows de Kurvo (ver README, "Ejecutable para Windows").
REM   construir.bat        variante sin deep learning (pequena)
REM   construir.bat dl     variante completa con PyTorch (varios GB si el .venv tiene PyTorch con CUDA)
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
    echo Falta el entorno .venv. Siga la instalacion del README.
    exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>nul || (
    echo Instalando PyInstaller...
    uv pip install --python .venv\Scripts\python.exe pyinstaller || exit /b 1
)
".venv\Scripts\python.exe" empaquetado\icono.py || exit /b 1
set KURVO_CON_DL=
if /i "%1"=="dl" set KURVO_CON_DL=1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist --workpath build empaquetado\kurvo.spec || exit /b 1
REM los ejemplos van junto al .exe, donde el usuario los ve (no escondidos en _internal; D123)
for %%D in (Kurvo-sinDL Kurvo) do (
    if exist "dist\%%D\_internal\ejemplos" move "dist\%%D\_internal\ejemplos" "dist\%%D\ejemplos" >nul
)
echo.
echo Listo: carpeta dist\ (Kurvo-sinDL o Kurvo). Para un instalador, compile
echo empaquetado\instalador.iss con Inno Setup (opcional).
