"""Bound multipart ingestion before the parser writes a private temporary file."""

import logging
import re
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import BigIntegerField, Case, F, Sum, Value, When
from django.utils import timezone
from rest_framework.exceptions import APIException, NotAuthenticated, NotFound

from ..models import Meeting, MeetingStatus, UploadGate, UploadLease
from .common import Conflict

logger = logging.getLogger(__name__)
UPLOAD_PATH = re.compile(r"^/api/v1/meetings/([0-9a-fA-F-]{36})/upload/$")
# Must outlive Gunicorn's 3600s hard request timeout. Never reap on a short idle
# timeout: the sender may still be using its reserved capacity.
LEASE_TTL = timedelta(hours=2)


class UploadCapacityExceeded(APIException):
    status_code = 429
    default_code = "upload_capacity"
    default_detail = "Capacidade temporária de envio atingida. Tente novamente mais tarde."


class UploadLengthRequired(APIException):
    status_code = 411
    default_code = "length_required"
    default_detail = "Informe Content-Length para enviar mídia."


class UploadTooLarge(APIException):
    status_code = 413
    default_code = "file_too_large"
    default_detail = "Arquivo acima do limite configurado."


def _staged_bytes(user_id=None):
    qs = Meeting.objects.filter(consent_confirmed_at__isnull=True).exclude(original_path="")
    if user_id is not None:
        qs = qs.filter(owner_id=user_id)
    # Old installations have no measured size. Count each legacy file at the
    # hard maximum until confirmed/discarded, rather than silently counting zero.
    return qs.aggregate(total=Sum(Case(
        When(original_size_bytes__gt=0, then=F("original_size_bytes")),
        default=Value(settings.MAX_UPLOAD_BYTES), output_field=BigIntegerField(),
    )))["total"] or 0


@transaction.atomic
def acquire_upload(meeting_id, user, body_bytes):
    UploadGate.objects.get_or_create(pk=1)
    UploadGate.objects.select_for_update().get(pk=1)
    now = timezone.now()
    UploadLease.objects.filter(expires_at__lte=now).delete()
    meeting = Meeting.objects.filter(pk=meeting_id, owner_id=user.pk).first()
    if meeting is None or meeting.deletion_requested_at is not None:
        raise NotFound()
    if meeting.original_path or meeting.job_id or meeting.status != MeetingStatus.ENVIADO:
        raise Conflict("Esta reunião já possui um envio ou processamento.")
    leases = UploadLease.objects.all()
    if leases.count() >= settings.MAX_INFLIGHT_UPLOADS:
        raise UploadCapacityExceeded("Já existe um envio em andamento. Aguarde sua conclusão.")
    if leases.filter(meeting_id=meeting_id).exists():
        raise UploadCapacityExceeded()
    reserved = leases.aggregate(total=Sum("reserved_bytes"))["total"] or 0
    user_reserved = leases.filter(user=user).aggregate(total=Sum("reserved_bytes"))["total"] or 0
    if (_staged_bytes() + reserved + body_bytes > settings.STAGED_UPLOAD_MAX_BYTES
            or _staged_bytes(user.pk) + user_reserved + body_bytes
            > settings.STAGED_UPLOAD_MAX_BYTES_PER_USER):
        raise UploadCapacityExceeded(
            "Limite de mídia temporária atingido. Confirme ou descarte envios."
        )
    root = Path(settings.MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.disk_usage(root).free < reserved + body_bytes + settings.MEDIA_MIN_FREE_BYTES:
        raise UploadCapacityExceeded("Espaço privado insuficiente para aceitar outro envio.")
    return UploadLease.objects.create(
        meeting_id=meeting.pk, user=user, reserved_bytes=body_bytes, expires_at=now + LEASE_TTL,
    )


def admit_multipart(request, content_length):
    if not request or not (match := UPLOAD_PATH.fullmatch(request.path)):
        return
    if not request.user.is_authenticated or not request.user.is_active:
        raise NotAuthenticated()
    if content_length is None or content_length <= 0:
        raise UploadLengthRequired()
    if content_length > settings.MAX_UPLOAD_BYTES + 1024 * 1024:
        raise UploadTooLarge()
    if not getattr(request, "upload_capacity_lease_id", None):
        lease = acquire_upload(match[1], request.user, content_length)
        request.upload_capacity_lease_id = lease.pk


class UploadCapacityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            if lease_id := getattr(request, "upload_capacity_lease_id", None):
                try:
                    with transaction.atomic():
                        UploadGate.objects.select_for_update().get(pk=1)
                        UploadLease.objects.filter(pk=lease_id).delete()
                except Exception:
                    # Fail closed: the lease stays charged until its safe TTL.
                    logger.exception("Could not release upload capacity lease")
