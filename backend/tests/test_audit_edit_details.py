"""Audit must identify every edited line/field without duplicating meeting content."""

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.change_tracking import fingerprint
from apps.audit.models import AuditEvent, SystemEvent
from apps.meetings.models import (
    Meeting,
    MeetingStatus,
    Minutes,
    MonthlyMediaUsage,
    ProcessingJob,
    Segment,
    Speaker,
)
from apps.meetings.services.transcription import edit_segments


@pytest.mark.django_db
def test_transcription_edit_records_line_version_and_only_fingerprints(
    api, user, tmp_path, settings
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Auditável", status=MeetingStatus.TRANSCRITO,
        transcription_version=3,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, text="Primeira frase confidencial",
        order=0, start_ms=0, end_ms=1000,
    )
    second = Segment.objects.create(
        meeting=meeting, speaker=speaker, text="Texto anterior confidencial",
        order=1, start_ms=1000, end_ms=2000,
        original_text="Texto anterior confidencial", original_start_ms=1000,
        original_end_ms=2000, original_speaker_code="A", original_source="ai_generation",
    )

    response = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {"version": 3, "segmentos": [{
            "id": second.id, "texto": "Texto novo confidencial", "inicio": 1, "fim": 2.5,
        }]},
        format="json", REMOTE_ADDR="203.0.113.15",
    )

    assert response.status_code == 200
    updated_line = next(row for row in response.data["segmentos"] if row["id"] == second.id)
    assert updated_line["original"]["texto"] == "Texto anterior confidencial"
    assert updated_line["original"]["proveniencia"] == "ai_generation"
    event = AuditEvent.objects.get(action="transcription_edited")
    assert event.actor == user
    assert event.client_ip == "203.0.113.15"
    assert event.details["version_before"] == 3
    assert event.details["version_after"] == 4
    assert event.details["changes"][0]["segment_id"] == second.id
    assert event.details["changes"][0]["line"] == 2
    assert set(event.details["changes"][0]["fields"]) == {"text", "end_ms"}
    assert event.details["changes"][0]["original_hash"] == fingerprint(
        "Texto anterior confidencial"
    )
    assert event.details["changes"][0]["current_hash"] == fingerprint(
        "Texto novo confidencial"
    )
    assert event.details["changes"][0]["matches_original"] is False
    second.refresh_from_db()
    assert second.original_text == "Texto anterior confidencial"
    assert second.text == "Texto novo confidencial"
    assert "Texto anterior confidencial" not in str(event.details)
    assert "Texto novo confidencial" not in str(event.details)

    again = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {"version": 4, "segmentos": [{
            "id": second.id, "texto": "Terceiro texto confidencial", "inicio": 1, "fim": 2.5,
        }]}, format="json",
    )
    assert again.status_code == 200
    second.refresh_from_db()
    assert second.original_text == "Texto anterior confidencial"
    assert second.text == "Terceiro texto confidencial"
    latest = AuditEvent.objects.filter(action="transcription_edited").latest("id")
    assert latest.details["changes"][0]["original_hash"] == fingerprint(
        "Texto anterior confidencial"
    )
    assert latest.details["changes"][0]["fields"]["text"]["before"] == fingerprint(
        "Texto novo confidencial"
    )


@pytest.mark.django_db
def test_minutes_edit_records_nested_topic_field_and_not_text(api, user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Auditável", status=MeetingStatus.ATA_PRONTA,
        minutes_version=2,
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Resumo privado",
        topicos=[{"titulo": "Café", "comentario": "Comentário antigo secreto"}],
        decisoes=[], tarefas=[], participantes=[],
    )

    response = api.patch(
        f"/api/v1/meetings/{meeting.id}/minutes/",
        {"version": 2, "topicos": [
            {"titulo": "Café", "comentario": "Comentário novo secreto"},
        ]},
        format="json", REMOTE_ADDR="203.0.113.16",
    )

    assert response.status_code == 200
    event = AuditEvent.objects.get(action="minutes_edited")
    assert event.client_ip == "203.0.113.16"
    assert event.details["version_before"] == 2
    assert event.details["version_after"] == 3
    assert event.details["changes"][0]["path"] == "topicos[0].comentario"
    assert event.details["changes"][0]["before"] != event.details["changes"][0]["after"]
    assert "Comentário antigo secreto" not in str(event.details)
    assert "Comentário novo secreto" not in str(event.details)


