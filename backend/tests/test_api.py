import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.meetings.models import Meeting, MeetingStatus, Segment, Speaker


@pytest.mark.django_db
def test_meetings_are_private_and_paginated(api, user, other_user):
    own = Meeting.objects.create(owner=user, title="Pauta A")
    Meeting.objects.create(owner=other_user, title="Segredo")
    response = api.get("/api/v1/meetings/?search=Pauta")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(own.id)
    hidden = api.get(f"/api/v1/meetings/{Meeting.objects.get(owner=other_user).id}/")
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_owner_can_rename_meeting_but_other_user_cannot(api, user, other_user):
    own = Meeting.objects.create(owner=user, title="Nome antigo")
    foreign = Meeting.objects.create(owner=other_user, title="Privada")
    path = f"/api/v1/meetings/{own.id}/"
    renamed = api.patch(path, {"title": "  Nome novo  "}, format="json")
    assert renamed.status_code == 200
    own.refresh_from_db()
    assert own.title == "Nome novo"
    assert api.patch(path, {"title": "   "}, format="json").status_code == 400
    assert api.patch(
        f"/api/v1/meetings/{foreign.id}/", {"title": "Outra"}, format="json"
    ).status_code == 404


@pytest.mark.django_db
def test_stuck_minutes_generation_is_visible_and_retryable(api, user):
    old_job = uuid.uuid4()
    meeting = Meeting.objects.create(
        owner=user, title="Ata travada", status=MeetingStatus.GERANDO_ATA,
        job_id=old_job, job_claimed=True,
        job_started_at=timezone.now() - timedelta(minutes=11),
    )
    detail = api.get(f"/api/v1/meetings/{meeting.id}/")
    assert detail.data["minutes_stuck"] is True
    with patch("apps.meetings.tasks.generate_minutes.delay"):
        retried = api.post(f"/api/v1/meetings/{meeting.id}/retry/")
    assert retried.status_code == 202
    meeting.refresh_from_db()
    assert meeting.job_id != old_job
    assert meeting.status == MeetingStatus.GERANDO_ATA


@pytest.mark.django_db
def test_minutes_status_is_lightweight_and_exposes_stuck_state(api, user, other_user):
    old = Meeting.objects.create(
        owner=user, title="Ata travada", status=MeetingStatus.GERANDO_ATA,
        job_started_at=timezone.now() - timedelta(minutes=11),
    )
    current = Meeting.objects.create(
        owner=user, title="Ata em andamento", status=MeetingStatus.GERANDO_ATA,
        job_started_at=timezone.now(),
    )
    with CaptureQueriesContext(connection) as queries:
        old_response = api.get(f"/api/v1/meetings/{old.id}/status/")
    assert old_response.status_code == 200
    assert old_response.data["minutes_stuck"] is True
    assert "segmentos" not in old_response.data
    assert "title" not in old_response.data
    assert not any(
        "meetings_segment" in query["sql"].lower()
        or "meetings_speaker" in query["sql"].lower()
        for query in queries
    )
    assert not AuditEvent.objects.filter(action="transcription_viewed").exists()
    current_response = api.get(f"/api/v1/meetings/{current.id}/status/")
    assert current_response.data["minutes_stuck"] is False
    api.force_authenticate(user=other_user)
    assert api.get(f"/api/v1/meetings/{old.id}/status/").status_code == 404


