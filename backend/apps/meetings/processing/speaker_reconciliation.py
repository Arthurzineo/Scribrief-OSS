"""Optional, conservative speaker-link suggestions from a short voice montage."""

import tempfile
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from ..processing.pipeline import MediaError, _run
from ..processing.providers import TranscribedSegment

SAMPLE_MS = 3000
GAP_MS = 750
MAX_SPEAKERS = 64
MAX_COMPOSITE_BYTES = 22_000_000


class ReconciliationError(ValueError):
    pass


@dataclass(frozen=True)
class VoiceSample:
    code: str
    start_ms: int
    end_ms: int
    composite_start_ms: int = 0
    composite_end_ms: int = 0


def _clean_windows(segment, all_segments):
    windows = [(segment.start_ms, segment.end_ms)]
    for other in all_segments:
        if other.speaker.code == segment.speaker.code:
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
        if not windows:
            break
    return windows


def select_voice_samples(segments) -> list[VoiceSample]:
    """Choose two disjoint 3-second clean excerpts for each eligible speaker."""
    segments = list(segments)
    codes = sorted({item.speaker.code for item in segments})
    if len(codes) > MAX_SPEAKERS:
        raise ReconciliationError(
            f"Há mais de {MAX_SPEAKERS} falantes; áudio composto excederia o limite."
        )
    by_code: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for segment in segments:
        for start, end in _clean_windows(segment, segments):
            if end - start >= SAMPLE_MS:
                by_code[segment.speaker.code].append((start, end))

    samples = []
    for code in codes:
        windows = sorted(by_code[code], key=lambda item: (-(item[1] - item[0]), item[0]))
        chosen: list[VoiceSample] = []
        for start, end in windows:
            positions = ([start, end - SAMPLE_MS] if end - start >= 2 * SAMPLE_MS + GAP_MS
                         else [start + (end - start - SAMPLE_MS) // 2])
            for position in positions:
                candidate = VoiceSample(code, position, position + SAMPLE_MS)
                if all(
                    candidate.end_ms <= old.start_ms or candidate.start_ms >= old.end_ms
                    for old in chosen
                ):
                    chosen.append(candidate)
                if len(chosen) == 2:
                    break
            if len(chosen) == 2:
                break
        if len(chosen) == 2:
            samples.extend(sorted(chosen, key=lambda item: item.start_ms))
    return samples


def _interleave_samples(samples: list[VoiceSample]) -> list[VoiceSample]:
    by_code: dict[str, list[VoiceSample]] = defaultdict(list)
    for sample in samples:
        by_code[sample.code].append(sample)
    return [sample for turn in range(2) for code in sorted(by_code)
            for sample in by_code[code][turn:turn + 1]]


@contextmanager
def build_composite_audio(audio_path: Path, samples: list[VoiceSample]):
    """Yield a temporary MP3 and indexed source windows; remove all clips on exit."""
    if not samples or len(samples) > MAX_SPEAKERS * 2:
        raise ReconciliationError("Quantidade de amostras inválida.")
    # Docker mounts /tmp as tmpfs: an interrupted worker cannot leave voice clips
    # in the persistent private-media volume.
    with tempfile.TemporaryDirectory(prefix=".speaker-reconcile-") as tmp:
        directory = Path(tmp)
        silence = directory / "silence.wav"
        _run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "anullsrc=r=16000:cl=mono", "-t", str(GAP_MS / 1000),
            "-c:a", "pcm_s16le", str(silence),
        ], 30)
        lines = []
        indexed = []
        cursor = 0
        for index, sample in enumerate(_interleave_samples(samples)):
            clip = directory / f"clip-{index:03d}.wav"
            _run([
                "ffmpeg", "-nostdin", "-v", "error", "-ss", f"{sample.start_ms / 1000:.3f}",
                "-i", str(audio_path), "-t", str(SAMPLE_MS / 1000),
                "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(clip),
            ], 90)
            if not clip.is_file() or clip.stat().st_size == 0:
                raise MediaError("Amostra de voz vazia")
            lines.extend([f"file '{clip.name}'", f"file '{silence.name}'"])
            indexed.append(replace(
                sample, composite_start_ms=cursor, composite_end_ms=cursor + SAMPLE_MS
            ))
            cursor += SAMPLE_MS + GAP_MS
        listing = directory / "clips.txt"
        listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
        output = directory / "voices.mp3"
        _run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(listing), "-ac", "1", "-ar", "16000", "-b:a", "96k", str(output),
        ], 600)
        if not output.is_file() or not 0 < output.stat().st_size <= MAX_COMPOSITE_BYTES:
            raise ReconciliationError("Áudio composto acima do limite ou vazio.")
        yield output, indexed


def infer_speaker_groups(
    samples: list[VoiceSample], transcript: list[TranscribedSegment]
) -> list[list[str]]:
    """Suggest only labels stable across two separate excerpts of each source."""
    labels: dict[str, list[str]] = defaultdict(list)
    for sample in samples:
        weights: dict[str, int] = defaultdict(int)
        for segment in transcript:
            if not segment.text.strip():
                continue
            overlap = min(sample.composite_end_ms, segment.end_ms) - max(
                sample.composite_start_ms, segment.start_ms
            )
            if overlap > 0:
                weights[segment.speaker] += overlap
        total = sum(weights.values())
        if total < 1000:
            continue
        label, dominant = max(weights.items(), key=lambda item: item[1])
        if dominant >= 1200 and dominant / total >= 0.8:
            labels[sample.code].append(label)

    by_label: dict[str, list[str]] = defaultdict(list)
    for code, values in labels.items():
        if len(values) == 2 and values[0] == values[1]:
            by_label[values[0]].append(code)
    return sorted([sorted(codes) for codes in by_label.values() if len(codes) >= 2])
