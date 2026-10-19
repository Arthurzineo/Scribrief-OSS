"""Read-only administrative audit and estimated OpenAI usage reports."""


from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.admin_panel.permissions import ActiveStaff
from apps.audit.models import record_audit
from apps.meetings.job_state import cancel_job
from apps.meetings.models import ProcessingJob
from config.celery import app as celery_app

from ..filters import _positive_int
from ..serializers.jobs import JobAdminSerializer


class JobAdminViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ActiveStaff]
    serializer_class = JobAdminSerializer
    queryset = ProcessingJob.objects.all()

    def get_queryset(self):
        qs = ProcessingJob.objects.select_related("sector", "requested_by")
        params = self.request.query_params
        if params.get("sector_id"):
            qs = qs.filter(sector_id=_positive_int(params["sector_id"], "sector_id"))
        if params.get("user_id"):
            qs = qs.filter(requested_by_id=_positive_int(params["user_id"], "user_id"))
        if params.get("status"):
            qs = qs.filter(status=params["status"][:20])
        return qs.order_by("-queued_at")

    @action(detail=False, methods=["get"], url_path="worker-health")
    def worker_health(self, request):
        try:
            replies = celery_app.control.inspect(timeout=1.5).ping() or {}
            return Response({
                "status": "responding" if replies else "no_response",
                "responding_workers": len(replies),
                "checked_at": timezone.now(),
            })
        except Exception:
            return Response({
                "status": "unavailable", "responding_workers": None,
                "checked_at": timezone.now(),
            })

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.get_queryset()
        totals = qs.aggregate(
            requests=Count("id"), queued=Count("id", filter=Q(status="queued")),
            running=Count("id", filter=Q(status="running")),
            failed=Count("id", filter=Q(status="failed")),
            cancelled=Count("id", filter=Q(status="cancelled")),
            uploaded_media_seconds=Sum(
                "media_duration_seconds", filter=Q(kind="transcription")
            ),
        )
        by_user = list(qs.values("requested_by_id", "requested_by__username").annotate(
            requests=Count("id"), uploaded_media_seconds=Sum(
                "media_duration_seconds", filter=Q(kind="transcription")
            ),
        ).order_by("requested_by__username")[:1000])
        by_sector = list(qs.values("sector_id", "sector__name").annotate(
            requests=Count("id"), uploaded_media_seconds=Sum(
                "media_duration_seconds", filter=Q(kind="transcription")
            ),
        ).order_by("sector__name")[:1000])
        return Response({"totals": totals, "by_user": by_user, "by_sector": by_sector})

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        password = request.data.get("current_password")
        if not isinstance(password, str) or not request.user.check_password(password):
            raise PermissionDenied("Confirme sua senha para cancelar a execução.")
        with transaction.atomic():
            result = cancel_job(job.pk)
            if result is None:
                raise NotFound()
            record_audit(
                request.user, "job_cancel_requested", request=request,
                sector=result.sector, subject_user=result.requested_by,
                target_type="job", target_ref=result.id,
                details={"kind": result.kind, "status": result.status},
            )
        result.refresh_from_db()
        return Response(JobAdminSerializer(result).data)
