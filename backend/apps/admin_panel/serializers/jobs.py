"""Read-only administrative audit and estimated OpenAI usage reports."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.meetings.models import ProcessingJob


class JobAdminSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="requested_by.username", read_only=True)
    sector_name = serializers.CharField(source="sector.name", read_only=True)
    potentially_stalled = serializers.SerializerMethodField()

    def get_potentially_stalled(self, obj) -> bool:
        return bool(
            obj.status == "running" and obj.heartbeat_at
            and obj.heartbeat_at < timezone.now() - timedelta(minutes=30)
        )

    class Meta:
        model = ProcessingJob
        fields = [
            "id", "meeting_id", "sector", "sector_name", "requested_by",
            "username", "kind", "status", "stage", "completed_units",
            "total_units", "media_duration_seconds", "error_code", "queued_at",
            "started_at", "heartbeat_at", "completed_at", "cancel_requested_at",
            "potentially_stalled",
        ]
