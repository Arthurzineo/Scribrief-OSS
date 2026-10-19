"""Transactional editing rules shared by the API actions."""


from rest_framework.exceptions import APIException, NotFound

from ..models import MeetingStatus


class Conflict(APIException):
    status_code = 409
    default_detail = "Versão desatualizada ou estado incompatível."
    default_code = "conflict"


def _editable_transcription(meeting):
    if meeting.status not in (MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA):
        raise Conflict("Transcrição ainda não está disponível para edição.")


def _require_owner(meeting, actor):
    if meeting.deletion_requested_at is not None or meeting.owner_id != actor.pk:
        raise NotFound()


def _invalidate_review(meeting):
    if meeting.status == MeetingStatus.ATA_PRONTA:
        minutes = meeting.minutes
        if minutes.reviewed_at is not None:
            minutes.reviewed_by = None
            minutes.reviewer_name = ""
            minutes.reviewed_at = None
            minutes.save(
                update_fields=["reviewed_by", "reviewer_name", "reviewed_at", "updated_at"]
            )
            meeting.minutes_version += 1
