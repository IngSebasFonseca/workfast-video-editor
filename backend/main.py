from __future__ import annotations

import threading
import uuid
import base64
import json
import os
import re
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse
import shutil
import urllib.request

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from yt_dlp import YoutubeDL

from video_processor import VideoEditor


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_FOLDER = BASE_DIR / "assets" / "uploads"
OUTPUT_FOLDER = BASE_DIR / "assets" / "outputs"
LIBRARY_FOLDER = BASE_DIR / "assets" / "library"
YOUTUBE_COOKIES_FILE = LIBRARY_FOLDER / "youtube_cookies.txt"
YOUTUBE_BROWSER_PROFILE = LIBRARY_FOLDER / "youtube_chrome_profile"
YOUTUBE_DEBUG_PORT = 9222

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "png", "jpg", "jpeg", "webp"}
ASSET_TYPES = {"logo", "follow", "ending"}
YOUTUBE_COOKIE_BROWSERS = {
    "auto": None,
    "none": None,
    "file": "file",
    "edge": "edge",
    "chrome": "chrome",
    "firefox": "firefox",
    "brave": "brave",
}
YOUTUBE_AUTO_COOKIE_SEQUENCE = [None, "file"]
YOUTUBE_DOWNLOAD_FORMATS = [
    "bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]/best",
    "bv*+ba/b",
    "best",
    None,
]

