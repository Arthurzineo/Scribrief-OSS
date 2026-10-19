"""Optional in-memory voice references for the first diarized chunk."""

import base64
import logging
from pathlib import Path

from ..processing.pipeline import MediaError, _run
from ..processing.providers import TranscribedSegment

logger = logging.getLogger(__name__)

MIN_REFERENCE_MS = 2000
MAX_REFERENCE_MS = 9000
MAX_REFERENCES = 4
MAX_REFERENCE_BYTES = 1_000_000


def _clean_windows(segment: TranscribedSegment, others: list[TranscribedSegment]):
    windows = [(segment.start_ms, segment.end_ms)]
    for other in others:
        if other.speaker == segment.speaker:
            continue
        remaining = []
        for start, end in windows:
            if other.end_ms <= start or other.start_ms >= end:
                remaining.append((start, end))
            else:
                if other.start_ms > start:
                    remaining.append((start, other.start_ms))
                if other.end_ms < end:
                    remaining.append((other.end_ms, end))
        windows = remaining
    return windows


def build_speaker_references(
    chunk_path: Path, segments: list[TranscribedSegment]
) -> tuple[dict[str, str], dict[str, str]]:
    """Return data URLs and first-chunk aliases; skip ambiguous/too-short voices."""
    best: dict[str, tuple[int, int]] = {}
    for segment in segments:
        if not segment.text or segment.end_ms - segment.start_ms < MIN_REFERENCE_MS:
            continue
        for start, end in _clean_windows(segment, segments):
            if end - start < MIN_REFERENCE_MS:
                continue
            previous = best.get(segment.speaker)
            if previous is None or end - start > previous[1] - previous[0]:
                best[segment.speaker] = (start, end)

    ranked = sorted(best.items(), key=lambda item: (-(item[1][1] - item[1][0]), item[1][0]))
    references: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for speaker, (start, end) in ranked[:MAX_REFERENCES]:
        duration = min(end - start, MAX_REFERENCE_MS)
        start += ((end - start) - duration) // 2
        name = f"ref_{len(references)}"
        try:
            sample = _run(
                [
                    "ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start / 1000:.3f}",
                    "-i", str(chunk_path), "-t", f"{duration / 1000:.3f}", "-ac", "1",
                    "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "96k", "-f", "mp3",
                    "pipe:1",
                ],
                60,
            )
        except MediaError:
            logger.warning("Could not extract a voice reference from first chunk")
            continue
        if not 0 < len(sample) <= MAX_REFERENCE_BYTES:
            logger.warning("Voice reference skipped: invalid encoded size")
            continue
        references[name] = "data:audio/mpeg;base64," + base64.b64encode(sample).decode("ascii")
        aliases[name] = speaker
    return references, aliases
