from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.meetings.models import Meeting, MeetingStatus, Segment, Speaker, SpeakerAnalysis
from apps.meetings.processing.providers import TranscribedSegment
from apps.meetings.processing.speaker_reconciliation import (
    VoiceSample,
    infer_speaker_groups,
    select_voice_samples,
)


def segment(code, start, end):
    return SimpleNamespace(speaker=SimpleNamespace(code=code), start_ms=start, end_ms=end)


def test_selects_two_non_overlapping_clean_samples_per_speaker():
    segments = [
        segment("A", 0, 9000), segment("B", 4000, 6000),
        segment("A", 20000, 25000), segment("B", 30000, 35000),
        segment("B", 45000, 50000), segment("C", 60000, 62000),
    ]
    samples = select_voice_samples(segments)
    assert [item.code for item in samples] == ["A", "A", "B", "B"]
    assert all(item.end_ms - item.start_ms == 3000 for item in samples)
    assert all(
        item.end_ms <= other.start_ms or item.start_ms >= other.end_ms
        for item in samples for other in segments
        if other.speaker.code != item.code
    )


def test_inference_requires_two_consistent_samples_per_person():
    samples = [
        VoiceSample("A", 0, 3000, 0, 3000),
        VoiceSample("B", 10000, 13000, 3750, 6750),
        VoiceSample("A", 20000, 23000, 7500, 10500),
        VoiceSample("B", 30000, 33000, 11250, 14250),
        VoiceSample("C", 40000, 43000, 15000, 18000),
        VoiceSample("C", 50000, 53000, 18750, 21750),
    ]
    transcript = [
        TranscribedSegment("voice_1", 200, 2750, "Um"),
        TranscribedSegment("voice_1", 3950, 6500, "Dois"),
        TranscribedSegment("voice_1", 7700, 10250, "Tres"),
        TranscribedSegment("voice_1", 11450, 14000, "Quatro"),
        TranscribedSegment("voice_2", 15200, 17750, "Cinco"),
        TranscribedSegment("voice_3", 18950, 21500, "Seis"),
    ]
    assert infer_speaker_groups(samples, transcript) == [["A", "B"]]


def test_inference_does_not_group_ambiguous_voice_sample():
    samples = [
        VoiceSample("A", 0, 3000, 0, 3000),
        VoiceSample("A", 10000, 13000, 3750, 6750),
        VoiceSample("B", 20000, 23000, 7500, 10500),
        VoiceSample("B", 30000, 33000, 11250, 14250),
    ]
    transcript = [
        TranscribedSegment("same", 0, 2500, "Um"),
        TranscribedSegment("same", 3750, 6250, "Dois"),
        TranscribedSegment("same", 7500, 8900, "Tres"),
        TranscribedSegment("other", 8900, 10300, "Outra voz"),
        TranscribedSegment("same", 11250, 13750, "Quatro"),
    ]
    assert infer_speaker_groups(samples, transcript) == []


def test_composite_is_bounded_and_temporary(tmp_path):
    from apps.meetings.processing.speaker_reconciliation import build_composite_audio

    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"mp3")
    samples = [VoiceSample("A", 0, 3000), VoiceSample("A", 20000, 23000)]
    calls = []

    def fake_run(args, timeout):
        calls.append(args)
        if args[-1] != "pipe:1":
            Path(args[-1]).write_bytes(b"encoded")
        return b""

    with patch("apps.meetings.processing.speaker_reconciliation._run", side_effect=fake_run):
        with build_composite_audio(audio, samples) as (composite, indexed):
            assert composite.exists()
            assert [item.composite_start_ms for item in indexed] == [0, 3750]
            assert composite.stat().st_size < 22_000_000
        assert not composite.exists()
    assert any("anullsrc=r=16000:cl=mono" in command for command in calls)