app = Flask(__name__, static_folder=None)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 2_000 * 1024 * 1024

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
LIBRARY_FOLDER.mkdir(parents=True, exist_ok=True)
YOUTUBE_BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    for prefix in ("video_", "youtube_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    return stem.replace("_", " ").replace("-", " ").strip() or "Mi Video"


def asset_dir(asset_type: str) -> Path:
    safe_type = secure_filename(asset_type)
    if safe_type not in ASSET_TYPES:
        raise ValueError("Tipo de recurso no valido.")
    folder = LIBRARY_FOLDER / safe_type
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def allowed_asset_file(filename: str, asset_type: str) -> bool:
    if not allowed_file(filename):
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    if asset_type in {"logo", "follow"}:
        return ext in {"png", "jpg", "jpeg", "webp"}
    if asset_type == "ending":
        return ext in {"mp4", "mov", "mkv", "avi"}
    return False


def serialize_asset(path: Path, asset_type: str) -> dict:
    return {
        "type": asset_type,
        "filename": path.name,
        "filepath": str(path),
        "preview_url": f"/api/assets/file/{asset_type}/{quote(path.name)}",
        "size": path.stat().st_size,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        "is_default": path.name.startswith("default_"),
    }


def list_library_assets(asset_type: str | None = None) -> dict:
    types = [asset_type] if asset_type else sorted(ASSET_TYPES)
    result: dict[str, dict] = {}
    for current_type in types:
        folder = asset_dir(current_type)
        assets = [
            serialize_asset(path, current_type)
            for path in folder.iterdir()
            if path.is_file() and allowed_asset_file(path.name, current_type)
        ]
        assets.sort(key=lambda item: (not item["is_default"], item["updated_at"]))
        default = next((item for item in assets if item["is_default"]), assets[0] if assets else None)
        result[current_type] = {"default": default, "items": assets}
    return result


def seed_library_defaults() -> None:
    patterns = {
        "logo": "logo_*",
        "follow": "follow_*",
        "ending": "ending_*",
    }
    for asset_type, pattern in patterns.items():
        folder = asset_dir(asset_type)
        if any(path.is_file() and path.name != ".gitkeep" for path in folder.iterdir()):
            continue
        candidates = [
            path
            for path in UPLOAD_FOLDER.glob(pattern)
            if path.is_file() and allowed_asset_file(path.name, asset_type)
        ]
        if not candidates:
            continue
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        target = folder / f"default_{secure_filename(latest.name)}"
        shutil.copy2(latest, target)


def set_job(job_id: str, **updates) -> None:
    with jobs_lock:
        jobs.setdefault(job_id, {}).update(updates)
        jobs[job_id]["updated_at"] = datetime.utcnow().isoformat() + "Z"


def is_supported_video_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_cookie_browser(value: str | None) -> str:
    browser = secure_filename((value or "auto").lower())
    return browser if browser in YOUTUBE_COOKIE_BROWSERS else "auto"


def youtube_cookie_attempts(cookie_browser: str) -> list[str | None]:
    if cookie_browser == "auto":
        return [
            browser
            for browser in YOUTUBE_AUTO_COOKIE_SEQUENCE
            if browser != "file" or YOUTUBE_COOKIES_FILE.exists()
        ]
    return [YOUTUBE_COOKIE_BROWSERS[cookie_browser]]


def youtube_options(base_options: dict, browser: str | None) -> dict:
    options = dict(base_options)
    options.setdefault("js_runtimes", {"node": {}})
    if browser == "file":
        if not YOUTUBE_COOKIES_FILE.exists():
            raise FileNotFoundError("No hay cookies.txt guardado. Sube el archivo en la seccion YouTube.")
        options["cookiefile"] = str(YOUTUBE_COOKIES_FILE)
    elif browser:
        options["cookiesfrombrowser"] = (browser, None, None, None)
    return options


def youtube_browser_label(browser: str | None) -> str:
    labels = {
        None: "sin cookies",
        "file": "cookies.txt",
        "edge": "Edge",
        "chrome": "Chrome",
        "firefox": "Firefox",
        "brave": "Brave",
    }
    return labels.get(browser, str(browser))


def youtube_error_message(error: Exception, attempted: list[str | None]) -> str:
    raw = clean_error_text(str(error))
    tried = ", ".join(youtube_browser_label(browser) for browser in attempted)
    if "not a bot" in raw or "Sign in to confirm" in raw:
        return (
            "YouTube pidio confirmar que no eres bot. Abre YouTube en el navegador donde tienes sesion, "
            "sube un cookies.txt o elige manualmente ese navegador en 'Sesion YouTube'. "
            f"Intentos realizados: {tried}."
        )
    if "failed to load cookies" in raw or "could not copy" in raw.lower():
        return (
            "No pude leer las cookies del navegador seleccionado. Cierra ese navegador por unos segundos, "
            "prueba otro navegador manualmente o sube un archivo cookies.txt. "
            f"Intentos realizados: {tried}."
        )
    if "no devolvio informacion" in raw:
        return (
            "YouTube no devolvio informacion sin sesion. Si antes funcionaba, puede ser un bloqueo temporal "
            "de YouTube para esta IP o este video. Sube un cookies.txt para hacerlo estable. "
            f"Intentos realizados: {tried}."
        )
    return f"No pude leer YouTube ({tried}): {raw}"


def clean_error_text(message: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", message or "").strip()


def find_chrome_executable() -> str | None:
    candidates = [
        os.environ.get("WORKFAST_CHROME_PATH", ""),
        str(Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        str(Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
    ]
    return next((path for path in candidates if path and Path(path).exists()), None)


def open_youtube_login_browser() -> None:
    chrome_path = find_chrome_executable()
    if not chrome_path:
        raise RuntimeError("No encontre Chrome o Edge instalado.")

    subprocess.Popen(
        [
            chrome_path,
            f"--remote-debugging-port={YOUTUBE_DEBUG_PORT}",
            f"--user-data-dir={YOUTUBE_BROWSER_PROFILE}",
            "--no-first-run",
            "--disable-features=DialMediaRouteProvider",
            "https://www.youtube.com/account",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def read_debug_json(path: str) -> dict | list:
    with urllib.request.urlopen(f"http://127.0.0.1:{YOUTUBE_DEBUG_PORT}{path}", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def websocket_request(ws_url: str, method: str, params: dict | None = None) -> dict:
    parsed = urlparse(ws_url)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path
    if parsed.query:
        path += f"?{parsed.query}"

    with socket.create_connection((host, port), timeout=5) as sock:
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(handshake.encode("ascii"))
        response = sock.recv(4096)
        if b" 101 " not in response:
            raise RuntimeError("No pude conectar con Chrome para leer la sesion.")

        payload = json.dumps({"id": 1, "method": method, "params": params or {}}).encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 255, length & 255])
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        sock.sendall(bytes(header) + masked)

        while True:
            frame_header = sock.recv(2)
            if len(frame_header) < 2:
                raise RuntimeError("Chrome cerro la conexion antes de responder.")
            opcode = frame_header[0] & 0x0F
            length = frame_header[1] & 0x7F
            if length == 126:
                length = int.from_bytes(sock.recv(2), "big")
            elif length == 127:
                length = int.from_bytes(sock.recv(8), "big")
            if frame_header[1] & 0x80:
                server_mask = sock.recv(4)
                raw_payload = sock.recv(length)
                frame_payload = bytes(byte ^ server_mask[index % 4] for index, byte in enumerate(raw_payload))
            else:
                frame_payload = sock.recv(length)
            if opcode == 8:
                raise RuntimeError("Chrome cerro la conexion.")
            if opcode != 1:
                continue
            message = json.loads(frame_payload.decode("utf-8"))
            if message.get("id") == 1:
                if "error" in message:
                    raise RuntimeError(message["error"].get("message", "Chrome no entrego cookies."))
                return message.get("result", {})


def export_youtube_cookies_from_debug_browser() -> int:
    try:
        version = read_debug_json("/json/version")
    except Exception as exc:
        raise RuntimeError("Primero pulsa 'Abrir login', inicia sesion en esa ventana y dejala abierta.") from exc

    ws_url = version.get("webSocketDebuggerUrl")
    if not ws_url:
        targets = read_debug_json("/json")
        pages = [target for target in targets if target.get("webSocketDebuggerUrl")]
        if not pages:
            raise RuntimeError("No encontre una pestaña de Chrome abierta para WorkFast.")
        ws_url = pages[0]["webSocketDebuggerUrl"]

    result = websocket_request(ws_url, "Storage.getCookies")
    cookies = [
        cookie
        for cookie in result.get("cookies", [])
        if "youtube.com" in cookie.get("domain", "") or "google.com" in cookie.get("domain", "")
    ]
    if not cookies:
        raise RuntimeError("No encontre sesion de YouTube. Inicia sesion en la ventana que abrio WorkFast.")

    lines = ["# Netscape HTTP Cookie File", "# Generated by WorkFast Video Editor"]
    for cookie in cookies:
        domain = cookie.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.get("path") or "/"
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        expires = int(cookie.get("expires") or 0)
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        lines.append("\t".join([domain, include_subdomains, path, secure, str(expires), name, value]))

    YOUTUBE_COOKIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(cookies)


def normalize_youtube_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        entry = {"url": str(entry), "title": str(entry)}

    video_id = entry.get("id") or ""
    webpage_url = entry.get("webpage_url") or entry.get("url") or ""
    if video_id and not webpage_url.startswith("http"):
        webpage_url = f"https://www.youtube.com/watch?v={video_id}"

    thumbnails = entry.get("thumbnails") or []
    thumbnail = entry.get("thumbnail") or ""
    if thumbnails and not thumbnail:
        thumbnail = thumbnails[-1].get("url") or ""

    return {
        "id": video_id,
        "title": entry.get("title") or "Video sin titulo",
        "url": webpage_url,
        "duration": entry.get("duration"),
        "channel": entry.get("channel") or entry.get("uploader") or "",
        "thumbnail": thumbnail,
    }


seed_library_defaults()


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
            "title": title_from_filename(original_name) if file_type == "video" else "",
        }
    )


@app.get("/api/assets")
def get_assets():
    return jsonify({"success": True, "assets": list_library_assets()})


@app.get("/api/assets/file/<asset_type>/<path:filename>")
def get_asset_file(asset_type: str, filename: str):
    safe_type = secure_filename(asset_type)
    safe_filename = secure_filename(filename)

    if safe_type not in ASSET_TYPES or not safe_filename:
        return jsonify({"error": "Recurso no valido."}), 400

    filepath = asset_dir(safe_type) / safe_filename
    if not filepath.exists() or not allowed_asset_file(filepath.name, safe_type):
        return jsonify({"error": "Recurso no encontrado."}), 404

    return send_file(filepath)


@app.post("/api/assets/upload")
def upload_asset():
    file = request.files.get("file")
    asset_type = secure_filename(request.form.get("type", ""))
    make_default = request.form.get("make_default", "true").lower() != "false"

    if asset_type not in ASSET_TYPES:
        return jsonify({"error": "Tipo de recurso no valido."}), 400

    if not file or not file.filename:
        return jsonify({"error": "No seleccionaste ningun archivo."}), 400

    if not allowed_asset_file(file.filename, asset_type):
        return jsonify({"error": "Archivo no permitido para ese recurso."}), 400

    folder = asset_dir(asset_type)
    original_name = secure_filename(file.filename)
    prefix = "default" if make_default else asset_type
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}_{original_name}"
    filepath = folder / filename
    file.save(filepath)

    if make_default:
        for other in folder.glob("default_*"):
            if other != filepath:
                other.rename(folder / other.name.replace("default_", f"{asset_type}_", 1))

    return jsonify({"success": True, "asset": serialize_asset(filepath, asset_type), "assets": list_library_assets()})


@app.post("/api/assets/default")
def set_default_asset():
    data = request.get_json(silent=True) or {}
    asset_type = secure_filename(data.get("type", ""))
    filename = secure_filename(data.get("filename", ""))

    if asset_type not in ASSET_TYPES:
        return jsonify({"error": "Tipo de recurso no valido."}), 400

    folder = asset_dir(asset_type)
    selected = folder / filename
    if not selected.exists() or not allowed_asset_file(selected.name, asset_type):
        return jsonify({"error": "Recurso no encontrado."}), 404

    for other in folder.glob("default_*"):
        if other != selected:
            other.rename(folder / other.name.replace("default_", f"{asset_type}_", 1))

    if not selected.name.startswith("default_"):
        selected = selected.rename(folder / f"default_{selected.name}")

    return jsonify({"success": True, "asset": serialize_asset(selected, asset_type), "assets": list_library_assets()})


@app.post("/api/youtube/list")
def list_youtube_videos():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    cookie_browser = normalize_cookie_browser(data.get("cookie_browser"))

    if not is_supported_video_url(url):
        return jsonify({"error": "Pega una URL valida de YouTube, canal o playlist."}), 400

    base_options = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    attempted: list[str | None] = []
    last_error: Exception | None = None

    try:
        info = None
        for browser in youtube_cookie_attempts(cookie_browser):
            attempted.append(browser)
            try:
                with YoutubeDL(youtube_options(base_options, browser)) as ydl:
                    info = ydl.extract_info(url, download=False)
                if not info:
                    raise RuntimeError("YouTube no devolvio informacion en este intento.")
                break
            except Exception as exc:
                last_error = exc
                continue

        if info is None and last_error:
            raise RuntimeError(youtube_error_message(last_error, attempted))

        if not info:
            return jsonify({"error": "YouTube no devolvio informacion para ese link."}), 404

        entries = info.get("entries") if isinstance(info, dict) else None
        if entries:
            videos = [normalize_youtube_entry(entry) for entry in entries if entry]
        else:
            videos = [normalize_youtube_entry(info)]

        videos = [video for video in videos if video.get("url")]
        return jsonify({"success": True, "videos": videos, "count": len(videos)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/youtube/cookies")
def get_youtube_cookies_status():
    if not YOUTUBE_COOKIES_FILE.exists():
        return jsonify({"success": True, "configured": False})
    return jsonify(
        {
            "success": True,
            "configured": True,
            "filename": YOUTUBE_COOKIES_FILE.name,
            "size": YOUTUBE_COOKIES_FILE.stat().st_size,
            "updated_at": datetime.fromtimestamp(YOUTUBE_COOKIES_FILE.stat().st_mtime).isoformat(),
        }
    )


@app.post("/api/youtube/cookies")
def upload_youtube_cookies():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No seleccionaste ningun archivo cookies.txt."}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".txt"):
        return jsonify({"error": "Sube un archivo .txt en formato Netscape cookies."}), 400

    file.save(YOUTUBE_COOKIES_FILE)
    return jsonify(
        {
            "success": True,
            "configured": True,
            "filename": YOUTUBE_COOKIES_FILE.name,
            "size": YOUTUBE_COOKIES_FILE.stat().st_size,
        }
    )


@app.post("/api/youtube/login-browser")
def youtube_login_browser():
    try:
        open_youtube_login_browser()
        return jsonify({"success": True, "message": "Chrome abierto para iniciar sesion en YouTube."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/youtube/capture-session")
def youtube_capture_session():
    try:
        cookie_count = export_youtube_cookies_from_debug_browser()
        return jsonify(
            {
                "success": True,
                "configured": True,
                "cookie_count": cookie_count,
                "filename": YOUTUBE_COOKIES_FILE.name,
                "size": YOUTUBE_COOKIES_FILE.stat().st_size,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/youtube/import")
def import_youtube_video():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    cookie_browser = normalize_cookie_browser(data.get("cookie_browser"))

    if not is_supported_video_url(url):
        return jsonify({"error": "URL de video no valida."}), 400

    job_id = uuid.uuid4().hex
    set_job(job_id, status="queued", progress=0, step="En cola para importar")

    def download_hook(payload: dict) -> None:
        status = payload.get("status")
        if status == "downloading":
            total = payload.get("total_bytes") or payload.get("total_bytes_estimate") or 0
            downloaded = payload.get("downloaded_bytes") or 0
            progress = 5
            if total:
                progress = 5 + int((downloaded / total) * 85)
            set_job(job_id, status="processing", progress=min(progress, 90), step="Descargando video")
        elif status == "finished":
            set_job(job_id, status="processing", progress=92, step="Preparando archivo")

    def worker() -> None:
        try:
            set_job(job_id, status="processing", progress=1, step="Conectando con YouTube")
            output_template = str(UPLOAD_FOLDER / f"youtube_{job_id}_%(title).80s.%(ext)s")
            base_options = {
                "merge_output_format": "mp4",
                "outtmpl": output_template,
                "quiet": True,
                "noprogress": True,
                "no_warnings": True,
                "noplaylist": True,
                "progress_hooks": [download_hook],
                "postprocessor_args": {"ffmpeg": ["-movflags", "+faststart"]},
            }
            info = None
            downloaded = None
            attempted: list[str | None] = []
            last_error: Exception | None = None

            for browser in youtube_cookie_attempts(cookie_browser):
                attempted.append(browser)
                for format_spec in YOUTUBE_DOWNLOAD_FORMATS:
                    set_job(
                        job_id,
                        status="processing",
                        progress=2,
                        step="Conectando con YouTube",
                    )
                    try:
                        options = dict(base_options)
                        if format_spec:
                            options["format"] = format_spec
                        with YoutubeDL(youtube_options(options, browser)) as ydl:
                            info = ydl.extract_info(url, download=True) or {}
                            downloaded = Path(ydl.prepare_filename(info))
                            if downloaded.suffix.lower() != ".mp4":
                                downloaded = downloaded.with_suffix(".mp4")
                        break
                    except Exception as exc:
                        last_error = exc
                        if "Requested format is not available" in str(exc):
                            continue
                        break
                if info is not None and downloaded is not None:
                    break

            if info is None or downloaded is None:
                raise RuntimeError(youtube_error_message(last_error or RuntimeError("YouTube no respondio."), attempted))

            if not downloaded.exists():
                candidates = sorted(
                    UPLOAD_FOLDER.glob(f"youtube_{job_id}_*"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
                if not candidates:
                    raise RuntimeError("No encontre el archivo descargado.")
                downloaded = candidates[0]

            safe_name = f"video_{job_id}_{secure_filename(downloaded.name)}"
            final_path = UPLOAD_FOLDER / safe_name
            if downloaded != final_path:
                downloaded.replace(final_path)

            set_job(
                job_id,
                status="completed",
                progress=100,
                step="Video importado",
                filename=safe_name,
                filepath=str(final_path),
                type="video",
                title=info.get("title") or title_from_filename(final_path.name),
            )
        except Exception as exc:
            set_job(job_id, status="error", progress=0, step="Error", error=clean_error_text(str(exc)))

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"success": True, "job_id": job_id})


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
    app.run(debug=False, host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
