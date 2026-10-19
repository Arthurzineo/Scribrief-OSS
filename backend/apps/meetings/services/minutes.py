"""Transactional editing rules shared by the API actions."""


from django.db import transaction
from django.utils import timezone

from apps.audit.change_tracking import describe_changes
from apps.audit.models import record_audit

from ..exports import export_best_effort, export_minutes
from ..models import Meeting, MeetingStatus
from .common import Conflict, _require_owner


def edit_minutes(meeting, data, version, actor, request=None):
    with transaction.atomic():
        current = Meeting.objects.select_for_update().get(pk=meeting.pk)
        _require_owner(current, actor)
        if current.status != MeetingStatus.ATA_PRONTA or current.minutes_version != version:
            raise Conflict()
        minutes = current.minutes
        before = {field: getattr(minutes, field) for field in data}
        for field, value in data.items():
            setattr(minutes, field, value)
        changed = describe_changes(before, data)
        minutes.human_edited = True
        minutes.reviewed_by = None
        minutes.reviewer_name = ""
        minutes.reviewed_at = None
        minutes.save()
        current.minutes_version += 1
        current.save(update_fields=["minutes_version", "updated_at"])
        record_audit(
            actor, "minutes_edited", current.id, request=request,
            sector=current.sector, target_type="meeting", target_ref=current.id,
            details={"version_before": version, "version_after": current.minutes_version,
                     "changes": changed},
        )
    export_best_effort(export_minutes, current)
    return current


def review_minutes(meeting, version, actor, request=None):
    with transaction.atomic():
        current = Meeting.objects.select_for_update().get(pk=meeting.pk)
        _require_owner(current, actor)
        if current.status != MeetingStatus.ATA_PRONTA or current.minutes_version != version:
            raise Conflict()
        if current.minutes_stale:
            raise Conflict("A ata está desatualizada. Gere-a novamente antes de revisar.")
        minutes = current.minutes
        if minutes.reviewed_at is not None:
            raise Conflict("Esta versão da ata já foi revisada.")
        minutes.reviewed_by = actor
        minutes.reviewer_name = (actor.get_full_name() or actor.get_username())[:150]
        minutes.reviewed_at = timezone.now()
        fields = ["reviewed_by", "reviewer_name", "reviewed_at", "updated_at"]
        if minutes.mind_map_status == "ready" and minutes.mind_map_version == version:
            # Revisar muda metadados, não o conteúdo que originou o mapa.
            minutes.mind_map_version = version + 1
            fields.append("mind_map_version")
        minutes.save(update_fields=fields)
        current.minutes_version += 1
        current.save(update_fields=["minutes_version", "updated_at"])
        record_audit(
            actor, "minutes_reviewed", current.id, request=request,
            sector=current.sector, target_type="meeting", target_ref=current.id,
            details={"version_before": version, "version_after": current.minutes_version},
        )
    export_best_effort(export_minutes, current)
    return current
