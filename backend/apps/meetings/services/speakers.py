"""Transactional editing rules shared by the API actions."""


from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.audit.change_tracking import fingerprint
from apps.audit.models import record_audit

from ..exports import export_best_effort, export_minutes, export_transcript
from ..models import Meeting, MeetingStatus, Speaker
from .common import Conflict, _editable_transcription, _invalidate_review, _require_owner


def rename_speaker(meeting, code, name, version, actor, request=None):
    with transaction.atomic():
        current = Meeting.objects.select_for_update().get(pk=meeting.pk)
        _require_owner(current, actor)
        _editable_transcription(current)
        if current.transcription_version != version:
            raise Conflict()
        speaker = Speaker.objects.filter(
            meeting=current, code=code, merged_into__isnull=True
        ).first()
        if speaker is None:
            raise NotFound("Falante não encontrado.")
        old_name = speaker.name
        speaker.name = name
        speaker.save(update_fields=["name"])
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
            actor, "speaker_renamed", current.id, request=request,
            sector=current.sector, target_type="meeting", target_ref=current.id,
            details={"speaker_code": code, "version_before": version,
                     "version_after": current.transcription_version,
                     "name_before": fingerprint(old_name), "name_after": fingerprint(name)},
        )
    export_best_effort(export_transcript, current)
    if current.status == MeetingStatus.ATA_PRONTA:
        export_best_effort(export_minutes, current)
    return current


def merge_speakers(meeting, source_code, target_code, version, actor, request=None):
    return merge_speakers_batch(meeting, [source_code], target_code, version, actor, request)


def merge_speakers_batch(meeting, source_codes, target_code, version, actor, request=None):
    if (
        not source_codes
        or len(source_codes) != len(set(source_codes))
        or target_code in source_codes
    ):
        raise ValidationError({"sources": "Escolha falantes distintos do destino."})
    with transaction.atomic():
        current = Meeting.objects.select_for_update().get(pk=meeting.pk)
        _require_owner(current, actor)
        _editable_transcription(current)
        if current.transcription_version != version:
            raise Conflict()
        target = Speaker.objects.filter(
            meeting=current, code=target_code, merged_into__isnull=True
        ).first()
        sources = list(Speaker.objects.filter(
            meeting=current, code__in=source_codes, merged_into__isnull=True
        ))
        if target is None or len(sources) != len(source_codes):
            raise NotFound("Falante não encontrado.")
        for source in sources:
            source.segments.update(speaker=target)
            source.merged_into = target
            source.save(update_fields=["merged_into"])
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
            actor, "speakers_merged", current.id, request=request,
            sector=current.sector, target_type="meeting", target_ref=current.id,
            details={"source_codes": sorted(source_codes), "target_code": target_code,
                     "version_before": version, "version_after": current.transcription_version},
        )
    export_best_effort(export_transcript, current)
    if current.status == MeetingStatus.ATA_PRONTA:
        export_best_effort(export_minutes, current)
    return current
