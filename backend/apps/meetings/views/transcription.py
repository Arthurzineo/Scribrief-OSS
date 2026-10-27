import uuid
from io import BytesIO

from django.core.cache import cache
from django.db import transaction
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.audit.models import record_audit

from ..access import readable_meetings
from ..correction_jobs import CORRECTION_JOB_TTL, active_key, result_key
from ..exports import render_transcript, transcript_payload
from ..job_state import accept_job, finish_job
from ..models import MeetingStatus
from ..processing.corrections import MAX_TRANSCRIPT_CHARS
from ..serializers import (
    CorrectionRequestSerializer,
    CorrectionResponseSerializer,
    TranscriptionEditSerializer,
)
from ..services import (
    Conflict,
    edit_segments,
)
from .common import _require_sector_key


class TranscriptionMixin:
    @action(detail=True, methods=["get", "patch"], url_path="transcription")
    def transcription(self, request, pk=None):
        meeting = self.get_object()
        readable = meeting.status in (
            MeetingStatus.TRANSCRITO,
            MeetingStatus.ATA_PRONTA,
            MeetingStatus.GERANDO_ATA,
        ) or (
            meeting.status == MeetingStatus.ERRO
            and meeting.error_code in ("minutes_failed", "minutes_queue_unavailable")
        )
        if not readable or (
            request.method != "GET"
            and meeting.status not in (MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA)
        ):
            raise Conflict("Transcrição indisponível.")
        if request.method == "GET":
            record_audit(request.user, "transcription_viewed", meeting.id, request=request)
            return Response(transcript_payload(meeting))
        serializer = TranscriptionEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = edit_segments(
            meeting,
            serializer.validated_data["segmentos"],
            serializer.validated_data["version"],
            request.user,
            request,
        )
        return Response(transcript_payload(current))

    @extend_schema(
        request=CorrectionRequestSerializer,
        responses={200: CorrectionResponseSerializer, 202: CorrectionResponseSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="correction-suggestions")
    def correction_suggestions(self, request, pk=None):
        meeting = self.get_object()
        if request.method == "GET":
            job_id = request.query_params.get("job_id", "")
            try:
                uuid.UUID(job_id)
            except (ValueError, TypeError):
                raise ValidationError({"job_id": "Identificador de análise inválido."}) from None
            result = cache.get(result_key(job_id))
            if not result or result.get("meeting_id") != str(meeting.id):
                raise NotFound("Análise não encontrada ou expirada.")
            return Response(result, status=202 if result["status"] == "processing" else 200)
        if meeting.status not in (MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA):
            raise Conflict("Transcrição indisponível para revisão.")
        _require_sector_key(meeting.sector_id, "correction", user_id=meeting.owner_id)
        serializer = CorrectionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = serializer.validated_data["version"]
        if meeting.transcription_version != version:
            raise Conflict()
        segments = list(meeting.segments.order_by("order").values("id", "text"))
        payload = [{"id": item["id"], "texto": item["text"]} for item in segments]
        if sum(len(item["texto"]) for item in payload) > MAX_TRANSCRIPT_CHARS:
            raise ValidationError({"transcricao": "Transcrição longa demais para esta análise."})
        key = active_key(meeting.id, version)
        job_id = str(uuid.uuid4())
        if not cache.add(key, job_id, timeout=CORRECTION_JOB_TTL):
            existing = cache.get(key)
            result = cache.get(result_key(existing)) if existing else None
            if result:
                return Response(result, status=202 if result["status"] == "processing" else 200)
            raise Conflict("Uma análise já foi solicitada. Tente novamente em instantes.")
        result = {"job_id": job_id, "meeting_id": str(meeting.id), "version": version,
                  "status": "processing", "sugestoes": []}
        cache.set(result_key(job_id), result, timeout=CORRECTION_JOB_TTL)
        from ..tasks import analyze_transcription_corrections

        try:
            accept_job(meeting, job_id, "correction")
            analyze_transcription_corrections.delay(str(meeting.id), version, job_id)
        except Exception:
            finish_job(job_id, "failed", "queue_unavailable")
            cache.delete(key)
            cache.delete(result_key(job_id))
            return Response(
                {"error": {
                    "code": "queue_unavailable",
                    "message": "Fila temporariamente indisponível.",
                }},
                status=503,
            )
        record_audit(request.user, "transcription_correction_requested", meeting.id,
                     request=request)
        return Response(result, status=202)

    @action(detail=True, methods=["get"], url_path="transcription/download")
    def transcription_download(self, request, pk=None):
        meeting = self.get_object()
        if meeting.status not in (MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA):
            raise Conflict("Transcrição indisponível.")
        fmt = request.query_params.get("format", "md")
        if fmt not in ("md", "json"):
            raise ValidationError({"format": "Use md ou json."})
        # A saved export may be stale; hold the meeting lock while taking a DB snapshot.
        with transaction.atomic():
            current = (
                readable_meetings(request.user).select_for_update()
                .filter(pk=meeting.pk).first()
            )
            if current is None:
                raise NotFound()
            if current.status not in (
                MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA
            ):
                raise Conflict("Transcrição indisponível.")
            content = render_transcript(current, fmt).encode("utf-8")
        record_audit(request.user, "transcription_download", meeting.id, request=request)
        response = FileResponse(
            BytesIO(content), as_attachment=True, filename=f"transcricao.{fmt}"
        )
        response["Cache-Control"] = "private, no-store"
        return response
