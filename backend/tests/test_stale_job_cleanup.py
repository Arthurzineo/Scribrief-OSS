"""Stale asynchronous work must not block meeting deletion forever."""

from uuid import uuid4

import pytest

from apps.meetings.job_state import accept_job, finish_stale_job
from apps.meetings.jobs.common import _claim
from apps.meetings.jobs.mind_map import generate_mind_map
from apps.meetings.models import Meeting, MeetingStatus, ProcessingJob


@pytest.mark.django_db
def test_stale_mind_map_finishes_processing_job(user):
    meeting = Meeting.objects.create(
        owner=user, title="Mapa alterado", status=MeetingStatus.ATA_PRONTA,
        minutes_version=2,
    )
    job_id = uuid4()
    accept_job(meeting, job_id, "mind_map")

    assert generate_mind_map(str(meeting.id), 1, str(job_id)) == "ignored"
    job = ProcessingJob.objects.get(pk=job_id)
    assert job.status == "failed"
    assert job.error_code == "stale_state"


@pytest.mark.django_db
def test_stale_finish_does_not_change_completed_job(user):
    meeting = Meeting.objects.create(owner=user, title="Finalizada")
    job_id = uuid4()
    accept_job(meeting, job_id, "mind_map")
    ProcessingJob.objects.filter(pk=job_id).update(status="completed")

    assert finish_stale_job(job_id) == "ignored"
    assert ProcessingJob.objects.get(pk=job_id).status == "completed"


@pytest.mark.django_db
def test_stale_queued_transcription_is_released_before_worker_claim(user):
    meeting = Meeting.objects.create(owner=user, title="Fila antiga")
    job_id = uuid4()
    accept_job(meeting, job_id, "transcription")
    meeting.status = MeetingStatus.ERRO
    meeting.save(update_fields=["status"])

    assert _claim(meeting.id, job_id, MeetingStatus.ENVIADO, MeetingStatus.EXTRAINDO_AUDIO) is None
    assert ProcessingJob.objects.get(pk=job_id).status == "failed"


@pytest.mark.django_db
def test_upload_reservation_can_receive_duration_when_dispatched(user):
    meeting = Meeting.objects.create(owner=user, title="Upload reservado")
    job_id = uuid4()
    accept_job(meeting, job_id, "transcription")
    assert ProcessingJob.objects.get(pk=job_id).media_duration_seconds is None

    accept_job(meeting, job_id, "transcription", 180.25)
    assert ProcessingJob.objects.get(pk=job_id).media_duration_seconds == 180.25
