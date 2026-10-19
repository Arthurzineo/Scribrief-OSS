from rest_framework import serializers

from ..models import Segment


class SegmentSerializer(serializers.ModelSerializer):
    falante_id = serializers.CharField(source="speaker.code", read_only=True)
    inicio = serializers.SerializerMethodField()
    fim = serializers.SerializerMethodField()

    class Meta:
        model = Segment
        fields = ["id", "falante_id", "inicio", "fim", "text", "order"]

    def get_inicio(self, obj):
        return obj.start_ms / 1000

    def get_fim(self, obj):
        return obj.end_ms / 1000


class SegmentEditSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    texto = serializers.CharField(allow_blank=False, max_length=10000, trim_whitespace=True)
    inicio = serializers.FloatField(min_value=0)
    fim = serializers.FloatField(min_value=0)

    def validate(self, attrs):
        if attrs["fim"] <= attrs["inicio"]:
            raise serializers.ValidationError("fim deve ser maior que inicio")
        return attrs


class TranscriptionEditSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)
    segmentos = SegmentEditSerializer(many=True)


class CorrectionRequestSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)


class CorrectionSuggestionSerializer(serializers.Serializer):
    segmento_id = serializers.IntegerField(min_value=1)
    texto_original = serializers.CharField()
    texto_sugerido = serializers.CharField()
    motivo = serializers.CharField()


class CorrectionResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    meeting_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=0)
    status = serializers.CharField(help_text="processing, ready ou error.")
    sugestoes = CorrectionSuggestionSerializer(many=True)
    message = serializers.CharField(required=False)