@pytest.mark.django_db
def test_upload_stages_without_consent_and_owner_only(api, user, other_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Teste")
    foreign = Meeting.objects.create(owner=other_user, title="Privado")
    file = SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100, content_type="audio/mpeg")
    with patch("apps.meetings.storage.probe_audio"):
        response = api.post(
            f"/api/v1/meetings/{meeting.id}/upload/",
            {"file": file, "consent_confirmed": "false"},
            format="multipart",
        )
    assert response.status_code == 201
    meeting.refresh_from_db()
    assert meeting.staged_at is not None and meeting.job_id is None
    assert api.post(f"/api/v1/meetings/{meeting.id}/discard-upload/").status_code == 204
    meeting = Meeting.objects.create(owner=user, title="Teste imediato")
    file = SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100, content_type="audio/mpeg")
    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.views.processing.duration_seconds", return_value=60),
        patch("apps.meetings.transcription_jobs.enqueue_transcription"),
    ):
        response = api.post(
            f"/api/v1/meetings/{meeting.id}/upload/",
            {"file": file, "consent_confirmed": "true"},
            format="multipart",
        )
    assert response.status_code == 202
    meeting.refresh_from_db()
    assert meeting.consent_confirmed_at is not None
    assert meeting.original_path.endswith("original.mp3")
    foreign_file = SimpleUploadedFile("clip.mp3", b"ID3data")
    hidden = api.post(
        f"/api/v1/meetings/{foreign.id}/upload/",
        {"file": foreign_file, "consent_confirmed": "true"},
        format="multipart",
    )
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_upload_rejects_disguised_content(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Teste")
    file = SimpleUploadedFile("clip.mp3", b"not an mp3")
    response = api.post(
        f"/api/v1/meetings/{meeting.id}/upload/",
        {"file": file, "consent_confirmed": "true"},
        format="multipart",
    )
    assert response.status_code == 400
    assert not (tmp_path / "reunioes" / str(meeting.id) / "original.mp3").exists()


@pytest.mark.django_db
def test_transcription_edit_and_speaker_merge_are_versioned(api, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Teste", status=MeetingStatus.TRANSCRITO, transcription_version=1
    )
    a = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    b = Speaker.objects.create(meeting=meeting, code="B", name="Pessoa 2")
    segment = Segment.objects.create(
        meeting=meeting, speaker=a, start_ms=0, end_ms=1000, text="Olá", order=0
    )
    Segment.objects.create(
        meeting=meeting, speaker=b, start_ms=1000, end_ms=2000, text="Bom dia", order=1
    )
    rename = api.patch(
        f"/api/v1/meetings/{meeting.id}/speakers/A/", {"nome": "Ana", "version": 1}, format="json"
    )
    assert rename.status_code == 200
    stale = api.patch(
        f"/api/v1/meetings/{meeting.id}/speakers/A/", {"nome": "Outra", "version": 1}, format="json"
    )
    assert stale.status_code == 409
    merged = api.post(
        f"/api/v1/meetings/{meeting.id}/speakers/merge/",
        {"source": "B", "target": "A", "version": 2},
        format="json",
    )
    assert merged.status_code == 200
    assert set(meeting.segments.values_list("speaker__code", flat=True)) == {"A"}
    edit = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {
            "version": 3,
            "segmentos": [{"id": segment.id, "texto": "Olá, equipe", "inicio": 0, "fim": 1.2}],
        },
        format="json",
    )
    assert edit.status_code == 200
    assert edit.data["segmentos"][0]["texto"] == "Olá, equipe"
    download = api.get(f"/api/v1/meetings/{meeting.id}/transcription/download/?format=md")
    assert download.status_code == 200
    assert "Ana" in b"".join(download.streaming_content).decode("utf-8")


@pytest.mark.django_db
def test_batch_speaker_merge_is_atomic_and_versioned(api, user, other_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Vários falantes", status=MeetingStatus.TRANSCRITO,
        transcription_version=1,
    )
    speakers = {
        code: Speaker.objects.create(meeting=meeting, code=code, name=name)
        for code, name in (("A", "Ana"), ("B", "Bruno"), ("C", "Carla"))
    }
    for order, code in enumerate(("A", "B", "C")):
        Segment.objects.create(
            meeting=meeting, speaker=speakers[code], start_ms=order * 1000,
            end_ms=(order + 1) * 1000, text=code, order=order,
        )
    url = f"/api/v1/meetings/{meeting.id}/speakers/merge-batch/"
    invalid = api.post(url, {"sources": ["B", "X"], "target": "A", "version": 1}, format="json")
    assert invalid.status_code in (400, 404)
    assert set(meeting.segments.values_list("speaker__code", flat=True)) == {"A", "B", "C"}
    assert meeting.speakers.filter(merged_into__isnull=True).count() == 3
    success = api.post(url, {"sources": ["B", "C"], "target": "A", "version": 1}, format="json")
    assert success.status_code == 200
    assert success.data["version"] == 2
    assert set(meeting.segments.values_list("speaker__code", flat=True)) == {"A"}
    merged_codes = set(
        meeting.speakers.filter(merged_into=speakers["A"]).values_list("code", flat=True)
    )
    assert merged_codes == {"B", "C"}
    stale = api.post(url, {"sources": ["B"], "target": "A", "version": 1}, format="json")
    assert stale.status_code == 409
    foreign = Meeting.objects.create(
        owner=other_user, title="Privada", status=MeetingStatus.TRANSCRITO
    )
    assert api.post(
        f"/api/v1/meetings/{foreign.id}/speakers/merge-batch/",
        {"sources": ["B"], "target": "A", "version": 0}, format="json",
    ).status_code == 404


