"""Retention for security and technical events, not AI usage or media."""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, HealthSample, SystemEvent, record_audit

RETENTION_LOCK = "audit:retention:lock"
BATCH_SIZE = 500
MAX_BATCHES = 200


def prune_audit_before(cutoff):
    """Delete old audit rows in bounded transactions, logging each committed batch.

    A shared cache lock prevents the daily task and manual command from competing.
    Failure to acquire the lock is a safe no-op; later scheduled runs retry.
    """
    if timezone.is_naive(cutoff):
        raise ValueError("Retention cutoff must be timezone-aware")
    if not cache.add(RETENTION_LOCK, True, timeout=3600):
        return {"status": "busy", "deleted": 0, "remaining": True,
                "system_deleted": 0, "system_remaining": True,
                "health_deleted": 0, "health_remaining": True}
    total = 0
    system_total = 0
    health_total = 0
    try:
        for _ in range(MAX_BATCHES):
            with transaction.atomic():
                ids = list(
                    AuditEvent.objects.filter(created_at__lt=cutoff)
                    .order_by("created_at", "id")
                    .values_list("id", flat=True)[:BATCH_SIZE]
                )
                if not ids:
                    break
                deleted, _ = AuditEvent.objects.filter(
                    id__in=ids, created_at__lt=cutoff
                ).delete()
                if deleted:
                    record_audit(
                        None, "audit_retention_purge", target_type="audit",
                        details={"before": cutoff.isoformat(), "count": deleted},
                    )
            if not deleted:
                break
            total += deleted
        for _ in range(MAX_BATCHES):
            with transaction.atomic():
                ids = list(
                    SystemEvent.objects.filter(created_at__lt=cutoff)
                    .order_by("created_at", "id")
                    .values_list("id", flat=True)[:BATCH_SIZE]
                )
                if not ids:
                    break
                system_deleted, _ = SystemEvent.objects.filter(
                    id__in=ids, created_at__lt=cutoff
                ).delete()
                if system_deleted:
                    record_audit(
                        None, "system_retention_purge", target_type="system_event",
                        details={"before": cutoff.isoformat(), "count": system_deleted},
                    )
            if not system_deleted:
                break
            system_total += system_deleted
        remaining = AuditEvent.objects.filter(created_at__lt=cutoff).exists()
        system_remaining = SystemEvent.objects.filter(created_at__lt=cutoff).exists()
        for _ in range(MAX_BATCHES):
            with transaction.atomic():
                ids = list(HealthSample.objects.filter(created_at__lt=cutoff)
                           .order_by("created_at", "id")
                           .values_list("id", flat=True)[:BATCH_SIZE])
                if not ids:
                    break
                deleted, _ = HealthSample.objects.filter(
                    id__in=ids, created_at__lt=cutoff
                ).delete()
                if deleted:
                    record_audit(None, "health_retention_purge", target_type="health_sample",
                                 details={"before": cutoff.isoformat(), "count": deleted})
            health_total += deleted
        health_remaining = HealthSample.objects.filter(created_at__lt=cutoff).exists()
        return {"status": "completed", "deleted": total, "remaining": remaining,
                "system_deleted": system_total, "system_remaining": system_remaining,
                "health_deleted": health_total, "health_remaining": health_remaining}
    finally:
        cache.delete(RETENTION_LOCK)


def prune_expired_audit_events(*, now=None):
    now = now or timezone.now()
    return prune_audit_before(now - timedelta(days=settings.AUDIT_RETENTION_DAYS))
