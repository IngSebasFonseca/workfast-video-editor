from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from video_processor import VideoEditor


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_FOLDER = BASE_DIR / "assets" / "uploads"
OUTPUT_FOLDER = BASE_DIR / "assets" / "outputs"

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "png", "jpg", "jpeg", "webp"}

app = Flask(__name__, static_folder=None)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 2_000 * 1024 * 1024

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def set_job(job_id: str, **updates) -> None:
    with jobs_lock:
        jobs.setdefault(job_id, {}).update(updates)
        jobs[job_id]["updated_at"] = datetime.utcnow().isoformat() + "Z"


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    return send_from_directory(FRONTEND_DIR, path)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "message": "WorkFast server running"})


@app.post("/api/upload")
def upload_file():
    file = request.files.get("file")
    file_type = secure_filename(request.form.get("type", "file"))

    if not file or not file.filename:
        return jsonify({"error": "No seleccionaste ningun archivo."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Tipo de archivo no permitido."}), 400

    original_name = secure_filename(file.filename)
    unique_name = f"{file_type}_{uuid.uuid4().hex[:10]}_{original_name}"
    filepath = UPLOAD_FOLDER / unique_name
    file.save(filepath)

    return jsonify(
        {
            "success": True,
            "filename": unique_name,
            "filepath": str(filepath),
            "type": file_type,
        }
    )


@app.post("/api/process")
def process_video():
    data = request.get_json(silent=True) or {}
    input_video = Path(data.get("input_video", ""))

    if not input_video.exists():
        return jsonify({"error": "No encontre el video de entrada."}), 400

    output_filename = f"edited_{uuid.uuid4().hex[:10]}_{secure_filename(input_video.name)}"
    output_path = OUTPUT_FOLDER / output_filename
    job_id = uuid.uuid4().hex

    set_job(
        job_id,
        status="queued",
        progress=0,
        step="En cola",
        output_filename=output_filename,
        output_path=str(output_path),
    )

    def progress_callback(progress: int, step: str) -> None:
        set_job(job_id, status="processing", progress=progress, step=step)

    def worker() -> None:
        try:
            set_job(job_id, status="processing", progress=1, step="Iniciando")
            editor = VideoEditor(
                input_video=input_video,
                output_path=output_path,
                logo_path=data.get("logo_path") or None,
                ending_path=data.get("ending_path") or None,
                follow_image_path=data.get("follow_image_path") or None,
                progress_callback=progress_callback,
            )
            editor.process_complete(
                title_text=data.get("title_text") or "Mi Video",
                speed=float(data.get("speed", 1.05)),
                zoom_bottom=float(data.get("zoom_bottom", 1.96)),
                zoom_top=float(data.get("zoom_top", 0.96)),
                saturation=float(data.get("saturation", 100)),
                volume_db=float(data.get("volume_db", 5.4)),
                filter_intensity=float(data.get("filter_intensity", 0.24)),
                title_interval=float(data.get("title_interval", 10)),
            )
            set_job(
                job_id,
                status="completed",
                progress=100,
                step="Completado",
                download_url=f"/api/download/{output_filename}",
            )
        except Exception as exc:
            set_job(job_id, status="error", progress=0, step="Error", error=str(exc))

    threading.Thread(target=worker, daemon=True).start()

    return jsonify(
        {
            "success": True,
            "job_id": job_id,
            "output_filename": output_filename,
        }
    )


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job no encontrado."}), 404
    return jsonify(job)


@app.get("/api/download/<filename>")
def download_file(filename: str):
    filepath = OUTPUT_FOLDER / secure_filename(filename)
    if not filepath.exists():
        return jsonify({"error": "Archivo no encontrado."}), 404
    return send_file(filepath, as_attachment=True, download_name=filepath.name)


if __name__ == "__main__":
    print("WorkFast server: http://localhost:5000")
    app.run(debug=True, host="127.0.0.1", port=5000, threaded=True)