@pytest.mark.django_db
def test_speaker_suggestion_api_is_private_versioned_and_does_not_merge(
    api, user, other_user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Teste", status=MeetingStatus.TRANSCRITO,
        transcription_version=1, audio_path="audio.mp3",
    )
    (tmp_path / "audio.mp3").write_bytes(b"mp3")
    first = Speaker.objects.create(meeting=meeting, code="A", name="Pessoa 1")
    second = Speaker.objects.create(meeting=meeting, code="B", name="Pessoa 2")
    for index, speaker in enumerate((first, second)):
        Segment.objects.create(
            meeting=meeting, speaker=speaker, start_ms=index * 10000,
            end_ms=index * 10000 + 3000, text="Fala", order=index,
        )
    path = f"/api/v1/meetings/{meeting.id}/speaker-suggestions/"
    with patch("apps.meetings.tasks.analyze_speaker_reconciliation.delay") as enqueue:
        started = api.post(path, {"version": 1}, format="json")
        repeated = api.post(path, {"version": 1}, format="json")
    assert started.status_code == repeated.status_code == 202
    assert started.data["job_id"] == repeated.data["job_id"]
    enqueue.assert_called_once()
    assert api.get(path, {"job_id": started.data["job_id"]}).status_code == 202
    api.force_authenticate(user=other_user)
    assert api.get(path, {"job_id": started.data["job_id"]}).status_code == 404
    api.force_authenticate(user=user)
    meeting.transcription_version = 2
    meeting.save(update_fields=["transcription_version"])
    assert api.get(path, {"job_id": started.data["job_id"]}).status_code == 409
    assert list(meeting.speakers.filter(merged_into__isnull=True)) == [first, second]


@pytest.mark.django_db
def test_worker_returns_suggestions_without_changing_speakers(user, settings, tmp_path):
    from apps.meetings.job_state import accept_job
    from apps.meetings.tasks import analyze_speaker_reconciliation

    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Teste", status=MeetingStatus.TRANSCRITO,
        transcription_version=1, audio_path="audio.mp3",
    )
    (tmp_path / "audio.mp3").write_bytes(b"mp3")
    for code in ("A", "B"):
        speaker = Speaker.objects.create(meeting=meeting, code=code, name=code)
        Segment.objects.create(
            meeting=meeting, speaker=speaker, start_ms=0, end_ms=5000,
            text="Fala", order=0 if code == "A" else 1,
        )
    job_id = "e11e2df1-757b-4bd8-ae9d-9a29eb637101"
    accept_job(meeting, job_id, "speaker_reconciliation")
    analysis = SpeakerAnalysis.objects.create(
        meeting=meeting, uses=1, job_id=job_id, version=1, status="processing",
    )
    samples = [
        VoiceSample("A", 0, 3000, 0, 3000),
        VoiceSample("A", 10000, 13000, 11250, 14250),
        VoiceSample("B", 20000, 23000, 3750, 6750),
        VoiceSample("B", 30000, 33000, 15000, 18000),
    ]
    transcript = [
        TranscribedSegment("voice", item.composite_start_ms, item.composite_end_ms, "Fala")
        for item in samples
    ]
    from contextlib import contextmanager

    @contextmanager
    def fake_composite(audio, selected):
        yield audio, samples

    with (
        patch("apps.meetings.jobs.speakers.select_voice_samples", return_value=samples),
        patch("apps.meetings.jobs.speakers.build_composite_audio", side_effect=fake_composite),
        patch("apps.meetings.jobs.speakers.transcription_provider", return_value=SimpleNamespace(
            transcribe=lambda path: transcript
        )),
    ):
        assert analyze_speaker_reconciliation(str(meeting.id), 1, job_id) == "ready"
    analysis.refresh_from_db()
    assert analysis.groups == [["A", "B"]]
    assert analysis.sample_times == {
        "A": [0.0, 10.0], "B": [20.0, 30.0],
    }
    assert meeting.speakers.filter(merged_into__isnull=True).count() == 2
