import json

from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse


def _error(code, message, status):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _user_payload(user):
    return {
        "id": user.pk,
        "username": user.get_username(),
        "name": user.get_full_name() or user.get_username(),
        "email": user.email,
        "is_staff": user.is_staff,
        "must_change_password": user.membership.must_change_password,
    }


def _active_member(user):
    if not user.is_authenticated or not user.is_active:
        return False
    try:
        return (
            user.membership.auth_source == "local"
            and user.membership.sector.is_active
        )
    except ObjectDoesNotExist:
        return False


def _payload(request):
    try:
        value = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None
