"""Stable Celery autodiscovery and task import surface."""

from .jobs.corrections import analyze_transcription_corrections as analyze_transcription_corrections
from .jobs.mind_map import generate_mind_map as generate_mind_map
from .jobs.minutes import generate_minutes as generate_minutes
from .jobs.purge import purge_expired_meetings_task as purge_expired_meetings_task
from .jobs.speakers import analyze_speaker_reconciliation as analyze_speaker_reconciliation
from .jobs.staged_upload import purge_staged_uploads_task as purge_staged_uploads_task
from .jobs.transcription import process_meeting as process_meeting
