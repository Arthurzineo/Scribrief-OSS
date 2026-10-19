"""Celery jobs. The database state guards against duplicate deliveries."""

import logging

from celery import shared_task
from django.core.cache import cache
from django.db import transaction

from apps.audit.models import record_audit

from ..job_state import (
    JobCancelled,
    ensure_not_cancelled,
    finish_job,
    finish_stale_job,
    start_job,
)
from ..models import (
    Meeting,
    Minutes,
)
from ..processing.mind_map import mind_map_provider, validate_mind_map_data
from .common import _call_context

logger = logging.getLogger(__name__)


@shared_task(name="meetings.generate_mind_map", acks_late=True)
def generate_mind_map(meeting_id, version, job_id):
    claim = f"mind_map:claimed:{meeting_id}:{job_id}"
    if not cache.add(claim, True, timeout=600):
        return "ignored"
    start_job(job_id, "mind_map")
    try:
        ensure_not_cancelled(job_id)
        meeting = Meeting.objects.get(pk=meeting_id)
        if (
            meeting.deletion_requested_at or meeting.minutes_version != version
            or meeting.minutes_stale
        ):
            return finish_stale_job(job_id)
        minutes = Minutes.objects.get(meeting=meeting)
        if (
            minutes.mind_map_status != "generating"
            or minutes.mind_map_version != version
            or str(minutes.mind_map_job_id) != str(job_id)
        ):
            return finish_stale_job(job_id)
        api_key, context = _call_context(meeting, job_id, "mind_map")
        data = validate_mind_map_data(mind_map_provider(api_key, context).generate(minutes))
        ensure_not_cancelled(job_id)
        with transaction.atomic():
            current = Meeting.objects.select_for_update().get(pk=meeting_id)
            if (
                current.deletion_requested_at or current.minutes_version != version
                or current.minutes_stale
            ):
                return finish_stale_job(job_id)
            current_minutes = Minutes.objects.select_for_update().get(meeting=current)
            if (
                current_minutes.mind_map_status != "generating"
                or current_minutes.mind_map_version != version
                or str(current_minutes.mind_map_job_id) != str(job_id)
            ):
                return finish_stale_job(job_id)
            current_minutes.mind_map = data
            current_minutes.mind_map_status = "ready"
            current_minutes.save(update_fields=["mind_map", "mind_map_status", "updated_at"])
            record_audit(
                current.owner, "mind_map_generated", current.id, sector=current.sector,
                target_type="meeting", target_ref=current.id,
                details={"job_id": str(job_id), "minutes_version": version},
            )
            finish_job(job_id, "completed")
        return "ready"
    except JobCancelled:
        return "cancelled"
    except Exception as exc:
        logger.error(
            "Mind map generation failed for meeting %s: %s", meeting_id, type(exc).__name__
        )
        Minutes.objects.filter(
            meeting_id=meeting_id, mind_map_version=version,
            mind_map_job_id=job_id, mind_map_status="generating",
        ).update(mind_map_status="error")
        finish_job(job_id, "failed", "mind_map_failed")
        return "failed"
    finally:
        cache.delete(claim)
