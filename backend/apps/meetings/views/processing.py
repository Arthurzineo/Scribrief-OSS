import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.change_tracking import fingerprint
from apps.audit.models import record_audit

from ..access import readable_meetings
from ..job_state import accept_job, finish_job
from ..models import MeetingStatus
from ..processing.pipeline import MediaError, duration_seconds
from ..processing.transcription_progress import transcription_progress
from ..serializers import (
    StatusSerializer,
    TranscriptionProgressSerializer,
    UploadSerializer,
)
from ..serializers.processing import ConfirmUploadSerializer, StagedUploadSerializer
from ..services import (
    Conflict,
    minutes_generation_stuck,
)
from ..services.media_quota import reserve_monthly_media
from ..services.staged_upload import STAGED_UPLOAD_TTL, discard_staged_upload
from ..storage import safe_media_path, save_original
from ..throttles import UploadThrottle
from .common import _require_sector_key


def _accept_uploaded_media(meeting, request, duration):
    """Caller holds the meeting row lock and an active DB transaction."""
    monthly_usage = reserve_monthly_media(meeting, duration)
    meeting.consent_confirmed_at = timezone.now()
    meeting.staged_at = None
    meeting.job_id = uuid.uuid4()
    meeting.job_claimed = False
    meeting.job_started_at = None
    meeting.save(update_fields=[
        "original_path", "original_name", "consent_confirmed_at", "staged_at",
        "job_id", "job_claimed", "job_started_at", "updated_at",
    ])
    accept_job(meeting, meeting.job_id, "transcription", duration)
    record_audit(
        request.user, "upload_confirmed", meeting.id, request=request,
        sector=meeting.sector, target_type="meeting", target_ref=meeting.id,
        details={
            "job_id": str(meeting.job_id),
            "file_extension": Path(meeting.original_name).suffix.lower(),
            "filename_fingerprint": fingerprint(meeting.original_name),
            "bytes": safe_media_path(meeting.original_path).stat().st_size,
            "duration_seconds": str(duration),
            "monthly_period": monthly_usage.period.isoformat(),
            "monthly_used_seconds": str(monthly_usage.used_seconds),
            "consent_confirmed": True,
            "state": "accepted_pending_dispatch",
        },
    )


def _dispatch_transcription(meeting, request, duration):
    from ..transcription_jobs import enqueue_transcription

    try:
        enqueue_transcription(meeting, duration)
    except Exception:
        finish_job(meeting.job_id, "failed", "queue_unavailable")
        meeting.status = MeetingStatus.ERRO
        meeting.error_code = "queue_unavailable"
        meeting.error_message = "Fila temporariamente indisponível."
        meeting.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        record_audit(
            request.user, "upload_dispatch_failed", meeting.id, outcome="failed",
            request=request, sector=meeting.sector, target_type="meeting",
            target_ref=meeting.id, details={"job_id": str(meeting.job_id),
                                            "error_code": "queue_unavailable"},
        )
        return Response(
            {"error": {
                "code": "queue_unavailable",
                "message": "Fila temporariamente indisponível.",
            }},
            status=503,
        )
    return Response(
        {"job_id": meeting.job_id, "status": meeting.status,
         "error_code": "", "error_message": ""},
        status=status.HTTP_202_ACCEPTED,
    )


