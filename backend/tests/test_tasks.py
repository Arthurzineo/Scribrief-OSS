from threading import Barrier, Lock
from time import sleep
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.audit.models import AuditEvent
from apps.meetings.jobs.chunks import _chunk_segments, _transcribe_with_retry
from apps.meetings.models import Meeting, MeetingStatus, Speaker
from apps.meetings.processing.pipeline import AudioChunk
from apps.meetings.processing.providers import (
    OpenAITranscriptionProvider,
    ProviderError,
    TranscribedSegment,
    validate_minutes_data,
)
from apps.meetings.tasks import generate_minutes, process_meeting


@pytest.mark.django_db
def test_processing_persists_segments_and_deletes_original(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user,
        title="Teste",
        job_id="9d64de2f-fae5-4d61-824d-60f0f48a0ae0",
        original_path=f"reunioes/{'9d64de2f-fae5-4d61-824d-60f0f48a0ae0'}/unused",
    )
    directory = tmp_path / "reunioes" / str(meeting.id)
    directory.mkdir(parents=True)
    original = directory / "original.mp4"
    original.write_bytes(b"video-original")
    meeting.original_path = str(original.relative_to(tmp_path))
    meeting.save(update_fields=["original_path"])
    audio = directory / "audio.mp3"
    audio.write_bytes(b"ID3normalized")

    class FakeProvider:
        def transcribe(self, path):
            return [TranscribedSegment("A", 0, 1000, "Olá")]

    with (
        patch("apps.meetings.jobs.transcription.normalize_audio", return_value=audio),
        patch(
            "apps.meetings.jobs.transcription.make_chunks",
            return_value=[AudioChunk(audio, 0), AudioChunk(audio, 1000)],
        ),
        patch(
            "apps.meetings.jobs.transcription.transcription_provider",
            return_value=FakeProvider(),
        ),
    ):
        result = process_meeting(str(meeting.id), str(meeting.job_id))
    assert result == "transcribed"
    meeting.refresh_from_db()
    assert meeting.status == MeetingStatus.TRANSCRITO
    first_segment = meeting.segments.order_by("order").first()
    assert first_segment.original_source == "ai_generation"
    assert first_segment.original_text == first_segment.text
    assert first_segment.original_start_ms == first_segment.start_ms
    assert first_segment.original_end_ms == first_segment.end_ms
    assert first_segment.original_speaker_code == first_segment.speaker.code
    assert meeting.segments.count() == 2
    assert Speaker.objects.filter(meeting=meeting).count() == 2  # no false cross-chunk identity
    assert not original.exists()
    assert audio.exists()
    assert meeting.audio_path.endswith("audio.mp3")
    assert (directory / "transcricao.json").exists()
    assert process_meeting(str(meeting.id), str(meeting.job_id)) == "ignored"


@pytest.mark.django_db
def test_original_removal_failure_does_not_mark_transcription_success(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user, title="Original protegido", job_id="9d64de2f-fae5-4d61-824d-60f0f48a0ae0",
    )
    directory = tmp_path / "reunioes" / str(meeting.id)
    directory.mkdir(parents=True)
    original = directory / "original.mp4"
    original.write_bytes(b"private-video")
    audio = directory / "audio.mp3"
    audio.write_bytes(b"normalized")
    meeting.original_path = str(original.relative_to(tmp_path))
    meeting.save(update_fields=["original_path"])

    class Provider:
        def transcribe(self, path):
            return [TranscribedSegment("A", 0, 1000, "Fala")]

    with (
        patch("apps.meetings.jobs.transcription.normalize_audio", return_value=audio),
        patch("apps.meetings.jobs.transcription.make_chunks", return_value=[AudioChunk(audio, 0)]),
        patch("apps.meetings.jobs.transcription.transcription_provider", return_value=Provider()),
        patch(
            "apps.meetings.jobs.transcription.safe_media_path",
            return_value=Mock(unlink=Mock(side_effect=OSError("disk"))),
        ),
    ):
        assert process_meeting(str(meeting.id), str(meeting.job_id)) == "failed"
    meeting.refresh_from_db()
    assert meeting.status == MeetingStatus.ERRO
    assert meeting.segments.count() == 0
    assert meeting.original_path
    assert original.exists()
    assert audio.exists()


