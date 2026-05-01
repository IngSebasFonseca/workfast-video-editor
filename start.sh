#!/bin/bash

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   WorkFast Video Editor - Setup Script    ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Verificar si Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no está instalado"
    exit 1
fi

echo "✅ Python3 detectado"

# Verificar si FFmpeg está instalado
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg no está instalado"
    echo "Instálalo con: brew install ffmpeg (Mac) o sudo apt-get install ffmpeg (Linux)"
fi

# Crear virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ Entorno virtual creado"
else
    echo "✅ Entorno virtual detectado"
    source venv/bin/activate
fi

echo ""
echo "📥 Instalando dependencias..."
pip install -r requirements.txt --quiet

echo ""
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║          ✅ SETUP COMPLETADO              ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "🚀 Iniciando servidor..."
echo "   Accede a: http://localhost:5000"
echo ""
echo "Presiona Ctrl+C para detener el servidor"
echo ""

cd backend
python main.py
