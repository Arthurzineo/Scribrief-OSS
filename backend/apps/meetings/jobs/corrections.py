"""Celery jobs. The database state guards against duplicate deliveries."""

import logging

from celery import shared_task
from django.core.cache import cache
from django.db import transaction

from ..correction_jobs import CORRECTION_JOB_TTL, active_key, result_key
from ..job_state import (
    JobCancelled,
    ensure_not_cancelled,
    finish_job,
    finish_stale_job,
    start_job,
)
from ..models import (
    Meeting,
    MeetingStatus,
    ProcessingJob,
)
from ..processing.corrections import correction_provider, validate_review_suggestions
from .common import _call_context

logger = logging.getLogger(__name__)


@shared_task(name="meetings.analyze_transcription_corrections", acks_late=True)
def analyze_transcription_corrections(meeting_id, version, job_id):
    key = result_key(job_id)
    state = cache.get(key)
    if not state or state.get("status") != "processing":
        return finish_stale_job(job_id)
    if not cache.add(f"correction:claimed:{job_id}", True, timeout=1800):
        return "ignored"
    start_job(job_id, "correction")
    try:
        ensure_not_cancelled(job_id)
        meeting = Meeting.objects.get(pk=meeting_id)
        if (
            meeting.deletion_requested_at or meeting.transcription_version != version
            or meeting.status not in (
            MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA
            )
        ):
            raise ValueError("stale_transcription")
        segments = list(meeting.segments.order_by("order").values("id", "text"))
        payload = [{"id": item["id"], "texto": item["text"]} for item in segments]
        if payload:
            api_key, context = _call_context(meeting, job_id, "correction")
            suggestions = validate_review_suggestions(
                correction_provider(api_key, context).suggest(payload), payload
            )
        else:
            suggestions = []
        ensure_not_cancelled(job_id)
        originals = {item["id"]: item["text"] for item in segments}
        if any(item.get("segmento_id") not in originals for item in suggestions):
            raise ValueError("invalid_suggestion_id")
        with transaction.atomic():
            current = Meeting.objects.select_for_update().get(pk=meeting_id)
            job = ProcessingJob.objects.select_for_update().get(pk=job_id)
            if job.cancel_requested_at or job.status == "cancelled":
                raise JobCancelled("Job cancelled")
            if (
                current.deletion_requested_at or current.transcription_version != version
                or current.status not in (
                MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA
                )
            ):
                raise ValueError("stale_transcription")
            state.update(status="ready", sugestoes=[
                {**item, "texto_original": originals[item["segmento_id"]]}
                for item in suggestions
            ])
            cache.set(key, state, timeout=CORRECTION_JOB_TTL)
            finish_job(job_id, "completed")
        return "ready"
    except JobCancelled:
        return "cancelled"
    except Exception as exc:
        logger.error(
            "Correction analysis failed for meeting %s: %s", meeting_id, type(exc).__name__
        )
        if ProcessingJob.objects.filter(pk=job_id, status="cancelled").exists():
            return "cancelled"
        state.update(status="error", message="Não foi possível analisar a transcrição.")
        cache.set(key, state, timeout=CORRECTION_JOB_TTL)
        active = active_key(meeting_id, version)
        if cache.get(active) == job_id:
            cache.delete(active)
        finish_job(job_id, "failed", "correction_failed")
        return "failed"
