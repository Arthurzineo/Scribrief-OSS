"""Administrative account/sector API; never mounted on the public Nginx listener."""

from rest_framework import serializers

from apps.accounts.models import Sector


class SectorAdminSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Sector
        fields = [
            "id", "name", "slug", "is_active", "max_upload_minutes",
            "max_monthly_minutes_per_user",
            "member_count", "created_at",
        ]
        read_only_fields = ["id", "member_count", "created_at"]

    def validate(self, attrs):
        max_minutes = attrs.get("max_upload_minutes")
        if max_minutes is not None and not 1 <= max_minutes <= 10080:
            raise serializers.ValidationError({
                "max_upload_minutes": "Informe de 1 a 10080 minutos ou deixe sem limite."
            })
        monthly_minutes = attrs.get("max_monthly_minutes_per_user")
        if monthly_minutes is not None and not 1 <= monthly_minutes <= 44640:
            raise serializers.ValidationError({
                "max_monthly_minutes_per_user": (
                    "Informe de 1 a 44640 minutos ou deixe sem limite."
                )
            })
        sector = self.instance
        if sector and attrs.get("is_active") is False:
            if sector.members.filter(user__is_active=True).exists():
                raise serializers.ValidationError(
                    {"is_active": "Desative ou transfira os usuários ativos primeiro."}
                )
        return attrs
