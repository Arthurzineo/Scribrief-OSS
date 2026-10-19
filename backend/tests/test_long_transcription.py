from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.meetings.models import Meeting, Speaker
from apps.meetings.processing.pipeline import AudioChunk, make_chunks
from apps.meetings.processing.providers import OpenAITranscriptionProvider, TranscribedSegment
from apps.meetings.processing.speaker_references import build_speaker_references
from apps.meetings.processing.stitching import stitch_transcripts
from apps.meetings.tasks import process_meeting


def test_twenty_minute_chunks_overlap_by_fifteen_seconds(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"mp3")
    commands = []

    def fake_run(args, timeout):
        commands.append(args)
        Path(args[-1]).write_bytes(b"chunk")
        return b""

    with (
        patch("apps.meetings.processing.pipeline.duration_seconds", return_value=2400),
        patch("apps.meetings.processing.pipeline._run", side_effect=fake_run),
    ):
        chunks = make_chunks(audio)

    assert [chunk.offset_ms for chunk in chunks] == [0, 1185000, 2370000]
    assert [float(args[args.index("-t") + 1]) for args in commands] == [1200, 1200, 30]


def test_reference_builder_uses_clean_speech_and_keeps_audio_in_memory(tmp_path):
    audio = tmp_path / "first.mp3"
    audio.write_bytes(b"mp3")
    segments = [
        TranscribedSegment("A", 0, 9000, "Fala longa de A"),
        TranscribedSegment("B", 20000, 23000, "Fala limpa de B"),
        TranscribedSegment("A", 10000, 19000, "Outra fala limpa de A"),
    ]
    with patch("apps.meetings.processing.speaker_references._run", return_value=b"sample") as run:
        references, aliases = build_speaker_references(audio, segments)

    assert aliases == {"ref_0": "A", "ref_1": "B"}
    assert all(value.startswith("data:audio/mpeg;base64,") for value in references.values())
    assert len(run.call_args_list) == 2
    for call in run.call_args_list:
        command = call.args[0]
        assert 2 <= float(command[command.index("-t") + 1]) <= 10
        assert command[-1] == "pipe:1"
    assert list(tmp_path.iterdir()) == [audio]


def test_reference_limit_does_not_limit_transcribed_speakers(tmp_path):
    audio = tmp_path / "first.mp3"
    audio.write_bytes(b"mp3")
    first_segments = [
        TranscribedSegment(f"person_{index}", index * 10000, index * 10000 + 5000, "Fala")
        for index in range(6)
    ]
    with patch("apps.meetings.processing.speaker_references._run", return_value=b"sample"):
        references, aliases = build_speaker_references(audio, first_segments)

    assert len(references) == 4
    chunks = [AudioChunk(audio, 0), AudioChunk(audio, 1185000)]
    later = [
        TranscribedSegment("ref_0", 0, 1000, "Fala conhecida"),
        TranscribedSegment("new_voice", 2000, 3000, "Outra pessoa"),
    ]
    _, stitched = stitch_transcripts(chunks, [first_segments, later], aliases)
    assert len({item[0] for item in stitched}) == 7


def test_provider_passes_known_speakers_without_prompt(tmp_path):
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"mp3")
    create = Mock(return_value=SimpleNamespace(segments=[
        SimpleNamespace(start=0, end=1, speaker="ref_0", text="Olá")
    ]))
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))

    with patch("apps.meetings.processing.providers._client", return_value=client):
        result = OpenAITranscriptionProvider().transcribe(
            audio, known_speakers={"ref_0": "data:audio/mpeg;base64,YQ=="}
        )

    assert result[0].speaker == "ref_0"
    options = create.call_args.kwargs
    assert options["extra_body"] == {
        "known_speaker_names": ["ref_0"],
        "known_speaker_references": ["data:audio/mpeg;base64,YQ=="],
    }
    assert "prompt" not in options


def test_stitching_deduplicates_overlap_and_matches_unknown_speaker():
    chunks = [AudioChunk(Path("first.mp3"), 0), AudioChunk(Path("second.mp3"), 1185000)]
    results = [
        [TranscribedSegment("A", 1190000, 1195000, "Aprovar o orçamento")],
        [
            TranscribedSegment("B", 5000, 10000, "Aprovar o orçamento"),
            TranscribedSegment("B", 20000, 23000, "Próxima pauta"),
            TranscribedSegment("C", 7000, 9000, "Outra fala distinta"),
        ],
    ]

    speakers, segments = stitch_transcripts(chunks, results, {})

    assert len(segments) == 3
    assert [item[3] for item in segments] == [
        "Aprovar o orçamento", "Outra fala distinta", "Próxima pauta"
    ]
    assert segments[0][0] == segments[2][0]
    assert segments[1][0] != segments[0][0]
    assert len(set(speakers.values())) == 2


@pytest.mark.django_db
def test_first_chunk_is_processed_before_parallel_reference_calls(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.TRANSCRIPTION_PARALLELISM = 10
    meeting = Meeting.objects.create(
        owner=user, title="Longa", job_id="9d64de2f-fae5-4d61-824d-60f0f48a0ae0"
    )
    directory = tmp_path / "reunioes" / str(meeting.id)
    directory.mkdir(parents=True)
    audio = directory / "audio.mp3"
    audio.write_bytes(b"normalized")
    chunks = []
    for index in range(11):
        path = directory / f"chunk-{index}.mp3"
        path.write_bytes(f"chunk-{index}".encode())
        chunks.append(AudioChunk(path, index * 1185000))
    barrier = Barrier(10, timeout=3)
    lock = Lock()
    first_done = False
    seen = []

    class Provider:
        def transcribe(self, path, known_speakers=None):
            nonlocal first_done
            index = int(path.stem.split("-")[-1])
            with lock:
                seen.append((index, known_speakers))
            if index == 0:
                assert known_speakers is None
                first_done = True
                return [TranscribedSegment("A", 0, 1000, "Primeira fala")]
            assert first_done
            assert known_speakers == {"ref_0": "data:audio/mpeg;base64,YQ=="}
            barrier.wait()
            return [TranscribedSegment("ref_0", 0, 1000, f"Fala {index}")]

    with (
        patch("apps.meetings.jobs.transcription.normalize_audio", return_value=audio),
        patch("apps.meetings.jobs.transcription.make_chunks", return_value=chunks),
        patch("apps.meetings.jobs.transcription.transcription_provider", return_value=Provider()),
        patch("apps.meetings.jobs.chunks.build_speaker_references", return_value=(
            {"ref_0": "data:audio/mpeg;base64,YQ=="}, {"ref_0": "A"}
        )),
    ):
        assert process_meeting(str(meeting.id), str(meeting.job_id)) == "transcribed"

    assert seen[0][0] == 0
    assert len(seen) == 11
    assert Speaker.objects.filter(meeting=meeting).count() == 1
    assert meeting.segments.count() == 11
