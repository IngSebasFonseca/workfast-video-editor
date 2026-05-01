@echo off
title WorkFast Video Editor - Setup

echo.
echo ╔════════════════════════════════════════════╗
echo ║   WorkFast Video Editor - Setup Script    ║
echo ╚════════════════════════════════════════════╝
echo.

REM Verificar si Python está instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python no está instalado o no está en PATH
    echo Por favor instala Python desde: https://www.python.org
    pause
    exit /b 1
)

echo ✅ Python detectado

REM Verificar si FFmpeg está instalado
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  FFmpeg no está en PATH
    echo Instalando FFmpeg a través de pip...
    echo.
)

REM Crear virtual environment si no existe
if not exist venv (
    echo 📦 Creando entorno virtual...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo ✅ Entorno virtual creado
) else (
    echo ✅ Entorno virtual detectado
    call venv\Scripts\activate.bat
)

echo.
echo 📥 Instalando dependencias...
pip install -r requirements.txt --quiet

echo.
echo.
echo ╔════════════════════════════════════════════╗
echo ║          ✅ SETUP COMPLETADO              ║
echo ╚════════════════════════════════════════════╝
echo.
echo 🚀 Iniciando servidor...
echo    Accede a: http://localhost:5000
echo.
echo Presiona Ctrl+C para detener el servidor
echo.

cd backend
python main.py