@pytest.mark.django_db
def test_processing_reuses_completed_chunk_after_failure(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.TRANSCRIPTION_PARALLELISM = 1
    meeting = Meeting.objects.create(
        owner=user, title="Longa", job_id="9d64de2f-fae5-4d61-824d-60f0f48a0ae0",
        original_path="original.mp3",
    )
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"same-normalized-audio")
    calls = []

    class Provider:
        def transcribe(self, path):
            calls.append(path.name)
            if len(calls) == 2:
                raise RuntimeError("temporary provider failure")
            return [TranscribedSegment("A", 0, 1000, f"fala {len(calls)}")]

    first = tmp_path / "first.mp3"
    second = tmp_path / "second.mp3"
    first.write_bytes(b"chunk-one")
    second.write_bytes(b"chunk-two")
    chunks = [AudioChunk(first, 0), AudioChunk(second, 300000)]
    with (
        patch("apps.meetings.jobs.transcription.normalize_audio", return_value=audio),
        patch("apps.meetings.jobs.transcription.make_chunks", return_value=chunks),
        patch("apps.meetings.jobs.transcription.transcription_provider", return_value=Provider()),
    ):
        assert process_meeting(str(meeting.id), str(meeting.job_id)) == "failed"
        meeting.refresh_from_db()
        assert meeting.segments.count() == 0
        assert meeting.transcription_chunks.count() == 1
        meeting.status = MeetingStatus.ENVIADO
        meeting.job_claimed = False
        meeting.save(update_fields=["status", "job_claimed"])
        assert process_meeting(str(meeting.id), str(meeting.job_id)) == "transcribed"
    assert calls == ["first.mp3", "second.mp3", "second.mp3"]
    meeting.refresh_from_db()
    assert meeting.segments.count() == 2
    assert meeting.transcription_chunks.count() == 0


