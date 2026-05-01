from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[[int, str], None]


class VideoEditor:
    """FFmpeg-based renderer for the WorkFast TikTok editing preset."""

    WIDTH = 1080
    HEIGHT = 1920
    FPS = 30

    def __init__(
        self,
        input_video: str | Path,
        output_path: str | Path,
        logo_path: str | Path | None = None,
        ending_path: str | Path | None = None,
        follow_image_path: str | Path | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.input_video = Path(input_video).resolve()
        self.output_path = Path(output_path).resolve()
        self.logo_path = Path(logo_path).resolve() if logo_path else None
        self.ending_path = Path(ending_path).resolve() if ending_path else None
        self.follow_image_path = Path(follow_image_path).resolve() if follow_image_path else None
        self.progress_callback = progress_callback
        temp_root = self.output_path.parent / ".workfast_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = temp_root / f"job_{self.output_path.stem}"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        if not self.input_video.exists():
            raise FileNotFoundError(f"Video no encontrado: {self.input_video}")

        self.video_info = self._probe(self.input_video)
        self.duration = float(self.video_info.get("duration") or 0)
        self.has_audio = self._has_audio(self.video_info)
        if self.duration <= 0:
            raise RuntimeError("No pude detectar la duracion del video.")

    def process_complete(
        self,
        title_text: str = "Mi Video",
        speed: float = 1.05,
        zoom_bottom: float = 1.96,
        zoom_top: float = 0.96,
        saturation: float = 100,
        volume_db: float = 5.4,
        filter_intensity: float = 0.24,
        title_interval: float = 10,
    ) -> Path:
        """Render the complete preset and return the final MP4 path."""
        self._ensure_tools()
        speed = self._clamp(speed, 0.5, 2.0)
        zoom_bottom = self._clamp(zoom_bottom, 1.0, 3.0)
        zoom_top = self._clamp(zoom_top, 0.5, 1.5)
        filter_intensity = self._clamp(filter_intensity, 0.0, 1.0)
        title_interval = self._clamp(title_interval, 3.0, 60.0)

        try:
            self._progress(5, "Preparando render FFmpeg")
            main_video = self.temp_dir / "main.mp4"
            self._render_main_video(
                output_path=main_video,
                title_text=title_text,
                speed=speed,
                zoom_bottom=zoom_bottom,
                zoom_top=zoom_top,
                saturation=saturation,
                volume_db=volume_db,
                filter_intensity=filter_intensity,
                title_interval=title_interval,
            )

            if self.ending_path and self.ending_path.exists():
                self._progress(88, "Normalizando ending")
                final_video = self._append_ending(main_video)
            else:
                final_video = main_video

            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            if self.output_path.exists():
                self.output_path.unlink()
            shutil.move(str(final_video), str(self.output_path))
            self._progress(100, "Video listo")
            return self.output_path
        finally:
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _render_main_video(
        self,
        output_path: Path,
        title_text: str,
        speed: float,
        zoom_bottom: float,
        zoom_top: float,
        saturation: float,
        volume_db: float,
        filter_intensity: float,
        title_interval: float,
    ) -> None:
        inputs = ["-i", str(self.input_video)]
        next_input_index = 1
        audio_index = 0
        logo_index = None
        follow_index = None

        if not self.has_audio:
            audio_index = next_input_index
            next_input_index += 1
            inputs.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    f"{self.duration:.3f}",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                ]
            )

        if self.logo_path and self.logo_path.exists():
            logo_index = next_input_index
            next_input_index += 1
            inputs.extend(["-i", str(self.logo_path)])

        if self.follow_image_path and self.follow_image_path.exists():
            follow_index = next_input_index
            next_input_index += 1
            inputs.extend(["-i", str(self.follow_image_path)])

        filter_complex = self._build_filter_complex(
            title_text=title_text,
            speed=speed,
            zoom_bottom=zoom_bottom,
            zoom_top=zoom_top,
            saturation=saturation,
            volume_db=volume_db,
            filter_intensity=filter_intensity,
            title_interval=title_interval,
            audio_index=audio_index,
            logo_index=logo_index,
            follow_index=follow_index,
        )

        command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "faster",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            "-progress",
            "pipe:1",
            "-nostats",
            str(output_path),
        ]

        target_duration = self.duration / speed
        self._run_ffmpeg(command, target_duration=target_duration, start=8, end=86)

    def _build_filter_complex(
        self,
        title_text: str,
        speed: float,
        zoom_bottom: float,
        zoom_top: float,
        saturation: float,
        volume_db: float,
        filter_intensity: float,
        title_interval: float,
        audio_index: int,
        logo_index: int | None,
        follow_index: int | None,
    ) -> str:
        bottom_crop_w = self._even(math.floor(self.WIDTH / zoom_bottom))
        bottom_crop_h = self._even(math.floor(self.HEIGHT / zoom_bottom))
        top_scale_w = self._even(math.ceil(self.WIDTH * zoom_top))
        top_scale_h = self._even(math.ceil(self.HEIGHT * zoom_top))
        bottom_saturation = 1.0 + self._clamp(saturation, 0.0, 100.0) / 100.0
        contrast = 1.0 + (filter_intensity * 0.35)
        sharpen = 0.25 + (filter_intensity * 0.75)
        title = self._escape_drawtext(title_text.strip() or "Mi Video")
        interval = f"{title_interval:.2f}"
        output_duration = max(self.duration / speed, 1.0)

        parts = [
            (
                f"[0:v]fps={self.FPS},scale={self.WIDTH}:{self.HEIGHT}:"
                "force_original_aspect_ratio=increase,"
                f"crop={self.WIDTH}:{self.HEIGHT},split=2[bottom_src][top_src]"
            ),
            (
                f"[bottom_src]hflip,crop={bottom_crop_w}:{bottom_crop_h}:"
                f"({self.WIDTH}-{bottom_crop_w})/2:({self.HEIGHT}-{bottom_crop_h})/2,"
                f"scale={self.WIDTH}:{self.HEIGHT}:flags=bicubic,"
                f"eq=saturation={bottom_saturation:.2f}:contrast=1.08:brightness=0.04,"
                "boxblur=10:1,format=rgba,colorchannelmixer=aa=0.78[bottom]"
            ),
            (
                f"[top_src]scale={top_scale_w}:{top_scale_h}:"
                "force_original_aspect_ratio=increase,"
                f"crop={top_scale_w}:{top_scale_h},"
                f"eq=contrast={contrast:.2f}:saturation=1.08:brightness=0.01,"
                f"unsharp=5:5:{sharpen:.2f}:3:3:0.20,format=rgba[top]"
            ),
            "[bottom][top]overlay=(W-w)/2:(H-h)/2:format=auto[stage0]",
        ]

        stage = "stage0"
        stage_count = 1

        if logo_index is not None:
            parts.append(
                f"[{logo_index}:v]scale=190:-1,format=rgba,"
                "colorchannelmixer=aa=0.24[logo]"
            )
            next_stage = f"stage{stage_count}"
            stage_count += 1
            parts.append(
                f"[{stage}][logo]overlay="
                f"x='(W-w)*t/{output_duration:.3f}':y=(H-h)/2:"
                f"format=auto:eof_action=repeat:repeatlast=1[{next_stage}]"
            )
            stage = next_stage

        if follow_index is not None:
            parts.append(
                f"[{follow_index}:v]scale=320:-1,format=rgba,"
                "colorchannelmixer=aa=0.88[follow]"
            )
            next_stage = f"stage{stage_count}"
            stage_count += 1
            parts.append(
                f"[{stage}][follow]overlay="
                "x=W-w-48:y=H-h-210:enable='lt(mod(t\\,15)\\,5)':"
                "format=auto:eof_action=repeat:repeatlast=1"
                f"[{next_stage}]"
            )
            stage = next_stage

        next_stage = f"stage{stage_count}"
        parts.append(
            f"[{stage}]drawtext=text='{title}':"
            "fontcolor=0x39FF14:fontsize=54:font='Arial Bold':box=1:"
            "boxcolor=black@0.92:boxborderw=24:x=(w-text_w)/2:y=64:"
            f"enable='lt(mod(t\\,{interval})\\,3)'[{next_stage}]"
        )
        stage = next_stage

        parts.append(
            f"[{stage}]drawtext=text='LIKE':fontcolor=white:fontsize=46:"
            "font='Arial Bold':box=1:boxcolor=0x10B981@0.82:boxborderw=18:"
            "x=54:y=H-360:enable='between(mod(t\\,12)\\,1\\,4)'[video_speed]"
        )
        parts.append(f"[video_speed]setpts=PTS/{speed:.5f},setsar=1[vout]")
        parts.append(
            f"[{audio_index}:a]atempo={speed:.5f},volume={volume_db:.2f}dB,"
            "afftdn=nf=-25,highpass=f=80,lowpass=f=15000,"
            "acompressor=threshold=-18dB:ratio=2.5:attack=20:release=250,"
            "alimiter=limit=0.97[aout]"
        )

        return ";".join(parts)

    def _append_ending(self, main_video: Path) -> Path:
        normalized_ending = self.temp_dir / "ending_normalized.mp4"
        output = self.temp_dir / "with_ending.mp4"
        concat_list = self.temp_dir / "concat.txt"
        ending_info = self._probe(self.ending_path)
        ending_duration = float(ending_info.get("duration") or 1)
        ending_has_audio = self._has_audio(ending_info)

        normalize_command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(self.ending_path),
        ]
        if not ending_has_audio:
            normalize_command.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    f"{ending_duration:.3f}",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                ]
            )

        normalize_command.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a:0" if ending_has_audio else "1:a:0",
            "-vf",
            (
                f"fps={self.FPS},scale={self.WIDTH}:{self.HEIGHT}:"
                f"force_original_aspect_ratio=decrease,pad={self.WIDTH}:{self.HEIGHT}:"
                "(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
            ),
            "-af",
            "aresample=48000",
            "-c:v",
            "libx264",
                "-preset",
                "faster",
                "-crf",
                "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(normalized_ending),
            ]
        )
        self._run_ffmpeg(normalize_command, target_duration=None, start=88, end=93)

        concat_list.write_text(
            f"file '{main_video.as_posix()}'\nfile '{normalized_ending.as_posix()}'\n",
            encoding="utf-8",
        )
        concat_command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(output),
        ]
        self._run_ffmpeg(concat_command, target_duration=None, start=94, end=99)
        return output

    def _run_ffmpeg(
        self,
        command: list[str],
        target_duration: float | None,
        start: int,
        end: int,
    ) -> None:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output_lines: list[str] = []

        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
            if target_duration and line.startswith("out_time_ms="):
                try:
                    seconds = int(line.split("=", 1)[1]) / 1_000_000
                    percent = start + int((seconds / target_duration) * (end - start))
                    self._progress(min(end, max(start, percent)), "Renderizando video")
                except ValueError:
                    pass

        return_code = process.wait()
        if return_code != 0:
            tail = "\n".join(output_lines[-30:])
            raise RuntimeError(f"FFmpeg fallo con codigo {return_code}:\n{tail}")

    def _probe(self, path: Path) -> dict:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"No pude leer el video con ffprobe: {result.stderr}")
        data = json.loads(result.stdout)
        duration = data.get("format", {}).get("duration")
        return {"duration": duration, "streams": data.get("streams", [])}

    @staticmethod
    def _has_audio(info: dict) -> bool:
        return any(stream.get("codec_type") == "audio" for stream in info.get("streams", []))

    def _ensure_tools(self) -> None:
        for tool in ("ffmpeg", "ffprobe"):
            if shutil.which(tool) is None:
                raise RuntimeError(f"{tool} no esta instalado o no esta en el PATH.")

    def _progress(self, percent: int, step: str) -> None:
        if self.progress_callback:
            self.progress_callback(percent, step)

    @staticmethod
    def _even(value: int) -> int:
        return value if value % 2 == 0 else value + 1

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, float(value)))

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        return (
            text.replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
            .replace("\n", " ")
        )
