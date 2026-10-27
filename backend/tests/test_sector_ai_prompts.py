import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Sector, SectorAIPrompt
from apps.audit.models import AIUsageEvent, AuditEvent
from apps.audit.usage import record_ai_attempt
from apps.meetings.jobs.common import _call_context
from apps.meetings.models import Meeting
from apps.meetings.processing.corrections import OpenAICorrectionProvider
from apps.meetings.processing.mind_map import OpenAIMindMapProvider
from apps.meetings.processing.prompt_defaults import SYSTEM_PROMPT_DEFAULTS
from apps.meetings.processing.providers import OpenAIMinutesProvider
from apps.meetings.processing.sector_prompts import effective_prompt
from apps.meetings.storage import save_original


@pytest.mark.django_db
def test_prompt_catalog_staff_only_defaults_and_isolated_by_sector(api, user, other_user):
    path = f"/api/admin/sectors/{user.membership.sector_id}/ai-prompts/"
    api.force_authenticate(user=other_user)
    assert api.get(path).status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    response = api.get(path)
    assert response.status_code == 200
    assert {item["kind"] for item in response.data["prompts"]} == set(SYSTEM_PROMPT_DEFAULTS)
    assert all(
        item["source"] == "default" and item["version"] == 0 for item in response.data["prompts"]
    )
    assert "não aceita instruções de sistema" in response.data["transcription_note"]
    for item in response.data["prompts"]:
        assert item["text"] == SYSTEM_PROMPT_DEFAULTS[item["kind"]]


@pytest.mark.django_db
def test_prompt_edit_version_audit_reset_and_job_context(api, user, other_user):
    other_user.membership.sector = Sector.objects.create(name="Outro setor", slug="outro-setor")
    other_user.membership.save(update_fields=["sector"])
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    api.force_authenticate(user=user)
    sector_id = user.membership.sector_id
    path = f"/api/admin/sectors/{sector_id}/ai-prompts/minutes/"
    new_text = "Crie uma ata dos assuntos tratados. Liste as decisões sem inventar prazos."
    data = {"text": new_text, "expected_version": 0, "current_password": "Strong-Test-Password-123"}
    assert api.put(path, {**data, "current_password": "wrong"}, format="json").status_code == 403
    response = api.put(path, data, format="json")
    assert response.status_code == 200
    assert response.data["source"] == "custom" and response.data["version"] == 1
    assert effective_prompt(sector_id, "minutes") == (new_text, 1)
    assert api.put(path, data, format="json").status_code == 409
    assert SectorAIPrompt.objects.filter(sector_id=sector_id).count() == 1
    meeting = Meeting.objects.create(owner=user, title="Prompt setorial")
    _, context = _call_context(meeting, uuid4(), "minutes")
    assert context["system_prompt"] == new_text and context["prompt_version"] == 1
    record_ai_attempt(context=context, provider_id="openai", model="test", request_id="prompt-1")
    usage = AIUsageEvent.objects.get(request_id="prompt-1")
    assert usage.prompt_version == 1 and len(usage.prompt_fingerprint) == 64
    assert new_text not in str(usage.__dict__)
    assert effective_prompt(other_user.membership.sector_id, "minutes") == (
        SYSTEM_PROMPT_DEFAULTS["minutes"],
        0,
    )
    event = AuditEvent.objects.filter(action="sector_prompt_updated").latest("created_at")
    assert new_text not in str(event.details)
    assert event.details["kind"] == "minutes"
    assert (
        api.delete(
            path,
            {"expected_version": 0, "current_password": data["current_password"]},
            format="json",
        ).status_code
        == 409
    )
    reset = api.delete(
        path, {"expected_version": 1, "current_password": data["current_password"]}, format="json"
    )
    assert reset.status_code == 200 and reset.data["source"] == "default"
    assert effective_prompt(sector_id, "minutes") == (SYSTEM_PROMPT_DEFAULTS["minutes"], 0)
    assert AuditEvent.objects.filter(action="sector_prompt_reset").exists()


