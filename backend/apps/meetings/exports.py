"""Derived files. Database rows remain authoritative."""

import json
import logging
import os
from pathlib import Path

from django.utils import timezone

from .storage import meeting_dir

logger = logging.getLogger(__name__)


def _atomic_write(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".part")
    try:
        temp.write_text(value, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def transcript_payload(meeting):
    speakers = {s.code: s.name for s in meeting.speakers.all() if not s.merged_into_id}
    segments = [
        {
            "id": seg.id,
            "falante_id": seg.speaker.code,
            "inicio": seg.start_ms / 1000,
            "fim": seg.end_ms / 1000,
            "texto": seg.text,
            "original": (
                {
                    "texto": seg.original_text,
                    "inicio": seg.original_start_ms / 1000,
                    "fim": seg.original_end_ms / 1000,
                    "falante_id": seg.original_speaker_code,
                    "proveniencia": seg.original_source,
                }
                if seg.original_source != "unverified"
                and seg.original_start_ms is not None
                and seg.original_end_ms is not None
                else None
            ),
        }
        for seg in meeting.segments.select_related("speaker").all()
    ]
    return {"version": meeting.transcription_version, "falantes": speakers, "segmentos": segments}


def transcript_text(meeting):
    data = transcript_payload(meeting)
    lines = []
    for seg in data["segmentos"]:
        speaker = data["falantes"].get(seg["falante_id"], seg["falante_id"])
        lines.append(f"[{seg['inicio']:.3f}–{seg['fim']:.3f}] {speaker}: {seg['texto']}")
    return "\n".join(lines) + ("\n" if lines else "")


def export_transcript(meeting):
    directory = meeting_dir(meeting)
    _atomic_write(directory / "transcricao.json", render_transcript(meeting, "json"))
    _atomic_write(directory / "transcricao.md", render_transcript(meeting, "md"))


def render_transcript(meeting, fmt):
    if fmt == "json":
        return json.dumps(transcript_payload(meeting), ensure_ascii=False, indent=2)
    if fmt == "md":
        return transcript_text(meeting)
    raise ValueError("Unsupported transcript format")


def minutes_payload(meeting):
    value = meeting.minutes
    return {
        "resumo_executivo": value.resumo_executivo,
        "topicos": value.topicos,
        "decisoes": value.decisoes,
        "tarefas": value.tarefas,
        "participantes": value.participantes,
        "revisor": value.reviewer_name if value.reviewed_at else None,
        "revisado_em": value.reviewed_at.isoformat() if value.reviewed_at else None,
    }


def minutes_text(meeting):
    data = minutes_payload(meeting)
    lines = [
        "# Ata",
        "",
        f"Participantes: {', '.join(data['participantes']) or 'Não informados'}",
        (
            f"Ata revisada por {data['revisor']} em {value_date(meeting.minutes.reviewed_at)}"
            if data["revisado_em"] else "Ata não revisada"
        ),
        "",
        "## Resumo executivo",
        data["resumo_executivo"],
        "",
    ]
    lines += ["## Tópicos"]
    for topic in data["topicos"]:
        lines += ["", f"### {topic['titulo']}", topic["comentario"]]
    lines += ["", "## Decisões"]
    lines += [f"- {item}" for item in data["decisoes"]]
    lines += ["", "## Tarefas"]
    lines += [
        f"- {item['descricao']} — {item['responsavel']}"
        + (f" (prazo: {item['prazo']})" if item["prazo"] else "")
        for item in data["tarefas"]
    ]
    return "\n".join(lines) + "\n"


def render_minutes(meeting, fmt):
    if fmt == "json":
        return json.dumps(minutes_payload(meeting), ensure_ascii=False, indent=2)
    if fmt == "md":
        return minutes_text(meeting)
    raise ValueError("Unsupported minutes format")


def export_minutes(meeting):
    directory = meeting_dir(meeting)
    _atomic_write(directory / "ata.json", render_minutes(meeting, "json"))
    _atomic_write(directory / "ata.md", render_minutes(meeting, "md"))


def export_best_effort(exporter, meeting):
    """Derived files are optional caches; an I/O fault must not undo a committed edit."""
    try:
        exporter(meeting)
    except OSError:
        logger.exception("Derived export failed for meeting %s", meeting.pk)


def value_date(value):
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")
