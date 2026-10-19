from rest_framework import serializers

from ..models import Minutes


class MinutesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Minutes
        fields = [
            "resumo_executivo",
            "topicos",
            "decisoes",
            "tarefas",
            "participantes",
            "human_edited",
            "reviewer_name",
            "reviewed_at",
            "updated_at",
        ]
        read_only_fields = ["human_edited", "reviewer_name", "reviewed_at", "updated_at"]

    def validate_participantes(self, value):
        if not isinstance(value, list) or len(value) > 100 or not all(
            isinstance(name, str) and 1 <= len(name.strip()) <= 150 for name in value
        ):
            raise serializers.ValidationError("participantes deve ser lista de até 100 nomes")
        return [name.strip() for name in value]

    def validate_topicos(self, value):
        if not isinstance(value, list) or not 1 <= len(value) <= 50:
            raise serializers.ValidationError("topicos deve ter entre 1 e 50 itens")
        for topic in value:
            if (
                not isinstance(topic, dict)
                or set(topic) != {"titulo", "comentario"}
                or not isinstance(topic["titulo"], str)
                or not isinstance(topic["comentario"], str)
                or not 1 <= len(topic["titulo"].strip()) <= 160
                or not 1 <= len(topic["comentario"].strip()) <= 4000
            ):
                raise serializers.ValidationError("tópico inválido")
        return value

    def validate_decisoes(self, value):
        if not isinstance(value, list) or len(value) > 100 or not all(
            isinstance(x, str) and 1 <= len(x.strip()) <= 4000 for x in value
        ):
            raise serializers.ValidationError("decisoes deve ser lista de textos")
        return value

    def validate_tarefas(self, value):
        if not isinstance(value, list) or len(value) > 100:
            raise serializers.ValidationError("tarefas deve ser lista")
        for item in value:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("descricao"), str)
                or not isinstance(item.get("responsavel"), str)
                or (item.get("prazo") is not None and not isinstance(item.get("prazo"), str))
                or not 1 <= len(item["descricao"].strip()) <= 4000
                or len(item["responsavel"]) > 150
                or (item["prazo"] is not None and len(item["prazo"]) > 100)
            ):
                raise serializers.ValidationError("tarefa inválida")
        return value


class MinutesReviewSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)


class MinutesResponseSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=0)
    resumo_executivo = serializers.CharField()
    topicos = serializers.JSONField()
    decisoes = serializers.ListField(child=serializers.CharField())
    tarefas = serializers.JSONField()
    participantes = serializers.ListField(child=serializers.CharField())
    revisor = serializers.CharField(allow_null=True)
    revisado_em = serializers.DateTimeField(allow_null=True)
