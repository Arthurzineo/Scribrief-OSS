"""Transactional editing rules shared by the API actions."""

from datetime import timedelta

from django.utils import timezone

from ..models import MeetingStatus


def minutes_generation_stuck(meeting):
    if meeting.status != MeetingStatus.GERANDO_ATA:
        return False
    started = meeting.job_started_at or meeting.updated_at
    return started < timezone.now() - timedelta(minutes=10)
