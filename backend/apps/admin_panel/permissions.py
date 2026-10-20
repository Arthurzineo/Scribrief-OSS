from rest_framework.permissions import BasePermission

from apps.accounts.models import UserMembership


class ActiveStaff(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and user.is_active
            and user.is_staff
            and UserMembership.objects.filter(
                user=user,
                sector__is_active=True,
            ).exists()
        )
