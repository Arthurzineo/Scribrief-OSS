"""Minutes generation Celery task."""

import logging

from celery import shared_task
from django.db import transaction

from apps.audit.models import record_audit

from ..exports import export_minutes, transcript_text
from ..job_state import (
    JobCancelled,
    ensure_not_cancelled,
    finish_job,
    finish_stale_job,
    start_job,
)
from ..models import Meeting, MeetingStatus, Minutes
from ..processing.providers import minutes_provider, validate_minutes_data
from .common import _call_context, _claim, _fail

logger = logging.getLogger(__name__)


@shared_task(name="meetings.generate_minutes", acks_late=True)
def generate_minutes(meeting_id, job_id):
    meeting = _claim(meeting_id, job_id, MeetingStatus.GERANDO_ATA, MeetingStatus.GERANDO_ATA)
    if meeting is None:
        return "ignored"
    start_job(job_id, "minutes")
    try:
        ensure_not_cancelled(job_id)
        api_key, context = _call_context(meeting, job_id, "minutes")
        data = validate_minutes_data(
            minutes_provider(api_key, context).generate(transcript_text(meeting))
        )
        ensure_not_cancelled(job_id)
        with transaction.atomic():
            current = Meeting.objects.select_for_update().get(pk=meeting_id)
            if current.status != MeetingStatus.GERANDO_ATA or str(current.job_id) != str(job_id):
                return finish_stale_job(job_id)
            Minutes.objects.update_or_create(
                meeting=current,
                defaults={
                    **data,
                    "participantes": list(
                        current.speakers.filter(merged_into__isnull=True)
                        .values_list("name", flat=True)
                    ),
                    "human_edited": False,
                    "reviewed_by": None,
                    "reviewer_name": "",
                    "reviewed_at": None,
                },
            )
            current.minutes_version += 1
            current.minutes_stale = False
            current.status = MeetingStatus.ATA_PRONTA
            current.save(update_fields=["minutes_version", "minutes_stale", "status", "updated_at"])
            record_audit(
                current.owner, "minutes_generated", current.id, sector=current.sector,
                target_type="meeting", target_ref=current.id,
                details={"job_id": str(job_id), "minutes_version": current.minutes_version,
                         "transcription_version": current.transcription_version},
            )
            finish_job(job_id, "completed")
        try:
            export_minutes(current)
        except OSError:
            logger.exception("Could not export minutes for meeting %s", meeting_id)
        return "minutes_ready"
    except JobCancelled:
        return "cancelled"
    except Exception as exc:
        logger.error("Minutes generation failed for meeting %s: %s", meeting_id, type(exc).__name__)
        _fail(meeting_id, job_id, "minutes_failed", "Geração da ata falhou. Tente novamente.")
        finish_job(job_id, "failed", "minutes_failed")
        return "failed"
