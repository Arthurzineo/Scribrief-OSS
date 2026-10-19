from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.cache import cache

from apps.audit.models import AuditEvent
from apps.meetings.correction_jobs import result_key
from apps.meetings.job_state import (
    JobCancelled,
    accept_job,
    cancel_job,
    ensure_not_cancelled,
    start_job,
)
from apps.meetings.models import (
    Meeting,
    MeetingStatus,
    ProcessingJob,
    Segment,
    Speaker,
    SpeakerAnalysis,
)
from apps.meetings.tasks import analyze_speaker_reconciliation, analyze_transcription_corrections


@pytest.mark.django_db
def test_admin_can_cancel_only_one_job_and_records_source_ip(api, user, other_user):
    meeting = Meeting.objects.create(owner=other_user, title="Longa")
    other_meeting = Meeting.objects.create(owner=user, title="Outra")
    job_id, other_id = uuid4(), uuid4()
    meeting.job_id = job_id
    meeting.status = MeetingStatus.TRANSCREVENDO
    meeting.save(update_fields=["job_id", "status"])
    accept_job(meeting, job_id, "transcription", 7200)
    accept_job(other_meeting, other_id, "transcription", 120)
    start_job(job_id)
    user.is_staff = True
    user.save(update_fields=["is_staff"])

    api.force_authenticate(user=other_user)
    assert api.post(f"/api/admin/jobs/{job_id}/cancel/").status_code == 403
    api.force_authenticate(user=user)
    assert api.post(
        f"/api/admin/jobs/{job_id}/cancel/", {"current_password": "wrong"}
    ).status_code == 403
    response = api.post(
        f"/api/admin/jobs/{job_id}/cancel/",
        {"current_password": "Strong-Test-Password-123"},
        format="json", REMOTE_ADDR="203.0.113.41",
    )
    assert response.status_code == 200
    assert response.data["status"] == "cancelled"
    meeting.refresh_from_db()
    assert meeting.status == MeetingStatus.ERRO
    assert meeting.error_code == "job_cancelled"
    assert ProcessingJob.objects.get(id=other_id).status == "queued"
    with pytest.raises(JobCancelled):
        ensure_not_cancelled(job_id)
    ensure_not_cancelled(other_id)
    event = AuditEvent.objects.get(action="job_cancel_requested")
    assert event.client_ip == "203.0.113.41"
    assert event.subject_user == other_user

    summary = api.get("/api/admin/jobs/summary/")
    assert summary.status_code == 200
    assert summary.data["totals"]["requests"] == 2
    assert summary.data["totals"]["uploaded_media_seconds"] == Decimal("7320")
    assert api.get("/api/admin/jobs/", {"user_id": other_user.pk}).data["count"] == 1