@pytest.mark.django_db
def test_prompt_validation_rejects_unknown_and_unbounded_text(api, user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    base = f"/api/admin/sectors/{user.membership.sector_id}/ai-prompts/"
    data = {"expected_version": 0, "current_password": "Strong-Test-Password-123"}
    assert (
        api.put(base + "transcription/", {**data, "text": "X" * 50}, format="json").status_code
        == 400
    )
    assert (
        api.put(base + "minutes/", {**data, "text": "X" * 8001}, format="json").status_code == 400
    )
    assert api.put(base + "minutes/", {**data, "text": "short"}, format="json").status_code == 400
    assert (
        api.put(base + "minutes/", {**data, "text": "a" * 30 + "\x00"}, format="json").status_code
        == 400
    )


def test_all_three_openai_calls_use_context_system_prompt_without_changing_schemas():
    used = []

    def create(**kwargs):
        used.append(kwargs)
        if kwargs["model"] == "gpt-4.1-mini":
            return SimpleNamespace(output_text='{"sugestoes": []}')
        if kwargs["text"]["format"]["name"] == "mapa_mental_curto":
            return SimpleNamespace(
                output_text='{"centro":"Tema","ramos":[{"titulo":"A","pontos":["B"]}]}'
            )
        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "resumo_executivo": "Resumo",
                    "topicos": [{"titulo": "Tema", "comentario": "Falado."}],
                    "decisoes": [],
                    "tarefas": [],
                }
            )
        )

    fake_client = SimpleNamespace(responses=SimpleNamespace(create=create))
    with (
        patch("apps.meetings.processing.providers._client", return_value=fake_client),
        patch("apps.meetings.processing.mind_map._client", return_value=fake_client),
        patch("apps.meetings.processing.corrections._client", return_value=fake_client),
        patch(
            "apps.meetings.processing.providers.tracked_openai_call",
            side_effect=lambda call, *args, **kwargs: call(),
        ),
        patch(
            "apps.meetings.processing.mind_map.tracked_openai_call",
            side_effect=lambda call, *args, **kwargs: call(),
        ),
        patch(
            "apps.meetings.processing.corrections.tracked_openai_call",
            side_effect=lambda call, *args, **kwargs: call(),
        ),
    ):
        OpenAIMinutesProvider("key", {"system_prompt": "Ata customizada"}).generate("Texto")
        OpenAIMindMapProvider("key", {"system_prompt": "Mapa customizado"}).generate(
            SimpleNamespace(resumo_executivo="Resumo", topicos=[], decisoes=[], tarefas=[])
        )
        OpenAICorrectionProvider("key", {"system_prompt": "Correção customizada"}).suggest(
            [{"id": 1, "texto": "Teste"}]
        )
    assert [item["input"][0]["content"] for item in used] == [
        "Ata customizada",
        "Mapa customizado",
        "Correção customizada",
    ]


@pytest.mark.django_db
def test_sector_media_duration_limit_is_server_side_and_rejects_oversize(
    api, user, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    sector = user.membership.sector
    path = f"/api/admin/sectors/{sector.id}/"
    assert api.patch(path, {"max_upload_minutes": 0}, format="json").status_code == 400
    assert api.patch(path, {"max_upload_minutes": 5}, format="json").status_code == 200
    sector.refresh_from_db()
    meeting = Meeting.objects.create(owner=user, title="Duração")

    def media():
        return SimpleUploadedFile("meeting.mp3", b"ID3" + b"x" * 100)

    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.processing.pipeline.duration_seconds", return_value=301),
    ):
        with pytest.raises(ValidationError):
            save_original(meeting, media())
    assert not (tmp_path / "reunioes" / str(meeting.id) / "original.mp3").exists()
    with (
        patch("apps.meetings.storage.probe_audio"),
        patch("apps.meetings.processing.pipeline.duration_seconds", return_value=300),
    ):
        relative = save_original(meeting, media())
    assert (tmp_path / relative).is_file()
