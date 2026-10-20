from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect


class SessionVersionMiddleware:
    """Reject cookies issued before the most recent account deactivation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            from apps.accounts.models import UserMembership

            state = UserMembership.objects.filter(user_id=user.pk).values(
                "session_version", "must_change_password", "bootstrap_local_only",
            ).first()
            session_version = request.session.get("account_session_version", 0)
            if state is None or session_version != state["session_version"]:
                request.session.flush()
                request.user = AnonymousUser()
            else:
                request.initial_password_state = state
        return self.get_response(request)


class InitialPasswordMiddleware:
    """The bootstrap session may only rotate its credential or end the session."""

    ALLOWED = {
        "/admin/login/", "/api/v1/csrf/", "/api/v1/session/",
        "/api/v1/account/password/", "/api/v1/logout/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            state = getattr(request, "initial_password_state", None)
            if state and state["must_change_password"]:
                from apps.accounts.initial_access import unsafe_bootstrap_bind

                if state["bootstrap_local_only"] and unsafe_bootstrap_bind():
                    if request.path.startswith("/api/"):
                        return JsonResponse({"error": {
                            "code": "initial_account_local_only",
                            "message": "Primeiro acesso permitido somente com portas em loopback.",
                        }}, status=403)
                    return HttpResponseForbidden("Primeiro acesso permitido somente em loopback.")
                page = "/admin/" if user.is_staff else "/primeiro-acesso/"
                if request.path not in self.ALLOWED and request.path != page:
                    if request.path.startswith("/api/"):
                        return JsonResponse({"error": {
                            "code": "password_change_required",
                            "message": "Troque a senha temporária antes de continuar.",
                        }}, status=403)
                    return redirect("mvt-admin" if user.is_staff else "mvt-first-access")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Small default CSP for API responses; frontend policy belongs to Nginx."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(("/api/v1/", "/api/admin/", "/api/schema/", "/api/docs/")):
            response["Cache-Control"] = "private, no-store"
        if request.path.startswith("/api/docs/"):
            response["Content-Security-Policy"] = (
                "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
            )
        elif response.get("Content-Type", "").startswith("text/html"):
            response["Content-Security-Policy"] = (
                "default-src 'none'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src https://fonts.gstatic.com; img-src 'self' data: blob:; "
                "media-src 'self' blob:; connect-src 'self'; form-action 'self'; "
                "frame-ancestors 'none'; base-uri 'none'"
            )
        else:
            response["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            )
        return response
