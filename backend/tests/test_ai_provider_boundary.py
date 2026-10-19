from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from apps.accounts.models import SectorAICredential
from apps.accounts.secrets import sector_credential
from apps.audit.models import AIUsageEvent
from apps.audit.usage import record_ai_attempt
from apps.meetings.ai_checks import check_ai_providers
from apps.meetings.jobs.chunks import _cached_chunk_segments
from apps.meetings.jobs.common import _call_context
from apps.meetings.models import Meeting, TranscriptionChunk
from apps.meetings.processing.ai_registry import (
    AIProviderConfigurationError,
    capability_for_operation,
    create_provider,
    selected_provider,
)
from apps.meetings.processing.corrections import validate_review_suggestions
from apps.meetings.processing.providers import (
    ProviderError,
    TranscribedSegment,
    minutes_provider,
    transcription_provider,
    validate_transcribed_segments,
)


class FakeMinutesAdapter:
    def __init__(self, credential, usage_context):
        self.credential = credential
        self.usage_context = usage_context

    def generate(self, transcript):
        return {
            "resumo_executivo": transcript,
            "topicos": [{"titulo": "Teste", "comentario": "OK"}],
            "decisoes": [], "tarefas": [],
        }


def test_default_adapters_preserve_current_vendor(settings):
    assert selected_provider("transcription") == "openai"
    assert selected_provider("minutes") == "openai"
    assert transcription_provider("secret").__class__.__name__ == "OpenAITranscriptionProvider"
    assert minutes_provider("secret").__class__.__name__ == "OpenAIMinutesProvider"
    assert capability_for_operation("speaker_reconciliation") == "transcription"


def test_registered_adapter_can_replace_minutes_without_changing_job_contract(settings):
    settings.AI_PROVIDER_MINUTES = "synthetic"
    with patch.dict("apps.meetings.processing.ai_registry.AI_ADAPTERS", {
        "synthetic": {"minutes": "tests.test_ai_provider_boundary.FakeMinutesAdapter"}
    }):
        adapter = minutes_provider("non-openai-credential", {"operation": "minutes"})
        result = adapter.generate("Falamos do plano")
    assert adapter.credential == "non-openai-credential"
    assert result["topicos"][0]["titulo"] == "Teste"


def test_unknown_or_unsupported_vendor_fails_closed(settings):
    settings.AI_PROVIDER_MINUTES = "unknown"
    with pytest.raises(AIProviderConfigurationError):
        create_provider("minutes", "key")
    with pytest.raises(AIProviderConfigurationError):
        selected_provider("unrecognized")
    with pytest.raises(AIProviderConfigurationError):
        capability_for_operation("unrecognized")
    assert any(issue.id == "meetings.E001" for issue in check_ai_providers(None))


@pytest.mark.django_db
def test_sector_credentials_are_isolated_per_registered_provider(api, user, settings):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    sector = user.membership.sector
    new_url = f"/api/admin/sectors/{sector.pk}/ai-credentials/synthetic/"
    old_url = f"/api/admin/sectors/{sector.pk}/openai-key/"
    with patch.dict("apps.meetings.processing.ai_registry.AI_ADAPTERS", {
        "synthetic": {"minutes": "tests.test_ai_provider_boundary.FakeMinutesAdapter"}
    }):
        assert api.get(new_url).data["configured"] is False
        secret = "synthetic-secret-123456"
        response = api.post(new_url, {
            "api_key": secret, "current_password": "Strong-Test-Password-123"
        }, format="json")
        assert response.status_code == 200
        saved = SectorAICredential.objects.get(sector=sector, provider_id="synthetic")
        assert secret not in saved.ciphertext
        assert sector_credential(sector.pk, "synthetic")[0] == secret
        assert api.get(old_url).data["configured"] is True
        settings.AI_PROVIDER_MINUTES = "synthetic"
        meeting = Meeting.objects.create(owner=user, title="Adapter")
        key, context = _call_context(meeting, uuid4(), "minutes")
        assert key == secret and context["provider_id"] == "synthetic"
        assert minutes_provider(key, context).generate("Texto")["resumo_executivo"] == "Texto"
        assert api.delete(new_url, {"current_password": "wrong"}, format="json").status_code == 403
        assert api.delete(new_url, {
            "current_password": "Strong-Test-Password-123"
        }, format="json").status_code == 204
        assert api.get(old_url).data["configured"] is True


@pytest.mark.django_db
def test_provider_catalog_requires_staff_and_never_exposes_credentials(api, user, other_user):
    api.force_authenticate(user=other_user)
    assert api.get("/api/admin/ai-providers/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    response = api.get("/api/admin/ai-providers/")
    assert response.status_code == 200
    assert response.data["selected"]["transcription"] == "openai"
    assert response.data["providers"][0]["id"] == "openai"
    assert "ciphertext" not in str(response.data)


@pytest.mark.django_db
def test_provider_neutral_ledger_keeps_provenance_without_fabricating_cost(user):
    meeting = Meeting.objects.create(owner=user, title="Ledger de provedor")
    context = {"sector_id": meeting.sector_id, "user_id": user.pk,
               "meeting_id": meeting.pk, "operation": "minutes", "key_version": 1}
    record_ai_attempt(
        context=context, provider_id="synthetic", model="synthetic-text",
        usage={"input_tokens": 10, "output_tokens": 3, "payload": "never-store-secret"},
        request_id="req-synthetic-1",
    )
    event = AIUsageEvent.objects.get(request_id="req-synthetic-1")
    assert event.provider_id == "synthetic" and event.total_tokens == 13
    assert event.estimated_usd is None and event.estimate_status == "unavailable"
    assert "never-store-secret" not in str(event.usage)


@pytest.mark.django_db
def test_transcription_checkpoint_is_not_reused_across_providers(user, settings):
    meeting = Meeting.objects.create(owner=user, title="Checkpoint")
    TranscriptionChunk.objects.create(
        meeting=meeting, index=0, offset_ms=0, audio_sha256="a" * 64,
        provider_id="openai", model=settings.MODELO_TRANSCRICAO,
        language=settings.TRANSCRIPTION_LANGUAGE, segments=[],
    )
    chunk = SimpleNamespace(offset_ms=0)
    assert _cached_chunk_segments(meeting, 0, chunk, "a" * 64) == []
    settings.AI_PROVIDER_TRANSCRIPTION = "synthetic"
    with patch.dict("apps.meetings.processing.ai_registry.AI_ADAPTERS", {
        "synthetic": {"transcription": "tests.test_ai_provider_boundary.FakeMinutesAdapter"}
    }):
        assert _cached_chunk_segments(meeting, 0, chunk, "a" * 64) is None


def test_application_rejects_malformed_output_from_any_adapter():
    with pytest.raises(ProviderError):
        validate_transcribed_segments([
            TranscribedSegment(speaker="A", start_ms=1000, end_ms=900, text="Inválido")
        ])
    with pytest.raises(ProviderError):
        validate_review_suggestions([
            {"segmento_id": 1, "texto_sugerido": "Texto diferente e inventado", "motivo": "X"}
        ], [{"id": 1, "texto": "Olá"}])
