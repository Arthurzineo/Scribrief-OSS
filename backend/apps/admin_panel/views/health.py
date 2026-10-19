"""Admin-only operational summary; observations are not an uptime SLA."""

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_panel.permissions import ActiveStaff
from apps.audit.health import collect_live_health
from apps.audit.models import AIUsageEvent, HealthSample, SystemEvent
from apps.meetings.models import ProcessingJob


class AdminHealthView(APIView):
    permission_classes = [ActiveStaff]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        now = timezone.now()
        since = now - timedelta(hours=24)
        current = collect_live_health()
        raw_samples = HealthSample.objects.filter(created_at__gte=since).values(
            "created_at", "services"
        )[:600]
        slots = {}
        for row in raw_samples:
            slot = int(row["created_at"].timestamp()) // 300
            slots.setdefault(slot, row)
        samples = list(slots.values())
        latest = HealthSample.objects.first()
        stale = latest is None or latest.created_at < now - timedelta(minutes=15)
        current["services"]["sampling"] = "down" if stale else "ok"
        availability = {}
        for component in ("backend", "database", "redis", "frontend", "worker", "storage"):
            up = sum(row["services"].get(component) == "ok" for row in samples)
            down = sum(row["services"].get(component) == "down" for row in samples)
            availability[component] = {
                "online_minutes_observed": up * 5,
                "minutes_observed": (up + down) * 5,
                "sample_count": up + down,
                "expected_sample_count": 288,
            }
        errors = SystemEvent.objects.filter(created_at__gte=since, severity="error")
        jobs = ProcessingJob.objects.filter(queued_at__gte=since)
        usage = AIUsageEvent.objects.filter(created_at__gte=since)
        by_component = list(errors.values("component").annotate(count=Count("id"))
                            .order_by("-count", "component")[:20])
        return Response({
            "checked_at": current["checked_at"],
            "services": current["services"],
            "disk": current["disk"],
            "latest_sample_at": latest.created_at if latest else None,
            "availability_24h": availability,
            "errors_24h": {
                "system_events": errors.count(),
                "by_component": by_component,
                "failed_jobs": jobs.filter(status="failed").count(),
                "failed_openai_attempts": usage.filter(outcome="failed").count(),
            },
            "jobs_24h": {
                "submitted": jobs.count(),
                "queued": ProcessingJob.objects.filter(status="queued").count(),
                "running": ProcessingJob.objects.filter(status="running").count(),
            },
        })
