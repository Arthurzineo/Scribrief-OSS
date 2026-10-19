"""Conservative cross-chunk speaker linking and overlap deduplication."""

import re
from collections import defaultdict
from difflib import SequenceMatcher

from ..processing.pipeline import AudioChunk
from ..processing.providers import TranscribedSegment

SpeakerKey = tuple[int, str]


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def _same_utterance(left: tuple, right: tuple) -> bool:
    _, left_start, left_end, left_text = left
    _, right_start, right_end, right_text = right
    ltext, rtext = _words(left_text), _words(right_text)
    if min(len(ltext), len(rtext)) < 10:
        return False
    overlap = min(left_end, right_end) - max(left_start, right_start)
    shortest = min(left_end - left_start, right_end - right_start)
    if shortest <= 0 or overlap / shortest < 0.65:
        return False
    if abs(left_start - right_start) > 2000 or abs(left_end - right_end) > 2000:
        return False
    return SequenceMatcher(None, ltext, rtext).ratio() >= 0.9


def stitch_transcripts(
    chunks: list[AudioChunk],
    chunk_results: list[list[TranscribedSegment]],
    reference_aliases: dict[str, str],
) -> tuple[dict[SpeakerKey, SpeakerKey], list[tuple[SpeakerKey, int, int, str]]]:
    """Merge only strong overlapping evidence; preserve distinct/uncertain speech."""
    speaker_map: dict[SpeakerKey, SpeakerKey] = {}
    output: list[tuple[SpeakerKey, int, int, str]] = []
    previous: list[tuple] = []
    for index, (chunk, raw_segments) in enumerate(zip(chunks, chunk_results, strict=True)):
        current = [
            (
                (index, raw.speaker),
                chunk.offset_ms + raw.start_ms,
                chunk.offset_ms + raw.end_ms,
                raw.text,
            )
            for raw in raw_segments
        ]
        for local, *_ in current:
            speaker_map.setdefault(
                local,
                (0, reference_aliases[local[1]])
                if index > 0 and local[1] in reference_aliases
                else local,
            )

        matches: dict[SpeakerKey, set[SpeakerKey]] = defaultdict(set)
        duplicate_pairs: set[tuple[int, int]] = set()
        for prev_index, old in enumerate(previous):
            for current_index, new in enumerate(current):
                if _same_utterance(old, new):
                    matches[new[0]].add(speaker_map[old[0]])
                    duplicate_pairs.add((prev_index, current_index))
        candidates = {
            local: next(iter(values))
            for local, values in matches.items()
            if len(values) == 1 and speaker_map[local] == local
        }
        reverse: dict[SpeakerKey, set[SpeakerKey]] = defaultdict(set)
        for local, canonical in candidates.items():
            reverse[canonical].add(local)
        for local, canonical in candidates.items():
            if len(reverse[canonical]) == 1:
                speaker_map[local] = canonical

        duplicate_current = {
            current_index
            for previous_index, current_index in duplicate_pairs
            if speaker_map[previous[previous_index][0]] == speaker_map[current[current_index][0]]
            and current[current_index][2] <= previous[previous_index][2] + 500
        }
        output.extend(
            (speaker_map[local], start, end, text)
            for current_index, (local, start, end, text) in enumerate(current)
            if current_index not in duplicate_current
        )
        previous = current
    output.sort(key=lambda item: (item[1], item[2]))
    return speaker_map, output
