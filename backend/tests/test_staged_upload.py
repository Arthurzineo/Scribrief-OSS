from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.meetings.models import Meeting, MonthlyMediaUsage, ProcessingJob


def clip():
    return SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100, content_type="audio/mpeg")


@pytest.mark.django_db
def test_upload_waits_for_explicit_consent_before_any_job_or_quota(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Aguardando decisão")
    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.views.processing.duration_seconds", return_value=60),
        patch("apps.meetings.transcription_jobs.enqueue_transcription") as enqueue,
    ):
        staged = api.post(
            f"/api/v1/meetings/{meeting.id}/upload/",
            {"file": clip(), "consent_confirmed": "false"}, format="multipart",
        )
        assert staged.status_code == 201
        meeting.refresh_from_db()
        assert meeting.staged_at is not None
        assert staged.data["expires_at"] - meeting.staged_at == timedelta(hours=2)
        assert meeting.consent_confirmed_at is None
        assert meeting.job_id is None
        assert (tmp_path / meeting.original_path).is_file()
        assert not ProcessingJob.objects.filter(meeting_id=meeting.id).exists()
        assert not MonthlyMediaUsage.objects.filter(user_id_snapshot=user.id).exists()
        assert not enqueue.called
        assert api.get(f"/api/v1/meetings/{meeting.id}/original/download/").status_code == 404

        denied = api.post(f"/api/v1/meetings/{meeting.id}/confirm-upload/", {}, format="json")
        assert denied.status_code == 400
        assert not enqueue.called
        confirmed = api.post(
            f"/api/v1/meetings/{meeting.id}/confirm-upload/",
            {"consent_confirmed": True}, format="json",
        )
        assert confirmed.status_code == 202
        assert enqueue.call_count == 1
    meeting.refresh_from_db()
    assert meeting.staged_at is None
    assert meeting.consent_confirmed_at is not None
    assert meeting.job_id is not None
    assert ProcessingJob.objects.filter(meeting_id=meeting.id).count() == 1
    assert MonthlyMediaUsage.objects.get(user_id_snapshot=user.id).upload_count == 1
    assert api.post(f"/api/v1/meetings/{meeting.id}/discard-upload/").status_code == 409
    assert api.post(
        f"/api/v1/meetings/{meeting.id}/confirm-upload/",
        {"consent_confirmed": True}, format="json",
    ).status_code == 409


