import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.audit.models import record_audit

from ..job_state import accept_job, finish_job
from ..models import Meeting, MeetingStatus, Minutes
from ..services import (
    Conflict,
)
from .common import _require_sector_key


class MindMapMixin:
    @action(detail=True, methods=["get", "post"], url_path="mind-map")
    def mind_map(self, request, pk=None):
        meeting = self.get_object()
        if meeting.status != MeetingStatus.ATA_PRONTA:
            raise Conflict("A ata precisa estar pronta para gerar o mapa mental.")
        if not hasattr(meeting, "minutes"):
            raise Conflict("Gere a ata antes do mapa mental.")
        minutes = meeting.minutes
        map_timed_out = (
            minutes.mind_map_status == "generating"
            and minutes.updated_at < timezone.now() - timedelta(minutes=10)
        )
        if request.method == "GET":
            if meeting.minutes_stale or minutes.mind_map_version != meeting.minutes_version:
                state = "stale" if minutes.mind_map else "none"
            else:
                state = "error" if map_timed_out else minutes.mind_map_status
            if state == "ready":
                record_audit(request.user, "mind_map_viewed", meeting.id, request=request)
            return Response({
                "status": state,
                "version": minutes.mind_map_version,
                "mapa": minutes.mind_map if state == "ready" else None,
            })
        if meeting.minutes_stale:
            raise Conflict("A ata está desatualizada. Gere a ata novamente antes do mapa.")
        _require_sector_key(meeting.sector_id, "mind_map")
        with transaction.atomic():
            current = Meeting.objects.select_for_update().get(pk=meeting.pk)
            if current.deletion_requested_at is not None:
                raise NotFound()
            current_minutes = Minutes.objects.select_for_update().get(meeting=current)
            if current.minutes_stale:
                raise Conflict("A ata está desatualizada.")
            if (
                current_minutes.mind_map_status == "generating"
                and current_minutes.mind_map_version == current.minutes_version
                and current_minutes.updated_at >= timezone.now() - timedelta(minutes=10)
            ):
                return Response({"status": "generating"}, status=202)
            current_minutes.mind_map_status = "generating"
            current_minutes.mind_map_version = current.minutes_version
            current_minutes.mind_map_job_id = uuid.uuid4()
            current_minutes.save(
                update_fields=[
                    "mind_map_status", "mind_map_version", "mind_map_job_id", "updated_at"
                ]
            )
            accept_job(current, current_minutes.mind_map_job_id, "mind_map")
        from ..tasks import generate_mind_map

        try:
            generate_mind_map.delay(
                str(meeting.id), current.minutes_version, str(current_minutes.mind_map_job_id)
            )
        except Exception:
            finish_job(current_minutes.mind_map_job_id, "failed", "queue_unavailable")
            Minutes.objects.filter(
                meeting=meeting, mind_map_job_id=current_minutes.mind_map_job_id,
                mind_map_status="generating",
            ).update(mind_map_status="error")
            return Response(
                {"error": {"code": "queue_unavailable", "message": "Fila indisponível."}},
                status=503,
            )
        record_audit(
            request.user, "mind_map_requested", meeting.id, request=request,
            sector=meeting.sector, target_type="meeting", target_ref=meeting.id,
            details={"job_id": str(current_minutes.mind_map_job_id),
                     "minutes_version": current.minutes_version},
        )
        return Response({"status": "generating"}, status=202)
