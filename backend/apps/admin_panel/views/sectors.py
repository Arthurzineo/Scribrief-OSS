"""Administrative account/sector API; never mounted on the public Nginx listener."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.response import Response

from apps.accounts.models import Sector, SectorAICredential
from apps.accounts.secrets import save_sector_credential
from apps.audit.change_tracking import describe_changes
from apps.audit.models import record_audit
from apps.meetings.models import MonthlyMediaUsage
from apps.meetings.processing.ai_registry import AI_ADAPTERS
from apps.meetings.services.media_quota import current_period

from ..permissions import ActiveStaff
from ..serializers.sectors import SectorAdminSerializer
from ..serializers.users import AdminUserSerializer


class SectorAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [ActiveStaff]
    serializer_class = SectorAdminSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = Sector.objects.all()

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    def perform_create(self, serializer):
        with transaction.atomic():
            sector = serializer.save()
            record_audit(
                self.request.user, "sector_created", request=self.request,
                sector=sector, target_type="sector", target_ref=sector.pk,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = {
                "name": serializer.instance.name,
                "slug": serializer.instance.slug,
                "is_active": serializer.instance.is_active,
                "max_upload_minutes": serializer.instance.max_upload_minutes,
                "max_monthly_minutes_per_user": (
                    serializer.instance.max_monthly_minutes_per_user
                ),
            }
            sector = serializer.save()
            record_audit(
                self.request.user, "sector_updated", request=self.request,
                sector=sector, target_type="sector", target_ref=sector.pk,
                details={"changes": describe_changes(before, {
                    "name": sector.name, "slug": sector.slug,
                    "is_active": sector.is_active,
                    "max_upload_minutes": sector.max_upload_minutes,
                    "max_monthly_minutes_per_user": sector.max_monthly_minutes_per_user,
                })},
            )

    def get_queryset(self):
        return Sector.objects.annotate(
            member_count=Count("members", distinct=True)
        ).order_by("name")

    @action(detail=False, methods=["get"])
    def choices(self, request):
        return Response(
            list(Sector.objects.filter(is_active=True).order_by("name").values("id", "name"))
        )

    @action(detail=True, methods=["get", "post", "delete"], url_path="openai-key")
    def openai_key(self, request, pk=None):
        return self._credential_action(request, "openai")

    @action(
        detail=True, methods=["get", "post", "delete"],
        url_path=r"ai-credentials/(?P<provider_id>[a-z][a-z0-9_-]{1,39})",
    )
    def ai_credential(self, request, pk=None, provider_id=None):
        return self._credential_action(request, provider_id)

    def _credential_action(self, request, provider_id):
        if provider_id not in AI_ADAPTERS:
            raise serializers.ValidationError({"provider_id": "Provedor não registrado."})
        sector = self.get_object()
        credential = SectorAICredential.objects.filter(
            sector=sector, provider_id=provider_id
        ).first()
        if request.method == "GET":
            return Response({
                "configured": credential is not None,
                "version": credential.version if credential else None,
                "updated_at": credential.updated_at if credential else None,
            })
        password = request.data.get("current_password")
        if not isinstance(password, str) or not request.user.check_password(password):
            raise PermissionDenied("Confirme sua senha para alterar a chave setorial.")
        if request.method == "DELETE":
            with transaction.atomic():
                SectorAICredential.objects.filter(sector=sector, provider_id=provider_id).delete()
                record_audit(
                    request.user, "sector_key_revoked", request=request,
                    sector=sector, target_type="sector", target_ref=sector.pk,
                    details={"provider_id": provider_id},
                )
            return Response(status=status.HTTP_204_NO_CONTENT)
        api_key = request.data.get("api_key")
        minimum = 20 if provider_id == "openai" else 8
        if not isinstance(api_key, str) or not minimum <= len(api_key) <= 500:
            raise serializers.ValidationError({"api_key": "Chave inválida."})
        with transaction.atomic():
            saved = save_sector_credential(sector, provider_id, api_key)
            record_audit(
                request.user, "sector_key_rotated", request=request,
                sector=sector, target_type="sector", target_ref=sector.pk,
                details={"provider_id": provider_id, "version": saved.version},
            )
        return Response({"configured": True, "version": saved.version}, status=200)

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        sector = self.get_object()
        users = get_user_model().objects.filter(membership__sector=sector).order_by("username")
        page = self.paginate_queryset(users)
        visible = page if page is not None else list(users)
        usage = {
            item.user_id_snapshot: item for item in MonthlyMediaUsage.objects.filter(
                sector=sector, period=current_period(),
                user_id_snapshot__in=[user.pk for user in visible],
            )
        }
        data = AdminUserSerializer(
            visible, many=True, context={"monthly_media_usage": usage}
        ).data
        if page is not None:
            response = self.get_paginated_response(data)
            response.data["monthly_period"] = current_period().strftime("%Y-%m")
            return response
        return Response({"results": data, "monthly_period": current_period().strftime("%Y-%m")})
