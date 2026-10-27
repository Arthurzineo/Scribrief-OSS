"""Business and privacy contract for reversible three-day meeting deletion."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.meetings.job_state import accept_job
from apps.meetings.models import Meeting, MeetingStatus, Minutes, Segment, Speaker


@pytest.mark.django_db(transaction=True)
def test_delete_hides_all_artifacts_but_preserves_data_for_admin_restore(
    api, user, other_user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Privada", status=MeetingStatus.ATA_PRONTA,
        shared_with_sector=True,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000,
        text="Conteúdo privado", order=0,
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Resumo",
        topicos=[{"titulo": "Pauta", "comentario": "Texto"}],
    )
    folder = tmp_path / "reunioes" / str(meeting.id)
    folder.mkdir(parents=True)
    (folder / "audio.mp3").write_bytes(b"mp3-private")
    meeting.audio_path = f"reunioes/{meeting.id}/audio.mp3"
    meeting.save(update_fields=["audio_path"])
    url = f"/api/v1/meetings/{meeting.id}/"

    assert api.delete(url).status_code == 204
    meeting.refresh_from_db()
    assert meeting.deletion_requested_at is not None
    assert meeting.segments.count() == 1
    assert meeting.minutes.resumo_executivo == "Resumo"
    assert (folder / "audio.mp3").exists()
    assert api.get("/api/v1/meetings/").data["count"] == 0
    assert api.get(url).status_code == 404
    assert api.get(url + "audio/").status_code == 404
    assert api.get(url + "transcription/").status_code == 404
    assert api.get(url + "minutes/").status_code == 404
    reader = APIClient()
    reader.force_authenticate(user=other_user)
    assert reader.get(url).status_code == 404
    assert reader.get(url + "audio/").status_code == 404

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    listing = api.get("/api/admin/deletions/")
    assert listing.status_code == 200
    assert listing.data["count"] == 1
    assert listing.data["results"][0]["id"] == str(meeting.id)
    restore = f"/api/admin/deletions/{meeting.id}/restore/"
    assert api.post(restore, {"current_password": "wrong"}, format="json").status_code == 403
    assert api.post(
        restore, {"current_password": "Strong-Test-Password-123"}, format="json"
    ).status_code == 200
    meeting.refresh_from_db()
    assert meeting.deletion_requested_at is None
    assert api.get(url).status_code == 200
    audio = api.get(url + "audio/")
    assert audio.status_code == 200
    # Closing a streaming response emits request_finished and closes PostgreSQL
    # connections. This journey must not live inside pytest's outer atomic block.
    audio.close()
    assert api.get("/api/admin/deletions/").data["count"] == 0


@pytest.mark.django_db
def test_non_admin_cannot_see_or_restore_deletion(api, user):
    meeting = Meeting.objects.create(owner=user, title="Excluir")
    assert api.delete(f"/api/v1/meetings/{meeting.id}/").status_code == 204
    assert api.get("/api/admin/deletions/").status_code == 403
    assert api.post(
        f"/api/admin/deletions/{meeting.id}/restore/",
        {"current_password": "Strong-Test-Password-123"}, format="json",
    ).status_code == 403


@pytest.mark.django_db
def test_restore_closes_exactly_at_seventy_two_hours(api, user):
    meeting = Meeting.objects.create(owner=user, title="Expirada")
    assert api.delete(f"/api/v1/meetings/{meeting.id}/").status_code == 204
    Meeting.objects.filter(pk=meeting.pk).update(
        deletion_requested_at=timezone.now() - timedelta(days=3, seconds=1)
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    response = api.post(
        f"/api/admin/deletions/{meeting.id}/restore/",
        {"current_password": "Strong-Test-Password-123"}, format="json",
    )
    assert response.status_code == 409
    meeting.refresh_from_db()
    assert meeting.deletion_requested_at is not None


@pytest.mark.django_db
def test_delete_waits_for_queued_work_and_stops_new_work_after_hiding(api, user):
    from uuid import uuid4

    from apps.meetings.job_state import JobCancelled
    from apps.meetings.models import ProcessingJob

    meeting = Meeting.objects.create(
        owner=user, title="Em análise", status=MeetingStatus.TRANSCRITO
    )
    queued_id = uuid4()
    accept_job(meeting, queued_id, "correction")
    url = f"/api/v1/meetings/{meeting.id}/"
    assert api.delete(url).status_code == 409
    assert Meeting.objects.get(pk=meeting.pk).deletion_requested_at is None
    ProcessingJob.objects.filter(pk=queued_id).update(status="completed")
    assert api.delete(url).status_code == 204
    with pytest.raises(JobCancelled):
        accept_job(meeting, uuid4(), "correction")


@pytest.mark.django_db
def test_purge_waits_seventy_two_hours_then_removes_database_and_files(
    api, user, settings, tmp_path
):
    from apps.meetings.services.deletion import purge_expired_meetings

    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Purgar", status=MeetingStatus.TRANSCRITO)
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    segment = Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000,
        text="Privado atual", original_text="Privado original da IA",
        original_start_ms=0, original_end_ms=1000,
        original_speaker_code="A", original_source="ai_generation", order=0,
    )
    folder = tmp_path / "reunioes" / str(meeting.id)
    folder.mkdir(parents=True)
    (folder / "audio.mp3").write_bytes(b"private")
    assert api.delete(f"/api/v1/meetings/{meeting.id}/").status_code == 204
    requested_at = Meeting.objects.get(pk=meeting.pk).deletion_requested_at

    early = purge_expired_meetings(now=requested_at + timedelta(hours=71, minutes=59))
    assert early["deleted"] == 0
    assert Meeting.objects.filter(pk=meeting.pk).exists()
    assert (folder / "audio.mp3").exists()

    due = purge_expired_meetings(now=requested_at + timedelta(days=3))
    assert due["deleted"] == 1
    assert not Meeting.objects.filter(pk=meeting.pk).exists()
    assert not Segment.objects.filter(pk=segment.pk).exists()
    assert not folder.exists()
    assert purge_expired_meetings(now=requested_at + timedelta(days=4))["deleted"] == 0


@pytest.mark.django_db
def test_failed_file_purge_keeps_hidden_data_for_retry(api, user, settings, tmp_path):
    from apps.meetings.services.deletion import purge_expired_meetings

    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Retry", status=MeetingStatus.TRANSCRITO)
    folder = tmp_path / "reunioes" / str(meeting.id)
    folder.mkdir(parents=True)
    (folder / "audio.mp3").write_bytes(b"private")
    assert api.delete(f"/api/v1/meetings/{meeting.id}/").status_code == 204
    now = timezone.now()
    Meeting.objects.filter(pk=meeting.pk).update(
        deletion_requested_at=now - timedelta(days=3, seconds=1)
    )

    with patch("apps.meetings.services.deletion.delete_media", side_effect=OSError("disk")):
        result = purge_expired_meetings(now=now)
    assert result["failed"] == 1
    meeting.refresh_from_db()
    assert meeting.purge_attempts == 1
    assert meeting.purge_error_code == "OSError"
    assert (folder / "audio.mp3").exists()
    assert api.get(f"/api/v1/meetings/{meeting.id}/").status_code == 404
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    queue = api.get("/api/admin/deletions/")
    assert queue.data["results"][0]["purge_error_code"] == "OSError"

    assert purge_expired_meetings(now=now)["deleted"] == 1
    assert not Meeting.objects.filter(pk=meeting.pk).exists()
    assert not folder.exists()
