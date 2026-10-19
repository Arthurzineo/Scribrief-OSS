import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from apps.accounts.models import Sector, UserMembership
from apps.audit.models import AuditEvent


@pytest.mark.django_db
def test_fresh_bootstrap_creates_only_admin_and_never_resets_password(monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "127.0.0.1")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    call_command("bootstrap_admin")
    admin = get_user_model().objects.get(username="ADMIN")
    assert get_user_model().objects.count() == 1
    assert not get_user_model().objects.filter(username="demo").exists()
    assert admin.is_staff and admin.is_superuser and admin.check_password("ADMIN123")
    assert admin.password != "ADMIN123"
    assert admin.password.startswith("argon2$")
    assert admin.membership.must_change_password
    assert admin.membership.sector.slug == "administracao"
    call_command("bootstrap_admin")
    admin.refresh_from_db()
    assert admin.check_password("ADMIN123")
    assert Sector.objects.filter(slug="administracao").count() == 1


@pytest.mark.django_db
def test_bootstrap_refuses_default_account_on_lan(monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "192.168.1.10")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    with pytest.raises(CommandError, match="loopback"):
        call_command("bootstrap_admin")
    assert not get_user_model().objects.exists()


@pytest.mark.django_db
def test_upgrade_does_not_create_or_reset_default_account(user, monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "192.168.1.10")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    call_command("bootstrap_admin")
    assert not get_user_model().objects.filter(username="ADMIN").exists()


@pytest.mark.django_db
def test_initial_admin_must_change_password_before_any_privileged_action(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "127.0.0.1")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    call_command("bootstrap_admin")
    login = client.post("/api/v1/login/", json.dumps({
        "username": "ADMIN", "password": "ADMIN123",
    }), content_type="application/json")
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True
    assert client.get("/api/v1/session/").status_code == 200
    assert client.get("/admin/").status_code == 200
    for path in ("/api/admin/sectors/", "/api/schema/", "/api/v1/account/", "/"):
        response = client.get(path)
        assert response.status_code in (302, 403), path
        if response.status_code == 302:
            assert response["Location"] == "/admin/"
    assert client.post(
        "/api/admin/sectors/", data="{}", content_type="application/json",
    ).status_code == 403
    assert AuditEvent.objects.filter(
        action="api_mutation", outcome="failed", target_ref="/api/admin/sectors/",
    ).exists()
    assert client.post("/api/v1/account/password/", json.dumps({
        "currentPassword": "wrong", "newPassword": "Different-Strong-Password-456",
    }), content_type="application/json").status_code == 400
    assert client.get("/api/admin/sectors/").status_code == 403
    invalid = client.post("/api/v1/account/password/", json.dumps({
        "currentPassword": "ADMIN123", "newPassword": "ADMIN123",
    }), content_type="application/json")
    assert invalid.status_code == 400
    assert client.get("/api/admin/sectors/").status_code == 403
    changed = client.post("/api/v1/account/password/", json.dumps({
        "currentPassword": "ADMIN123", "newPassword": "Different-Strong-Password-456",
    }), content_type="application/json")
    assert changed.status_code == 200
    assert client.get("/api/v1/session/").json()["user"]["must_change_password"] is False
    assert client.get("/api/admin/sectors/").status_code == 200
    admin = get_user_model().objects.get(username="ADMIN")
    assert not admin.membership.must_change_password
    assert not admin.check_password("ADMIN123")
    assert admin.check_password("Different-Strong-Password-456")
    assert client.post("/api/v1/logout/").status_code == 200
    assert client.post("/api/v1/login/", json.dumps({
        "username": "ADMIN", "password": "ADMIN123",
    }), content_type="application/json").status_code == 401
    assert client.post("/api/v1/login/", json.dumps({
        "username": "ADMIN", "password": "Different-Strong-Password-456",
    }), content_type="application/json").status_code == 200


@pytest.mark.django_db
def test_pending_bootstrap_blocks_reexposure_on_lan(monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "127.0.0.1")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    call_command("bootstrap_admin")
    monkeypatch.setenv("PUBLIC_BIND_IP", "192.168.1.10")
    with pytest.raises(CommandError, match="loopback"):
        call_command("bootstrap_admin", skip_create=True)


@pytest.mark.django_db
def test_direct_compose_exposure_cannot_use_known_password(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "127.0.0.1")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    call_command("bootstrap_admin")
    monkeypatch.setenv("PUBLIC_BIND_IP", "192.168.1.10")
    assert client.post("/api/v1/login/", json.dumps({
        "username": "ADMIN", "password": "ADMIN123",
    }), content_type="application/json").status_code == 401
    assert client.post("/admin/login/", {
        "username": "ADMIN", "password": "ADMIN123",
    }).status_code == 200
    admin = get_user_model().objects.get(username="ADMIN")
    client.force_login(admin)
    assert client.get("/api/v1/session/").status_code == 403
    assert client.post("/api/v1/account/password/", json.dumps({
        "currentPassword": "ADMIN123", "newPassword": "Different-Strong-Password-456",
    }), content_type="application/json").status_code == 403
    assert admin.membership.must_change_password
    monkeypatch.setenv("PUBLIC_BIND_IP", "127.0.0.1")
    assert client.post("/api/v1/account/password/", json.dumps({
        "currentPassword": "ADMIN123", "newPassword": "Different-Strong-Password-456",
    }), content_type="application/json").status_code == 200
    monkeypatch.setenv("PUBLIC_BIND_IP", "192.168.1.10")
    assert client.post("/api/v1/logout/").status_code == 200
    assert client.post("/api/v1/login/", json.dumps({
        "username": "ADMIN", "password": "Different-Strong-Password-456",
    }), content_type="application/json").status_code == 200


@pytest.mark.django_db
def test_bootstrap_skip_create_does_not_seed_demo(monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "127.0.0.1")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    call_command("bootstrap_admin", skip_create=True)
    assert UserMembership.objects.count() == 0


@pytest.mark.django_db
def test_initial_admin_html_login_and_password_change_require_csrf(monkeypatch):
    monkeypatch.setenv("PUBLIC_BIND_IP", "127.0.0.1")
    monkeypatch.setenv("ADMIN_BIND_IP", "127.0.0.1")
    call_command("bootstrap_admin")
    browser = Client(enforce_csrf_checks=True)
    assert browser.get("/admin/login/").status_code == 200
    token = browser.cookies["csrftoken"].value
    signed_in = browser.post("/admin/login/", {
        "username": "ADMIN", "password": "ADMIN123", "csrfmiddlewaretoken": token,
    })
    assert signed_in.status_code == 302 and signed_in.url == "/admin/"
    assert browser.get("/admin/").status_code == 200
    payload = json.dumps({
        "currentPassword": "ADMIN123", "newPassword": "Different-Strong-Password-456",
    })
    assert browser.post(
        "/api/v1/account/password/", payload, content_type="application/json",
    ).status_code == 403
    assert browser.post(
        "/api/v1/account/password/", payload, content_type="application/json",
        HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value,
    ).status_code == 200
