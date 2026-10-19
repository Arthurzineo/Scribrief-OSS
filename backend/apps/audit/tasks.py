"""Scheduled audit-retention maintenance; no media or usage-ledger deletion."""

import logging

from celery import shared_task

from .health import save_health_sample
from .retention import prune_expired_audit_events

logger = logging.getLogger(__name__)


@shared_task(name="audit.collect_health_sample", acks_late=True)
def collect_health_sample_task():
    return save_health_sample().pk


@shared_task(name="audit.prune_expired_events", acks_late=True)
def prune_expired_audit_events_task():
    result = prune_expired_audit_events()
    logger.info(
        "Audit retention: status=%s deleted=%s remaining=%s system_deleted=%s health_deleted=%s",
        result["status"], result["deleted"], result["remaining"],
        result["system_deleted"], result["health_deleted"],
    )
    return result
