"""Read-only progress derived from durable chunk checkpoints and a short plan."""

from django.core.cache import cache

from ..job_state import heartbeat_job
from ..models import MeetingStatus

PROGRESS_TTL_SECONDS = 7 * 24 * 3600


def progress_key(meeting_id, job_id):
    return f"transcription:progress:{meeting_id}:{job_id}"


def plan_transcription(meeting, total_chunks):
    """Remember only the planned count; actual completion lives in PostgreSQL."""
    if not meeting.job_id or not isinstance(total_chunks, int) or total_chunks <= 0:
        raise ValueError("Plano de transcrição inválido")
    cache.set(
        progress_key(meeting.id, meeting.job_id),
        {"total_chunks": total_chunks},
        timeout=PROGRESS_TTL_SECONDS,
    )
    heartbeat_job(meeting.job_id, stage="transcribing", total_units=total_chunks)


def transcription_progress(meeting):
    state = cache.get(progress_key(meeting.id, meeting.job_id)) if meeting.job_id else None
    total = state.get("total_chunks") if isinstance(state, dict) else None
    if not isinstance(total, int) or total <= 0:
        total = None
    done = meeting.status in (
        MeetingStatus.TRANSCRITO, MeetingStatus.GERANDO_ATA, MeetingStatus.ATA_PRONTA
    ) or (meeting.status == MeetingStatus.ERRO and meeting.segments.exists())
    if done:
        return {
            "stage": "concluido", "completed_chunks": total,
            "total_chunks": total, "percent": 100,
        }
    completed = meeting.transcription_chunks.count()
    if total is not None:
        completed = min(completed, total)
    if meeting.status == MeetingStatus.EXTRAINDO_AUDIO:
        stage = "extraindo_audio"
    elif meeting.status == MeetingStatus.TRANSCREVENDO:
        stage = "finalizando" if total is not None and completed == total else "transcrevendo"
    elif meeting.status == MeetingStatus.ERRO:
        stage = "erro"
    else:
        stage = "aguardando"
    return {
        "stage": stage,
        "completed_chunks": completed,
        "total_chunks": total,
        "percent": min(99, completed * 100 // total) if total is not None else None,
    }
