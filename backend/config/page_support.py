"""Shared MVT rendering and membership guard for server-owned pages."""

from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.views import _active_member
from apps.meetings.access import readable_meetings

TEMPLATES = {
    "login": "accounts/login.html",
    "admin_login": "admin_panel/login.html",
    "meetings": "meetings/list.html",
    "new_meeting": "meetings/new.html",
    "meeting": "meetings/detail.html",
    "account": "accounts/profile.html",
    "first_access": "accounts/first_access.html",
    "admin": "admin_panel/dashboard.html",
}


def member_page(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _active_member(request.user):
            return redirect(f"{reverse('mvt-login')}?{urlencode({'next': request.path})}")
        return view(request, *args, **kwargs)

    return wrapped


def render_page(request, page, title, **extra):
    meetings = ()
    if page not in ("login", "admin_login", "admin", "first_access"):
        meetings = readable_meetings(request.user).only(
            "id", "title", "status", "meeting_date", "owner_id", "sector_id", "shared_with_sector"
        ).order_by("-created_at")[:100]
    response = render(request, TEMPLATES[page], {
        "page": page, "title": title, "meetings": meetings, **extra,
    })
    response["Cache-Control"] = "private, no-store"
    return response
