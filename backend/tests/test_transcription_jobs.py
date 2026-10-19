from types import SimpleNamespace
from unittest.mock import patch

from apps.meetings.transcription_jobs import (
    enqueue_transcription,
    transcription_stale_after_seconds,
    transcription_time_limits,
)


def test_timeout_exceeds_video_duration():
    soft, hard = transcription_time_limits(9375.192, multiplier=2, minimum=3600, grace=600)
    assert soft > 9375.192
    assert hard > soft


def test_enqueue_uses_per_meeting_limits(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = SimpleNamespace(id="meeting-id", job_id="job-id", audio_path="audio.mp3")
    (tmp_path / "audio.mp3").write_bytes(b"audio")
    with (
        patch("apps.meetings.transcription_jobs.duration_seconds", return_value=9375.192),
        patch("apps.meetings.transcription_jobs.accept_job"),
        patch("apps.meetings.tasks.process_meeting.apply_async") as send,
    ):
        enqueue_transcription(meeting)
    kwargs = send.call_args.kwargs
    assert kwargs["args"] == ("meeting-id", "job-id")
    assert kwargs["soft_time_limit"] > 9375.192
    assert kwargs["time_limit"] > kwargs["soft_time_limit"]


def test_stale_retry_waits_beyond_hard_limit(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = SimpleNamespace(audio_path="audio.mp3")
    (tmp_path / "audio.mp3").write_bytes(b"audio")
    with patch("apps.meetings.transcription_jobs.duration_seconds", return_value=20000):
        stale = transcription_stale_after_seconds(meeting)
    assert stale > transcription_time_limits(20000)[1]
