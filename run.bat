@echo off
REM Abre Kurvo. La primera vez prepara el entorno con uv, que descarga Python 3.12 si hace falta.
REM Con KURVO_SIN_DL=1 no se instala PyTorch (sin el paso 5, Reconstruir).
cd /d "%~dp0"
if exist ".venv\kurvo_listo.txt" goto abrir

where uv >nul 2>nul
if errorlevel 1 (
    echo Kurvo necesita uv para instalarse. Instalelo con este comando y vuelva a abrir run.bat:
    echo.
    echo     winget install astral-sh.uv
    echo.
    echo o siga https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

echo Primera vez: preparando Kurvo. Puede tardar unos minutos...
uv venv .venv --python 3.12 --allow-existing
if errorlevel 1 goto fallo
uv pip install --python .venv\Scripts\python.exe -e ".[dev,dlis]"
if errorlevel 1 goto fallo

if "%KURVO_SIN_DL%"=="1" goto listo
REM PyTorch para Reconstruir: version CUDA si hay GPU NVIDIA, si no la de CPU
where nvidia-smi >nul 2>nul
if errorlevel 1 (
    uv pip install --python .venv\Scripts\python.exe torch --index-url https://download.pytorch.org/whl/cpu
) else (
    uv pip install --python .venv\Scripts\python.exe torch --index-url https://download.pytorch.org/whl/cu128
)
if errorlevel 1 echo No se pudo instalar PyTorch: Kurvo abre igual, sin el paso 5 (Reconstruir).

:listo
echo listo> ".venv\kurvo_listo.txt"

:abrir
".venv\Scripts\python.exe" -m kurvo %*
exit /b

:fallo
echo.
echo No se pudo preparar el entorno. Revise el mensaje de arriba.
pause
exit /b 1
