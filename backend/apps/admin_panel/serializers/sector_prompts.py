from rest_framework import serializers


class SectorPromptSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("minutes", "mind_map", "correction"))
    label = serializers.CharField()
    text = serializers.CharField()
    source = serializers.ChoiceField(choices=("default", "custom"))
    version = serializers.IntegerField(min_value=0)
    updated_at = serializers.DateTimeField(allow_null=True)


class SectorPromptListSerializer(serializers.Serializer):
    sector_id = serializers.IntegerField()
    prompts = SectorPromptSerializer(many=True)
    transcription_note = serializers.CharField()


class SectorPromptWriteSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=20, max_length=8000)
    expected_version = serializers.IntegerField(min_value=0)
    current_password = serializers.CharField(write_only=True)


class SectorPromptResetSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=0)
    current_password = serializers.CharField(write_only=True)
