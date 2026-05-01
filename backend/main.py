from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
from video_processor import VideoEditor
import threading
import json
from datetime import datetime
from queue import Queue

app = Flask(__name__)
CORS(app)

# Cola para mensajes de progreso
progress_queue = Queue()

UPLOAD_FOLDER = "../assets/uploads"
OUTPUT_FOLDER = "../assets/outputs"
TEMPLATES_FOLDER = "../assets/templates"
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'png', 'jpg', 'jpeg'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024  # 2GB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'Server running'}), 200

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Subir video y assets"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        file_type = request.form.get('type', 'video')  # video, logo, ending, follow
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{file_type}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            return jsonify({
                'success': True,
                'filename': filename,
                'filepath': filepath,
                'type': file_type
            }), 200
        
        return jsonify({'error': 'File type not allowed'}), 400
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/process', methods=['POST'])
def process_video():
    """Procesar video con ediciones automáticas"""
    try:
        data = request.json
        input_video = data.get('input_video')
        logo_path = data.get('logo_path')
        ending_path = data.get('ending_path')
        follow_image_path = data.get('follow_image_path')
        title_text = data.get('title_text', 'Mi Video')
        
        # Parámetros con defaults
        speed = float(data.get('speed', 1.05))
        zoom_bottom = float(data.get('zoom_bottom', 1.96))
        zoom_top = float(data.get('zoom_top', 0.96))
        saturation = float(data.get('saturation', 100))
        volume_db = float(data.get('volume_db', 5.4))
        filter_intensity = float(data.get('filter_intensity', 0.24))
        title_interval = float(data.get('title_interval', 10))
        
        if not input_video or not os.path.exists(input_video):
            return jsonify({'error': 'Input video not found'}), 400
        
        output_filename = f"edited_{os.path.basename(input_video)}"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        
        # Crear editor
        editor = VideoEditor(
            input_video=input_video,
            logo_path=logo_path if logo_path and os.path.exists(logo_path) else None,
            ending_path=ending_path if ending_path and os.path.exists(ending_path) else None,
            follow_image_path=follow_image_path,
            output_path=output_path
        )
        
        # Procesar en background
        def process_async():
            try:
                # Informar que comienza
                progress_queue.put({'status': 'processing', 'step': 'Iniciando...', 'progress': 10})
                
                editor.process_complete(
                    title_text=title_text,
                    speed=speed,
                    zoom_bottom=zoom_bottom,
                    zoom_top=zoom_top,
                    saturation=saturation,
                    volume_db=volume_db,
                    filter_intensity=filter_intensity,
                    title_interval=title_interval
                )
                
                # Completado
                progress_queue.put({'status': 'completed', 'step': 'Completado!', 'progress': 100})
            except Exception as e:
                print(f"❌ Error: {e}")
                progress_queue.put({'status': 'error', 'error': str(e), 'progress': 0})
        
        thread = threading.Thread(target=process_async, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Processing started',
            'output_path': output_path,
            'output_filename': output_filename
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Descargar video procesado"""
    try:
        filepath = os.path.join(OUTPUT_FOLDER, secure_filename(filename))
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(filepath, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def status():
    """Ver estado de procesamiento (Server-Sent Events)"""
    def generate():
        while True:
            try:
                msg = progress_queue.get(timeout=1)
                yield f"data: {json.dumps(msg)}\n\n"
            except:
                yield f"data: {json.dumps({'status': 'waiting'})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/progress', methods=['GET'])
def get_progress():
    """Obtener último estado"""
    try:
        # Obtener sin bloquear
        msg = progress_queue.get_nowait()
        return jsonify(msg), 200
    except:
        return jsonify({'status': 'idle'}), 200

if __name__ == '__main__':
    print("🚀 Server iniciado en http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
