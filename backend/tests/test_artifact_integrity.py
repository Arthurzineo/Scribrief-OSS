"""Regression tests for stale review and outdated derived downloads."""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.meetings.exports import export_minutes, export_transcript
from apps.meetings.models import Meeting, MeetingStatus, Minutes, Segment, Speaker


@pytest.mark.django_db
def test_outdated_minutes_cannot_be_marked_reviewed(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Ata desatualizada", status=MeetingStatus.ATA_PRONTA,
        minutes_version=2, minutes_stale=True,
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Resumo anterior",
        topicos=[{"titulo": "Pauta", "comentario": "Anterior"}],
    )
    url = f"/api/v1/meetings/{meeting.id}/minutes/review/"

    rejected = api.post(url, {"version": 2}, format="json")
    meeting.refresh_from_db()
    assert rejected.status_code == 409
    assert meeting.minutes.reviewed_at is None
    assert meeting.minutes_stale is True
    assert meeting.minutes_version == 2

    meeting.minutes_stale = False  # Simula ata regenerada/reconciliada.
    meeting.save(update_fields=["minutes_stale"])
    accepted = api.post(url, {"version": 2}, format="json")
    assert accepted.status_code == 200
    assert accepted.data["revisor"] == user.username


@pytest.mark.django_db
def test_minutes_download_uses_current_database_version_after_export_failure(
    api, user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Ata", status=MeetingStatus.ATA_PRONTA, minutes_version=1
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Resumo antigo",
        topicos=[{"titulo": "Pauta", "comentario": "Antigo"}],
    )
    export_minutes(meeting)  # Um cache anterior permanece no volume.
    api.raise_request_exception = False
    with patch("apps.meetings.services.minutes.export_minutes", side_effect=OSError("disk full")):
        edited = api.patch(
            f"/api/v1/meetings/{meeting.id}/minutes/",
            {"version": 1, "resumo_executivo": "Resumo novo"}, format="json",
        )
    assert edited.status_code == 200
    meeting.refresh_from_db()
    assert meeting.minutes.resumo_executivo == "Resumo novo"
    assert (tmp_path / "reunioes" / str(meeting.id) / "ata.md").read_text(
        encoding="utf-8"
    ).find("Resumo antigo") >= 0

    base = f"/api/v1/meetings/{meeting.id}/minutes/download/"
    json_response = api.get(base + "?format=json")
    md_response = api.get(base + "?format=md")
    assert json_response.status_code == md_response.status_code == 200
    payload = json.loads(b"".join(json_response.streaming_content))
    assert payload["resumo_executivo"] == "Resumo novo"
    assert "Resumo novo" in b"".join(md_response.streaming_content).decode("utf-8")


@pytest.mark.django_db
def test_transcription_download_uses_current_database_version_after_export_failure(
    api, user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Transcrição", status=MeetingStatus.TRANSCRITO,
        transcription_version=1,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    segment = Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000,
        text="Texto antigo", order=0,
    )
    export_transcript(meeting)
    api.raise_request_exception = False
    with patch(
        "apps.meetings.services.transcription.export_transcript",
        side_effect=OSError("disk full"),
    ):
        edited = api.patch(
            f"/api/v1/meetings/{meeting.id}/transcription/",
            {"version": 1, "segmentos": [
                {"id": segment.id, "texto": "Texto novo", "inicio": 0, "fim": 1}
            ]}, format="json",
        )
    assert edited.status_code == 200

    base = f"/api/v1/meetings/{meeting.id}/transcription/download/"
    json_response = api.get(base + "?format=json")
    md_response = api.get(base + "?format=md")
    assert json_response.status_code == md_response.status_code == 200
    payload = json.loads(b"".join(json_response.streaming_content))
    assert payload["version"] == 2
    assert payload["segmentos"][0]["texto"] == "Texto novo"
    assert "Texto novo" in b"".join(md_response.streaming_content).decode("utf-8")


@pytest.mark.django_db
def test_sector_reader_cannot_review_minutes(api, user, other_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Compartilhada", status=MeetingStatus.ATA_PRONTA,
        minutes_version=1, shared_with_sector=True,
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Resumo",
        topicos=[{"titulo": "Pauta", "comentario": "Conteúdo"}],
    )
    reader = APIClient()
    reader.force_authenticate(user=other_user)
    assert reader.get(f"/api/v1/meetings/{meeting.id}/minutes/download/").status_code == 200
    assert reader.post(
        f"/api/v1/meetings/{meeting.id}/minutes/review/",
        {"version": 1}, format="json",
    ).status_code == 404
