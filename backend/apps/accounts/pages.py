"""MVT login and profile pages; credential checks stay server-side."""

from django.contrib.auth import authenticate, login
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_safe

from apps.audit.change_tracking import fingerprint
from apps.audit.models import record_audit
from config.page_support import member_page, render_page

from .initial_access import initial_login_forbidden, unsafe_bootstrap_bind
from .views import _active_member


def login_form(request, *, admin=False):
    if _active_member(request.user) and (not admin or request.user.is_staff):
        return redirect("mvt-admin" if admin else "mvt-meetings")
    requested_next = request.POST.get("next") or request.GET.get("next") or ""
    safe_next = (
        requested_next if requested_next.startswith("/")
        and not requested_next.startswith(("//", "/\\"))
        and url_has_allowed_host_and_scheme(
            requested_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ) else "/"
    )
    error = False
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user = None
        if len(username) <= 150 and username and password and not initial_login_forbidden(username):
            user = authenticate(request, username=username, password=password)
        if (user is not None and _active_member(user) and (not admin or user.is_staff)
                and not (user.membership.must_change_password and unsafe_bootstrap_bind())):
            login(request, user)
            record_audit(user, "login", request=request, subject_user=user,
                         target_type="user", target_ref=user.pk)
            return redirect("mvt-admin" if admin else safe_next)
        record_audit(None, "login", outcome="failed", request=request,
                     details={"username_fingerprint": fingerprint(username.casefold())})
        error = True
    return render_page(
        request, "admin_login" if admin else "login", "Entrar", error=error,
        next_url=safe_next,
    )


@require_http_methods(["GET", "POST"])
def login_page(request):
    return login_form(request)


@require_safe
@member_page
def account_page(request):
    return render_page(request, "account", "Conta")
