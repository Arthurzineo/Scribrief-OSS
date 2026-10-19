from rest_framework import serializers

from apps.audit.models import SystemEvent


class SystemEventSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = SystemEvent
        fields = [
            "id", "created_at", "component", "event_code", "severity", "outcome",
            "error_code", "stage", "kind", "job_id", "meeting_id", "sector",
            "sector_id_snapshot", "user", "user_id_snapshot", "user_name",
            "request_id", "client_ip", "http_status",
        ]
