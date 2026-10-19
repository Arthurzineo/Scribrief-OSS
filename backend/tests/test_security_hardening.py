import pytest
from django.contrib.sessions.models import Session
from django.db.models import F
from django.test import Client

from apps.accounts.models import UserMembership


@pytest.mark.django_db
def test_openapi_requires_active_staff(client, user):
    for path in ("/api/schema/", "/api/docs/"):
        assert client.get(path).status_code == 403
        client.force_login(user)
        assert client.get(path).status_code == 403
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        assert client.get(path).status_code == 200
        user.membership.sector.is_active = False
        user.membership.sector.save(update_fields=["is_active"])
        assert client.get(path).status_code == 403
        user.membership.sector.is_active = True
        user.membership.sector.save(update_fields=["is_active"])
        client.logout()
        user.is_staff = False
        user.save(update_fields=["is_staff"])


@pytest.mark.django_db
def test_deactivation_revokes_existing_sessions_even_after_reactivation(user, other_user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    administrator = Client()
    administrator.force_login(user)
    member = Client()
    member.force_login(other_user)
    member_session_key = member.session.session_key
    assert member.get("/api/v1/session/").status_code == 200

    response = administrator.patch(
        f"/api/admin/users/{other_user.pk}/",
        data='{"is_active":false}',
        content_type="application/json",
    )
    assert response.status_code == 200
    assert not Session.objects.filter(session_key=member_session_key).exists()
    assert member.get("/api/v1/session/").status_code == 401

    response = administrator.patch(
        f"/api/admin/users/{other_user.pk}/",
        data='{"is_active":true}',
        content_type="application/json",
    )
    assert response.status_code == 200
    assert member.get("/api/v1/session/").status_code == 401
    assert member.post(
        "/api/v1/login/",
        data='{"username":"bruno","password":"Strong-Test-Password-456"}',
        content_type="application/json",
    ).status_code == 200
    assert member.get("/api/v1/session/").status_code == 200


@pytest.mark.django_db
def test_sensitive_api_responses_are_not_cacheable(client, user):
    client.force_login(user)
    response = client.get("/api/v1/meetings/")
    assert response.status_code == 200
    assert "private" in response.headers["Cache-Control"]
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.django_db
def test_session_epoch_rejects_cookie_that_escaped_physical_purge(user):
    browser = Client()
    browser.force_login(user)
    assert browser.get("/api/v1/session/").status_code == 200
    UserMembership.objects.filter(user=user).update(session_version=F("session_version") + 1)
    assert browser.get("/").status_code == 302
    assert browser.get("/api/v1/session/").status_code == 401
