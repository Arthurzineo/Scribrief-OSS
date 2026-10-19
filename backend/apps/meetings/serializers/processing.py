from rest_framework import serializers

from ..models import MeetingStatus


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    consent_confirmed = serializers.BooleanField(required=False, default=False)


class ConfirmUploadSerializer(serializers.Serializer):
    consent_confirmed = serializers.BooleanField()

    def validate_consent_confirmed(self, value):
        if value is not True:
            raise serializers.ValidationError("Confirme o consentimento dos participantes.")
        return value


class StagedUploadSerializer(serializers.Serializer):
    meeting_id = serializers.UUIDField()
    awaiting_consent = serializers.BooleanField()
    expires_at = serializers.DateTimeField()


class StatusSerializer(serializers.Serializer):
    job_id = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(choices=MeetingStatus.choices)
    error_code = serializers.CharField(allow_blank=True)
    error_message = serializers.CharField(allow_blank=True)
    minutes_stuck = serializers.BooleanField(required=False)


class TranscriptionProgressSerializer(serializers.Serializer):
    stage = serializers.CharField()
    completed_chunks = serializers.IntegerField(allow_null=True)
    total_chunks = serializers.IntegerField(allow_null=True)
    percent = serializers.IntegerField(allow_null=True, min_value=0, max_value=100)
