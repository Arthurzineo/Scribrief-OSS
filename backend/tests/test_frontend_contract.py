import json
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.meetings.models import Meeting, MeetingStatus, Minutes, Segment, Speaker


@pytest.mark.django_db
def test_account_session_update_and_password(user):
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/v1/csrf/").cookies["csrftoken"].value
    login = client.post(
        "/api/v1/login/",
        data=json.dumps({"username": "ana", "password": "Strong-Test-Password-123"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert login.status_code == 200
    token = login.cookies["csrftoken"].value
    update = client.patch(
        "/api/v1/account/",
        data=json.dumps({"name": "Ana Silva", "email": "ana@example.com"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert update.status_code == 200
    assert update.json()["user"]["name"] == "Ana Silva"
    assert client.get("/api/v1/session/").json()["user"]["email"] == "ana@example.com"
    blank = client.patch(
        "/api/v1/account/",
        data=json.dumps({"name": "Ana", "email": ""}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert blank.status_code == 200
    denied = client.post(
        "/api/v1/account/password/",
        data=json.dumps({"currentPassword": "wrong", "newPassword": "Better-Password-456"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert denied.status_code == 400
    changed = client.post(
        "/api/v1/account/password/",
        data=json.dumps(
            {"currentPassword": "Strong-Test-Password-123", "newPassword": "Better-Password-456"}
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/session/").status_code == 200
    user.refresh_from_db()
    assert user.check_password("Better-Password-456")


@pytest.mark.django_db
def test_meeting_detail_and_private_ranged_audio(api, user, other_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user,
        title="Gravação",
        status=MeetingStatus.TRANSCRITO,
        meeting_date="2026-10-07",
        audio_path="reunioes/audio.mp3",
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=5000, text="Texto", order=0
    )
    audio = tmp_path / "reunioes" / "audio.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"ID3abcdef")
    detail = api.get(f"/api/v1/meetings/{meeting.id}/")
    assert detail.status_code == 200
    assert detail.data["duration_seconds"] == 5
    assert detail.data["speaker_count"] == 1
    assert detail.data["audio_available"] is True
    response = api.get(f"/api/v1/meetings/{meeting.id}/audio/", HTTP_RANGE="bytes=3-5")
    assert response.status_code == 206
    assert response["Content-Range"] == "bytes 3-5/9"
    assert b"".join(response.streaming_content) == b"abc"
    suffix = api.get(f"/api/v1/meetings/{meeting.id}/audio/", HTTP_RANGE="bytes=-3")
    assert suffix.status_code == 206
    assert b"".join(suffix.streaming_content) == b"def"
    denied = api.get(f"/api/v1/meetings/{meeting.id}/audio/", HTTP_RANGE="bytes=99-")
    assert denied.status_code == 416
    api.force_authenticate(user=other_user)
    assert api.get(f"/api/v1/meetings/{meeting.id}/audio/").status_code == 404


@pytest.mark.django_db
def test_transcript_remains_readable_while_minutes_generate(api, user):
    meeting = Meeting.objects.create(
        owner=user,
        title="Ata",
        status=MeetingStatus.GERANDO_ATA,
        transcription_version=1,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000, text="Olá", order=0
    )
    response = api.get(f"/api/v1/meetings/{meeting.id}/transcription/")
    assert response.status_code == 200
    assert response.data["segmentos"][0]["texto"] == "Olá"
    edit = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {"version": 1, "segmentos": [{"id": 1, "texto": "Mudança", "inicio": 0, "fim": 1}]},
        format="json",
    )
    assert edit.status_code == 409


@pytest.mark.django_db
def test_minutes_can_be_regenerated_and_queue_retry_recovers(api, user):
    meeting = Meeting.objects.create(
        owner=user,
        title="Ata",
        status=MeetingStatus.ATA_PRONTA,
        minutes_version=1,
    )
    Minutes.objects.create(
        meeting=meeting,
        resumo_executivo="Anterior",
        topicos=[{"titulo": "Registro", "comentario": "Texto"}],
        decisoes=[],
        tarefas=[],
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000, text="Olá", order=0
    )
    with patch("apps.meetings.tasks.generate_minutes.delay", side_effect=RuntimeError("queue")):
        failed = api.post(f"/api/v1/meetings/{meeting.id}/minutes/", {}, format="json")
    assert failed.status_code == 503
    meeting.refresh_from_db()
    assert meeting.error_code == "minutes_queue_unavailable"
    assert api.get(f"/api/v1/meetings/{meeting.id}/transcription/").status_code == 200
    with patch("apps.meetings.tasks.generate_minutes.delay") as enqueue:
        retried = api.post(f"/api/v1/meetings/{meeting.id}/retry/", {}, format="json")
    assert retried.status_code == 202
    enqueue.assert_called_once()
    assert Minutes.objects.get(meeting=meeting).resumo_executivo == "Anterior"


@pytest.mark.django_db
def test_create_meeting_with_date_for_frontend(api):
    created = api.post(
        "/api/v1/meetings/",
        {"title": "Planejamento", "meeting_date": "2026-10-08"},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["meeting_date"] == "2026-10-08"
    listed = api.get("/api/v1/meetings/")
    assert listed.data["results"][0]["meeting_date"] == "2026-10-08"


@pytest.mark.django_db
def test_transcription_changes_mark_existing_minutes_stale(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user,
        title="Ata",
        status=MeetingStatus.ATA_PRONTA,
        transcription_version=1,
        minutes_version=1,
    )
    Minutes.objects.create(
        meeting=meeting,
        resumo_executivo="Resumo",
        topicos=[{"titulo": "Registro", "comentario": "Texto"}],
        decisoes=[],
        tarefas=[],
        reviewed_by=user,
        reviewer_name=user.get_username(),
        reviewed_at=timezone.now(),
    )
    Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    renamed = api.patch(
        f"/api/v1/meetings/{meeting.id}/speakers/A/",
        {"nome": "Ana", "version": 1},
        format="json",
    )
    assert renamed.status_code == 200
    meeting.refresh_from_db()
    assert meeting.minutes_stale is True
    assert meeting.minutes.reviewed_at is None
    assert meeting.minutes_version == 2
    assert api.get(f"/api/v1/meetings/{meeting.id}/").data["minutes_stale"] is True


@pytest.mark.django_db
def test_topic_minutes_can_be_read_edited_and_exported(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Pautas", status=MeetingStatus.ATA_PRONTA, minutes_version=1
    )
    Minutes.objects.create(
        meeting=meeting,
        resumo_executivo="Resumo",
        topicos=[{"titulo": "Planejamento", "comentario": "Equipe discutiu o cronograma."}],
        decisoes=[],
        tarefas=[],
    )
    url = f"/api/v1/meetings/{meeting.id}/minutes/"
    response = api.get(url)
    assert response.status_code == 200
    assert response.data["topicos"][0]["titulo"] == "Planejamento"
    assert "ata" not in response.data
    edited = api.patch(
        url,
        {
            "version": 1,
            "topicos": [{"titulo": "Prazos", "comentario": "Equipe ajustou o cronograma."}],
        },
        format="json",
    )
    assert edited.status_code == 200
    assert edited.data["topicos"][0]["titulo"] == "Prazos"
    assert Minutes.objects.get(meeting=meeting).human_edited is True
    export = tmp_path / "reunioes" / str(meeting.id) / "ata.md"
    assert "### Prazos" in export.read_text(encoding="utf-8")
    invalid = api.patch(
        url,
        {"version": 2, "topicos": [{"titulo": "", "comentario": "Texto"}]},
        format="json",
    )
    assert invalid.status_code == 400


@pytest.mark.django_db
def test_minutes_participants_review_and_edit_invalidation(
    api, user, other_user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Comitê", status=MeetingStatus.ATA_PRONTA, minutes_version=1
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Resumo",
        topicos=[{"titulo": "Pauta", "comentario": "Conversa."}],
        decisoes=[], tarefas=[], participantes=["Ana"],
    )
    url = f"/api/v1/meetings/{meeting.id}/minutes/"
    assert api.get(url).data["revisado_em"] is None
    edited = api.patch(url, {
        "version": 1, "participantes": ["Ana", "Bruno"],
        "decisoes": ["Aprovado"],
        "tarefas": [
            {"descricao": "Enviar relatório", "responsavel": "Bruno", "prazo": "2026-10-21"}
        ],
    }, format="json")
    assert edited.status_code == 200
    assert edited.data["participantes"] == ["Ana", "Bruno"]
    assert edited.data["tarefas"][0]["prazo"] == "2026-10-21"
    review_url = f"{url}review/"
    assert api.post(review_url, {"version": 1}, format="json").status_code == 409
    stranger = APIClient()
    stranger.force_authenticate(user=other_user)
    assert stranger.post(review_url, {"version": 2}, format="json").status_code == 404
    hidden = api.post(
        review_url, {"version": 2}, format="json", HTTP_X_TEST_USER=other_user.username
    )
    # The authenticated owner is still the reviewer; a spoofed header has no effect.
    assert hidden.status_code == 200
    assert hidden.data["revisor"] == user.get_username()
    assert hidden.data["revisado_em"] is not None
    assert api.post(review_url, {"version": 2}, format="json").status_code == 409
    export = tmp_path / "reunioes" / str(meeting.id) / "ata.md"
    assert "Ata revisada por ana" in export.read_text(encoding="utf-8")
    again = api.patch(url, {"version": 3, "decisoes": ["Ajustado"]}, format="json")
    assert again.status_code == 200
    assert again.data["revisado_em"] is None
    assert "Ata não revisada" in export.read_text(encoding="utf-8")
    assert api.patch(url, {"version": 4, "participantes": [""]}, format="json").status_code == 400
    assert api.patch(url, {"version": 2, "topicos": []}, format="json").status_code == 400


@pytest.mark.django_db
def test_delete_meeting_with_segments_hides_it_and_retains_media_during_grace(
    api, user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Apagar", status=MeetingStatus.TRANSCRITO)
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000, text="Olá", order=0
    )
    directory = tmp_path / "reunioes" / str(meeting.id)
    directory.mkdir(parents=True)
    (directory / "audio.mp3").write_bytes(b"audio")
    response = api.delete(f"/api/v1/meetings/{meeting.id}/")
    assert response.status_code == 204
    meeting.refresh_from_db()
    assert meeting.deletion_requested_at is not None
    assert meeting.segments.count() == 1
    assert directory.exists()
    assert api.get(f"/api/v1/meetings/{meeting.id}/").status_code == 404


@pytest.mark.django_db
def test_delete_meeting_rejects_active_processing(api, user):
    meeting = Meeting.objects.create(
        owner=user, title="Processando", status=MeetingStatus.TRANSCREVENDO
    )
    response = api.delete(f"/api/v1/meetings/{meeting.id}/")
    assert response.status_code == 409
    assert Meeting.objects.filter(id=meeting.id).exists()


@pytest.mark.django_db
def test_delete_empty_draft_is_allowed(api, user):
    meeting = Meeting.objects.create(owner=user, title="Rascunho")
    response = api.delete(f"/api/v1/meetings/{meeting.id}/")
    assert response.status_code == 204
    meeting.refresh_from_db()
    assert meeting.deletion_requested_at is not None
    assert api.get(f"/api/v1/meetings/{meeting.id}/").status_code == 404


@pytest.mark.django_db
def test_delete_other_users_meeting_is_denied(api, other_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=other_user, title="Privada", status=MeetingStatus.TRANSCRITO
    )
    directory = tmp_path / "reunioes" / str(meeting.id)
    directory.mkdir(parents=True)
    (directory / "audio.mp3").write_bytes(b"audio")
    response = api.delete(f"/api/v1/meetings/{meeting.id}/")
    assert response.status_code == 404
    assert Meeting.objects.filter(id=meeting.id).exists()
    assert directory.exists()
