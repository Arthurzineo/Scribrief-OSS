"""Authenticated account/session API; mounted below /api/v1/."""

from django.urls import path

from .views import (
    account_view,
    csrf_view,
    login_view,
    logout_view,
    password_view,
    sector_members_view,
    session_view,
)

urlpatterns = [
    path("csrf/", csrf_view),
    path("login/", login_view),
    path("logout/", logout_view),
    path("session/", session_view),
    path("sector-members/", sector_members_view),
    path("account/", account_view),
    path("account/password/", password_view),
]
