"""Read-only administrative audit and estimated OpenAI usage reports."""


from rest_framework import serializers

from apps.audit.models import AIUsageEvent


class AIBudgetSnapshotSerializer(serializers.Serializer):
    period = serializers.CharField()
    sector_id = serializers.IntegerField()
    sector_limit_usd = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    sector_used_usd = serializers.DecimalField(max_digits=18, decimal_places=8)
    sector_remaining_usd = serializers.DecimalField(
        max_digits=18, decimal_places=8, allow_null=True,
    )
    user_id = serializers.IntegerField(required=False)
    user_limit_usd = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, required=False,
    )
    user_used_usd = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    user_remaining_usd = serializers.DecimalField(
        max_digits=18, decimal_places=8, allow_null=True, required=False,
    )


class UsageEventSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="requested_by.username", read_only=True)
    sector_name = serializers.CharField(source="sector.name", read_only=True)
    usage_basis = serializers.SerializerMethodField()

    def get_usage_basis(self, obj) -> str:
        return "measured" if any(
            key in obj.usage for key in ("input_tokens", "output_tokens", "seconds")
        ) else "unavailable"

    class Meta:
        model = AIUsageEvent
        fields = [
            "id", "sector", "sector_name", "requested_by", "username",
            "meeting_id", "job_id", "operation", "provider_id", "model", "key_version",
            "prompt_version", "prompt_fingerprint",
            "request_id", "source_label", "outcome", "error_type", "usage", "usage_basis",
            "estimated_usd",
            "estimate_status", "pricing_version", "created_at",
        ]
