import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.audit.models import AuditEvent
from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_admin_created_user_must_rotate_password_on_public_lan(api, user, monkeypatch):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    monkeypatch.setenv("PUBLIC_BIND_IP", "192.168.1.10")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    created = api.post("/api/admin/users/", {
        "username": "carla", "password": "Safe-Temporary-Password-789",
        "sector_id": user.membership.sector_id,
    }, format="json")
    assert created.status_code == 201, created.data
    account = get_user_model().objects.get(username="carla")
    assert account.membership.must_change_password
    assert not account.membership.bootstrap_local_only
    browser = Client()
    signed_in = browser.post("/api/v1/login/", json.dumps({
        "username": "carla", "password": "Safe-Temporary-Password-789",
    }), content_type="application/json")
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["must_change_password"]
    html_login = Client().post("/login/", {
        "username": "carla", "password": "Safe-Temporary-Password-789",
    })
    assert html_login.status_code == 302
    assert html_login["Location"] == "/primeiro-acesso/"
    assert browser.get("/api/v1/meetings/").status_code == 403
    assert browser.get("/conta/").status_code == 302
    assert browser.get("/conta/")["Location"] == "/primeiro-acesso/"
    first = browser.get("/primeiro-acesso/")
    assert first.status_code == 200
    assert b"Safe-Temporary-Password-789" not in first.content
    reused = browser.post("/api/v1/account/password/", json.dumps({
        "currentPassword": "Safe-Temporary-Password-789",
        "newPassword": "Safe-Temporary-Password-789",
    }), content_type="application/json")
    assert reused.status_code == 400
    assert browser.get("/api/v1/meetings/").status_code == 403
    changed = browser.post("/api/v1/account/password/", json.dumps({
        "currentPassword": "Safe-Temporary-Password-789",
        "newPassword": "A-New-Private-Password-456",
    }), content_type="application/json")
    assert changed.status_code == 200
    account.membership.refresh_from_db()
    assert not account.membership.must_change_password
    assert browser.get("/api/v1/meetings/").status_code == 200


@pytest.mark.django_db
def test_admin_reset_revokes_sessions_and_requires_rotation(api, user, other_user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    meeting = Meeting.objects.create(
        owner=other_user, sector=other_user.membership.sector, title="Privada antes do reset",
    )
    browser = Client()
    assert browser.post("/api/v1/login/", json.dumps({
        "username": "bruno", "password": "Strong-Test-Password-456",
    }), content_type="application/json").status_code == 200
    assert browser.get(f"/api/v1/meetings/{meeting.id}/").status_code == 200
    session_before = browser.cookies["sessionid"].value
    reset = api.patch(f"/api/admin/users/{other_user.pk}/", {
        "password": "Safe-Reset-Password-789",
    }, format="json")
    assert reset.status_code == 200, reset.data
    other_user.membership.refresh_from_db()
    assert other_user.membership.must_change_password
    assert not other_user.membership.bootstrap_local_only
    assert browser.get("/api/v1/session/").status_code == 401
    assert browser.cookies["sessionid"].value != session_before
    assert browser.post("/api/v1/login/", json.dumps({
        "username": "bruno", "password": "Strong-Test-Password-456",
    }), content_type="application/json").status_code == 401
    signed_in = browser.post("/api/v1/login/", json.dumps({
        "username": "bruno", "password": "Safe-Reset-Password-789",
    }), content_type="application/json")
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["must_change_password"]
    assert browser.get(f"/api/v1/meetings/{meeting.id}/").status_code == 403
    first = browser.get("/primeiro-acesso/")
    assert first.status_code == 200
    assert b"Privada antes do reset" not in first.content
    event = AuditEvent.objects.filter(action="user_updated", subject_user=other_user).latest("id")
    assert event.details["password_changed"] is True
    assert "Safe-Reset-Password-789" not in str(event.details)


@pytest.mark.django_db
def test_admin_profile_edit_without_password_preserves_session_and_rotation_flag(
    api, user, other_user,
):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    browser = Client()
    assert browser.post("/api/v1/login/", json.dumps({
        "username": "bruno", "password": "Strong-Test-Password-456",
    }), content_type="application/json").status_code == 200
    session_before = browser.cookies["sessionid"].value
    changed = api.patch(f"/api/admin/users/{other_user.pk}/", {
        "first_name": "Bruno Novo",
    }, format="json")
    assert changed.status_code == 200
    other_user.membership.refresh_from_db()
    assert not other_user.membership.must_change_password
    assert browser.get("/api/v1/session/").status_code == 200
    assert browser.cookies["sessionid"].value == session_before


@pytest.mark.django_db
def test_public_first_access_password_change_requires_csrf(api, user):
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    created = api.post("/api/admin/users/", {
        "username": "diana", "password": "Safe-Temporary-Password-789",
        "sector_id": user.membership.sector_id,
    }, format="json")
    assert created.status_code == 201
    browser = Client(enforce_csrf_checks=True)
    assert browser.get("/login/").status_code == 200
    token = browser.cookies["csrftoken"].value
    signed_in = browser.post("/login/", {
        "username": "diana", "password": "Safe-Temporary-Password-789",
        "csrfmiddlewaretoken": token,
    })
    assert signed_in.status_code == 302 and signed_in.url == "/primeiro-acesso/"
    payload = json.dumps({
        "currentPassword": "Safe-Temporary-Password-789",
        "newPassword": "A-New-Private-Password-456",
    })
    assert browser.post(
        "/api/v1/account/password/", payload, content_type="application/json",
    ).status_code == 403
    assert browser.post(
        "/api/v1/account/password/", payload, content_type="application/json",
        HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value,
    ).status_code == 200
    assert browser.get("/api/v1/meetings/").status_code == 200
