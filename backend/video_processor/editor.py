import cv2
import numpy as np
import os
from PIL import Image
import librosa
import soundfile as sf
from scipy import signal
import subprocess
import logging
from pathlib import Path
import tempfile
import shutil

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class VideoEditor:
    """Editor profesional de video para TikTok/Redes Sociales"""
    
    def __init__(self, input_video, logo_path=None, ending_path=None, 
                 follow_image_path=None, output_path="output.mp4"):
        self.input_video = input_video
        self.logo_path = logo_path
        self.ending_path = ending_path
        self.follow_image_path = follow_image_path
        self.output_path = output_path
        self.temp_dir = tempfile.mkdtemp(prefix="workfast_")
        
        if not os.path.exists(input_video):
            raise FileNotFoundError(f"❌ Video no encontrado: {input_video}")
        
        self.fps, self.duration, self.width, self.height = self._get_video_info(input_video)
        logger.info(f"✓ Video detectado: {self.width}x{self.height} @ {self.fps}fps")
    
    def _get_video_info(self, video_path):
        """Obtener info del video con ffprobe o fallback a OpenCV"""
        try:
            # Intentar ffprobe
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,r_frame_rate',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
            
            if len(lines) >= 3:
                w, h = int(lines[0]), int(lines[1])
                fps = float(lines[2].split('/')[0]) if '/' in lines[2] else float(lines[2])
            else:
                raise ValueError("Parseo fallido")
            
            # Duración
            dur_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video_path
            ]
            dur_result = subprocess.run(dur_cmd, capture_output=True, text=True, timeout=10)
            duration = float(dur_result.stdout.strip())
            return fps, duration, w, h
            
        except Exception as e:
            logger.warning(f"ffprobe falló: {e}, usando OpenCV...")
            return self._get_video_info_cv2(video_path)
    
    def _get_video_info_cv2(self, video_path):
        """Fallback a OpenCV"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"No se puede abrir: {video_path}")
        
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1080
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 10
        cap.release()
        return fps, duration, w, h
    
    def process_complete(self, title_text="Mi Video", speed=1.05, zoom_bottom=1.96, 
                        zoom_top=0.96, saturation=100, volume_db=5.4, 
                        filter_intensity=0.24, title_interval=10):
        """Procesar video COMPLETO con TODAS las ediciones"""
        try:
            logger.info("\n" + "="*60)
            logger.info("⚡ INICIANDO PROCESAMIENTO")
            logger.info("="*60)
            
            # 1. Extraer audio
            logger.info("📊 [1/5] Extrayendo audio...")
            audio_path = self._extract_audio(self.input_video)
            
            # 2. Procesar audio
            logger.info(f"🔊 [2/5] Procesando audio (+{volume_db}dB, denoise)...")
            processed_audio = self._process_audio(audio_path, volume_db=volume_db)
            
            # 3. Procesar video con efectos
            logger.info(f"🎬 [3/5] Procesando video (velocidad {speed}x, zoom, filtros)...")
            video_with_effects = self._create_effects_video(
                speed=speed, zoom_bottom=zoom_bottom, zoom_top=zoom_top,
                saturation=saturation, filter_intensity=filter_intensity
            )
            
            # 4. Combinar video con audio
            logger.info("🔗 [4/5] Combinando video + audio...")
            video_with_audio = self._combine_video_audio(video_with_effects, processed_audio)
            
            # 5. Agregar ending si existe
            if self.ending_path and os.path.exists(self.ending_path):
                logger.info("🎞️  [5/5] Agregando ending...")
                final_video = self._add_ending(video_with_audio)
            else:
                final_video = video_with_audio
            
            # Mover a destino final
            shutil.move(final_video, self.output_path)
            
            logger.info("="*60)
            logger.info(f"✅ PROCESAMIENTO COMPLETADO")
            logger.info(f"📁 Archivo: {self.output_path}")
            logger.info("="*60 + "\n")
            
            return self.output_path
            
        except Exception as e:
            logger.error(f"\n❌ ERROR: {e}\n", exc_info=False)
            raise
        finally:
            self._cleanup()
    
    def _extract_audio(self, video_path):
        """Extraer audio a WAV"""
        audio_path = os.path.join(self.temp_dir, "audio.wav")
        cmd = ['ffmpeg', '-i', video_path, '-q:a', '9', '-vn', '-y', audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Error extrayendo audio: {result.stderr}")
        return audio_path
    
    def _process_audio(self, audio_path, volume_db=5.4):
        """Procesar audio: amplificar, denoise"""
        try:
            audio, sr = librosa.load(audio_path, sr=None)
            
            # Amplificar
            gain = 10 ** (volume_db / 20)
            audio = audio * gain
            
            # Normalizar
            max_val = np.max(np.abs(audio))
            if max_val > 1.0:
                audio = audio / max_val
            
            # Denoise
            audio = self._denoise_audio(audio, sr)
            
            output = os.path.join(self.temp_dir, "audio_processed.wav")
            sf.write(output, audio, sr)
            return output
        except Exception as e:
            logger.warning(f"Error en procesamiento de audio: {e}, usando original")
            return audio_path
    
    def _denoise_audio(self, audio, sr):
        """Denoise básico"""
        try:
            D = librosa.stft(audio, n_fft=2048)
            mag = np.abs(D)
            threshold = np.mean(mag) * 0.5
            D *= (mag > threshold)
            return librosa.istft(D)
        except:
            return audio
    
    def _create_effects_video(self, speed=1.05, zoom_bottom=1.96, zoom_top=0.96,
                             saturation=100, filter_intensity=0.24):
        """Procesar video con efectos usando ffmpeg"""
        output = os.path.join(self.temp_dir, "video_effects.mp4")
        
        filters = self._build_filter_chain(
            speed=speed, zoom_bottom=zoom_bottom, zoom_top=zoom_top,
            saturation=saturation, filter_intensity=filter_intensity
        )
        
        cmd = [
            'ffmpeg', '-i', self.input_video,
            '-vf', filters,
            '-c:v', 'libx264', '-preset', 'faster', '-crf', '22',
            '-an', '-y', output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Error procesando video: {result.stderr}")
        return output
    
    def _build_filter_chain(self, speed=1.05, zoom_bottom=1.96, zoom_top=0.96,
                           saturation=100, filter_intensity=0.24):
        """Construir filtros ffmpeg"""
        filters = []
        
        # 1. Escalar a 9:16 (1080x1920)
        filters.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2")
        
        # 2. Velocidad
        filters.append(f"setpts=PTS/{speed}")
        
        # 3. Zoom simulado (escalar + padding)
        zoom_w = int(1080 * zoom_top)
        zoom_h = int(1920 * zoom_top)
        filters.append(f"scale={zoom_w}:{zoom_h},pad=1080:1920:(1080-{zoom_w})/2:(1920-{zoom_h})/2")
        
        # 4. Mejorar calidad (saturación + contraste)
        sat_val = 1 + (saturation - 100) * 0.01
        filters.append(f"eq=contrast=1.{int(filter_intensity*10)}:saturation={sat_val:.2f}")
        
        return ','.join(filters)
    
    def _combine_video_audio(self, video_path, audio_path):
        """Combinar video sin audio con audio procesado"""
        output = os.path.join(self.temp_dir, "video_audio.mp4")
        
        cmd = [
            'ffmpeg', '-i', video_path, '-i', audio_path,
            '-c:v', 'copy', '-c:a', 'aac',
            '-map', '0:v:0', '-map', '1:a:0', '-shortest',
            '-y', output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Error combinando: {result.stderr}")
        return output
    
    def _add_ending(self, video_path):
        """Agregar video de ending"""
        if not os.path.exists(self.ending_path):
            return video_path
        
        output = os.path.join(self.temp_dir, "video_ending.mp4")
        concat_file = os.path.join(self.temp_dir, "concat.txt")
        
        with open(concat_file, 'w') as f:
            f.write(f"file '{video_path}'\n")
            f.write(f"file '{self.ending_path}'\n")
        
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', concat_file, '-c', 'copy',
            '-y', output
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"No se pudo agregar ending: {result.stderr}")
            return video_path
        return output
    
    def _cleanup(self):
        """Limpiar temporales"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass
