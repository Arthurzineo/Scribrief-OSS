"""Private media storage. Paths are always derived from server-owned UUIDs."""

import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError

MAGIC_TYPES = {
    ".mp3": lambda b: (
        b.startswith(b"ID3") or (len(b) >= 2 and b[0] == 0xFF and b[1] & 0xE0 == 0xE0)
    ),
    ".mp4": lambda b: len(b) >= 8 and b[4:8] == b"ftyp",
    ".m4a": lambda b: len(b) >= 8 and b[4:8] == b"ftyp",
    ".wav": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WAVE",
    ".webm": lambda b: b.startswith(bytes.fromhex("1a45dfa3")),
}


def meeting_dir(meeting):
    root = Path(settings.MEDIA_ROOT).resolve()
    result = (root / "reunioes" / str(meeting.id)).resolve()
    if not result.is_relative_to(root):
        raise ValueError("invalid media path")
    return result


def safe_media_path(relative):
    root = Path(settings.MEDIA_ROOT).resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError("invalid media path")
    return result


def probe_audio(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError({"file": "Não foi possível analisar a mídia."}) from exc
    if result.returncode != 0 or "codec_type=audio" not in result.stdout:
        raise ValidationError({"file": "Arquivo sem áudio válido."})


def save_original(meeting, uploaded):
    ext = Path(uploaded.name).suffix.lower()
    if ext not in MAGIC_TYPES:
        raise ValidationError({"file": "Formato não permitido."})
    if uploaded.size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "Arquivo acima do limite configurado."})
    head = uploaded.read(16)
    uploaded.seek(0)
    if not MAGIC_TYPES[ext](head):
        raise ValidationError({"file": "Conteúdo não corresponde ao formato informado."})

    directory = meeting_dir(meeting)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = directory / "original.part"
    target = directory / f"original{ext}"
    total = 0
    try:
        source_temp = getattr(uploaded, "temporary_file_path", None)
        if source_temp and settings.FILE_UPLOAD_TEMP_DIR:
            source = Path(source_temp()).resolve()
            upload_root = Path(settings.FILE_UPLOAD_TEMP_DIR).resolve()
            if not source.is_relative_to(upload_root):
                raise ValidationError({"file": "Caminho temporário inválido."})
            os.replace(source, temp)  # same media volume: no second 5 GB copy
        else:
            with temp.open("wb") as out:
                for chunk in uploaded.chunks():
                    total += len(chunk)
                    if total > settings.MAX_UPLOAD_BYTES:
                        raise ValidationError({"file": "Arquivo acima do limite configurado."})
                    out.write(chunk)
        probe_audio(temp)
        if meeting.sector.max_upload_minutes is not None:
            from .processing.pipeline import MediaError, duration_seconds

            try:
                duration = duration_seconds(temp)
            except MediaError as exc:
                raise ValidationError({
                    "file": "Não foi possível medir a duração da mídia."
                }) from exc
            if duration > meeting.sector.max_upload_minutes * 60:
                raise ValidationError({
                    "file": (
                        "Mídia acima do limite de duração deste setor "
                        f"({meeting.sector.max_upload_minutes} minutos)."
                    )
                })
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return str(target.relative_to(Path(settings.MEDIA_ROOT).resolve()))


def delete_media(meeting):
    directory = meeting_dir(meeting)
    if directory.exists():
        shutil.rmtree(directory)
