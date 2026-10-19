from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.meetings.models import Meeting, MeetingStatus, Minutes
from apps.meetings.processing.mind_map import (
    MindMapError,
    OpenAIMindMapProvider,
    validate_mind_map_data,
)
from apps.meetings.tasks import generate_mind_map


def test_map_validation_requires_short_connected_keywords():
    valid = {"centro": "Planejamento", "ramos": [
        {"titulo": "Logística", "pontos": ["Café até outubro", "Equipe responsável"]},
    ]}
    assert validate_mind_map_data(valid) == valid
    with pytest.raises(MindMapError):
        validate_mind_map_data({"centro": "Planejamento", "ramos": [
            {"titulo": "Logística", "pontos": [
                "Este é um parágrafo longo que não cabe em um mapa mental e repete toda a ata"
            ]},
        ]})


@pytest.mark.django_db
def test_map_provider_uses_dedicated_short_prompt_and_structured_output(settings):
    settings.MODELO_MAPA = "gpt-6-luna"
    source = Minutes(
        resumo_executivo="Planejamento do encontro.",
        topicos=[{"titulo": "Logística", "comentario": "Café será providenciado."}],
        decisoes=["Aprovar café"], tarefas=[],
    )
    with patch("apps.meetings.processing.mind_map._client") as client:
        client.return_value.responses.create.return_value.output_text = (
            '{"centro":"Encontro","ramos":[{"titulo":"Logística",'
            '"pontos":["Café aprovado"]}]}'
        )
        result = OpenAIMindMapProvider().generate(source)
    call = client.return_value.responses.create.call_args.kwargs
    assert call["model"] == "gpt-6-luna"
    assert "não atas" in call["input"][0]["content"]
    assert "8 palavras" in call["input"][0]["content"]
    assert call["text"]["format"]["strict"] is True
    assert result["ramos"][0]["pontos"] == ["Café aprovado"]


@pytest.mark.django_db
def test_mind_map_is_generated_from_minutes_and_invalidated_by_edit(
    api, user, other_user, settings
):
    meeting = Meeting.objects.create(
        owner=user, title="Planejamento", status=MeetingStatus.ATA_PRONTA,
        minutes_version=1,
    )
    Minutes.objects.create(
        meeting=meeting, resumo_executivo="Equipe organizou o encontro.",
        topicos=[{"titulo": "Logística", "comentario": "Café será providenciado."}],
        decisoes=["Aprovar café"], tarefas=[], participantes=["Ana"],
    )
    url = f"/api/v1/meetings/{meeting.id}/mind-map/"
    assert api.get(url).data["status"] == "none"
    generated = {"centro": "Encontro", "ramos": [
        {"titulo": "Logística", "pontos": ["Café aprovado", "Providenciar café"]},
    ]}
    with patch("apps.meetings.jobs.mind_map.mind_map_provider") as provider:
        provider.return_value.generate.return_value = generated
        response = api.post(url, {}, format="json")
    assert response.status_code == 202
    ready = api.get(url)
    assert ready.data["status"] == "ready"
    assert ready.data["mapa"] == generated
    generated_event = AuditEvent.objects.get(action="mind_map_generated", target_id=meeting.id)
    assert generated_event.details["minutes_version"] == 1
    assert generated_event.details["job_id"]
    assert "Café aprovado" not in str(generated_event.details)
    reviewed = api.post(
        f"/api/v1/meetings/{meeting.id}/minutes/review/",
        {"version": 1}, format="json",
    )
    assert reviewed.status_code == 200
    assert api.get(url).data["status"] == "ready"
    meeting.minutes_version = 3
    meeting.save(update_fields=["minutes_version"])
    assert api.get(url).data["status"] == "stale"
    foreign = Meeting.objects.create(owner=other_user, title="Privado")
    assert api.get(f"/api/v1/meetings/{foreign.id}/mind-map/").status_code == 404


@pytest.mark.django_db
def test_map_provider_failure_can_be_retried_without_losing_minutes(api, user):
    meeting = Meeting.objects.create(
        owner=user, title="Planejamento", status=MeetingStatus.ATA_PRONTA,
        minutes_version=1,
    )
    minutes = Minutes.objects.create(
        meeting=meeting, resumo_executivo="Planejamento.",
        topicos=[{"titulo": "Pauta", "comentario": "Revisada."}],
    )
    url = f"/api/v1/meetings/{meeting.id}/mind-map/"
    with patch("apps.meetings.jobs.mind_map.mind_map_provider") as provider:
        provider.return_value.generate.side_effect = RuntimeError("falha simulada")
        assert api.post(url, {}, format="json").status_code == 202
    assert api.get(url).data["status"] == "error"
    minutes.refresh_from_db()
    assert minutes.resumo_executivo == "Planejamento."
    with patch("apps.meetings.jobs.mind_map.mind_map_provider") as provider:
        provider.return_value.generate.return_value = {
            "centro": "Planejamento", "ramos": [{"titulo": "Pauta", "pontos": ["Revisão"]}],
        }
        assert api.post(url, {}, format="json").status_code == 202
    assert api.get(url).data["status"] == "ready"


@pytest.mark.django_db
def test_stuck_map_job_can_be_restarted_without_old_job_overwriting(api, user):
    meeting = Meeting.objects.create(
        owner=user, title="Planejamento", status=MeetingStatus.ATA_PRONTA,
        minutes_version=1,
    )
    minutes = Minutes.objects.create(
        meeting=meeting, resumo_executivo="Planejamento.",
        topicos=[{"titulo": "Pauta", "comentario": "Revisada."}],
    )
    url = f"/api/v1/meetings/{meeting.id}/mind-map/"
    with patch("apps.meetings.tasks.generate_mind_map.delay"):
        assert api.post(url, {}, format="json").status_code == 202
        minutes.refresh_from_db()
        old_job = str(minutes.mind_map_job_id)
        Minutes.objects.filter(pk=minutes.pk).update(
            updated_at=timezone.now() - timedelta(minutes=11)
        )
        assert api.get(url).data["status"] == "error"
        assert api.post(url, {}, format="json").status_code == 202
    minutes.refresh_from_db()
    assert str(minutes.mind_map_job_id) != old_job
    assert generate_mind_map(str(meeting.id), 1, old_job) == "ignored"
    minutes.refresh_from_db()
    assert minutes.mind_map_status == "generating"