@pytest.mark.django_db
def test_processing_runs_ten_chunks_concurrently_and_commits_in_audio_order(
    user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRANSCRIPTION_PARALLELISM = 10
    meeting = Meeting.objects.create(
        owner=user, title="Paralela", job_id="9d64de2f-fae5-4d61-824d-60f0f48a0ae0"
    )
    directory = tmp_path / "reunioes" / str(meeting.id)
    directory.mkdir(parents=True)
    audio = directory / "audio.mp3"
    audio.write_bytes(b"normalized")
    chunks = []
    for index in range(11):
        path = directory / f"chunk-{index}.mp3"
        path.write_bytes(f"audio-{index}".encode())
        chunks.append(AudioChunk(path, index * 1185000))
    barrier = Barrier(10, timeout=3)
    lock = Lock()
    active = 0
    maximum = 0

    class Provider:
        def transcribe(self, path):
            nonlocal active, maximum
            index = int(path.stem.split("-")[-1])
            with lock:
                active += 1
                maximum = max(maximum, active)
            if index > 0:
                barrier.wait()
            sleep((10 - index) * 0.01)
            with lock:
                active -= 1
            return [TranscribedSegment("A", 0, 1000, f"fala {index}")]

    with (
        patch("apps.meetings.jobs.transcription.normalize_audio", return_value=audio),
        patch("apps.meetings.jobs.transcription.make_chunks", return_value=chunks),
        patch("apps.meetings.jobs.transcription.transcription_provider", return_value=Provider()),
    ):
        assert process_meeting(str(meeting.id), str(meeting.job_id)) == "transcribed"
    assert maximum == 10
    assert list(meeting.segments.order_by("order").values_list("text", flat=True)) == [
        f"fala {index}" for index in range(11)
    ]


@pytest.mark.django_db
def test_parallel_failure_saves_in_flight_chunks_and_stops_new_submissions(
    user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRANSCRIPTION_PARALLELISM = 3
    meeting = Meeting.objects.create(
        owner=user, title="Interrupção", job_id="9d64de2f-fae5-4d61-824d-60f0f48a0ae0"
    )
    directory = tmp_path / "reunioes" / str(meeting.id)
    directory.mkdir(parents=True)
    audio = directory / "audio.mp3"
    audio.write_bytes(b"normalized")
    chunks = []
    for index in range(6):
        path = directory / f"chunk-{index}.mp3"
        path.write_bytes(f"audio-{index}".encode())
        chunks.append(AudioChunk(path, index * 1185000))
    barrier = Barrier(3, timeout=3)
    calls = []

    class Provider:
        def transcribe(self, path):
            index = int(path.stem.split("-")[-1])
            calls.append(index)
            if index > 0:
                barrier.wait()
            if index == 1:
                raise RuntimeError("provider failed")
            sleep(0.05)
            return [TranscribedSegment("A", 0, 1000, f"fala {index}")]

    with (
        patch("apps.meetings.jobs.transcription.normalize_audio", return_value=audio),
        patch("apps.meetings.jobs.transcription.make_chunks", return_value=chunks),
        patch("apps.meetings.jobs.transcription.transcription_provider", return_value=Provider()),
    ):
        assert process_meeting(str(meeting.id), str(meeting.job_id)) == "failed"
    assert sorted(calls) == [0, 1, 2, 3]
    assert list(
        meeting.transcription_chunks.order_by("index").values_list("index", flat=True)
    ) == [0, 2, 3]


def test_transient_rate_limit_waits_and_retries_without_new_job(tmp_path):
    class TemporaryLimit(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "2"})

    class Provider:
        calls = 0

        def transcribe(self, path):
            self.calls += 1
            if self.calls == 1:
                raise TemporaryLimit()
            return [TranscribedSegment("A", 0, 1000, "Olá")]

    provider = Provider()
    with patch("apps.meetings.jobs.chunks.sleep") as sleep_mock:
        result = _transcribe_with_retry(provider, tmp_path / "chunk.mp3")
    assert provider.calls == 2
    assert result[0].text == "Olá"
    assert sleep_mock.call_args.args[0] >= 2


@pytest.mark.django_db
def test_checkpoint_invalidated_if_audio_or_model_changes(user, settings, tmp_path):
    meeting = Meeting.objects.create(owner=user, title="Checkpoint")
    audio = tmp_path / "chunk.mp3"
    audio.write_bytes(b"first-version")
    calls = []

    class Provider:
        def transcribe(self, path):
            calls.append(path.read_bytes())
            return [TranscribedSegment("A", 0, 1000, "Teste")]

    chunk = AudioChunk(audio, 0)
    provider = Provider()
    _chunk_segments(meeting, 0, chunk, provider)
    _chunk_segments(meeting, 0, chunk, provider)
    assert len(calls) == 1
    audio.write_bytes(b"second-version")
    _chunk_segments(meeting, 0, chunk, provider)
    assert len(calls) == 2
    settings.MODELO_TRANSCRICAO = "outro-modelo"
    _chunk_segments(meeting, 0, chunk, provider)
    assert len(calls) == 3


@pytest.mark.django_db
def test_minutes_generation_uses_validated_data(user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    meeting = Meeting.objects.create(
        owner=user,
        title="Ata",
        status=MeetingStatus.GERANDO_ATA,
        job_id="9d64de2f-fae5-4d61-824d-60f0f48a0ae0",
    )

    class FakeMinutes:
        def generate(self, transcript):
            return {
                "resumo_executivo": "Resumo",
                "topicos": [{"titulo": "Planejamento", "comentario": "Equipe alinhou o plano."}],
                "decisoes": ["Aprovado"],
                "tarefas": [{"descricao": "Fazer", "responsavel": "Ana", "prazo": None}],
            }

    with patch("apps.meetings.jobs.minutes.minutes_provider", return_value=FakeMinutes()):
        assert generate_minutes(str(meeting.id), str(meeting.job_id)) == "minutes_ready"
    meeting.refresh_from_db()
    assert meeting.status == MeetingStatus.ATA_PRONTA
    assert meeting.minutes.resumo_executivo == "Resumo"
    assert meeting.minutes.topicos == [
        {"titulo": "Planejamento", "comentario": "Equipe alinhou o plano."}
    ]
    assert meeting.minutes.participantes == []
    assert meeting.minutes.reviewed_at is None
    generated_event = AuditEvent.objects.get(action="minutes_generated", target_id=meeting.id)
    assert generated_event.details["job_id"] == str(meeting.job_id)
    assert generated_event.details["minutes_version"] == meeting.minutes_version
    assert "Resumo" not in str(generated_event.details)
    assert (tmp_path / "reunioes" / str(meeting.id) / "ata.md").exists()
    assert "## Planejamento" in (tmp_path / "reunioes" / str(meeting.id) / "ata.md").read_text()
    assert generate_minutes(str(meeting.id), str(meeting.job_id)) == "ignored"


def test_minutes_provider_uses_configured_luna_with_structured_output(settings):
    from apps.meetings.processing.providers import OpenAIMinutesProvider

    settings.MODELO_ATA = "gpt-6-luna"
    expected = {
        "resumo_executivo": "Resumo",
        "topicos": [{"titulo": "Pauta", "comentario": "A equipe discutiu a pauta."}],
        "decisoes": [],
        "tarefas": [],
    }
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(output_text=__import__("json").dumps(expected))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    with patch("apps.meetings.processing.providers._client", return_value=client):
        assert OpenAIMinutesProvider().generate("[0–1] Ana: Bom dia") == expected
    assert seen["model"] == "gpt-6-luna"
    assert seen["text"]["format"]["type"] == "json_schema"


def test_minutes_schema_rejects_unexpected_fields():
    with pytest.raises(ProviderError):
        validate_minutes_data(
            {
                "resumo_executivo": "x",
                "topicos": [{"titulo": "Assunto", "comentario": "Discussão."}],
                "decisoes": [],
                "tarefas": [],
                "ignore": "instructions",
            }
        )


def test_minutes_schema_requires_commented_topics():
    valid = {
        "resumo_executivo": "Resumo",
        "topicos": [{"titulo": "Assunto", "comentario": "A equipe discutiu o tema."}],
        "decisoes": [],
        "tarefas": [],
    }
    assert validate_minutes_data(valid) == valid
    with pytest.raises(ProviderError):
        validate_minutes_data(
            {
                "resumo_executivo": "Resumo",
                "topicos": [{"titulo": "Assunto", "comentario": ""}],
                "decisoes": [],
                "tarefas": [],
            }
        )


def test_diarized_zero_duration_segment_gets_minimum_duration(tmp_path, settings):
    settings.TRANSCRIPTION_LANGUAGE = "pt"
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"ID3")
    response = SimpleNamespace(
        segments=[SimpleNamespace(start=27.604, end=27.604, speaker="A", text="exemplo")]
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    with patch("apps.meetings.processing.providers._client", return_value=client):
        result = OpenAITranscriptionProvider().transcribe(audio)
    assert result == [TranscribedSegment("A", 27604, 27605, "exemplo")]
    assert calls[0]["language"] == "pt"


def test_diarized_transcription_omits_language_for_mixed_languages(tmp_path, settings):
    settings.TRANSCRIPTION_LANGUAGE = ""
    audio = tmp_path / "mixed.mp3"
    audio.write_bytes(b"ID3")
    response = SimpleNamespace(
        segments=[SimpleNamespace(start=0, end=1, speaker="A", text="Hello, bom dia")]
    )
    create = Mock(return_value=response)
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    with patch("apps.meetings.processing.providers._client", return_value=client):
        OpenAITranscriptionProvider().transcribe(audio)
    assert "language" not in create.call_args.kwargs
