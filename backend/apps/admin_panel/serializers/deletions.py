from rest_framework import serializers

from apps.meetings.models import Meeting


class PendingDeletionSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    sector_name = serializers.CharField(source="sector.name", read_only=True)
    deletion_due_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Meeting
        fields = [
            "id", "title", "owner_name", "sector_name", "status",
            "deletion_requested_at", "deletion_due_at", "purge_attempts",
            "purge_error_code",
        ]
        read_only_fields = fields


class RestoreDeletionSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
