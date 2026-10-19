"""Periodic purge after the reversible deletion window."""

from celery import shared_task

from ..services.deletion import purge_expired_meetings


@shared_task(name="meetings.purge_expired", acks_late=True)
def purge_expired_meetings_task():
    return purge_expired_meetings()
