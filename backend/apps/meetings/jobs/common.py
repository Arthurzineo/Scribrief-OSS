"""Shared provider context and guarded meeting state transitions."""

from django.db import transaction
from django.utils import timezone

from apps.accounts.secrets import sector_credential

from ..models import Meeting, MeetingStatus
from ..processing.ai_registry import capability_for_operation, selected_provider
from ..processing.sector_prompts import effective_prompt


def _call_context(meeting, job_id, operation):
    provider_id = selected_provider(capability_for_operation(operation))
    key, version = sector_credential(meeting.sector_id, provider_id)
    context = {
        "sector_id": meeting.sector_id,
        "user_id": meeting.owner_id,
        "meeting_id": meeting.id,
        "job_id": job_id,
        "operation": operation,
        "key_version": version,
        "provider_id": provider_id,
    }
    capability = capability_for_operation(operation)
    if capability in ("minutes", "mind_map", "correction"):
        context["system_prompt"], context["prompt_version"] = effective_prompt(
            meeting.sector_id, capability
        )
    return key, context


def _claim(meeting_id, job_id, expected, next_state):
    with transaction.atomic():
        meeting = Meeting.objects.select_for_update().get(pk=meeting_id)
        from ..models import ProcessingJob

        if ProcessingJob.objects.filter(
            id=job_id, cancel_requested_at__isnull=False
        ).exists():
            return None
        if meeting.deletion_requested_at is not None:
            return None
        if meeting.job_claimed and str(meeting.job_id) == str(job_id):
            return None  # duplicate delivery; the first worker owns this job
        if str(meeting.job_id) != str(job_id) or meeting.status != expected:
            from ..job_state import finish_stale_job

            finish_stale_job(job_id)
            return None
        meeting.status = next_state
        meeting.job_claimed = True
        meeting.job_started_at = timezone.now()
        meeting.error_code = ""
        meeting.error_message = ""
        meeting.save(
            update_fields=[
                "status",
                "job_claimed",
                "job_started_at",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        return meeting


def _fail(meeting_id, job_id, code, message):
    expected = (
        [MeetingStatus.GERANDO_ATA] if code == "minutes_failed"
        else [MeetingStatus.EXTRAINDO_AUDIO, MeetingStatus.TRANSCREVENDO]
    )
    Meeting.objects.filter(
        pk=meeting_id, job_id=job_id, status__in=expected,
        deletion_requested_at__isnull=True,
    ).exclude(
        error_code="job_cancelled"
    ).update(
        status=MeetingStatus.ERRO, error_code=code, error_message=message
    )
