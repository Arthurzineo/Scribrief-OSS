from rest_framework import serializers

from ..models import Speaker


class SpeakerSerializer(serializers.ModelSerializer):
    falante_id = serializers.CharField(source="code", read_only=True)

    class Meta:
        model = Speaker
        fields = ["falante_id", "name", "merged_into"]
        read_only_fields = ["falante_id", "merged_into"]


class SpeakerSuggestionsRequestSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)


class SpeakerSuggestionsDismissSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)
    codes = serializers.ListField(
        child=serializers.RegexField(r"^[A-Z]+$"), min_length=2,
        max_length=128, required=False,
    )


class SpeakerSuggestionsResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField(allow_null=True)
    meeting_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=0)
    status = serializers.CharField(help_text="none, processing, ready, dismissed ou error.")
    uses = serializers.IntegerField(min_value=0, max_value=2)
    remaining = serializers.IntegerField(min_value=0, max_value=2)
    groups = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))
    caution = serializers.BooleanField()
    sample_times = serializers.DictField(
        child=serializers.ListField(child=serializers.FloatField())
    )
    message = serializers.CharField(required=False)
