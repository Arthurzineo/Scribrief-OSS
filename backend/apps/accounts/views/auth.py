import json

from django.contrib.auth import (
    authenticate,
    login,
    logout,
)
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.initial_access import initial_login_forbidden, unsafe_bootstrap_bind
from apps.audit.change_tracking import fingerprint
from apps.audit.models import record_audit

from .common import _active_member, _error, _user_payload


@ensure_csrf_cookie
@require_GET
def csrf_view(request):
    return JsonResponse({"csrf": "ok"})


@csrf_protect
@require_POST
def login_view(request):
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return _error("invalid_json", "JSON inválido.", 400)
    if not isinstance(payload, dict):
        return _error("invalid_data", "Credenciais inválidas.", 400)
    username, password = payload.get("username"), payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 150:
        return _error("invalid_data", "Credenciais inválidas.", 400)
    if initial_login_forbidden(username):
        record_audit(None, "login", outcome="failed", request=request,
                     details={"username_fingerprint": fingerprint(username.casefold())})
        return _error("invalid_credentials", "Credenciais inválidas.", 401)
    user = authenticate(request, username=username, password=password)
    if user is None:
        record_audit(None, "login", outcome="failed", request=request,
                     details={"username_fingerprint": fingerprint(username.casefold())})
        return _error("invalid_credentials", "Credenciais inválidas.", 401)
    if not _active_member(user) or (
        user.membership.must_change_password and unsafe_bootstrap_bind()
    ):
        record_audit(None, "login", outcome="failed", request=request,
                     details={"username_fingerprint": fingerprint(username.casefold())})
        return _error("invalid_credentials", "Credenciais inválidas.", 401)
    login(request, user)
    record_audit(user, "login", request=request, subject_user=user,
                 target_type="user", target_ref=user.pk)
    return JsonResponse({"user": _user_payload(user)})


@csrf_protect
@require_POST
def logout_view(request):
    if not request.user.is_authenticated:
        return _error("not_authenticated", "Autenticação necessária.", 401)
    record_audit(request.user, "logout", request=request, subject_user=request.user,
                 target_type="user", target_ref=request.user.pk)
    logout(request)
    return JsonResponse({"ok": True})


@require_GET
def session_view(request):
    if not _active_member(request.user):
        return _error("not_authenticated", "Autenticação necessária.", 401)
    return JsonResponse({"user": _user_payload(request.user)})
