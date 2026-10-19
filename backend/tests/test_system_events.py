"""System diagnostics are distinct from user audit and contain no payloads."""

import uuid
from datetime import timedelta

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone

from apps.audit.middleware import MutationAuditMiddleware
from apps.audit.models import AuditEvent, SystemEvent, record_audit
from apps.audit.retention import prune_expired_audit_events
from apps.meetings.job_state import accept_job, finish_job, start_job
from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_job_lifecycle_persists_separate_system_events(user):
    meeting = Meeting.objects.create(owner=user, title="Trabalho")
    job_id = uuid.uuid4()

    accept_job(meeting, job_id, "transcription", 60)
    start_job(job_id, "extracting_audio")
    finish_job(job_id, "failed", "processing_failed")

    events = list(SystemEvent.objects.filter(job_id=job_id).order_by("created_at", "id"))
    assert [event.event_code for event in events] == [
        "job_queued", "job_started", "job_failed",
    ]
    assert all(event.meeting_id == meeting.id for event in events)
    assert all(event.sector_id == user.membership.sector_id for event in events)
    assert all(event.user_id == user.id for event in events)
    assert events[-1].error_code == "processing_failed"
    assert events[-1].stage == "extracting_audio"


@pytest.mark.django_db
def test_system_events_are_staff_only_and_have_90_day_retention(api, user, other_user):
    old = SystemEvent.objects.create(component="worker", event_code="job_failed", severity="error")
    recent = SystemEvent.objects.create(component="worker", event_code="job_completed")
    SystemEvent.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=91)
    )
    assert api.get("/api/admin/system-events/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    response = api.get("/api/admin/system-events/?event_code=job_completed")
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["event_code"] == "job_completed"
    result = prune_expired_audit_events(now=timezone.now())
    assert result["system_deleted"] == 1
    assert not SystemEvent.objects.filter(pk=old.pk).exists()
    assert SystemEvent.objects.filter(pk=recent.pk).exists()


@pytest.mark.django_db
def test_http_5xx_has_correlated_safe_system_event(user):
    request = RequestFactory().post(
        "/api/v1/meetings/", data="secret body", content_type="text/plain",
        REMOTE_ADDR="203.0.113.29",
    )
    request.user = user
    response = MutationAuditMiddleware(lambda unused: HttpResponse(status=503))(request)

    assert response.status_code == 503
    event = SystemEvent.objects.get(event_code="http_5xx")
    assert event.http_status == 503
    assert event.user == user
    assert event.client_ip == "203.0.113.29"
    assert str(event.request_id) == response["X-Request-ID"]
    assert "secret body" not in str(event.__dict__)


@pytest.mark.django_db
def test_account_deletion_keeps_nonsecret_account_and_sector_ids(user):
    actor_id = user.pk
    sector_id = user.membership.sector_id
    audit = record_audit(user, "login", subject_user=user)
    system = SystemEvent.objects.create(
        component="worker", event_code="job_failed", user=user,
        user_id_snapshot=actor_id, sector_id=sector_id,
        sector_id_snapshot=sector_id,
    )

    user.delete()
    audit.refresh_from_db()
    system.refresh_from_db()
    assert audit.actor_id is None
    assert audit.actor_id_snapshot == actor_id
    assert audit.subject_user_id_snapshot == actor_id
    assert audit.sector_id_snapshot == sector_id
    assert system.user_id is None
    assert system.user_id_snapshot == actor_id
    assert AuditEvent.objects.filter(actor_id_snapshot=actor_id).exists()
