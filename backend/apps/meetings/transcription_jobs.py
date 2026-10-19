"""Per-recording Celery limits; the fixed global limit is too short for long meetings."""

import math

from django.conf import settings

from .job_state import accept_job, finish_job
from .processing.pipeline import MediaError, duration_seconds
from .storage import safe_media_path


def transcription_time_limits(duration, *, multiplier=None, minimum=None, grace=None):
    multiplier = (
        settings.TRANSCRIPTION_TIME_MULTIPLIER if multiplier is None else multiplier
    )
    minimum = settings.TRANSCRIPTION_MIN_SOFT_SECONDS if minimum is None else minimum
    grace = settings.TRANSCRIPTION_HARD_GRACE_SECONDS if grace is None else grace
    if (
        not math.isfinite(duration)
        or duration <= 0
        or not math.isfinite(multiplier)
        or multiplier <= 1
        or minimum <= 0
        or grace <= 0
    ):
        raise ValueError("Limites de transcrição inválidos")
    soft = max(minimum, math.ceil(duration * multiplier))
    return soft, soft + grace


def enqueue_transcription(meeting, duration=None):
    """Queue with a deadline longer than the actual recording, not a fixed 30 minutes."""
    from .tasks import process_meeting

    relative_path = meeting.audio_path or meeting.original_path
    if duration is None:
        duration = duration_seconds(safe_media_path(relative_path))
    soft, hard = transcription_time_limits(duration)
    accept_job(meeting, meeting.job_id, "transcription", duration)
    try:
        return process_meeting.apply_async(
            args=(str(meeting.id), str(meeting.job_id)),
            soft_time_limit=soft,
            time_limit=hard,
        )
    except Exception:
        finish_job(meeting.job_id, "failed", "queue_unavailable")
        raise


def transcription_stale_after_seconds(meeting):
    """Do not offer retry while a long, valid worker deadline is still active."""
    relative_path = meeting.audio_path or getattr(meeting, "original_path", "")
    if not relative_path:
        return 6 * 3600
    try:
        duration = duration_seconds(safe_media_path(relative_path))
        _, hard = transcription_time_limits(duration)
    except (MediaError, OSError, ValueError):
        return 6 * 3600
    return max(6 * 3600, hard + 600)
