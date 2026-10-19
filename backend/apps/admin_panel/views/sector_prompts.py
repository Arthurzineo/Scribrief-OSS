"""Staff-only, versioned system prompts scoped to a sector."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Sector, SectorAIPrompt
from apps.audit.change_tracking import fingerprint
from apps.audit.models import record_audit
from apps.meetings.processing.prompt_defaults import SYSTEM_PROMPT_DEFAULTS

from ..permissions import ActiveStaff
from ..serializers.sector_prompts import (
    SectorPromptListSerializer,
    SectorPromptResetSerializer,
    SectorPromptSerializer,
    SectorPromptWriteSerializer,
)

LABELS = {
    "minutes": "Geração da ata",
    "mind_map": "Mapa mental",
    "correction": "Sugestões de correção da transcrição",
}


class PromptVersionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "As instruções foram alteradas por outro administrador. "
        "Recarregue antes de salvar."
    )
    default_code = "prompt_version_conflict"


def _prompt_payload(kind, override):
    return {
        "kind": kind,
        "label": LABELS[kind],
        "text": override.text if override else SYSTEM_PROMPT_DEFAULTS[kind],
        "source": "custom" if override else "default",
        "version": override.version if override else 0,
        "updated_at": override.updated_at if override else None,
    }


def _reauth(request):
    password = request.data.get("current_password")
    if not isinstance(password, str) or not request.user.check_password(password):
        raise PermissionDenied("Confirme sua senha para alterar as instruções do setor.")


def _expected_version(request):
    value = request.data.get("expected_version")
    if type(value) is not int or value < 0:
        raise ValidationError({"expected_version": "Versão atual obrigatória."})
    return value


class SectorPromptListView(APIView):
    permission_classes = [ActiveStaff]

    @extend_schema(responses=SectorPromptListSerializer)
    def get(self, request, sector_id):
        sector = get_object_or_404(Sector, pk=sector_id)
        overrides = {item.kind: item for item in SectorAIPrompt.objects.filter(sector=sector)}
        return Response({
            "sector_id": sector.id,
            "prompts": [
                _prompt_payload(kind, overrides.get(kind)) for kind in SYSTEM_PROMPT_DEFAULTS
            ],
            "transcription_note": (
                "A API de transcrição diarizada atual não aceita instruções de sistema; "
                "não existe campo editável para ela."
            ),
        })


class SectorPromptDetailView(APIView):
    permission_classes = [ActiveStaff]

    @extend_schema(request=SectorPromptWriteSerializer, responses=SectorPromptSerializer)
    def put(self, request, sector_id, kind):
        if kind not in SYSTEM_PROMPT_DEFAULTS:
            raise ValidationError({"kind": "Prompt desconhecido."})
        _reauth(request)
        expected = _expected_version(request)
        value = request.data.get("text")
        if (
            not isinstance(value, str)
            or not 20 <= len(value.strip()) <= 8000
            or "\x00" in value
        ):
            raise ValidationError({"text": "Informe de 20 a 8000 caracteres, sem NUL."})
        with transaction.atomic():
            sector = get_object_or_404(Sector.objects.select_for_update(), pk=sector_id)
            override = SectorAIPrompt.objects.select_for_update().filter(
                sector=sector, kind=kind
            ).first()
            current_version = override.version if override else 0
            if expected != current_version:
                raise PromptVersionConflict()
            old_text = override.text if override else SYSTEM_PROMPT_DEFAULTS[kind]
            if override:
                override.text = value.strip()
                override.version += 1
                override.save(update_fields=["text", "version", "updated_at"])
            else:
                override = SectorAIPrompt.objects.create(
                    sector=sector, kind=kind, text=value.strip()
                )
            record_audit(
                request.user, "sector_prompt_updated", request=request,
                sector=sector, target_type="sector", target_ref=sector.id,
                details={"kind": kind, "version": override.version,
                         "before_hash": fingerprint(old_text),
                         "after_hash": fingerprint(override.text)},
            )
        return Response(_prompt_payload(kind, override))

    @extend_schema(request=SectorPromptResetSerializer, responses=SectorPromptSerializer)
    def delete(self, request, sector_id, kind):
        if kind not in SYSTEM_PROMPT_DEFAULTS:
            raise ValidationError({"kind": "Prompt desconhecido."})
        _reauth(request)
        expected = _expected_version(request)
        with transaction.atomic():
            sector = get_object_or_404(Sector.objects.select_for_update(), pk=sector_id)
            override = SectorAIPrompt.objects.select_for_update().filter(
                sector=sector, kind=kind
            ).first()
            current_version = override.version if override else 0
            if expected != current_version:
                raise PromptVersionConflict()
            if override:
                record_audit(
                    request.user, "sector_prompt_reset", request=request,
                    sector=sector, target_type="sector", target_ref=sector.id,
                    details={"kind": kind, "version": current_version,
                             "before_hash": fingerprint(override.text),
                             "after_hash": fingerprint(SYSTEM_PROMPT_DEFAULTS[kind])},
                )
                override.delete()
        return Response(_prompt_payload(kind, None))