@pytest.mark.django_db
def test_abandon_deletes_unconfirmed_file_and_is_owner_only(
    api, user, other_user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Abandonar")
    with patch("apps.meetings.storage.probe_audio"):
        assert api.post(
            f"/api/v1/meetings/{meeting.id}/upload/",
            {"file": clip(), "consent_confirmed": "false"}, format="multipart",
        ).status_code == 201
    meeting.refresh_from_db()
    path = tmp_path / meeting.original_path
    api.force_authenticate(user=other_user)
    assert api.post(f"/api/v1/meetings/{meeting.id}/discard-upload/").status_code == 404
    assert path.exists()
    api.force_authenticate(user=user)
    assert api.post(f"/api/v1/meetings/{meeting.id}/discard-upload/").status_code == 204
    assert not path.exists()
    assert not Meeting.objects.filter(pk=meeting.pk).exists()
    assert AuditEvent.objects.filter(action="upload_discarded", target_id=meeting.pk).exists()


@pytest.mark.django_db
def test_stale_staged_upload_is_purged_but_confirmed_upload_is_not(api, user, settings, tmp_path):
    from apps.meetings.services.staged_upload import purge_stale_uploads

    settings.MEDIA_ROOT = tmp_path
    old = Meeting.objects.create(owner=user, title="Expirado")
    current = Meeting.objects.create(owner=user, title="Recente")
    for meeting in (old, current):
        with patch("apps.meetings.storage.probe_audio"):
            assert api.post(
                f"/api/v1/meetings/{meeting.id}/upload/",
                {"file": clip(), "consent_confirmed": "false"}, format="multipart",
            ).status_code == 201
    old.refresh_from_db()
    old_path = tmp_path / old.original_path
    Meeting.objects.filter(pk=old.pk).update(staged_at=timezone.now() - timedelta(hours=2))
    expired = api.post(
        f"/api/v1/meetings/{old.id}/confirm-upload/",
        {"consent_confirmed": True}, format="json",
    )
    assert expired.status_code == 410
    assert expired.data["error"]["code"] == "staged_expired"
    result = purge_stale_uploads(now=timezone.now())
    assert result["deleted"] == 1
    assert not old_path.exists()
    assert not Meeting.objects.filter(pk=old.pk).exists()
    assert Meeting.objects.filter(pk=current.pk).exists()


@pytest.mark.django_db
def test_staged_media_remains_confirmable_until_two_hours(api, user, settings, tmp_path):
    from apps.meetings.services.staged_upload import purge_stale_uploads

    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Aguardando por 90 minutos")
    with patch("apps.meetings.storage.probe_audio"):
        assert api.post(
            f"/api/v1/meetings/{meeting.id}/upload/",
            {"file": clip(), "consent_confirmed": "false"}, format="multipart",
        ).status_code == 201
    Meeting.objects.filter(pk=meeting.pk).update(
        staged_at=timezone.now() - timedelta(minutes=90)
    )
    assert purge_stale_uploads(now=timezone.now())["deleted"] == 0
    with (
        patch("apps.meetings.views.processing.duration_seconds", return_value=60),
        patch("apps.meetings.transcription_jobs.enqueue_transcription"),
    ):
        response = api.post(
            f"/api/v1/meetings/{meeting.id}/confirm-upload/",
            {"consent_confirmed": True}, format="json",
        )
    assert response.status_code == 202


def test_configured_upload_limit_never_exceeds_five_gib():
    from config.upload_limits import configured_upload_bytes

    assert configured_upload_bytes("5120") == 5 * 1024**3
    assert configured_upload_bytes("10240") == 5 * 1024**3
    assert configured_upload_bytes("256") == 256 * 1024**2
    with pytest.raises(ValueError):
        configured_upload_bytes("0")


@pytest.mark.django_db
def test_oversized_upload_is_rejected_without_saved_media_or_job(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MAX_UPLOAD_BYTES = 64
    meeting = Meeting.objects.create(owner=user, title="Acima do limite")
    result = api.post(
        f"/api/v1/meetings/{meeting.pk}/upload/",
        {"file": clip(), "consent_confirmed": "false"}, format="multipart",
    )
    assert result.status_code in (400, 413)
    meeting.refresh_from_db()
    assert not meeting.original_path and meeting.staged_at is None
    assert not ProcessingJob.objects.filter(meeting_id=meeting.pk).exists()
    assert not list((tmp_path / "reunioes" / str(meeting.pk)).glob("original*"))


@pytest.mark.django_db
def test_rejected_quota_does_not_start_job_or_erase_staged_media(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    sector = user.membership.sector
    sector.max_monthly_minutes_per_user = 1
    sector.save(update_fields=["max_monthly_minutes_per_user"])
    meeting = Meeting.objects.create(owner=user, title="Acima da cota")
    with patch("apps.meetings.storage.probe_audio"):
        assert api.post(
            f"/api/v1/meetings/{meeting.id}/upload/",
            {"file": clip(), "consent_confirmed": "false"}, format="multipart",
        ).status_code == 201
    with patch("apps.meetings.views.processing.duration_seconds", return_value=120):
        response = api.post(
            f"/api/v1/meetings/{meeting.id}/confirm-upload/",
            {"consent_confirmed": True}, format="json",
        )
    assert response.status_code == 409
    meeting.refresh_from_db()
    assert meeting.staged_at is not None and meeting.job_id is None
    assert (tmp_path / meeting.original_path).exists()
    assert not MonthlyMediaUsage.objects.filter(user_id_snapshot=user.id).exists()


@pytest.mark.django_db
def test_staged_creation_without_completed_upload_is_eventually_discarded(
    api, user, settings, tmp_path
):
    from apps.meetings.services.staged_upload import discard_staged_upload, purge_stale_uploads

    settings.MEDIA_ROOT = tmp_path
    created = api.post(
        "/api/v1/meetings/", {"title": "Upload interrompido"},
        format="json", HTTP_X_STAGED_UPLOAD="1",
    )
    assert created.status_code == 201
    meeting = Meeting.objects.get(pk=created.data["id"])
    assert meeting.staged_at is not None and not meeting.original_path
    assert api.get(f"/api/v1/meetings/{meeting.pk}/").status_code == 404
    assert discard_staged_upload(meeting.pk, expired=True, now=timezone.now()) is False
    Meeting.objects.filter(pk=meeting.pk).update(staged_at=timezone.now() - timedelta(hours=5))
    assert purge_stale_uploads(now=timezone.now())["deleted"] == 1
    assert not Meeting.objects.filter(pk=meeting.pk).exists()
