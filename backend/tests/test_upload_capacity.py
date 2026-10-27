"""Tiny limits prove admission without allocating large files or exhausting disk."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.meetings.models import Meeting, UploadLease
from apps.meetings.services.upload_capacity import UploadCapacityExceeded, acquire_upload


@pytest.mark.django_db
def test_active_ingestion_denies_second_parser_before_storage(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    first = Meeting.objects.create(owner=user, title="Em andamento")
    second = Meeting.objects.create(owner=user, title="Concorrente")
    acquire_upload(first.pk, user, 100)
    with patch("apps.meetings.views.processing.save_original") as save:
        response = api.post(f"/api/v1/meetings/{second.pk}/upload/", {
            "file": SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100),
        }, format="multipart")
    assert response.status_code == 429
    save.assert_not_called()
    assert UploadLease.objects.count() == 1  # did not release another request's lease


@pytest.mark.django_db
def test_global_and_personal_staging_bytes_include_legacy_media(
    user, other_user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.STAGED_UPLOAD_MAX_BYTES = 200
    settings.STAGED_UPLOAD_MAX_BYTES_PER_USER = 150
    old = Meeting.objects.create(owner=user, title="Guardado", original_path="reunioes/a.mp3",
                                 original_size_bytes=100)
    new = Meeting.objects.create(owner=user, title="Novo")
    with pytest.raises(UploadCapacityExceeded):
        acquire_upload(new.pk, user, 51)
    peer = Meeting.objects.create(owner=other_user, title="Colega")
    lease = acquire_upload(peer.pk, other_user, 100)
    lease.delete()
    old.original_size_bytes = 0
    old.save(update_fields=["original_size_bytes"])
    with pytest.raises(UploadCapacityExceeded):
        acquire_upload(peer.pk, other_user, 1)


@pytest.mark.django_db
def test_confirmation_releases_staging_capacity_but_disk_floor_still_applies(
    user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.STAGED_UPLOAD_MAX_BYTES = 200
    settings.STAGED_UPLOAD_MAX_BYTES_PER_USER = 200
    Meeting.objects.create(owner=user, title="Confirmado", original_path="reunioes/a.mp3",
                           original_size_bytes=1000, consent_confirmed_at=timezone.now())
    new = Meeting.objects.create(owner=user, title="Novo")
    with patch("apps.meetings.services.upload_capacity.shutil.disk_usage",
               return_value=SimpleNamespace(free=settings.MEDIA_MIN_FREE_BYTES + 99)):
        with pytest.raises(UploadCapacityExceeded):
            acquire_upload(new.pk, user, 100)
    assert not UploadLease.objects.exists()
    assert acquire_upload(new.pk, user, 100).reserved_bytes == 100


@pytest.mark.django_db
def test_parser_failure_releases_capacity_and_success_charges_measured_bytes(
    api, user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Inválido")
    response = api.post(f"/api/v1/meetings/{meeting.pk}/upload/", {
        "file": SimpleUploadedFile("clip.mp3", b"not-audio"),
    }, format="multipart")
    assert response.status_code == 400 and not UploadLease.objects.exists()
    clip = b"ID3" + b"x" * 100
    with patch("apps.meetings.storage.probe_audio"):
        response = api.post(f"/api/v1/meetings/{meeting.pk}/upload/", {
            "file": SimpleUploadedFile("clip.mp3", clip),
        }, format="multipart")
    assert response.status_code == 201 and not UploadLease.objects.exists()
    meeting.refresh_from_db()
    assert meeting.original_size_bytes == len(clip)


@pytest.mark.django_db
def test_expired_abandoned_lease_recovers_and_owner_is_checked(
    user, other_user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Abandonado")
    lease = acquire_upload(meeting.pk, user, 100)
    with pytest.raises(NotFound):
        acquire_upload(meeting.pk, other_user, 100)
    UploadLease.objects.filter(pk=lease.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    recovered = acquire_upload(meeting.pk, user, 100)
    assert recovered.pk != lease.pk and UploadLease.objects.count() == 1


@pytest.mark.django_db
def test_session_csrf_upload_checks_admission_and_releases_rejected_request(
    user, settings, tmp_path,
):
    from rest_framework.test import APIClient

    settings.MEDIA_ROOT = tmp_path
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.get("/api/v1/csrf/").status_code == 200
    meeting = Meeting.objects.create(owner=user, title="Sessão CSRF")
    with patch("apps.meetings.storage.probe_audio"):
        result = client.post(f"/api/v1/meetings/{meeting.pk}/upload/", {
            "file": SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100),
        }, format="multipart", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert result.status_code == 201 and not UploadLease.objects.exists()
    another = Meeting.objects.create(owner=user, title="CSRF ausente")
    result = client.post(f"/api/v1/meetings/{another.pk}/upload/", {
        "file": SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100),
    }, format="multipart")
    assert result.status_code == 403 and not UploadLease.objects.exists()


@pytest.mark.django_db
def test_deleting_draft_cannot_free_an_active_http_upload_slot(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    draft = Meeting.objects.create(owner=user, title="Descartado durante upload")
    acquire_upload(draft.pk, user, 100)
    draft.delete()
    another = Meeting.objects.create(owner=user, title="Outro envio")
    with pytest.raises(UploadCapacityExceeded):
        acquire_upload(another.pk, user, 100)
    assert UploadLease.objects.count() == 1
