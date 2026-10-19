"""Read-only administrative audit and estimated OpenAI usage reports."""


from rest_framework import serializers

from apps.audit.models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id", "actor", "actor_id_snapshot", "actor_name", "subject_user",
            "subject_user_id_snapshot", "sector", "sector_id_snapshot", "action",
            "target_id", "target_type", "target_ref", "outcome", "client_ip",
            "peer_ip", "details", "created_at",
            "request_id",
        ]
