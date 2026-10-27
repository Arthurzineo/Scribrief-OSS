"""Administrative account/sector API; never mounted on the public Nginx listener."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import Sector, UserMembership
from apps.meetings.models import Meeting


class AdminUserSerializer(serializers.ModelSerializer):
    sector_id = serializers.PrimaryKeyRelatedField(
        queryset=Sector.objects.filter(is_active=True), source="membership.sector"
    )
    sector_name = serializers.CharField(source="membership.sector.name", read_only=True)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    must_change_password = serializers.BooleanField(
        source="membership.must_change_password", read_only=True,
    )
    monthly_ai_budget_usd = serializers.DecimalField(
        source="membership.monthly_ai_budget_usd", max_digits=12, decimal_places=2,
        allow_null=True, required=False,
    )
    monthly_used_seconds = serializers.SerializerMethodField()
    monthly_upload_count = serializers.SerializerMethodField()

    def get_monthly_used_seconds(self, obj) -> str | None:
        if "monthly_media_usage" not in self.context:
            return None
        item = self.context.get("monthly_media_usage", {}).get(obj.pk)
        return str(item.used_seconds) if item else "0.00"

    def get_monthly_upload_count(self, obj) -> int | None:
        if "monthly_media_usage" not in self.context:
            return None
        item = self.context.get("monthly_media_usage", {}).get(obj.pk)
        return item.upload_count if item else 0

    class Meta:
        model = get_user_model()
        fields = [
            "id", "username", "first_name", "last_name", "email", "is_active",
            "is_staff", "sector_id", "sector_name", "password",
            "must_change_password", "monthly_ai_budget_usd",
            "monthly_used_seconds", "monthly_upload_count",
        ]
        read_only_fields = [
            "id", "is_staff", "sector_name", "must_change_password",
            "monthly_used_seconds", "monthly_upload_count",
        ]
        extra_kwargs = {"username": {"required": True}}

    def validate(self, attrs):
        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "Senha obrigatória."})
        if password:
            try:
                validate_password(password, user=self.instance)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        budget = attrs.get("membership", {}).get("monthly_ai_budget_usd")
        if budget is not None and not 0 < budget <= 1_000_000:
            raise serializers.ValidationError({
                "monthly_ai_budget_usd": "Informe de US$ 0,01 a US$ 1.000.000,00 ou deixe vazio."
            })
        if self.instance is not None:
            if self.instance.is_staff:
                raise PermissionDenied("Contas administrativas não são alteradas por esta API.")
            new_sector = attrs.get("membership", {}).get("sector")
            if new_sector and new_sector.pk != self.instance.membership.sector_id:
                if Meeting.objects.filter(owner=self.instance).exists():
                    raise serializers.ValidationError(
                        {"sector_id": "Transfira as reuniões antes de mudar o setor."}
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        membership_data = validated_data.pop("membership")
        sector = membership_data["sector"]
        password = validated_data.pop("password")
        user = get_user_model()(**validated_data)
        user.set_password(password)
        user.save()
        UserMembership.objects.create(
            user=user, sector=sector, must_change_password=True,
            monthly_ai_budget_usd=membership_data.get("monthly_ai_budget_usd"),
        )
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        membership = validated_data.pop("membership", None)
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        fields = []
        if membership:
            if "sector" in membership:
                instance.membership.sector = membership["sector"]
                fields.append("sector")
            if "monthly_ai_budget_usd" in membership:
                instance.membership.monthly_ai_budget_usd = membership["monthly_ai_budget_usd"]
                fields.append("monthly_ai_budget_usd")
        if password:
            instance.membership.must_change_password = True
            fields.append("must_change_password")
        if fields:
            instance.membership.save(update_fields=fields)
        return instance
