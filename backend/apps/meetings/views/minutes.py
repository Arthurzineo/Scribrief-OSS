import uuid
from io import BytesIO

from django.db import transaction
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.audit.models import record_audit

from ..access import readable_meetings
from ..exports import minutes_payload, render_minutes
from ..job_state import accept_job, finish_job
from ..models import MeetingStatus
from ..serializers import (
    MinutesResponseSerializer,
    MinutesReviewSerializer,
    MinutesSerializer,
)
from ..services import (
    Conflict,
    edit_minutes,
    review_minutes,
)
from .common import _require_sector_key


class MinutesMixin:
    @action(detail=True, methods=["get", "post", "patch"], url_path="minutes")
    def minutes(self, request, pk=None):
        meeting = self.get_object()
        if request.method == "POST":
            _require_sector_key(meeting.sector_id, "minutes")
            with transaction.atomic():
                current = type(meeting).objects.select_for_update().get(pk=meeting.pk)
                if current.deletion_requested_at is not None:
                    raise NotFound()
                if current.status not in (MeetingStatus.TRANSCRITO, MeetingStatus.ATA_PRONTA):
                    raise Conflict("É necessária transcrição pronta e sem ata em processamento.")
                current.job_id = uuid.uuid4()
                current.job_claimed = False
                current.job_started_at = None
                current.status = MeetingStatus.GERANDO_ATA
                current.save(
                    update_fields=[
                        "job_id",
                        "job_claimed",
                        "job_started_at",
                        "status",
                        "updated_at",
                    ]
                )
                accept_job(current, current.job_id, "minutes")
            from ..tasks import generate_minutes

            try:
                generate_minutes.delay(str(current.id), str(current.job_id))
            except Exception:
                finish_job(current.job_id, "failed", "queue_unavailable")
                current.status = MeetingStatus.ERRO
                current.error_code = "minutes_queue_unavailable"
                current.error_message = "Fila temporariamente indisponível."
                current.save(update_fields=["status", "error_code", "error_message", "updated_at"])
                return Response(
                    {"error": {"code": "queue_unavailable", "message": current.error_message}},
                    status=503,
                )
            record_audit(
                request.user, "minutes_requested", meeting.id, request=request,
                sector=meeting.sector, target_type="meeting", target_ref=meeting.id,
                details={"job_id": str(current.job_id),
                         "transcription_version": current.transcription_version},
            )
            return Response(
                {"job_id": current.job_id, "status": MeetingStatus.GERANDO_ATA}, status=202
            )
        if meeting.status != MeetingStatus.ATA_PRONTA:
            raise Conflict("Ata indisponível.")
        if request.method == "GET":
            record_audit(request.user, "minutes_viewed", meeting.id, request=request)
            return Response({"version": meeting.minutes_version, **minutes_payload(meeting)})
        version = request.data.get("version")
        if not isinstance(version, int):
            raise ValidationError({"version": "Versão obrigatória."})
        serializer = MinutesSerializer(
            meeting.minutes,
            data={k: v for k, v in request.data.items() if k != "version"},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        current = edit_minutes(
            meeting, serializer.validated_data, version, request.user, request
        )
        return Response({"version": current.minutes_version, **minutes_payload(current)})

    @extend_schema(request=MinutesReviewSerializer, responses=MinutesResponseSerializer)
    @action(detail=True, methods=["post"], url_path="minutes/review")
    def minutes_review(self, request, pk=None):
        meeting = self.get_object()
        serializer = MinutesReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = review_minutes(
            meeting, serializer.validated_data["version"], request.user, request
        )
        return Response({"version": current.minutes_version, **minutes_payload(current)})

    @action(detail=True, methods=["get"], url_path="minutes/download")
    def minutes_download(self, request, pk=None):
        meeting = self.get_object()
        if meeting.status != MeetingStatus.ATA_PRONTA:
            raise Conflict("Ata indisponível.")
        fmt = request.query_params.get("format", "md")
        if fmt not in ("md", "json"):
            raise ValidationError({"format": "Use md ou json."})
        # Recheck access and serialize with edits/transfers before reading the snapshot.
        with transaction.atomic():
            current = (
                readable_meetings(request.user).select_for_update()
                .filter(pk=meeting.pk).first()
            )
            if current is None:
                raise NotFound()
            if current.status != MeetingStatus.ATA_PRONTA:
                raise Conflict("Ata indisponível.")
            content = render_minutes(current, fmt).encode("utf-8")
        record_audit(request.user, "minutes_download", meeting.id, request=request)
        response = FileResponse(BytesIO(content), as_attachment=True, filename=f"ata.{fmt}")
        response["Cache-Control"] = "private, no-store"
        return response
