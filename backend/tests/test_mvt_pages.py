import pytest
from django.test import Client

from apps.meetings.models import Meeting


@pytest.mark.django_db
def test_anonymous_html_routes_require_login_and_do_not_expose_admin(client):
    assert client.get("/login/").status_code == 200
    assert client.get("/").status_code == 302
    assert client.get("/reunioes/nova/").status_code == 302
    assert client.get("/conta/").status_code == 302
    admin_redirect = client.get("/admin/")
    assert admin_redirect.status_code == 302
    assert admin_redirect["Location"] == "/admin/login/"


@pytest.mark.django_db
def test_mvt_list_and_detail_use_server_policy(client, user, other_user):
    own = Meeting.objects.create(owner=user, sector=user.membership.sector, title="Minha reunião")
    hidden = Meeting.objects.create(
        owner=other_user, sector=user.membership.sector, title="Reunião privada"
    )
    client.force_login(user)
    list_page = client.get("/")
    assert list_page.status_code == 200
    assert b"Minha reuni" in list_page.content
    assert b"Reuni\xc3\xa3o privada" not in list_page.content
    assert client.get(f"/reunioes/{own.id}/").status_code == 200
    assert client.get(f"/reunioes/{hidden.id}/").status_code == 404
    hidden.shared_with_sector = True
    hidden.save(update_fields=["shared_with_sector"])
    assert client.get(f"/reunioes/{hidden.id}/ata/").status_code == 200


@pytest.mark.django_db
def test_mvt_html_escapes_title_and_sets_private_cache_and_csp(client, user):
    item = Meeting.objects.create(
        owner=user, sector=user.membership.sector, title="<script>alert(1)</script>"
    )
    client.force_login(user)
    response = client.get(f"/reunioes/{item.id}/")
    assert response.status_code == 200
    assert b"<script>alert(1)</script>" not in response.content
    assert b"&lt;script&gt;" in response.content
    assert response["Cache-Control"] == "private, no-store"
    assert "script-src 'self'" in response["Content-Security-Policy"]
    assert "unsafe-inline" not in response["Content-Security-Policy"].split("style-src")[0]


@pytest.mark.django_db
def test_admin_html_requires_active_staff(client, user):
    client.force_login(user)
    assert client.get("/admin/").status_code == 403
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    response = client.get("/admin/")
    assert response.status_code == 200
    assert b"Administra" in response.content


@pytest.mark.django_db
def test_html_login_supports_csrf_protected_form(client, user):
    csrf_client = Client(enforce_csrf_checks=True)
    page = csrf_client.get("/login/")
    assert page.status_code == 200
    assert b"csrfmiddlewaretoken" in page.content
    assert csrf_client.post("/login/", {"username": "ana", "password": "bad"}).status_code == 403
    token = csrf_client.cookies["csrftoken"].value
    response = csrf_client.post(
        "/login/",
        {"username": "ana", "password": "Strong-Test-Password-123", "csrfmiddlewaretoken": token},
    )
    assert response.status_code == 302
    assert response.url == "/"


@pytest.mark.django_db
def test_html_login_only_redirects_to_local_path(client, user):
    response = client.get("/login/?next=//attacker.example/path")
    assert b'data-next="/"' in response.content
    response = client.post(
        "/login/", {"username": "ana", "password": "Strong-Test-Password-123",
                    "next": "//attacker.example/path"},
    )
    assert response.status_code == 302
    assert response.url == "/"


@pytest.mark.django_db
def test_html_login_returns_to_deep_link(client, user):
    response = client.post(
        "/login/", {"username": "ana", "password": "Strong-Test-Password-123",
                    "next": "/conta/"},
    )
    assert response.status_code == 302
    assert response.url == "/conta/"
