from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Sector, UserMembership
from apps.meetings.models import Meeting, MeetingStatus, Minutes, Segment, Speaker


@pytest.mark.django_db
def test_sector_read_only_includes_all_artifacts_and_revocation(
    api, user, other_user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Compartilhada", status=MeetingStatus.ATA_PRONTA,
        audio_path="reunioes/private/audio.mp3",
        original_path="reunioes/private/original.mp4", minutes_version=1,
    )
    audio = tmp_path / meeting.audio_path
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"ID3audio")
    (audio.parent / "original.mp4").write_bytes(b"video")
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000,
        text="Decidimos o prazo.", order=0,
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Prazo decidido.",
        topicos=[{"titulo": "Prazo", "comentario": "Pela manhã."}],
        mind_map={"centro": "Prazo", "ramos": []}, mind_map_status="ready",
        mind_map_version=1,
    )
    base = f"/api/v1/meetings/{meeting.id}/"
    api.force_authenticate(user=other_user)
    assert api.get(base).status_code == 404
    api.force_authenticate(user=user)
    shared = api.patch(
        f"{base}sharing/", {"shared_with_sector": True, "access_version": 0}, format="json"
    )
    assert shared.status_code == 200
    api.force_authenticate(user=other_user)
    assert api.get(base).data["can_edit"] is False
    assert any(row["id"] == str(meeting.id) for row in api.get("/api/v1/meetings/").data["results"])
    for suffix in (
        "audio/", "original/download/", "transcription/", "transcription/download/", "minutes/",
        "minutes/download/", "mind-map/", "speakers/", "status/", "progress/",
    ):
        response = api.get(base + suffix)
        assert response.status_code == 200, (suffix, response.status_code)
        if hasattr(response, "streaming_content"):
            b"".join(response.streaming_content)
    assert api.patch(base, {"title": "Invadida"}, format="json").status_code == 404
    assert api.post(base + "minutes/", {}, format="json").status_code == 404
    assert api.delete(base).status_code == 404
    outsider_sector = Sector.objects.create(name="Externo", slug="externo-matrix")
    outsider = get_user_model().objects.create_user(
        username="outsider", password="Strong-Test-Password-789"
    )
    UserMembership.objects.create(user=outsider, sector=outsider_sector)
    api.force_authenticate(user=outsider)
    for suffix in ("", "audio/", "transcription/download/", "minutes/download/", "mind-map/"):
        assert api.get(base + suffix).status_code == 404, suffix
    api.force_authenticate(user=user)
    revoked = api.patch(
        f"{base}sharing/", {"shared_with_sector": False, "access_version": 1}, format="json"
    )
    assert revoked.status_code == 200
    api.force_authenticate(user=other_user)
    for suffix in ("", "audio/", "transcription/download/", "minutes/download/", "mind-map/"):
        assert api.get(base + suffix).status_code == 404, suffix


@pytest.mark.django_db
def test_transfer_changes_owner_not_creator_or_files(api, user, other_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Transferível", status=MeetingStatus.TRANSCRITO,
        audio_path="reunioes/stable/audio.mp3",
    )
    audio = tmp_path / meeting.audio_path
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"ID3audio")
    base = f"/api/v1/meetings/{meeting.id}/"
    response = api.post(
        base + "transfer/",
        {"target_user_id": other_user.pk, "access_version": 0}, format="json",
    )
    assert response.status_code == 200, response.data
    meeting.refresh_from_db()
    assert meeting.owner_id == other_user.pk
    assert meeting.created_by_id == user.pk
    assert meeting.access_version == 1
    assert meeting.audio_path == "reunioes/stable/audio.mp3" and audio.is_file()
    assert api.patch(base, {"title": "Antigo dono"}, format="json").status_code == 404
    api.force_authenticate(user=other_user)
    assert api.patch(base, {"title": "Novo dono"}, format="json").status_code == 200


@pytest.mark.django_db
def test_transfer_rejects_other_sector_active_job_and_stale_version(api, user, other_user):
    meeting = Meeting.objects.create(
        owner=user, title="Estado", status=MeetingStatus.TRANSCRITO
    )
    base = f"/api/v1/meetings/{meeting.id}/transfer/"
    other_sector = Sector.objects.create(name="Externo", slug="externo")
    other_user.membership.sector = other_sector
    other_user.membership.save(update_fields=["sector"])
    payload = {"target_user_id": other_user.pk, "access_version": 0}
    assert api.post(base, payload, format="json").status_code == 400
    other_user.membership.sector = user.membership.sector
    other_user.membership.save(update_fields=["sector"])
    meeting.status = MeetingStatus.GERANDO_ATA
    meeting.save(update_fields=["status"])
    assert api.post(base, payload, format="json").status_code == 409
    meeting.status = MeetingStatus.TRANSCRITO
    meeting.access_version = 1
    meeting.save(update_fields=["status", "access_version"])
    assert api.post(base, payload, format="json").status_code == 409


@pytest.mark.django_db
def test_sharing_rolls_back_if_critical_audit_cannot_be_written(api, user):
    meeting = Meeting.objects.create(owner=user, title="Transação")
    with patch(
        "apps.meetings.views.meetings.record_audit", side_effect=RuntimeError("db unavailable")
    ):
        with pytest.raises(RuntimeError):
            api.patch(
                f"/api/v1/meetings/{meeting.pk}/sharing/",
                {"shared_with_sector": True, "access_version": 0}, format="json",
            )
    meeting.refresh_from_db()
    assert meeting.shared_with_sector is False and meeting.access_version == 0
