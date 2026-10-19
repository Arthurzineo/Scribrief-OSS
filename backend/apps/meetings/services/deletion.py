"""Durable, idempotent purge of meetings hidden for at least 72 hours."""

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.audit.models import record_audit

from ..models import Meeting, MeetingStatus, ProcessingJob
from ..models.meeting import DELETION_GRACE_PERIOD
from ..storage import delete_media
from .common import Conflict

logger = logging.getLogger(__name__)
BATCH_SIZE = 100


def request_deletion(meeting_id, actor, request):
    """Hide a meeting atomically; keep all private artifacts until the purge deadline."""
    with transaction.atomic():
        meeting = Meeting.objects.select_for_update().filter(pk=meeting_id).first()
        if meeting is None or meeting.owner_id != actor.pk or meeting.deletion_requested_at:
            raise NotFound()
        if (
            (meeting.status == MeetingStatus.ENVIADO and meeting.job_id)
            or meeting.status in (
                MeetingStatus.EXTRAINDO_AUDIO,
                MeetingStatus.TRANSCREVENDO,
                MeetingStatus.GERANDO_ATA,
            )
            or ProcessingJob.objects.filter(
                meeting_id=meeting_id, status__in=["queued", "running"]
            ).exists()
        ):
            raise Conflict("Aguarde o fim do processamento para excluir a reunião.")
        meeting.deletion_requested_at = timezone.now()
        meeting.purge_attempts = 0
        meeting.purge_error_code = ""
        meeting.save(update_fields=[
            "deletion_requested_at", "purge_attempts", "purge_error_code", "updated_at"
        ])
        record_audit(
            actor, "meeting_deletion_requested", meeting_id,
            request=request, sector=meeting.sector, target_type="meeting",
            target_ref=meeting_id,
            details={"purge_after": meeting.deletion_due_at.isoformat()},
        )


def restore_meeting(meeting_id, actor, request):
    """Restore only inside the 72-hour window, serialized with the purger."""
    with transaction.atomic():
        meeting = Meeting.objects.select_for_update().filter(pk=meeting_id).first()
        if meeting is None or meeting.deletion_requested_at is None:
            raise NotFound()
        if timezone.now() >= meeting.deletion_due_at:
            raise Conflict("Prazo de restauração encerrado.")
        meeting.deletion_requested_at = None
        meeting.purge_error_code = ""
        meeting.purge_attempts = 0
        meeting.save(update_fields=[
            "deletion_requested_at", "purge_error_code", "purge_attempts", "updated_at"
        ])
        record_audit(
            actor, "meeting_restored", meeting.id, request=request,
            sector=meeting.sector, subject_user=meeting.owner,
            target_type="meeting", target_ref=meeting.id,
        )
    return meeting


def _purge_one(meeting_id, now):
    with transaction.atomic():
        meeting = Meeting.objects.select_for_update().filter(pk=meeting_id).first()
        if meeting is None or meeting.deletion_requested_at is None:
            return False
        if now < meeting.deletion_requested_at + DELETION_GRACE_PERIOD:
            return False
        # The row lock serializes with admin restore. Missing files are safe on retry.
        delete_media(meeting)
        record_audit(
            None, "meeting_purged", meeting.id, sector=meeting.sector,
            subject_user=meeting.owner, target_type="meeting", target_ref=meeting.id,
            details={"requested_at": meeting.deletion_requested_at.isoformat()},
        )
        # Segment.speaker uses PROTECT: delete segments before cascading speakers.
        meeting.segments.all().delete()
        meeting.delete()
    return True


def purge_expired_meetings(*, now=None, limit=BATCH_SIZE):
    now = now or timezone.now()
    if timezone.is_naive(now) or limit < 1 or limit > BATCH_SIZE:
        raise ValueError("Invalid purge schedule")
    candidates = list(
        Meeting.objects.filter(deletion_requested_at__lte=now - DELETION_GRACE_PERIOD)
        # Repeated filesystem failures must not starve newer due meetings.
        .order_by("purge_attempts", "deletion_requested_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    deleted = failed = 0
    for meeting_id in candidates:
        try:
            deleted += int(_purge_one(meeting_id, now))
        except Exception as exc:
            logger.exception("Could not purge meeting %s", meeting_id)
            Meeting.objects.filter(pk=meeting_id, deletion_requested_at__isnull=False).update(
                purge_attempts=F("purge_attempts") + 1,
                purge_error_code=type(exc).__name__[:60],
            )
            failed += 1
    return {"deleted": deleted, "failed": failed, "remaining": len(candidates) == limit}
