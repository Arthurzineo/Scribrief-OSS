"""Transcription Celery task and persistence of diarized segments."""

import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction

from ..exports import export_transcript
from ..job_state import (
    JobCancelled,
    ensure_not_cancelled,
    finish_job,
    finish_stale_job,
    start_job,
)
from ..models import Meeting, MeetingStatus, Segment, Speaker, TranscriptionChunk
from ..processing.pipeline import make_chunks, normalize_audio
from ..processing.providers import transcription_provider
from ..processing.stitching import stitch_transcripts
from ..processing.transcription_progress import plan_transcription
from ..storage import safe_media_path
from .chunks import _speaker_code, _transcribe_chunks
from .common import _call_context, _claim, _fail

logger = logging.getLogger(__name__)


@shared_task(name="meetings.process_meeting", acks_late=True)
def process_meeting(meeting_id, job_id):
    meeting = _claim(meeting_id, job_id, MeetingStatus.ENVIADO, MeetingStatus.EXTRAINDO_AUDIO)
    if meeting is None:
        return "ignored"
    start_job(job_id, "extracting_audio")
    try:
        ensure_not_cancelled(job_id)
        audio_path = normalize_audio(meeting)
        ensure_not_cancelled(job_id)
        with transaction.atomic():
            meeting = Meeting.objects.select_for_update().get(pk=meeting_id)
            ensure_not_cancelled(job_id)
            if (
                meeting.status != MeetingStatus.EXTRAINDO_AUDIO
                or str(meeting.job_id) != str(job_id)
            ):
                return finish_stale_job(job_id)
            meeting.audio_path = str(audio_path.relative_to(Path(settings.MEDIA_ROOT).resolve()))
            meeting.status = MeetingStatus.TRANSCREVENDO
            meeting.save(update_fields=["audio_path", "status", "updated_at"])
        chunks = make_chunks(audio_path)
        plan_transcription(meeting, len(chunks))
        api_key, context = _call_context(meeting, job_id, "transcription_chunk")
        provider = transcription_provider(api_key, context)
        chunk_results, reference_aliases = _transcribe_chunks(meeting, chunks, provider)
        ensure_not_cancelled(job_id)
        _, stitched = stitch_transcripts(chunks, chunk_results, reference_aliases)
        speaker_codes = {}
        segments = []
        for speaker_key, start, end, text in stitched:
            if speaker_key not in speaker_codes:
                speaker_codes[speaker_key] = _speaker_code(len(speaker_codes))
            segments.append((speaker_codes[speaker_key], start, end, text))
        if not segments:
            raise ValueError("empty_transcription")
        segments.sort(key=lambda item: (item[1], item[2]))
        with transaction.atomic():
            current = Meeting.objects.select_for_update().get(pk=meeting_id)
            if current.status != MeetingStatus.TRANSCREVENDO or str(current.job_id) != str(job_id):
                return finish_stale_job(job_id)
            speakers = {}
            for code in speaker_codes.values():
                speakers[code] = Speaker.objects.create(
                    meeting=current, code=code, name=f"Pessoa {len(speakers) + 1}"
                )
            Segment.objects.bulk_create(
                [
                    Segment(
                        meeting=current,
                        speaker=speakers[code],
                        start_ms=start,
                        end_ms=end,
                        text=text,
                        original_text=text,
                        original_start_ms=start,
                        original_end_ms=end,
                        original_speaker_code=code,
                        original_source="ai_generation",
                        order=index,
                    )
                    for index, (code, start, end, text) in enumerate(segments)
                ]
            )
            current.transcription_version += 1
            current.status = MeetingStatus.TRANSCRITO
            TranscriptionChunk.objects.filter(meeting=current).delete()
            # A transcription is not successful while the uploaded original remains.
            # If removal fails, roll back segments/status and retain the original for retry.
            original_path = current.original_path
            current.original_path = ""
            current.save(update_fields=[
                "transcription_version", "status", "original_path", "updated_at"
            ])
            if original_path:
                safe_media_path(original_path).unlink(missing_ok=True)
            finish_job(job_id, "completed")
        try:
            export_transcript(current)
        except OSError:
            logger.exception("Could not export transcription for meeting %s", meeting_id)
        return "transcribed"
    except JobCancelled:
        return "cancelled"
    except Exception as exc:
        logger.error("Processing failed for meeting %s: %s", meeting_id, type(exc).__name__)
        _fail(
            meeting_id,
            job_id,
            "processing_failed",
            "Processamento falhou. Tente novamente ou contate o suporte.",
        )
        finish_job(job_id, "failed", "processing_failed")
        return "failed"
