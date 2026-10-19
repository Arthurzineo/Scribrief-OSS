"""Best-effort technical diagnostics with stable codes and no free-form payloads."""

import logging

from django.db import transaction

from .models.system_event import SystemEvent

logger = logging.getLogger(__name__)


def record_system_event(component, event_code, *, severity="info", **fields):
    """Do not let telemetry failure corrupt a committed business transition.

    DB retention and access are bounded; stdout remains the fallback when DB
    writes fail. Callers must pass only structured, non-secret fields.
    """
    allowed = {
        "outcome", "error_code", "stage", "kind", "job_id", "meeting_id",
        "sector_id", "user_id", "request_id", "client_ip", "http_status",
    }
    if set(fields) - allowed:
        raise ValueError("Unsupported system event field")
    try:
        with transaction.atomic():
            return SystemEvent.objects.create(
                component=component, event_code=event_code, severity=severity,
                user_id_snapshot=fields.get("user_id"),
                sector_id_snapshot=fields.get("sector_id"), **fields
            )
    except Exception:
        # Never include an exception message: it may carry a credential or payload.
        logger.error("System event write failed: component=%s event=%s", component, event_code)
        return None
