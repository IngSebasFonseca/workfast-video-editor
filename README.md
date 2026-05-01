# WorkFast Video Editor

App local para automatizar un preset de edicion estilo CapCut/Filmora para videos verticales de redes sociales.

## Que hace

- Exporta en formato vertical 9:16, 1080x1920.
- Duplica el video en dos capas.
- Capa inferior: espejo horizontal, zoom 196%, saturacion alta y desvanecimiento suave.
- Capa superior: zoom 96%, filtro HD ligero y enfoque.
- Acelera video y audio a 1.05x.
- Audio: +5.4 dB, reduccion de ruido, filtros de voz y limitador.
- Logo con movimiento de izquierda a derecha durante todo el video.
- Titulo centrado con fondo negro y texto verde cada 10 segundos.
- Imagen "sigueme" en intervalos.
- Badge tipo sticker "LIKE".
- Ending opcional al final.
- Barra de progreso real por job.
- Importacion desde YouTube: pega un canal, playlist o video, elige uno e importalo como video principal.
- Audio HD: denoise, EQ de voz, compresion, loudness y AAC 256 kbps.
- Biblioteca de recursos: logo, imagen de sigueme y ending quedan guardados como predeterminados.

## Requisitos

- Windows 10/11.
- Python 3.10 o superior.
- FFmpeg y ffprobe disponibles en PATH.

Para comprobar FFmpeg:

```powershell
ffmpeg -version
ffprobe -version
```

## Inicio rapido

En PowerShell o CMD:

```bat
cd C:\Users\fonck\Downloads\Workfast\video-editor
start.bat
```

Luego abre:

```text
http://localhost:5000
```

## Uso

1. Sube el video principal.
2. O pega un link de YouTube, pulsa `Cargar` e importa el video que quieras.
3. Usa los recursos predeterminados o sube nuevos logo, sigueme y ending.
4. El titulo se llena con el nombre del video importado/subido y puedes editarlo.
5. Pulsa `Procesar video`.
6. Revisa la barra de progreso.
7. Descarga el resultado cuando termine.

Usa la importacion de YouTube solo con contenido propio, con permiso o con derechos de uso para tus redes.

Los videos subidos y generados se guardan localmente en:

- `assets/uploads`
- `assets/outputs`

Esas carpetas estan ignoradas por Git para no subir tus videos privados.

## Desarrollo

Instalacion manual:

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python backend\main.py
```

Prueba de humo:

```powershell
python scripts\smoke_test.py
```

## Estructura

```text
backend/
  main.py
  video_processor/editor.py
frontend/
  index.html
assets/
  uploads/
  outputs/
requirements.txt
start.bat
```
