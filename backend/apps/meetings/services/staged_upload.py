"""Immediate disposal and bounded retention for media lacking consent."""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.audit.models import record_audit

from ..models import Meeting, MeetingStatus
from ..storage import delete_media
from .common import Conflict

logger = logging.getLogger(__name__)
STAGED_UPLOAD_TTL = timedelta(hours=2)
EMPTY_DRAFT_TTL = timedelta(hours=4)
BATCH_SIZE = 100


def discard_staged_upload(meeting_id, *, actor=None, request=None, expired=False, now=None):
    """Never delete a consented or processing meeting via this fast path."""
    with transaction.atomic():
        meeting = Meeting.objects.select_for_update().filter(pk=meeting_id).first()
        if meeting is None or (actor is not None and meeting.owner_id != actor.pk):
            raise NotFound()
        if (meeting.consent_confirmed_at is not None or meeting.job_id is not None
                or meeting.status != MeetingStatus.ENVIADO
                or meeting.deletion_requested_at is not None):
            raise Conflict("Envio já confirmado ou em processamento.")
        if expired:
            deadline = (meeting.staged_at + (
                STAGED_UPLOAD_TTL if meeting.original_path else EMPTY_DRAFT_TTL
            )) if meeting.staged_at else None
            if deadline is None or (now or timezone.now()) < deadline:
                return False
        delete_media(meeting)
        record_audit(
            actor, "upload_staged_expired" if expired else "upload_discarded",
            meeting.id, request=request, sector=meeting.sector,
            subject_user=meeting.owner, target_type="meeting", target_ref=meeting.id,
            details={"had_file": bool(meeting.original_path)},
        )
        meeting.delete()
    return True


def purge_stale_uploads(*, now=None, limit=BATCH_SIZE):
    now = now or timezone.now()
    if timezone.is_naive(now) or limit < 1 or limit > BATCH_SIZE:
        raise ValueError("Invalid staged upload purge schedule")
    candidates = list(
        Meeting.objects.filter(
            Q(staged_at__lte=now - STAGED_UPLOAD_TTL) & ~Q(original_path="")
            | Q(staged_at__lte=now - EMPTY_DRAFT_TTL, original_path="")
        )
        .order_by("staged_at", "id").values_list("id", flat=True)[:limit]
    )
    deleted = failed = 0
    for meeting_id in candidates:
        try:
            deleted += int(discard_staged_upload(meeting_id, expired=True, now=now))
        except (NotFound, Conflict):
            continue  # Confirmation or another cleanup won the row lock.
        except Exception:
            failed += 1
            logger.exception("Could not purge staged upload %s", meeting_id)
    return {"deleted": deleted, "failed": failed, "remaining": len(candidates) == limit}
