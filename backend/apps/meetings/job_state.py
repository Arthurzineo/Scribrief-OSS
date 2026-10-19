"""Durable job lifecycle and cooperative cancellation, not worker termination."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.system_recording import record_system_event

from .models import Meeting, MeetingStatus, Minutes, ProcessingJob, SpeakerAnalysis


class JobCancelled(RuntimeError):
    pass


def accept_job(meeting, job_id, kind, media_duration_seconds=None):
    with transaction.atomic():
        current = Meeting.objects.select_for_update().get(pk=meeting.pk)
        if current.deletion_requested_at is not None:
            raise JobCancelled("Meeting is pending deletion")
        job, created = ProcessingJob.objects.get_or_create(
            id=job_id,
            defaults={
                "meeting_id": current.pk,
                "sector_id": current.sector_id,
                "requested_by_id": current.owner_id,
                "kind": kind,
                "media_duration_seconds": (
                    Decimal(str(media_duration_seconds)).quantize(Decimal("0.01"))
                    if media_duration_seconds is not None else None
                ),
            },
        )
        if media_duration_seconds is not None and job.media_duration_seconds is None:
            job.media_duration_seconds = Decimal(str(media_duration_seconds)).quantize(
                Decimal("0.01")
            )
            job.save(update_fields=["media_duration_seconds"])
        if created:
            record_system_event(
                "worker", "job_queued", outcome="queued", kind=kind,
                job_id=job.id, meeting_id=current.pk, sector_id=current.sector_id,
                user_id=current.owner_id,
            )
        return job


def start_job(job_id, stage="running"):
    now = timezone.now()
    changed = ProcessingJob.objects.filter(id=job_id, status="queued").update(
        status="running", stage=stage, started_at=now, heartbeat_at=now
    )
    if changed:
        job = ProcessingJob.objects.get(id=job_id)
        record_system_event(
            "worker", "job_started", outcome="running", kind=job.kind,
            stage=stage, job_id=job.id, meeting_id=job.meeting_id,
            sector_id=job.sector_id, user_id=job.requested_by_id,
        )


def heartbeat_job(job_id, *, stage=None, completed_units=None, total_units=None):
    updates = {"heartbeat_at": timezone.now()}
    if stage is not None:
        updates["stage"] = stage
    if completed_units is not None:
        updates["completed_units"] = completed_units
    if total_units is not None:
        updates["total_units"] = total_units
    ProcessingJob.objects.filter(id=job_id, status="running").update(**updates)


def finish_job(job_id, status, error_code=""):
    changed = ProcessingJob.objects.filter(id=job_id, status__in=["queued", "running"]).update(
        status=status, error_code=error_code, completed_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )
    if changed:
        job = ProcessingJob.objects.get(id=job_id)
        record_system_event(
            "worker", f"job_{status}", severity="error" if status == "failed" else "info",
            outcome=status, error_code=error_code, stage=job.stage, kind=job.kind,
            job_id=job.id, meeting_id=job.meeting_id,
            sector_id=job.sector_id, user_id=job.requested_by_id,
        )


def finish_stale_job(job_id):
    """Release a queued/running job whose input version or meeting state changed."""
    finish_job(job_id, "failed", "stale_state")
    return "ignored"


def ensure_not_cancelled(job_id):
    if ProcessingJob.objects.filter(id=job_id, cancel_requested_at__isnull=False).exists():
        raise JobCancelled("Job cancelled")


@transaction.atomic
def cancel_job(job_id):
    job = ProcessingJob.objects.filter(id=job_id).first()
    if job is None:
        return None
    meeting = Meeting.objects.select_for_update().filter(pk=job.meeting_id).first()
    job = ProcessingJob.objects.select_for_update().get(id=job_id)
    if job.status in ("completed", "failed", "cancelled"):
        return job
    now = timezone.now()
    job.cancel_requested_at = now
    job.status = "cancelled"
    job.completed_at = now
    job.error_code = "job_cancelled"
    job.save(update_fields=["cancel_requested_at", "status", "completed_at", "error_code"])
    record_system_event(
        "worker", "job_cancelled", outcome="cancelled", error_code="job_cancelled",
        stage=job.stage, kind=job.kind, job_id=job.id, meeting_id=job.meeting_id,
        sector_id=job.sector_id, user_id=job.requested_by_id,
    )
    if meeting is None:
        return job
    if job.kind == "transcription" and meeting.job_id == job.id:
        if meeting.status in (
            MeetingStatus.ENVIADO, MeetingStatus.EXTRAINDO_AUDIO, MeetingStatus.TRANSCREVENDO
        ):
            meeting.status = MeetingStatus.ERRO
            meeting.error_code = "job_cancelled"
            meeting.error_message = "Processamento cancelado pelo administrador."
            meeting.save(update_fields=["status", "error_code", "error_message", "updated_at"])
    elif job.kind == "minutes" and meeting.job_id == job.id:
        if meeting.status == MeetingStatus.GERANDO_ATA:
            meeting.status = (
                MeetingStatus.ATA_PRONTA
                if Minutes.objects.filter(meeting=meeting).exists()
                else MeetingStatus.TRANSCRITO
            )
            meeting.save(update_fields=["status", "updated_at"])
    elif job.kind == "mind_map":
        Minutes.objects.filter(
            meeting=meeting, mind_map_job_id=job.id, mind_map_status="generating"
        ).update(mind_map_status="error")
    elif job.kind == "speaker_reconciliation":
        SpeakerAnalysis.objects.filter(
            meeting=meeting, job_id=job.id, status="processing"
        ).update(status="error", message="Análise cancelada.")
    elif job.kind == "correction":
        from django.core.cache import cache

        from .correction_jobs import active_key, result_key

        state = cache.get(result_key(str(job.id)))
        if state:
            state.update(status="error", message="Análise cancelada.")
            cache.set(result_key(str(job.id)), state)
        key = active_key(meeting.id, meeting.transcription_version)
        if cache.get(key) == str(job.id):
            cache.delete(key)
    return job
