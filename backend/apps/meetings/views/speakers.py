import re
import uuid

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.audit.models import record_audit

from ..job_state import accept_job, finish_job
from ..models import Meeting, MeetingStatus, SpeakerAnalysis
from ..serializers import (
    SpeakerSuggestionsDismissSerializer,
    SpeakerSuggestionsRequestSerializer,
    SpeakerSuggestionsResponseSerializer,
)
from ..services import (
    Conflict,
    merge_speakers,
    merge_speakers_batch,
    rename_speaker,
)
from ..storage import safe_media_path
from .common import _require_sector_key, _speaker_analysis_payload


class SpeakersMixin:
    @action(detail=True, methods=["get"], url_path="speakers")
    def speakers(self, request, pk=None):
        meeting = self.get_object()
        return Response(
            {
                "version": meeting.transcription_version,
                "falantes": [
                    {"falante_id": s.code, "nome": s.name}
                    for s in meeting.speakers.filter(merged_into__isnull=True)
                ],
            }
        )

    @action(detail=True, methods=["patch"], url_path=r"speakers/(?P<code>[A-Z]+)")
    def speaker(self, request, pk=None, code=None):
        meeting = self.get_object()
        name = request.data.get("nome")
        version = request.data.get("version")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 100
            or not isinstance(version, int)
        ):
            raise ValidationError({"nome": "Nome e versão válidos são obrigatórios."})
        current = rename_speaker(meeting, code, name.strip(), version, request.user, request)
        return Response({"version": current.transcription_version})

    @action(detail=True, methods=["post"], url_path="speakers/merge")
    def speaker_merge(self, request, pk=None):
        meeting = self.get_object()
        source, target, version = (
            request.data.get("source"),
            request.data.get("target"),
            request.data.get("version"),
        )
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or not isinstance(version, int)
        ):
            raise ValidationError({"source": "source, target e version são obrigatórios."})
        current = merge_speakers(meeting, source, target, version, request.user, request)
        return Response({"version": current.transcription_version})

    @action(detail=True, methods=["post"], url_path="speakers/merge-batch")
    def speaker_merge_batch(self, request, pk=None):
        meeting = self.get_object()
        sources = request.data.get("sources")
        target = request.data.get("target")
        version = request.data.get("version")
        if (
            not isinstance(sources, list)
            or not sources
            or len(sources) > 128
            or any(
                not isinstance(code, str) or not re.fullmatch(r"[A-Z]+", code)
                for code in sources
            )
            or not isinstance(target, str)
            or not re.fullmatch(r"[A-Z]+", target)
            or not isinstance(version, int)
        ):
            raise ValidationError(
                {"sources": "sources, target e version válidos são obrigatórios."}
            )
        current = merge_speakers_batch(
            meeting, sources, target, version, request.user, request
        )
        return Response({"version": current.transcription_version})

    @extend_schema(
        methods=["GET"],
        parameters=[OpenApiParameter("job_id", OpenApiTypes.UUID, OpenApiParameter.QUERY)],
        responses={
            200: SpeakerSuggestionsResponseSerializer,
            202: SpeakerSuggestionsResponseSerializer,
        },
    )
    @extend_schema(
        methods=["POST"], request=SpeakerSuggestionsRequestSerializer,
        responses={
            200: SpeakerSuggestionsResponseSerializer,
            202: SpeakerSuggestionsResponseSerializer,
        },
    )
    @action(detail=True, methods=["get", "post"], url_path="speaker-suggestions")
    def speaker_suggestions(self, request, pk=None):
        meeting = self.get_object()
        if request.method == "GET":
            analysis = SpeakerAnalysis.objects.filter(meeting=meeting).first()
            job_id = request.query_params.get("job_id")
            if job_id:
                try:
                    uuid.UUID(job_id)
                except (ValueError, TypeError):
                    raise ValidationError({"job_id": "Identificador inválido."}) from None
                if not analysis or str(analysis.job_id) != job_id:
                    raise NotFound("Análise não encontrada.")
            if (
                analysis and analysis.status == "processing"
                and analysis.version != meeting.transcription_version
            ):
                raise Conflict("A transcrição mudou. Solicite uma nova análise.")
            result = _speaker_analysis_payload(meeting, analysis)
            return Response(result, status=202 if result["status"] == "processing" else 200)
        if meeting.status not in (MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA):
            raise Conflict("Transcrição indisponível para análise.")
        _require_sector_key(meeting.sector_id, "speaker_reconciliation")
        serializer = SpeakerSuggestionsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = serializer.validated_data["version"]
        if version != meeting.transcription_version:
            raise Conflict()
        if not meeting.audio_path or not safe_media_path(meeting.audio_path).is_file():
            raise Conflict("Áudio não disponível para análise.")
        with transaction.atomic():
            locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
            if locked.deletion_requested_at is not None:
                raise NotFound()
            if locked.transcription_version != version:
                raise Conflict()
            analysis, _ = SpeakerAnalysis.objects.select_for_update().get_or_create(meeting=locked)
            existing = _speaker_analysis_payload(locked, analysis)
            if analysis.status == "processing":
                return Response(existing, status=202)
            if analysis.status == "ready" and existing["groups"]:
                return Response(existing)
            if analysis.uses >= 2:
                raise Conflict("O limite de duas análises de falantes desta reunião foi atingido.")
            job_id = uuid.uuid4()
            analysis.uses += 1
            analysis.job_id = job_id
            analysis.version = version
            analysis.status = "processing"
            analysis.groups = []
            analysis.caution = False
            analysis.sample_times = {}
            analysis.message = ""
            analysis.save()
            accept_job(locked, job_id, "speaker_reconciliation")
            result = _speaker_analysis_payload(locked, analysis)
        from ..tasks import analyze_speaker_reconciliation

        try:
            analyze_speaker_reconciliation.delay(str(meeting.id), version, job_id)
        except Exception:
            finish_job(job_id, "failed", "queue_unavailable")
            with transaction.atomic():
                analysis = SpeakerAnalysis.objects.select_for_update().get(meeting=meeting)
                if analysis.job_id == job_id and analysis.status == "processing":
                    analysis.uses -= 1
                    analysis.status = "error"
                    analysis.message = "Fila temporariamente indisponível."
                    analysis.save(update_fields=["uses", "status", "message", "updated_at"])
            return Response({"error": {
                "code": "queue_unavailable", "message": "Fila temporariamente indisponível.",
            }}, status=503)
        record_audit(request.user, "speaker_reconciliation_requested", meeting.id,
                     request=request)
        return Response(result, status=202)

    @extend_schema(
        request=SpeakerSuggestionsDismissSerializer,
        responses={200: SpeakerSuggestionsResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="speaker-suggestions/dismiss")
    def speaker_suggestions_dismiss(self, request, pk=None):
        meeting = self.get_object()
        serializer = SpeakerSuggestionsDismissSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["version"] != meeting.transcription_version:
            raise Conflict()
        with transaction.atomic():
            analysis = SpeakerAnalysis.objects.select_for_update().filter(meeting=meeting).first()
            if not analysis or analysis.status != "ready":
                raise Conflict("Não há sugestões prontas para dispensar.")
            codes = serializer.validated_data.get("codes")
            if codes is not None:
                if codes not in analysis.groups:
                    raise ValidationError({"codes": "Grupo de falantes não encontrado."})
                analysis.groups = [group for group in analysis.groups if group != codes]
            else:
                analysis.groups = []
            if not analysis.groups:
                analysis.status = "dismissed"
                analysis.caution = False
                analysis.sample_times = {}
            analysis.save(update_fields=[
                "groups", "status", "caution", "sample_times", "updated_at",
            ])
            result = _speaker_analysis_payload(meeting, analysis)
        record_audit(request.user, "speaker_reconciliation_dismissed", meeting.id,
                     request=request)
        return Response(result)
