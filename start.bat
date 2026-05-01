@echo off
setlocal
title WorkFast Video Editor

cd /d "%~dp0"

echo.
echo WorkFast Video Editor
echo =====================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no esta en PATH.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ERROR: FFmpeg no esta instalado o no esta en PATH.
    echo Instala FFmpeg y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

where ffprobe >nul 2>nul
if errorlevel 1 (
    echo ERROR: ffprobe no esta instalado o no esta en PATH.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

call "venv\Scripts\activate.bat"

echo Instalando dependencias...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo ERROR: No se pudo actualizar pip.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

echo.
echo Servidor iniciado en http://localhost:5000
echo Presiona Ctrl+C para detenerlo.
echo.

python backend\main.py
