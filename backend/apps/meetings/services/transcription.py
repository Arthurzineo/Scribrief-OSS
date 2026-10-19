"""Transactional editing rules shared by the API actions."""


from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.audit.change_tracking import describe_changes, fingerprint
from apps.audit.models import record_audit

from ..exports import export_best_effort, export_minutes, export_transcript
from ..models import Meeting, MeetingStatus
from .common import Conflict, _editable_transcription, _invalidate_review, _require_owner


def edit_segments(meeting, changes, version, actor, request=None):
    with transaction.atomic():
        current = Meeting.objects.select_for_update().get(pk=meeting.pk)
        _require_owner(current, actor)
        _editable_transcription(current)
        if current.transcription_version != version:
            raise Conflict()
        ids = [item["id"] for item in changes]
        if len(ids) != len(set(ids)):
            raise ValidationError({"segmentos": "IDs duplicados."})
        segments = {seg.id: seg for seg in current.segments.filter(id__in=ids)}
        if set(segments) != set(ids):
            raise NotFound("Segmento não encontrado.")
        audit_changes = []
        for item in changes:
            segment = segments[item["id"]]
            previous = {
                "text": segment.text,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
            }
            if segment.original_source == "unverified":
                segment.original_text = segment.text
                segment.original_start_ms = segment.start_ms
                segment.original_end_ms = segment.end_ms
                segment.original_speaker_code = segment.speaker.code
                segment.original_source = "first_edit_baseline"
                segment.save(update_fields=[
                    "original_text", "original_start_ms", "original_end_ms",
                    "original_speaker_code", "original_source",
                ])
            segment.text = item["texto"]
            segment.start_ms = round(item["inicio"] * 1000)
            segment.end_ms = round(item["fim"] * 1000)
            if segment.end_ms <= segment.start_ms:
                raise ValidationError({"segmentos": "Intervalo inválido."})
            updated = {
                "text": segment.text,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
            }
            changed = describe_changes(previous, updated)
            if changed:
                audit_changes.append({
                    "segment_id": segment.id,
                    "line": segment.order + 1,
                    "original_source": segment.original_source,
                    "original_hash": fingerprint(segment.original_text),
                    "current_hash": fingerprint(segment.text),
                    "matches_original": segment.text == segment.original_text,
                    "fields": {item["path"]: {"before": item["before"], "after": item["after"]}
                               for item in changed},
                })
                segment.save(update_fields=["text", "start_ms", "end_ms"])
        if not audit_changes:
            record_audit(
                actor, "transcription_edit_noop", current.id, request=request,
                sector=current.sector, target_type="meeting", target_ref=current.id,
                details={"version": version, "segment_ids": ids},
            )
            return current
        current.transcription_version += 1
        if current.status == MeetingStatus.ATA_PRONTA:
            current.minutes_stale = True
            _invalidate_review(current)
        current.save(
            update_fields=[
                "transcription_version", "minutes_version", "minutes_stale", "updated_at"
            ]
        )
        record_audit(
            actor, "transcription_edited", current.id, request=request,
            sector=current.sector, target_type="meeting", target_ref=current.id,
            details={
                "version_before": version,
                "version_after": current.transcription_version,
                "changes": audit_changes,
            },
        )
    export_best_effort(export_transcript, current)
    if current.status == MeetingStatus.ATA_PRONTA:
        export_best_effort(export_minutes, current)
    return current
