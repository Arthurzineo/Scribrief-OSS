
from django.contrib.auth import (
    get_user_model,
    update_session_auth_hash,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.audit.change_tracking import describe_changes
from apps.audit.models import record_audit

from ..models import UserMembership
from .common import _active_member, _error, _payload, _user_payload


@require_GET
def sector_members_view(request):
    if not _active_member(request.user):
        return _error("not_authenticated", "Autenticação necessária.", 401)
    memberships = UserMembership.objects.filter(
        sector_id=request.user.membership.sector_id,
        sector__is_active=True,
        user__is_active=True,
    ).select_related("user").order_by("user__username")
    return JsonResponse({"members": [
        {"id": item.user_id, "username": item.user.username,
         "name": item.user.get_full_name() or item.user.username}
        for item in memberships
    ]})


@csrf_protect
@require_http_methods(["GET", "PATCH"])
def account_view(request):
    if not _active_member(request.user):
        return _error("not_authenticated", "Autenticação necessária.", 401)
    if request.method == "GET":
        return JsonResponse({"user": _user_payload(request.user)})
    payload = _payload(request)
    if payload is None or set(payload) - {"name", "email"}:
        return _error("invalid_data", "Dados inválidos.", 400)
    name = payload.get("name")
    email = payload.get("email")
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 150):
        return _error("invalid_name", "Nome inválido.", 400)
    if email is not None:
        if not isinstance(email, str) or len(email) > 254:
            return _error("invalid_email", "E-mail inválido.", 400)
        if email.strip():
            try:
                validate_email(email.strip())
            except DjangoValidationError:
                return _error("invalid_email", "E-mail inválido.", 400)
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        before = {}
        if name is not None:
            before["name"] = user.get_full_name()
        if email is not None:
            before["email"] = user.email
        if name is not None:
            parts = name.strip().split(" ", 1)
            user.first_name = parts[0][:150]
            user.last_name = parts[1][:150] if len(parts) > 1 else ""
        if email is not None:
            user.email = email.strip()
        user.save(update_fields=["first_name", "last_name", "email"])
        after = {}
        if name is not None:
            after["name"] = user.get_full_name()
        if email is not None:
            after["email"] = user.email
        record_audit(
            user, "account_updated", request=request, subject_user=user,
            target_type="user", target_ref=user.pk,
            details={"changes": describe_changes(before, after)},
        )
    return JsonResponse({"user": _user_payload(user)})


@csrf_protect
@require_POST
def password_view(request):
    if not _active_member(request.user):
        return _error("not_authenticated", "Autenticação necessária.", 401)
    payload = _payload(request)
    if payload is None:
        return _error("invalid_data", "Dados inválidos.", 400)
    current, new = payload.get("currentPassword"), payload.get("newPassword")
    if not isinstance(current, str) or not isinstance(new, str):
        return _error("invalid_data", "Senhas inválidas.", 400)
    if not request.user.check_password(current):
        record_audit(
            request.user, "password_change_failed", outcome="failed", request=request,
            subject_user=request.user, target_type="user", target_ref=request.user.pk,
            details={"reason": "incorrect_current_password"},
        )
        return _error("invalid_credentials", "Senha atual incorreta.", 400)
    if current == new:
        record_audit(
            request.user, "password_change_failed", outcome="failed", request=request,
            subject_user=request.user, target_type="user", target_ref=request.user.pk,
            details={"reason": "reused_current_password"},
        )
        return _error("invalid_password", "A nova senha deve ser diferente da atual.", 400)
    try:
        validate_password(new, user=request.user)
    except DjangoValidationError as exc:
        record_audit(
            request.user, "password_change_failed", outcome="failed", request=request,
            subject_user=request.user, target_type="user", target_ref=request.user.pk,
            details={"reason": "invalid_new_password"},
        )
        return _error("invalid_password", " ".join(exc.messages), 400)
    with transaction.atomic():
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        UserMembership.objects.filter(user_id=request.user.pk).update(
            must_change_password=False, bootstrap_local_only=False,
        )
        record_audit(request.user, "password_changed", request=request,
                     subject_user=request.user, target_type="user", target_ref=request.user.pk)
    update_session_auth_hash(request, request.user)
    return JsonResponse({"ok": True})
