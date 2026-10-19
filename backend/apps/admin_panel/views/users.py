"""Administrative account/sector API; never mounted on the public Nginx listener."""

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import viewsets

from apps.accounts.services.session_revocation import revoke_user_sessions
from apps.audit.change_tracking import describe_changes
from apps.audit.models import record_audit

from ..permissions import ActiveStaff
from ..serializers.users import AdminUserSerializer


class UserAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [ActiveStaff]
    serializer_class = AdminUserSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = get_user_model().objects.all()

    def perform_create(self, serializer):
        with transaction.atomic():
            user = serializer.save()
            record_audit(
                self.request.user, "user_created", request=self.request,
                sector=user.membership.sector, subject_user=user,
                target_type="user", target_ref=user.pk,
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            was_active = serializer.instance.is_active
            old_sector_id = serializer.instance.membership.sector_id
            before = {
                "username": serializer.instance.username,
                "first_name": serializer.instance.first_name,
                "last_name": serializer.instance.last_name,
                "email": serializer.instance.email,
            }
            password_changed = "password" in serializer.validated_data
            user = serializer.save()
            if was_active and not user.is_active:
                revoke_user_sessions(user.pk)
            record_audit(
                self.request.user, "user_updated", request=self.request,
                sector=user.membership.sector, subject_user=user,
                target_type="user", target_ref=user.pk,
                details={
                    "is_active_before": was_active, "is_active_after": user.is_active,
                    "sector_before": old_sector_id,
                    "sector_after": user.membership.sector_id,
                    "password_changed": password_changed,
                    "profile_changes": describe_changes(before, {
                        "username": user.username, "first_name": user.first_name,
                        "last_name": user.last_name, "email": user.email,
                    }),
                },
            )

    def get_queryset(self):
        return get_user_model().objects.select_related("membership__sector").order_by("username")