@pytest.mark.django_db
def test_speaker_and_meeting_renames_are_identifiable_without_copying_names(
    api, user, tmp_path, settings
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Nome antigo privado", status=MeetingStatus.TRANSCRITO,
        transcription_version=1,
    )
    Speaker.objects.create(meeting=meeting, code="A", name="Pessoa anterior")
    response = api.patch(
        f"/api/v1/meetings/{meeting.id}/speakers/A/",
        {"nome": "Pessoa nova", "version": 1}, format="json", REMOTE_ADDR="203.0.113.18",
    )
    assert response.status_code == 200
    speaker_event = AuditEvent.objects.get(action="speaker_renamed")
    assert speaker_event.client_ip == "203.0.113.18"
    assert speaker_event.details["speaker_code"] == "A"
    assert speaker_event.details["name_before"] != speaker_event.details["name_after"]
    assert "Pessoa nova" not in str(speaker_event.details)

    response = api.patch(
        f"/api/v1/meetings/{meeting.id}/", {"title": "Nome novo privado"},
        format="json", REMOTE_ADDR="203.0.113.19",
    )
    assert response.status_code == 200
    meeting_event = AuditEvent.objects.get(action="meeting_renamed")
    assert meeting_event.client_ip == "203.0.113.19"
    assert meeting_event.details["title_before"] != meeting_event.details["title_after"]
    assert "Nome antigo privado" not in str(meeting_event.details)
    assert "Nome novo privado" not in str(meeting_event.details)


@pytest.mark.django_db
def test_account_update_has_semantic_audit_with_no_email_copy(client, user):
    client.force_login(user)
    response = client.patch(
        "/api/v1/account/", data='{"email":"private@example.test"}',
        content_type="application/json", REMOTE_ADDR="203.0.113.20",
    )
    assert response.status_code == 200
    event = AuditEvent.objects.get(action="account_updated")
    assert event.actor == user
    assert event.client_ip == "203.0.113.20"
    assert event.details["changes"][0]["path"] == "email"
    assert "private@example.test" not in str(event.details)


@pytest.mark.django_db
def test_transcript_edit_rolls_back_if_critical_audit_write_fails(user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Privada", status=MeetingStatus.TRANSCRITO,
        transcription_version=1,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    segment = Segment.objects.create(
        meeting=meeting, speaker=speaker, text="Texto original", order=0,
        start_ms=0, end_ms=1000,
    )
    with patch("apps.meetings.services.transcription.record_audit", side_effect=OSError):
        with pytest.raises(OSError):
            edit_segments(
                meeting, [{"id": segment.id, "texto": "Mudança", "inicio": 0, "fim": 1}],
                1, user,
            )
    segment.refresh_from_db()
    meeting.refresh_from_db()
    assert segment.text == "Texto original"
    assert meeting.transcription_version == 1


@pytest.mark.django_db
def test_upload_audit_failure_rolls_back_db_and_removes_file(api, user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Upload")
    file = SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100)
    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.views.processing.duration_seconds", return_value=60),
        patch("apps.meetings.views.processing.record_audit", side_effect=OSError),
    ):
        with pytest.raises(OSError):
            api.post(
                f"/api/v1/meetings/{meeting.id}/upload/",
                {"file": file, "consent_confirmed": "true"}, format="multipart",
            )
    meeting.refresh_from_db()
    assert not meeting.original_path
    assert MonthlyMediaUsage.objects.count() == 0
    assert not (tmp_path / "reunioes" / str(meeting.id) / "original.mp3").exists()


