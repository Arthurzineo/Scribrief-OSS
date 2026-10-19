"""MVT entry points for the isolated administrative listener."""

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods, require_safe

from apps.accounts.pages import login_form
from apps.accounts.views import _active_member
from config.page_support import render_page


@require_http_methods(["GET", "POST"])
def admin_login_page(request):
    return login_form(request, admin=True)


@require_safe
def admin_page(request):
    if not _active_member(request.user):
        return redirect("mvt-admin-login")
    if not request.user.is_staff:
        return HttpResponseForbidden("Acesso negado.")
    return render_page(request, "admin", "Administração")
