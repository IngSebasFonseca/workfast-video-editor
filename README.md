# 🎬 WorkFast Video Editor

Automatizador de ediciones de video para TikTok y Redes Sociales. Procesa videos con las mismas ediciones que haces manualmente en CapCut.

## 📋 Características

✅ **Duplicación y Espejo**: Capa inferior con efecto espejo  
✅ **Zoom Personalizado**: 196% abajo, 96% arriba  
✅ **Procesamiento de Audio**: +5.4dB, denoise, enhancement  
✅ **Velocidad**: 1.05x en ambas capas  
✅ **Filtro HD**: 24% de intensidad  
✅ **Overlay de Logo**: Animación de izquierda a derecha  
✅ **Títulos Automáticos**: Cada 10 segundos, personalizables  
✅ **Ending Video**: Agrega tu video de cierre  
✅ **Formatos**: 9:16 (TikTok), MP4 optimizado  

## 🚀 Instalación

### Requisitos
- Python 3.10+
- FFmpeg instalado en el sistema

### Pasos

1. **Clonar o descargar el proyecto**
```bash
cd video-editor
```

2. **Crear entorno virtual**
```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Instalar FFmpeg** (si no lo tienes)
```bash
# Windows (con Chocolatey)
choco install ffmpeg

# Mac (con Homebrew)
brew install ffmpeg

# Linux (Ubuntu/Debian)
sudo apt-get install ffmpeg
```

## 📁 Estructura de Archivos

```
video-editor/
├── backend/
│   ├── main.py                 # Servidor Flask
│   ├── video_processor/
│   │   ├── __init__.py
│   │   └── editor.py           # Lógica de procesamiento
│   └── requirements.txt
├── frontend/
│   └── index.html              # Interfaz web
├── assets/
│   ├── uploads/                # Videos/assets subidos
│   ├── outputs/                # Videos procesados
│   └── templates/              # Logo, ending, etc.
└── README.md
```

## 🎬 Cómo Usar

### 1. Iniciar el Servidor

```bash
cd backend
python main.py
```

El servidor estará disponible en: `http://localhost:5000`

### 2. Abrir la Interfaz Web

Abre `frontend/index.html` en tu navegador o accede a:
```
http://localhost:5000
```

### 3. Cargar Archivos

1. **Video Principal**: Sube tu video (MP4, AVI, MOV, MKV)
2. **Logo** (Opcional): PNG/JPG con transparencia
3. **Ending Video** (Opcional): Video MP4 corto para el final
4. **Imagen Sígueme** (Opcional): PNG/JPG

### 4. Configurar Parámetros

- **Título**: Texto que aparecerá en el video
- **Velocidad**: 1.05x (recomendado)
- **Zoom**: 196% abajo, 96% arriba
- **Volumen**: +5.4dB
- **Filtro HD**: 24% de intensidad

### 5. Procesar

Click en **"⚡ PROCESAR VIDEO"** y espera a que termine.

### 6. Descargar

Una vez procesado, descarga tu video editado.

## 📊 Parámetros Detallados

| Parámetro | Valor Default | Rango | Descripción |
|-----------|---------------|-------|-------------|
| Velocidad | 1.05x | 0.5x - 2x | Velocidad de reproducción |
| Zoom Abajo | 196% | 100% - 300% | Zoom de capa inferior (espejo) |
| Zoom Arriba | 96% | 50% - 200% | Zoom de capa principal |
| Saturación | 100% | 0% - 200% | Intensidad de colores (capa inferior) |
| Volumen Audio | +5.4dB | -20dB - +20dB | Ganancia de volumen |
| Intervalo Títulos | 10s | 5s - 30s | Cada cuántos segundos aparece un título |
| Filtro HD | 24% | 0% - 100% | Intensidad del filtro de claridad |

## 🎨 Personalización

### Cambiar Colores de Títulos

Edita `frontend/index.html` (línea ~250):

```javascript
// Cambiar color del texto
txt_clip = TextClip(title_text, color='#00FF00')  // Verde
```

### Agregar Más Efectos

En `backend/video_processor/editor.py`, agrega métodos como:

```python
def custom_effect(self, video_clip):
    # Tu efecto aquí
    return video_clip
```

## ⚙️ Troubleshooting

### Error: "FFmpeg not found"
Asegúrate de instalar FFmpeg y añadirlo a PATH.

### Error: "Movie py not working"
```bash
pip install --upgrade moviepy
```

### Video muy lento en procesar
- Reduce la resolución del video original
- Disminuye tamaño de fuentes/overlays

### Audio desincronizado
- Verifica que el video fuente sea válido
- Intenta con otro códec de audio

## 🔧 Desarrollo

Para agregar características nuevas:

1. Edita `backend/video_processor/editor.py`
2. Agrega métodos nuevos a la clase `VideoEditor`
3. Llama desde `main.py` en la ruta `/api/process`
4. Actualiza `frontend/index.html` con nuevos controls

## 📦 Deploy

Para desplegar en servidor:

```bash
# Usar Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 backend.main:app
```

## 📄 Licencia

Este proyecto es de código abierto. Úsalo libremente.

## 💬 Soporte

Si encuentras problemas:
1. Verifica que todos los archivos estén en lugar correcto
2. Asegúrate de tener permisos en la carpeta `assets/`
3. Revisa la consola del servidor para errores

---

**Creado con ❤️ para creators de contenido**