@pytest.mark.django_db
def test_upload_dispatch_failure_has_matching_business_and_system_outcome(
    api, user, tmp_path, settings,
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(owner=user, title="Upload")
    file = SimpleUploadedFile("clip.mp3", b"ID3" + b"x" * 100)
    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.views.processing.duration_seconds", return_value=60),
        patch("apps.meetings.transcription_jobs.enqueue_transcription",
              side_effect=ConnectionError),
    ):
        response = api.post(
            f"/api/v1/meetings/{meeting.id}/upload/",
            {"file": file, "consent_confirmed": "true"}, format="multipart",
        )
    assert response.status_code == 503
    meeting.refresh_from_db()
    assert meeting.status == MeetingStatus.ERRO
    job = ProcessingJob.objects.get(id=meeting.job_id)
    assert job.status == "failed"
    assert MonthlyMediaUsage.objects.get(user_id_snapshot=user.pk).used_seconds == 60
    assert AuditEvent.objects.filter(
        target_id=meeting.id, action="upload_dispatch_failed", outcome="failed",
    ).exists()
    assert SystemEvent.objects.filter(job_id=job.id, event_code="job_failed").exists()


@pytest.mark.django_db
def test_multiple_transcription_lines_are_audited_and_foreign_edit_is_not(
    api, user, other_user, tmp_path, settings,
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Privada", status=MeetingStatus.TRANSCRITO,
        transcription_version=2,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    lines = [Segment.objects.create(
        meeting=meeting, speaker=speaker, text=f"Linha {index}", order=index,
        start_ms=index * 1000, end_ms=(index + 1) * 1000,
    ) for index in range(2)]
    changes = [
        {"id": segment.id, "texto": f"Novo {index}",
         "inicio": index, "fim": index + 1}
        for index, segment in enumerate(lines)
    ]
    response = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {"version": 2, "segmentos": changes}, format="json",
    )
    assert response.status_code == 200
    event = AuditEvent.objects.get(action="transcription_edited")
    assert [row["line"] for row in event.details["changes"]] == [1, 2]
    assert all(list(row["fields"]) == ["text"] for row in event.details["changes"])

    api.force_authenticate(user=other_user)
    denied = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {"version": 3, "segmentos": changes}, format="json",
    )
    assert denied.status_code == 404
    assert AuditEvent.objects.filter(action="transcription_edited").count() == 1


@pytest.mark.django_db
def test_noop_transcription_patch_is_logged_without_version_change(api, user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Sem mudança", status=MeetingStatus.TRANSCRITO,
        transcription_version=4,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    segment = Segment.objects.create(
        meeting=meeting, speaker=speaker, text="Mesmo texto", order=0,
        start_ms=0, end_ms=1000,
    )
    response = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {"version": 4, "segmentos": [{
            "id": segment.id, "texto": "Mesmo texto", "inicio": 0, "fim": 1,
        }]}, format="json",
    )
    assert response.status_code == 200
    meeting.refresh_from_db()
    assert meeting.transcription_version == 4
    assert AuditEvent.objects.filter(
        action="transcription_edit_noop", target_id=meeting.id,
    ).exists()


@pytest.mark.django_db
def test_unverified_manual_segment_uses_honest_first_edit_baseline(api, user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Legado", status=MeetingStatus.TRANSCRITO,
        transcription_version=1,
    )
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    segment = Segment.objects.create(
        meeting=meeting, speaker=speaker, text="Valor já presente", order=0,
        start_ms=0, end_ms=1000,
    )
    response = api.patch(
        f"/api/v1/meetings/{meeting.id}/transcription/",
        {"version": 1, "segmentos": [{
            "id": segment.id, "texto": "Valor editado", "inicio": 0, "fim": 1,
        }]}, format="json",
    )
    assert response.status_code == 200
    segment.refresh_from_db()
    assert segment.original_text == "Valor já presente"
    assert segment.original_source == "first_edit_baseline"
    event = AuditEvent.objects.get(action="transcription_edited")
    assert event.details["changes"][0]["original_source"] == "first_edit_baseline"