@pytest.mark.django_db
def test_completed_job_is_not_cancelled(api, user):
    meeting = Meeting.objects.create(owner=user, title="Feita")
    job_id = uuid4()
    accept_job(meeting, job_id, "transcription", 60)
    ProcessingJob.objects.filter(pk=job_id).update(status="completed")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    response = api.post(
        f"/api/admin/jobs/{job_id}/cancel/",
        {"current_password": "Strong-Test-Password-123"}, format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "completed"
    assert ProcessingJob.objects.get(pk=job_id).cancel_requested_at is None


@pytest.mark.django_db
def test_worker_health_is_admin_only_and_bounded(api, user, other_user):
    api.force_authenticate(user=other_user)
    assert api.get("/api/admin/jobs/worker-health/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    with patch("apps.admin_panel.views.jobs.celery_app.control.inspect") as inspect:
        inspect.return_value.ping.return_value = {"celery@worker": {"ok": "pong"}}
        response = api.get("/api/admin/jobs/worker-health/")
    assert response.status_code == 200
    assert response.data["responding_workers"] == 1
    assert response.data["status"] == "responding"
    inspect.assert_called_once_with(timeout=1.5)


@pytest.mark.django_db
def test_cancellation_during_speaker_analysis_cannot_publish_ready(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "audio.mp3").write_bytes(b"audio")
    meeting = Meeting.objects.create(
        owner=user, title="Vozes", status=MeetingStatus.TRANSCRITO,
        audio_path="audio.mp3", transcription_version=1,
    )
    job_id = uuid4()
    accept_job(meeting, job_id, "speaker_reconciliation")
    analysis = SpeakerAnalysis.objects.create(
        meeting=meeting, job_id=job_id, version=1, status="processing",
    )

    def cancel_during_analysis(_segments):
        cancel_job(job_id)
        return []

    with patch(
        "apps.meetings.jobs.speakers.select_voice_samples", side_effect=cancel_during_analysis
    ):
        assert analyze_speaker_reconciliation(str(meeting.id), 1, str(job_id)) == "cancelled"
    analysis.refresh_from_db()
    assert analysis.status == "error"
    assert ProcessingJob.objects.get(pk=job_id).status == "cancelled"


@pytest.mark.django_db
def test_cancellation_during_correction_cannot_publish_suggestions(user):
    meeting = Meeting.objects.create(
        owner=user, title="Correção", status=MeetingStatus.TRANSCRITO,
        transcription_version=1,
    )
    job_id = uuid4()
    accept_job(meeting, job_id, "correction")
    speaker = Speaker.objects.create(meeting=meeting, code="A", name="Ana")
    Segment.objects.create(
        meeting=meeting, speaker=speaker, start_ms=0, end_ms=1000,
        text="Teste", order=0,
    )
    cache.set(result_key(str(job_id)), {"status": "processing"})

    def cancel_during_provider(_segments):
        cancel_job(job_id)
        return []

    with patch("apps.meetings.jobs.corrections.correction_provider") as provider:
        provider.return_value.suggest.side_effect = cancel_during_provider
        assert analyze_transcription_corrections(str(meeting.id), 1, str(job_id)) == "cancelled"
    assert cache.get(result_key(str(job_id)))["status"] == "error"
    assert ProcessingJob.objects.get(pk=job_id).status == "cancelled"


@pytest.mark.django_db
def test_job_dashboard_filters_and_pages_representative_queue(api, user, other_user):
    meeting = Meeting.objects.create(owner=other_user, title="Carga")
    ProcessingJob.objects.bulk_create([
        ProcessingJob(
            id=uuid4(), meeting_id=meeting.pk, sector=meeting.sector,
            requested_by=other_user, kind="transcription",
            status="running" if index < 3 else "completed",
            media_duration_seconds=Decimal("300.00"),
        ) for index in range(120)
    ])
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    params = {"user_id": other_user.pk, "sector_id": meeting.sector_id}
    response = api.get("/api/admin/jobs/", params)
    assert response.status_code == 200 and response.data["count"] == 120
    assert response.data["next"] is not None
    running = api.get("/api/admin/jobs/summary/", {**params, "status": "running"})
    assert running.data["totals"]["running"] == 3
    assert running.data["totals"]["uploaded_media_seconds"] == Decimal("900")
    all_jobs = api.get("/api/admin/jobs/summary/", params)
    assert all_jobs.data["totals"]["requests"] == 120
    assert all_jobs.data["totals"]["uploaded_media_seconds"] == Decimal("36000")


@pytest.mark.django_db
def test_admin_cancel_rolls_back_when_critical_audit_fails(api, user, other_user):
    meeting = Meeting.objects.create(owner=other_user, title="Rollback")
    job_id = uuid4()
    accept_job(meeting, job_id, "correction")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    with patch("apps.admin_panel.views.jobs.record_audit", side_effect=RuntimeError("audit down")):
        with pytest.raises(RuntimeError):
            api.post(
                f"/api/admin/jobs/{job_id}/cancel/",
                {"current_password": "Strong-Test-Password-123"}, format="json",
            )
    job = ProcessingJob.objects.get(pk=job_id)
    assert job.status == "queued" and job.cancel_requested_at is None
