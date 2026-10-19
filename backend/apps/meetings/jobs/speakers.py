"""Celery jobs. The database state guards against duplicate deliveries."""

import logging

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

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
    SpeakerAnalysis,
)
from ..processing.providers import transcription_provider
from ..processing.speaker_reconciliation import (
    build_composite_audio,
    infer_speaker_groups,
    select_voice_samples,
)
from ..storage import safe_media_path
from .common import _call_context

logger = logging.getLogger(__name__)


@shared_task(name="meetings.analyze_speaker_reconciliation", acks_late=True)
def analyze_speaker_reconciliation(meeting_id, version, job_id):
    analysis = SpeakerAnalysis.objects.filter(
        meeting_id=meeting_id, job_id=job_id, version=version, status="processing"
    ).first()
    if analysis is None:
        return finish_stale_job(job_id)
    if not cache.add(f"speaker-analysis:claimed:{job_id}", True, timeout=1800):
        return "ignored"
    start_job(job_id, "speaker_reconciliation")
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
        audio = safe_media_path(meeting.audio_path)
        if not audio.is_file():
            raise ValueError("audio_unavailable")
        segments = list(meeting.segments.select_related("speaker").order_by("start_ms"))
        samples = select_voice_samples(segments)
        sample_times = {}
        for sample in samples:
            sample_times.setdefault(sample.code, []).append(sample.start_ms / 1000)
        caution = False
        if len({sample.code for sample in samples}) < 2:
            groups = []
        else:
            with build_composite_audio(audio, samples) as (composite, indexed):
                key, context = _call_context(meeting, job_id, "speaker_reconciliation")
                transcript = transcription_provider(key, context).transcribe(composite)
            ensure_not_cancelled(job_id)
            caution = len({item.speaker for item in transcript}) == 1 and len({
                item.code for item in samples
            }) > 2
            groups = infer_speaker_groups(indexed, transcript)
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
            updated = SpeakerAnalysis.objects.filter(
                meeting_id=meeting_id, job_id=job_id, version=version, status="processing"
            ).update(
                status="ready", groups=groups, caution=caution,
                sample_times=sample_times, message="", updated_at=timezone.now(),
            )
            finish_job(job_id, "completed" if updated else "failed")
        return "ready" if updated else "ignored"
    except JobCancelled:
        return "cancelled"
    except Exception as exc:
        logger.error(
            "Speaker reconciliation failed for meeting %s: %s",
            meeting_id, type(exc).__name__,
        )
        SpeakerAnalysis.objects.filter(
            meeting_id=meeting_id, job_id=job_id, version=version, status="processing"
        ).update(
            status="error", message="Não foi possível analisar os falantes.",
            updated_at=timezone.now(),
        )
        finish_job(job_id, "failed", "speaker_reconciliation_failed")
        return "failed"
