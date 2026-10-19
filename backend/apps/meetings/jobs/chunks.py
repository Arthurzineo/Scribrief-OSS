"""Ordered parallel chunk transcription and durable checkpoints."""

import logging
import math
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
from hashlib import file_digest
from random import uniform
from time import sleep

from django.conf import settings

from ..job_state import ensure_not_cancelled, heartbeat_job
from ..models import TranscriptionChunk
from ..processing.ai_registry import selected_provider
from ..processing.providers import TranscribedSegment, validate_transcribed_segments
from ..processing.speaker_references import build_speaker_references

logger = logging.getLogger(__name__)


def _speaker_code(index):
    value = ""
    while True:
        index, rem = divmod(index, 26)
        value = chr(65 + rem) + value
        if index == 0:
            return value
        index -= 1


def _chunk_hash(chunk):
    with chunk.path.open("rb") as source:
        return file_digest(source, "sha256").hexdigest()


def _cached_chunk_segments(meeting, chunk_index, chunk, audio_sha256):
    checkpoint = TranscriptionChunk.objects.filter(meeting=meeting, index=chunk_index).first()
    if (
        checkpoint
        and checkpoint.offset_ms == chunk.offset_ms
        and checkpoint.audio_sha256 == audio_sha256
        and checkpoint.provider_id == selected_provider("transcription")
        and checkpoint.model == settings.MODELO_TRANSCRICAO
        and checkpoint.language == settings.TRANSCRIPTION_LANGUAGE
    ):
        raw = validate_transcribed_segments([
            TranscribedSegment(**item) for item in checkpoint.segments
        ])
        logger.info("Reused transcription checkpoint %s for meeting %s", chunk_index, meeting.id)
        return raw
    return None


def _save_chunk_segments(meeting, chunk_index, chunk, audio_sha256, raw):
    raw = validate_transcribed_segments(raw)
    TranscriptionChunk.objects.update_or_create(
        meeting=meeting,
        index=chunk_index,
        defaults={
            "offset_ms": chunk.offset_ms,
            "audio_sha256": audio_sha256,
            "provider_id": selected_provider("transcription"),
            "model": settings.MODELO_TRANSCRICAO,
            "language": settings.TRANSCRIPTION_LANGUAGE,
            "segments": [asdict(item) for item in raw],
        },
    )
    logger.info("Saved transcription checkpoint %s for meeting %s", chunk_index, meeting.id)
    heartbeat_job(
        meeting.job_id, stage="transcribing",
        completed_units=TranscriptionChunk.objects.filter(meeting=meeting).count(),
    )


def _chunk_segments(meeting, chunk_index, chunk, provider):
    audio_sha256 = _chunk_hash(chunk)
    raw = _cached_chunk_segments(meeting, chunk_index, chunk, audio_sha256)
    if raw is not None:
        return raw
    raw = provider.transcribe(chunk.path)
    _save_chunk_segments(meeting, chunk_index, chunk, audio_sha256, raw)
    return raw


def _transcribe_with_retry(provider, path, known_speakers=None, job_id=None):
    for attempt in range(4):
        try:
            if job_id:
                ensure_not_cancelled(job_id)
            if known_speakers:
                result = provider.transcribe(path, known_speakers=known_speakers)
            else:
                result = provider.transcribe(path)
            if job_id:
                ensure_not_cancelled(job_id)
            return result
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status not in (429, 503) or attempt == 3:
                raise
            headers = getattr(getattr(exc, "response", None), "headers", {})
            try:
                retry_after = float(headers.get("retry-after", 0))
            except (TypeError, ValueError):
                retry_after = 0
            if not math.isfinite(retry_after) or retry_after < 0:
                retry_after = 0
            delay = max(retry_after, 2 ** attempt) + uniform(0, 5)
            logger.warning("Transient transcription HTTP %s; retry %s", status, attempt + 1)
            sleep(delay)


def _transcribe_chunks(meeting, chunks, provider):
    parallelism = settings.TRANSCRIPTION_PARALLELISM
    if not 1 <= parallelism <= 10:
        raise ValueError("TRANSCRIPTION_PARALLELISM deve estar entre 1 e 10")
    if not chunks:
        return [], {}
    results = [None] * len(chunks)
    first_digest = _chunk_hash(chunks[0])
    first = _cached_chunk_segments(meeting, 0, chunks[0], first_digest)
    if first is None:
        first = _transcribe_with_retry(provider, chunks[0].path, job_id=meeting.job_id)
        _save_chunk_segments(meeting, 0, chunks[0], first_digest, first)
    results[0] = first
    references, aliases = (
        build_speaker_references(chunks[0].path, first)
        if len(chunks) > 1
        else ({}, {})
    )
    work = []
    for index, chunk in enumerate(chunks[1:], start=1):
        digest = _chunk_hash(chunk)
        cached = _cached_chunk_segments(meeting, index, chunk, digest)
        if cached is not None:
            results[index] = cached
        else:
            work.append((index, chunk, digest))
    if not work:
        return results, aliases

    with ThreadPoolExecutor(max_workers=min(parallelism, len(work))) as executor:
        remaining = iter(work)
        pending = {}

        def submit_next():
            ensure_not_cancelled(meeting.job_id)
            try:
                index, chunk, digest = next(remaining)
            except StopIteration:
                return
            future = executor.submit(
                _transcribe_with_retry, provider, chunk.path, references
            )
            pending[future] = (index, chunk, digest)

        for _ in range(min(parallelism, len(work))):
            submit_next()
        error = None
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index, chunk, digest = pending.pop(future)
                try:
                    raw = future.result()
                    ensure_not_cancelled(meeting.job_id)
                    _save_chunk_segments(meeting, index, chunk, digest, raw)
                    results[index] = raw
                except Exception as exc:
                    if error is None:
                        error = exc
            if error is None:
                for _ in done:
                    submit_next()
        if error is not None:
            raise error
    return results, aliases