@pytest.mark.django_db
def test_session_login_requires_csrf_and_logout(user):
    client = Client(enforce_csrf_checks=True)
    refused = client.post(
        "/api/v1/login/",
        data='{"username":"ana","password":"Strong-Test-Password-123"}',
        content_type="application/json",
    )
    assert refused.status_code == 403
    csrf = client.get("/api/v1/csrf/")
    token = csrf.cookies["csrftoken"].value
    logged = client.post(
        "/api/v1/login/",
        data='{"username":"ana","password":"Strong-Test-Password-123"}',
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert logged.status_code == 200
    assert client.get("/api/v1/session/").status_code == 200
    # Django rotates the CSRF token when a session is created.
    token = logged.cookies["csrftoken"].value
    logged_out = client.post("/api/v1/logout/", HTTP_X_CSRFTOKEN=token)
    assert logged_out.status_code == 200
    assert client.get("/api/v1/session/").status_code == 401


@pytest.mark.django_db
def test_status_is_private(api, user, other_user):
    meeting = Meeting.objects.create(owner=other_user, title="Privado", job_id=uuid.uuid4())
    assert api.get(f"/api/v1/meetings/{meeting.id}/status/").status_code == 404


@pytest.mark.django_db
def test_minutes_request_is_idempotent_while_queued(api, user):
    meeting = Meeting.objects.create(owner=user, title="Ata", status=MeetingStatus.TRANSCRITO)
    with patch("apps.meetings.tasks.generate_minutes.delay") as enqueue:
        first = api.post(f"/api/v1/meetings/{meeting.id}/minutes/", {}, format="json")
        second = api.post(f"/api/v1/meetings/{meeting.id}/minutes/", {}, format="json")
    assert first.status_code == 202
    assert second.status_code == 409
    enqueue.assert_called_once()


@pytest.mark.django_db
def test_minutes_requests_have_no_hourly_limit(api, user):
    meetings = [
        Meeting.objects.create(owner=user, title=f"Ata {number}", status=MeetingStatus.TRANSCRITO)
        for number in range(5)
    ]
    with patch("apps.meetings.tasks.generate_minutes.delay"):
        responses = [
            api.post(f"/api/v1/meetings/{meeting.id}/minutes/", {}, format="json")
            for meeting in meetings
        ]
    assert [response.status_code for response in responses] == [202] * 5


@pytest.mark.django_db
def test_correction_suggestions_never_edit_transcription_without_acceptance(api, user):
    meeting = Meeting.objects.create(
        owner=user, title="Revisão", status=MeetingStatus.TRANSCRITO, transcription_version=1
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    segment = Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000,
        text="A Aná apresentou o projeto.", order=0,
    )

    class FakeCorrection:
        def suggest(self, segments):
            assert segments == [{"id": segment.id, "texto": segment.text}]
            return [{
                "segmento_id": segment.id,
                "texto_sugerido": "A Ana apresentou o projeto.",
                "motivo": "Nome mencionado em outras falas.",
            }]

    with patch("apps.meetings.tasks.analyze_transcription_corrections.delay") as enqueue:
        response = api.post(
            f"/api/v1/meetings/{meeting.id}/correction-suggestions/",
            {"version": 1}, format="json",
        )
    assert response.status_code == 202
    enqueue.assert_called_once()
    with patch("apps.meetings.tasks.analyze_transcription_corrections.delay") as duplicate_enqueue:
        pending = api.post(
            f"/api/v1/meetings/{meeting.id}/correction-suggestions/",
            {"version": 1}, format="json",
        )
    assert pending.status_code == 202
    assert pending.data["job_id"] == response.data["job_id"]
    duplicate_enqueue.assert_not_called()
    from apps.meetings.tasks import analyze_transcription_corrections

    with patch("apps.meetings.jobs.corrections.correction_provider", return_value=FakeCorrection()):
        assert analyze_transcription_corrections(
            str(meeting.id), 1, response.data["job_id"]
        ) == "ready"
    finished = api.get(
        f"/api/v1/meetings/{meeting.id}/correction-suggestions/",
        {"job_id": response.data["job_id"]},
    )
    assert finished.status_code == 200
    assert finished.data["sugestoes"][0]["segmento_id"] == segment.id
    assert finished.data["sugestoes"][0]["texto_original"] == segment.text
    with patch("apps.meetings.tasks.analyze_transcription_corrections.delay") as extra_enqueue:
        repeated = api.post(
            f"/api/v1/meetings/{meeting.id}/correction-suggestions/",
            {"version": 1}, format="json",
        )
    assert repeated.status_code == 200
    assert repeated.data["job_id"] == response.data["job_id"]
    extra_enqueue.assert_not_called()
    segment.refresh_from_db()
    meeting.refresh_from_db()
    assert segment.text == "A Aná apresentou o projeto."
    assert meeting.transcription_version == 1


@pytest.mark.django_db
def test_correction_suggestions_reject_foreign_meeting_and_stale_version(api, user, other_user):
    foreign = Meeting.objects.create(
        owner=other_user, title="Privada", status=MeetingStatus.TRANSCRITO
    )
    own = Meeting.objects.create(
        owner=user, title="Minha", status=MeetingStatus.TRANSCRITO, transcription_version=2
    )
    with patch("apps.meetings.tasks.analyze_transcription_corrections.delay") as enqueue:
        hidden = api.post(
            f"/api/v1/meetings/{foreign.id}/correction-suggestions/",
            {"version": 0}, format="json",
        )
        stale = api.post(
            f"/api/v1/meetings/{own.id}/correction-suggestions/",
            {"version": 1}, format="json",
        )
    assert hidden.status_code == 404
    assert stale.status_code == 409
    enqueue.assert_not_called()
