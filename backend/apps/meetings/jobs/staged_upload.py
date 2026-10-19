"""Periodic fail-safe for pre-consent media if the browser disappears."""

from celery import shared_task

from ..services.staged_upload import purge_stale_uploads


@shared_task(name="meetings.purge_staged_uploads", acks_late=True)
def purge_staged_uploads_task():
    return purge_stale_uploads()
