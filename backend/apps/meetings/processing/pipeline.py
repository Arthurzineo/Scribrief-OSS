"""FFmpeg processing with bounded commands and explicit chunk offsets."""

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from ..storage import meeting_dir, safe_media_path


class MediaError(RuntimeError):
    pass


CHUNK_DURATION_SECONDS = 1200
CHUNK_OVERLAP_SECONDS = 15


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    offset_ms: int


def _run(args: list[str], timeout: int):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError("Processamento de mídia indisponível ou expirado") from exc
    if result.returncode != 0:
        raise MediaError("ffmpeg/ffprobe não conseguiu processar a mídia")
    return result.stdout


def duration_seconds(path: Path) -> float:
    value = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        30,
    )
    try:
        duration = float(value.decode().strip())
    except ValueError as exc:
        raise MediaError("Duração inválida") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError("Duração inválida")
    return duration


def normalize_audio(meeting) -> Path:
    if not meeting.original_path:
        raise MediaError("Arquivo original indisponível")
    source = safe_media_path(meeting.original_path)
    if not source.is_file():
        raise MediaError("Arquivo original indisponível")
    directory = meeting_dir(meeting)
    target = directory / "audio.mp3"
    temp = directory / "audio.part.mp3"
    try:
        _run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "96k",
                str(temp),
            ],
            settings.FFMPEG_TIMEOUT_SECONDS,
        )
        if not temp.is_file() or temp.stat().st_size == 0:
            raise MediaError("Áudio vazio")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def make_chunks(audio_path: Path, max_bytes: int = 22_000_000) -> list[AudioChunk]:
    """Make overlapping 20-minute MP3s, checking actual bytes before upload."""
    duration = duration_seconds(audio_path)
    if (
        duration <= CHUNK_DURATION_SECONDS
        and audio_path.is_file()
        and 0 < audio_path.stat().st_size <= max_bytes
    ):
        return [AudioChunk(audio_path, 0)]
    result = []
    chunk_dir = audio_path.parent / "chunks"
    chunk_dir.mkdir(mode=0o700, exist_ok=True)

    def add_chunk(start: float, length: float) -> float:
        index = len(result)
        path = chunk_dir / f"chunk-{index:05d}.mp3"
        while True:
            _run(
                [
                    "ffmpeg", "-nostdin", "-y", "-ss", str(start), "-i", str(audio_path),
                    "-t", str(length), "-ac", "1", "-ar", "16000", "-b:a", "96k",
                    str(path),
                ],
                settings.FFMPEG_TIMEOUT_SECONDS,
            )
            if not path.is_file() or path.stat().st_size == 0:
                raise MediaError("Bloco de áudio vazio")
            if path.stat().st_size <= max_bytes:
                result.append(AudioChunk(path, round(start * 1000)))
                return length
            path.unlink(missing_ok=True)
            length /= 2
            if length <= CHUNK_OVERLAP_SECONDS + 30:
                raise MediaError("Bloco acima do limite")

    cursor = 0.0
    while cursor < duration:
        length = min(CHUNK_DURATION_SECONDS, duration - cursor)
        actual_length = add_chunk(cursor, length)
        end = cursor + actual_length
        if end >= duration - 0.001:
            break
        cursor = end - CHUNK_OVERLAP_SECONDS
    return result