class ProcessingMixin:
    @extend_schema(
        request=UploadSerializer,
        responses={201: StagedUploadSerializer, 202: StatusSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[UploadThrottle],
    )
    def upload(self, request, pk=None):
        meeting = self.get_object()
        _require_sector_key(meeting.sector_id)
        declared_size = request.META.get("CONTENT_LENGTH")
        if (
            declared_size
            and declared_size.isdigit()
            and int(declared_size) > settings.MAX_UPLOAD_BYTES + 1024 * 1024
        ):
            return Response(
                {
                    "error": {
                        "code": "file_too_large",
                        "message": "Arquivo acima do limite configurado.",
                    }
                },
                status=413,
            )
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The file write and state transition share the meeting row lock. A concurrent
        # delete/upload cannot purge or replace the media halfway through this request.
        relative_path = None
        try:
            with transaction.atomic():
                meeting = type(meeting).objects.select_for_update().get(pk=meeting.pk)
                if meeting.deletion_requested_at is not None:
                    raise NotFound()
                if (meeting.original_path or meeting.job_id
                        or meeting.status != MeetingStatus.ENVIADO):
                    return Response(
                        {"error": {
                            "code": "conflict",
                            "message": "A reunião já possui um arquivo enviado.",
                        }},
                        status=409,
                    )
                relative_path = save_original(meeting, serializer.validated_data["file"])
                meeting.original_path = relative_path
                meeting.original_name = serializer.validated_data["file"].name[:255]
                if serializer.validated_data["consent_confirmed"]:
                    try:
                        duration = duration_seconds(safe_media_path(relative_path))
                    except MediaError as exc:
                        raise ValidationError({
                            "file": "Não foi possível medir a duração da mídia."
                        }) from exc
                    _accept_uploaded_media(meeting, request, duration)
                else:
                    meeting.staged_at = timezone.now()
                    meeting.save(update_fields=[
                        "original_path", "original_name", "staged_at", "updated_at",
                    ])
                    record_audit(
                        request.user, "upload_staged", meeting.id, request=request,
                        sector=meeting.sector, target_type="meeting", target_ref=meeting.id,
                        details={
                            "file_extension": Path(meeting.original_name).suffix.lower(),
                            "filename_fingerprint": fingerprint(meeting.original_name),
                            "bytes": serializer.validated_data["file"].size,
                            "expires_at": (meeting.staged_at + STAGED_UPLOAD_TTL).isoformat(),
                        },
                    )
        except Exception:
            if relative_path is not None:
                safe_media_path(relative_path).unlink(missing_ok=True)
            raise
        if serializer.validated_data["consent_confirmed"]:
            return _dispatch_transcription(meeting, request, duration)
        return Response({
            "meeting_id": meeting.id, "awaiting_consent": True,
            "expires_at": meeting.staged_at + STAGED_UPLOAD_TTL,
        }, status=status.HTTP_201_CREATED)

    @extend_schema(request=ConfirmUploadSerializer, responses={202: StatusSerializer})
    @action(detail=True, methods=["post"], url_path="confirm-upload")
    def confirm_upload(self, request, pk=None):
        meeting = self.get_object()
        serializer = ConfirmUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _require_sector_key(meeting.sector_id)
        with transaction.atomic():
            meeting = type(meeting).objects.select_for_update().get(pk=meeting.pk)
            if (meeting.deletion_requested_at is not None or meeting.staged_at is None
                    or not meeting.original_path or meeting.job_id is not None
                    or meeting.consent_confirmed_at is not None
                    or meeting.status != MeetingStatus.ENVIADO):
                raise Conflict("O envio não está aguardando confirmação.")
            if timezone.now() >= meeting.staged_at + STAGED_UPLOAD_TTL:
                return Response({
                    "error": {
                        "code": "staged_expired",
                        "message": "O envio temporário expirou. Envie o arquivo novamente.",
                    }
                }, status=status.HTTP_410_GONE)
            try:
                duration = duration_seconds(safe_media_path(meeting.original_path))
            except MediaError as exc:
                raise ValidationError({
                    "file": "Não foi possível medir a duração da mídia."
                }) from exc
            _accept_uploaded_media(meeting, request, duration)
        return _dispatch_transcription(meeting, request, duration)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"], url_path="discard-upload")
    def discard_upload(self, request, pk=None):
        meeting = self.get_object()
        discard_staged_upload(meeting.id, actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=StatusSerializer)
    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        # Polling needs only job fields; the regular detail queryset aggregates
        # speakers and all segments and must not run every three seconds.
        meeting = get_object_or_404(
            readable_meetings(request.user).only(
                "job_id", "status", "error_code", "error_message",
                "job_started_at", "updated_at",
            ),
            pk=pk,
        )
        self.check_object_permissions(request, meeting)
        return Response(
            {
                "job_id": meeting.job_id,
                "status": meeting.status,
                "error_code": meeting.error_code,
                "error_message": meeting.error_message,
                "minutes_stuck": minutes_generation_stuck(meeting),
            }
        )

    @extend_schema(responses=TranscriptionProgressSerializer)
    @action(detail=True, methods=["get"], url_path="progress")
    def progress(self, request, pk=None):
        return Response(transcription_progress(self.get_object()))

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        meeting = self.get_object()
        retrying_minutes = (
            meeting.error_code in ("minutes_failed", "minutes_queue_unavailable")
            and meeting.segments.exists()
        ) or minutes_generation_stuck(meeting)
        _require_sector_key(
            meeting.sector_id, "minutes" if retrying_minutes else "transcription_chunk"
        )
        if (
            meeting.status == MeetingStatus.ERRO
            and meeting.error_code in ("minutes_failed", "minutes_queue_unavailable")
            and meeting.segments.exists()
        ) or minutes_generation_stuck(meeting):
            meeting.job_id = uuid.uuid4()
            meeting.job_claimed = False
            meeting.job_started_at = None
            meeting.status = MeetingStatus.GERANDO_ATA
            meeting.error_code = ""
            meeting.error_message = ""
            meeting.save(
                update_fields=[
                    "job_id",
                    "job_claimed",
                    "job_started_at",
                    "status",
                    "error_code",
                    "error_message",
                    "updated_at",
                ]
            )
            from ..tasks import generate_minutes

            try:
                accept_job(meeting, meeting.job_id, "minutes")
                generate_minutes.delay(str(meeting.id), str(meeting.job_id))
            except Exception:
                finish_job(meeting.job_id, "failed", "queue_unavailable")
                meeting.status = MeetingStatus.ERRO
                meeting.error_code = "minutes_queue_unavailable"
                meeting.error_message = "Fila temporariamente indisponível."
                meeting.save(update_fields=["status", "error_code", "error_message", "updated_at"])
                return Response(
                    {"error": {"code": meeting.error_code, "message": meeting.error_message}},
                    status=503,
                )
            return Response(
                {"job_id": meeting.job_id, "status": MeetingStatus.GERANDO_ATA}, status=202
            )
        from ..transcription_jobs import transcription_stale_after_seconds

        stale = (
            meeting.status in (MeetingStatus.EXTRAINDO_AUDIO, MeetingStatus.TRANSCREVENDO)
            and meeting.job_started_at
            and meeting.job_started_at
            < timezone.now() - timedelta(seconds=transcription_stale_after_seconds(meeting))
        )
        if not ((meeting.status == MeetingStatus.ERRO or stale) and meeting.original_path):
            raise Conflict("Sem original ou estado elegível para nova tentativa.")
        meeting.job_id = uuid.uuid4()
        meeting.job_claimed = False
        meeting.job_started_at = None
        meeting.status = MeetingStatus.ENVIADO
        meeting.error_code = ""
        meeting.error_message = ""
        meeting.save(
            update_fields=[
                "job_id",
                "job_claimed",
                "job_started_at",
                "status",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        from ..transcription_jobs import enqueue_transcription

        try:
            enqueue_transcription(meeting)
        except Exception:
            meeting.status = MeetingStatus.ERRO
            meeting.error_code = "queue_unavailable"
            meeting.error_message = "Fila temporariamente indisponível."
            meeting.save(update_fields=["status", "error_code", "error_message", "updated_at"])
            return Response(
                {"error": {"code": "queue_unavailable", "message": meeting.error_message}},
                status=503,
            )
        return Response({"job_id": meeting.job_id, "status": MeetingStatus.ENVIADO}, status=202)
