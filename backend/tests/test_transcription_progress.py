import uuid

import pytest

from apps.meetings.models import Meeting, MeetingStatus, TranscriptionChunk
from apps.meetings.processing.transcription_progress import (
    plan_transcription,
    transcription_progress,
)


@pytest.mark.django_db
def test_progress_counts_durable_checkpoints_and_finishes_only_after_commit(
    api, user, other_user
):
    meeting = Meeting.objects.create(
        owner=user, title="Em andamento", status=MeetingStatus.TRANSCREVENDO,
        job_id=uuid.uuid4(),
    )
    plan_transcription(meeting, 3)
    first = api.get(f"/api/v1/meetings/{meeting.id}/progress/")
    assert first.status_code == 200
    assert first.data["total_chunks"] == 3
    assert first.data["completed_chunks"] == 0
    assert first.data["percent"] == 0
    TranscriptionChunk.objects.create(
        meeting=meeting, index=0, offset_ms=0, audio_sha256="a" * 64,
        model="gpt-4o-transcribe-diarize", language="", segments=[],
    )
    progress = api.get(f"/api/v1/meetings/{meeting.id}/progress/")
    assert progress.data["completed_chunks"] == 1
    assert progress.data["percent"] == 33
    for index in (1, 2):
        TranscriptionChunk.objects.create(
            meeting=meeting, index=index, offset_ms=index * 1185000,
            audio_sha256="a" * 64, model="gpt-4o-transcribe-diarize",
            language="", segments=[],
        )
    almost = api.get(f"/api/v1/meetings/{meeting.id}/progress/")
    assert almost.data["completed_chunks"] == 3
    assert almost.data["percent"] == 99
    meeting.status = MeetingStatus.TRANSCRITO
    meeting.save(update_fields=["status"])
    done = api.get(f"/api/v1/meetings/{meeting.id}/progress/")
    assert done.data["percent"] == 100
    api.force_authenticate(user=other_user)
    assert api.get(f"/api/v1/meetings/{meeting.id}/progress/").status_code == 404


@pytest.mark.django_db
def test_progress_without_plan_is_indeterminate_and_old_job_plan_is_not_reused(user):
    meeting = Meeting.objects.create(
        owner=user, title="Legado", status=MeetingStatus.TRANSCREVENDO,
        job_id=uuid.uuid4(),
    )
    assert transcription_progress(meeting)["percent"] is None
    plan_transcription(meeting, 2)
    meeting.job_id = uuid.uuid4()
    meeting.save(update_fields=["job_id"])
    result = transcription_progress(meeting)
    assert result["total_chunks"] is None
    assert result["percent"] is None
