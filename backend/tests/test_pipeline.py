from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.meetings.processing.pipeline import make_chunks, normalize_audio


def test_normalize_audio_encodes_mp3_at_higher_bitrate(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    meeting = SimpleNamespace(id="meeting-1", original_path="source.mp4")
    (tmp_path / "reunioes" / "meeting-1").mkdir(parents=True)
    commands = []

    def fake_run(args, timeout):
        commands.append(args)
        (tmp_path / "reunioes" / "meeting-1" / "audio.part.mp3").write_bytes(b"mp3")
        return b""

    with patch("apps.meetings.processing.pipeline._run", side_effect=fake_run):
        output = normalize_audio(meeting)

    assert output.name == "audio.mp3"
    assert output.read_bytes() == b"mp3"
    assert commands[0][commands[0].index("-b:a") + 1] == "96k"


def test_short_mp3_is_sent_without_second_encoding(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"mp3-data")

    with (
        patch("apps.meetings.processing.pipeline.duration_seconds", return_value=60),
        patch("apps.meetings.processing.pipeline._run") as run,
    ):
        chunks = make_chunks(audio)

    assert len(chunks) == 1
    assert chunks[0].path == audio
    assert chunks[0].offset_ms == 0
    run.assert_not_called()


def test_long_mp3_chunks_are_twenty_minutes_with_overlap_and_keep_higher_bitrate(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"mp3-data")
    commands = []

    def fake_run(args, timeout):
        commands.append(args)
        Path(args[-1]).write_bytes(b"chunk")
        return b""

    with (
        patch("apps.meetings.processing.pipeline.duration_seconds", return_value=1801),
        patch("apps.meetings.processing.pipeline._run", side_effect=fake_run),
    ):
        chunks = make_chunks(audio)

    assert [chunk.offset_ms for chunk in chunks] == [0, 1185000]
    assert [float(args[args.index('-t') + 1]) for args in commands] == [1200, 616]
    assert all(args[args.index("-b:a") + 1] == "96k" for args in commands)
