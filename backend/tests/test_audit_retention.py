from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from celery.schedules import crontab
from django.core.cache import cache
from django.utils import timezone

from apps.audit.models import AIUsageEvent, AuditEvent
from apps.audit.retention import prune_expired_audit_events
from config.celery import app as celery_app


@pytest.mark.django_db
def test_90_day_retention_removes_only_expired_audit_events(user):
    now = timezone.now()
    old = AuditEvent.objects.create(actor=user, action="old", outcome="success")
    boundary = AuditEvent.objects.create(actor=user, action="boundary", outcome="success")
    recent = AuditEvent.objects.create(actor=user, action="recent", outcome="success")
    AuditEvent.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=90, seconds=1))
    AuditEvent.objects.filter(pk=boundary.pk).update(created_at=now - timedelta(days=90))
    AuditEvent.objects.filter(pk=recent.pk).update(created_at=now - timedelta(days=89))
    usage = AIUsageEvent.objects.create(
        sector=user.membership.sector, requested_by=user, meeting_id=uuid4(),
        operation="minutes", model="gpt-6-luna", key_version=1,
    )
    AIUsageEvent.objects.filter(pk=usage.pk).update(created_at=now - timedelta(days=200))

    result = prune_expired_audit_events(now=now)

    assert result["deleted"] == 1
    assert result["remaining"] is False
    assert not AuditEvent.objects.filter(pk=old.pk).exists()
    assert AuditEvent.objects.filter(pk__in=[boundary.pk, recent.pk]).count() == 2
    event = AuditEvent.objects.get(action="audit_retention_purge")
    assert event.details["count"] == 1
    assert "old" not in str(event.details)
    assert prune_expired_audit_events(now=now)["deleted"] == 0
    assert AuditEvent.objects.filter(action="audit_retention_purge").count() == 1
    assert AIUsageEvent.objects.filter(pk=usage.pk).exists()  # Separate retention domain.


@pytest.mark.django_db
def test_retention_skips_when_another_run_holds_lock(user):
    old = AuditEvent.objects.create(actor=user, action="old", outcome="success")
    AuditEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=91))
    assert cache.add("audit:retention:lock", True, timeout=3600)
    try:
        result = prune_expired_audit_events(now=timezone.now())
        assert result["status"] == "busy"
        assert AuditEvent.objects.filter(pk=old.pk).exists()
    finally:
        cache.delete("audit:retention:lock")


@pytest.mark.django_db
def test_retention_does_not_delete_without_its_audit_record(user):
    old = AuditEvent.objects.create(actor=user, action="old", outcome="success")
    AuditEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=91))
    with patch("apps.audit.retention.record_audit", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            prune_expired_audit_events(now=timezone.now())
    assert AuditEvent.objects.filter(pk=old.pk).exists()
    assert cache.get("audit:retention:lock") is None


def test_retention_schedule_is_daily_at_local_off_peak_hour(settings):
    assert settings.AUDIT_RETENTION_DAYS == 90
    assert celery_app.conf.timezone == "America/Sao_Paulo"
    entry = celery_app.conf.beat_schedule["audit-retention-daily"]
    assert entry["task"] == "audit.prune_expired_events"
    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"]._orig_hour == 3
    assert entry["schedule"]._orig_minute == 15
    celery_app.autodiscover_tasks(force=True)
    assert "audit.prune_expired_events" in celery_app.tasks
