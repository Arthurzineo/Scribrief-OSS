from django.db import models
from rest_framework import serializers

from ..models import Meeting
from ..services import minutes_generation_stuck


class MeetingSerializer(serializers.ModelSerializer):
    speaker_count = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()
    audio_available = serializers.SerializerMethodField()
    minutes_stuck = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source="owner.username", read_only=True)

    def get_can_edit(self, obj) -> bool:
        return obj.owner_id == self.context["request"].user.pk

    def get_minutes_stuck(self, obj) -> bool:
        return minutes_generation_stuck(obj)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Informe um nome para a reunião.")
        return value

    def get_speaker_count(self, obj) -> int:
        value = getattr(obj, "speaker_count", None)
        return value if value is not None else obj.speakers.filter(merged_into__isnull=True).count()

    def get_duration_seconds(self, obj) -> float:
        value = getattr(obj, "duration_ms", None)
        if value is None:
            value = obj.segments.aggregate(models.Max("end_ms"))["end_ms__max"]
        return (value or 0) / 1000

    def get_audio_available(self, obj) -> bool:
        return bool(obj.audio_path)

    class Meta:
        model = Meeting
        fields = [
            "id",
            "title",
            "owner_name",
            "owner_id",
            "can_edit",
            "shared_with_sector",
            "access_version",
            "meeting_date",
            "status",
            "job_id",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
            "speaker_count",
            "duration_seconds",
            "audio_available",
            "transcription_version",
            "minutes_version",
            "minutes_stale",
            "minutes_stuck",
        ]
        read_only_fields = [
            "id",
            "owner_name",
            "owner_id",
            "can_edit",
            "shared_with_sector",
            "access_version",
            "status",
            "job_id",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
            "speaker_count",
            "duration_seconds",
            "audio_available",
            "transcription_version",
            "minutes_version",
            "minutes_stale",
            "minutes_stuck",
        ]


class SharingSerializer(serializers.Serializer):
    shared_with_sector = serializers.BooleanField()
    access_version = serializers.IntegerField(min_value=0)


class TransferSerializer(serializers.Serializer):
    target_user_id = serializers.IntegerField(min_value=1)
    access_version = serializers.IntegerField(min_value=0)
